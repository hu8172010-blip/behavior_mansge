"""Command line entry points for later download/prepare/train/evaluate workflows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile

import torch
from torch.utils.data import DataLoader

from anomaly_training.config import DATA_ROOT, MAX_DATA_BYTES
from anomaly_training.dataset import VideoClipDataset, seeded_worker_init_fn
from anomaly_training.downloads import ensure_pretrained_weights
from anomaly_training.metrics import write_confusion_matrix
from anomaly_training.model import load_checkpoint
from anomaly_training.orchestration import (
    audit_splits,
    canonical_training_provenance,
    checkpoint_promotion_eligibility,
    consume_protected_test,
    download_datasets,
    managed_root_for_path,
    prepare_manifests,
    promotion_eligibility,
    smoke_promotion_eligibility,
    verify_sources,
)
from anomaly_training.storage import (
    ManagedArtifactLedger,
    atomic_copy,
    atomic_json_write,
    digest,
    inside,
)
from anomaly_training.trainer import TrainConfig, evaluate, train


def _artifact_ledger(*extra_roots: Path) -> ManagedArtifactLedger:
    return ManagedArtifactLedger(
        [
            DATA_ROOT,
            Path("training_runs"),
            Path("models"),
            Path("runs"),
            *extra_roots,
        ],
        limit_bytes=MAX_DATA_BYTES,
        state_path=DATA_ROOT / ".managed-artifact-ledger.json",
    )


def _write_ledger_snapshot(ledger: ManagedArtifactLedger) -> None:
    atomic_json_write(
        DATA_ROOT / "managed-artifacts.json",
        ledger.snapshot(),
        managed_root=DATA_ROOT,
        limit_bytes=MAX_DATA_BYTES,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m anomaly_training")
    commands = parser.add_subparsers(dest="command", required=True)
    download_parser = commands.add_parser("download", help="download bounded, traceable first-round datasets")
    download_parser.add_argument("--datasets", nargs="+", required=True, choices=("rlvs", "urfall", "avenue"))
    download_parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    verify_parser = commands.add_parser("verify-sources", help="verify source receipts, sizes, and checksums")
    verify_parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    prepare_parser = commands.add_parser("prepare", help="validate videos and write deterministic manifests")
    prepare_parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    prepare_parser.add_argument("--output-dir", type=Path)
    prepare_parser.add_argument("--per-class", type=int, default=30)
    prepare_parser.add_argument("--seed", type=int, default=42)
    audit_parser = commands.add_parser("audit-splits", help="prove class coverage and split disjointness")
    audit_parser.add_argument("--manifest-dir", type=Path, default=DATA_ROOT / "manifests")
    audit_parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    train_parser = commands.add_parser("train", help="train a three-class R3D-18 model from manifests")
    train_parser.add_argument("--run-dir", type=Path, required=True)
    train_parser.add_argument("--train-manifest", type=Path, default=DATA_ROOT / "manifests" / "train.csv")
    train_parser.add_argument("--val-manifest", type=Path, default=DATA_ROOT / "manifests" / "val.csv")
    train_parser.add_argument("--epochs", type=int, default=20)
    train_parser.add_argument("--head-epochs", type=int, default=5)
    train_parser.add_argument("--batch-size", type=int, default=2)
    train_parser.add_argument("--accumulate-steps", type=int, default=1)
    train_parser.add_argument("--patience", type=int, default=5)
    train_parser.add_argument("--learning-rate", type=float, default=1e-4)
    train_parser.add_argument("--seed", type=int, default=42)
    train_parser.add_argument("--max-train-batches", type=int)
    train_parser.add_argument("--max-val-batches", type=int)
    train_parser.add_argument("--device")
    train_parser.add_argument("--no-pretrained", action="store_true", help="start R3D-18 without Kinetics-400 weights")
    train_parser.add_argument("--no-resume", action="store_true")
    evaluate_parser = commands.add_parser("evaluate", help="evaluate an R3D-18 checkpoint against a manifest")
    evaluate_parser.add_argument("--checkpoint", type=Path, required=True)
    evaluate_parser.add_argument("--manifest", type=Path)
    evaluate_parser.add_argument("--split", choices=("train", "val", "test"), default="test")
    evaluate_parser.add_argument("--device")
    evaluate_parser.add_argument("--batch-size", type=int, default=2)
    evaluate_parser.add_argument("--accepted-model", type=Path, default=Path("models") / "best.pth")
    evaluate_parser.add_argument("--smoke-evidence", type=Path)
    return parser


def _write_evaluation_artifacts(
    checkpoint: Path,
    payload: dict[str, object],
    report,
    artifact_ledger: ManagedArtifactLedger | None = None,
) -> tuple[Path, Path]:
    run_dir = checkpoint.parent
    try:
        inside(DATA_ROOT, run_dir)
        managed_root: Path | None = DATA_ROOT
    except ValueError:
        managed_root = None
    training_path = run_dir / "training_metrics.json"
    legacy_path = run_dir / "metrics.json"
    if not training_path.exists() and legacy_path.exists():
        try:
            legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            legacy = None
        if isinstance(legacy, dict) and isinstance(legacy.get("epochs"), list):
            atomic_json_write(training_path, legacy, managed_root=managed_root)
    evaluation_path = run_dir / "evaluation_metrics.json"
    atomic_json_write(
        evaluation_path,
        payload,
        managed_root=managed_root,
        artifact_ledger=artifact_ledger,
    )
    matrix_path = run_dir / "evaluation_confusion_matrix.png"
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
        temporary_matrix = Path(handle.name)
    try:
        write_confusion_matrix(report, temporary_matrix)
        atomic_copy(
            temporary_matrix,
            matrix_path,
            managed_root=managed_root,
            artifact_ledger=artifact_ledger,
        )
    finally:
        temporary_matrix.unlink(missing_ok=True)
    index = {
        "artifact_type": "metrics_index",
        "training_metrics": training_path.name if training_path.exists() else None,
        "loss_curve": (
            "loss_curve.json"
            if (run_dir / "loss_curve.json").exists()
            else None
        ),
        "evaluation_metrics": evaluation_path.name,
        "evaluation_confusion_matrix": matrix_path.name,
    }
    atomic_json_write(
        legacy_path,
        index,
        managed_root=managed_root,
        artifact_ledger=artifact_ledger,
    )
    return evaluation_path, matrix_path


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "download":
        result = download_datasets(args.datasets, args.data_root)
        print(json.dumps(result, indent=2, sort_keys=True))
        required = list(args.datasets)
        if "avenue" in required:
            required.append("avenue_ground_truth")
        return 0 if all(
            result["sources"].get(key, {}).get("status") == "acquired"
            for key in required
        ) else 1
    if args.command == "verify-sources":
        result = verify_sources(args.data_root)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["ok"] else 1
    if args.command == "prepare":
        result = prepare_manifests(
            args.data_root,
            output_dir=args.output_dir,
            per_class=args.per_class,
            seed=args.seed,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.command == "audit-splits":
        managed_root = managed_root_for_path(args.manifest_dir, args.data_root)
        result = audit_splits(args.manifest_dir, managed_root=managed_root)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.command == "train":
        if not args.no_pretrained:
            DATA_ROOT.mkdir(parents=True, exist_ok=True)
            ensure_pretrained_weights(DATA_ROOT)
            torch.hub.set_dir(str(DATA_ROOT / ".torch" / "hub"))
        train_data = VideoClipDataset(
            args.train_manifest,
            split="train",
            seed=args.seed,
        )
        val_data = VideoClipDataset(
            args.val_manifest,
            split="val",
            seed=args.seed,
        )
        provenance = canonical_training_provenance(
            args.train_manifest,
            args.val_manifest,
            DATA_ROOT,
        )
        ledger = _artifact_ledger(args.run_dir)
        result = train(TrainConfig(run_dir=args.run_dir, epochs=args.epochs, head_epochs=min(args.head_epochs, args.epochs), batch_size=args.batch_size, accumulate_steps=args.accumulate_steps, patience=args.patience, learning_rate=args.learning_rate, seed=args.seed, max_train_batches=args.max_train_batches, max_val_batches=args.max_val_batches, device=args.device, pretrained=not args.no_pretrained, provenance=provenance, managed_artifact_roots=tuple(str(root) for root in ledger.roots), managed_limit_bytes=ledger.limit_bytes), train_loader=DataLoader(train_data, batch_size=args.batch_size, shuffle=True, worker_init_fn=seeded_worker_init_fn), val_loader=DataLoader(val_data, batch_size=args.batch_size, worker_init_fn=seeded_worker_init_fn), resume=not args.no_resume)
        _write_ledger_snapshot(ledger)
        print(result.metrics_path)
        return 0
    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    manifest = args.manifest or DATA_ROOT / "manifests" / f"{args.split}.csv"
    model, checkpoint_metadata = load_checkpoint(args.checkpoint, device=device)
    smoke_path = args.smoke_evidence or args.checkpoint.parent / "app_smoke.json"
    smoke_eligible, smoke_reason = smoke_promotion_eligibility(
        smoke_path,
        args.checkpoint,
    )
    if args.split == "test" and not smoke_eligible:
        print(json.dumps({
            "split": args.split,
            "promotion": {
                "promoted": False,
                "reason": smoke_reason,
                "app_smoke": smoke_reason,
            },
        }, indent=2, sort_keys=True))
        return 2
    provenance_eligible, provenance_reason = checkpoint_promotion_eligibility(
        checkpoint_metadata,
        DATA_ROOT,
    )
    if args.split == "test" and not provenance_eligible:
        print(json.dumps({
            "split": args.split,
            "promotion": {
                "promoted": False,
                "reason": provenance_reason,
                "validation": provenance_reason,
                "app_smoke": smoke_reason,
            },
        }, indent=2, sort_keys=True))
        return 2
    eligible, promotion_reason = promotion_eligibility(
        args.split, manifest, DATA_ROOT
    )
    if args.split == "test" and not eligible:
        print(json.dumps({
            "split": args.split,
            "promotion": {
                "promoted": False,
                "reason": promotion_reason,
                "validation": provenance_reason,
                "app_smoke": smoke_reason,
            },
        }, indent=2, sort_keys=True))
        return 2
    if args.split == "test":
        consume_protected_test(manifest, DATA_ROOT)
    report = evaluate(
        model,
        DataLoader(
            VideoClipDataset(manifest, split=args.split),
            batch_size=args.batch_size,
        ),
        device=device,
    )
    payload = report.to_dict()
    promoted = bool(
        report.accepted
        and eligible
        and provenance_eligible
        and smoke_eligible
    )
    payload.update(
        {
            "split": args.split,
            "manifest": str(Path(manifest).resolve()),
            "manifest_sha256": digest(Path(manifest)),
            "promotion": {
                "promoted": promoted,
                "reason": (
                    "all validation, provenance, canonical test, and app smoke gates accepted"
                    if promoted
                    else (
                        "acceptance thresholds were not met"
                        if not report.accepted
                        else next(
                            reason
                            for accepted, reason in (
                                (eligible, promotion_reason),
                                (provenance_eligible, provenance_reason),
                                (smoke_eligible, smoke_reason),
                            )
                            if not accepted
                        )
                    )
                ),
                "validation": provenance_reason,
                "app_smoke": smoke_reason,
            },
        }
    )
    ledger = _artifact_ledger(args.checkpoint.parent, args.accepted_model.parent)
    evaluation_path, matrix_path = _write_evaluation_artifacts(
        args.checkpoint,
        payload,
        report,
        ledger,
    )
    if promoted:
        try:
            inside(DATA_ROOT, args.accepted_model)
            promotion_root: Path | None = DATA_ROOT
        except ValueError:
            promotion_root = None
        atomic_copy(
            args.checkpoint,
            args.accepted_model,
            managed_root=promotion_root,
            artifact_ledger=ledger,
        )
        for source, suffix in (
            (args.checkpoint.parent / "training_metrics.json", "training_metrics.json"),
            (args.checkpoint.parent / "loss_curve.json", "loss_curve.json"),
            (evaluation_path, "evaluation_metrics.json"),
            (matrix_path, "evaluation_confusion_matrix.png"),
            (smoke_path, "app_smoke.json"),
        ):
            if source.is_file():
                atomic_copy(
                    source,
                    args.accepted_model.with_name(
                        f"{args.accepted_model.stem}.{suffix}"
                    ),
                    artifact_ledger=ledger,
                )
    _write_ledger_snapshot(ledger)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0
