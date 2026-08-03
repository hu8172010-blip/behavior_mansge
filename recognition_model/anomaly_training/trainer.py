"""Two-stage R3D-18 training with safe checkpoints and sklearn validation."""

from __future__ import annotations

import json
import os
import random
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import torch
from torch import nn
from torch.optim import AdamW, Optimizer
from torch.optim.lr_scheduler import StepLR

from anomaly_training.config import LABELS, MAX_DATA_BYTES
from anomaly_training.metrics import MetricReport, compute_metrics, write_confusion_matrix
from anomaly_training.model import build_model, configure_head_training, configure_layer4_training
from anomaly_training.storage import (
    ManagedArtifactLedger,
    atomic_copy,
    atomic_json_write,
)


@dataclass(slots=True)
class TrainConfig:
    run_dir: Path | str
    epochs: int = 20
    head_epochs: int = 5
    patience: int = 5
    batch_size: int = 2
    accumulate_steps: int = 1
    learning_rate: float = 1e-4
    weight_decay: float = 1e-4
    scheduler_gamma: float = 0.5
    scheduler_step_size: int = 3
    seed: int = 42
    device: str | None = None
    pretrained: bool = True
    class_weights: tuple[float, float, float] | None = None
    max_train_batches: int | None = None
    max_val_batches: int | None = None
    label_mapping: dict[str, int] = field(default_factory=lambda: dict(LABELS))
    provenance: dict[str, Any] = field(default_factory=dict)
    managed_artifact_roots: tuple[str, ...] = ()
    managed_limit_bytes: int = MAX_DATA_BYTES

    def __post_init__(self) -> None:
        self.run_dir = Path(self.run_dir)
        if self.epochs < 1 or self.head_epochs < 1 or self.head_epochs > self.epochs:
            raise ValueError("require 1 <= head_epochs <= epochs")
        if self.patience < 1 or self.accumulate_steps < 1:
            raise ValueError("patience and accumulate_steps must be positive")
        if self.label_mapping != LABELS:
            raise ValueError("label mapping must be normal=0, violence=1, fall=2")


@dataclass(frozen=True, slots=True)
class TrainingResult:
    best_checkpoint: Path
    last_checkpoint: Path
    metrics_path: Path
    loss_curve_path: Path
    confusion_matrix_path: Path
    best_score: float
    epochs_completed: int
    optimizer_steps: int
    stopped_early: bool


def set_deterministic(seed: int) -> None:
    """Set repeatable Python/NumPy/PyTorch state for a training run."""
    # PyTorch requires this setting before deterministic CUDA matrix
    # multiplication is used. Preserve an explicit operator choice.
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)
    if torch.backends.cudnn.is_available():
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True


def _device(config: TrainConfig) -> torch.device:
    requested = config.device or ("cuda" if torch.cuda.is_available() else "cpu")
    device = torch.device(requested)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is unavailable")
    return device


def _serializable_config(config: TrainConfig) -> dict[str, Any]:
    data = asdict(config)
    data["run_dir"] = str(data["run_dir"])
    return data


def _labels_from_loader(loader: Iterable[Any]) -> list[int]:
    dataset = getattr(loader, "dataset", None)
    tensors = getattr(dataset, "tensors", None)
    if tensors is not None and len(tensors) > 1:
        return [int(item) for item in tensors[1].tolist()]
    rows = getattr(dataset, "rows", None)
    if rows is not None:
        return [int(row.label) for row in rows]
    # The public contract accepts ordinary DataLoaders, not just our two dataset
    # implementations. Iterate a generic re-iterable loader once so class
    # weighting remains real for custom datasets too.
    labels: list[int] = []
    for batch in loader:
        if not isinstance(batch, (tuple, list)) or len(batch) < 2:
            raise ValueError("loader batches must contain (clips, labels)")
        values = batch[1]
        labels.extend(int(item) for item in torch.as_tensor(values).reshape(-1).tolist())
    return labels


def _class_weights(config: TrainConfig, loader: Iterable[Any], device: torch.device) -> torch.Tensor:
    if config.class_weights is not None:
        values = config.class_weights
    else:
        labels = _labels_from_loader(loader)
        counts = [labels.count(index) for index in range(3)]
        total = sum(counts)
        values = tuple(total / (3 * count) if count else 0.0 for count in counts) if total else (1.0, 1.0, 1.0)
    return torch.tensor(values, dtype=torch.float32, device=device)


def _phase_for_epoch(epoch: int, config: TrainConfig) -> str:
    return "head" if epoch <= config.head_epochs else "layer4"


def _configure_phase(model: nn.Module, phase: str) -> None:
    if phase == "head":
        configure_head_training(model)
    elif phase == "layer4":
        configure_layer4_training(model)
    else:  # pragma: no cover - internal invariant
        raise ValueError(f"unknown training phase: {phase}")


def _optimizer_and_scheduler(model: nn.Module, config: TrainConfig) -> tuple[Optimizer, StepLR]:
    params = [parameter for parameter in model.parameters() if parameter.requires_grad]
    if not params:
        raise RuntimeError("training phase left no parameters trainable")
    optimizer = AdamW(params, lr=config.learning_rate, weight_decay=config.weight_decay)
    return optimizer, StepLR(optimizer, step_size=config.scheduler_step_size, gamma=config.scheduler_gamma)


def _checkpoint_payload(
    *, model: nn.Module, optimizer: Optimizer, scheduler: StepLR, scaler: torch.amp.GradScaler, phase: str, epoch: int, best_score: float, no_improvement: int, config: TrainConfig, best_validation_report: dict[str, Any], current_validation_report: dict[str, Any]
) -> dict[str, Any]:
    return {
        "architecture": {"name": "r3d_18", "num_classes": 3, "classes": ["normal", "violence", "fall"]},
        "model": model.state_dict(),
        "phase": phase,
        "epoch": epoch,
        "optimizer": optimizer.state_dict(),
        "scheduler": scheduler.state_dict(),
        "scaler": scaler.state_dict(),
        "best_score": float(best_score),
        "no_improvement": int(no_improvement),
        "config": _serializable_config(config),
        "label_mapping": dict(config.label_mapping),
        "training_provenance": dict(config.provenance),
        "best_validation_report": dict(best_validation_report),
        "current_validation_report": dict(current_validation_report),
    }


def _load_resume(path: Path, device: torch.device) -> dict[str, Any]:
    payload = torch.load(path, map_location=device, weights_only=True)
    required = {"model", "epoch", "phase", "optimizer", "scheduler", "scaler", "best_score", "no_improvement"}
    missing = required - set(payload) if isinstance(payload, dict) else required
    if missing:
        raise ValueError(f"resume checkpoint missing fields: {sorted(missing)}")
    return payload


def _atomic_torch_save(
    payload: dict[str, Any],
    destination: Path,
    artifact_ledger: ManagedArtifactLedger | None = None,
) -> None:
    """Publish a checkpoint only after its same-directory temporary file is complete."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp", delete=False)
    temporary = Path(handle.name)
    handle.close()
    try:
        torch.save(payload, temporary)
        if artifact_ledger is not None:
            artifact_ledger.reserve(
                temporary.stat().st_size,
                replaced_path=destination,
            )
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_json_write(
    payload: dict[str, Any],
    destination: Path,
    artifact_ledger: ManagedArtifactLedger | None = None,
) -> None:
    """Atomically replace the per-epoch metrics record."""
    atomic_json_write(
        destination,
        payload,
        artifact_ledger=artifact_ledger,
    )


def _load_training_history(run_dir: Path, metrics_path: Path) -> list[dict[str, Any]]:
    """Read training history, migrating only an unmistakable legacy history."""
    candidates = [metrics_path]
    if not metrics_path.exists():
        candidates.append(run_dir / "metrics.json")
    for candidate in candidates:
        try:
            stored = json.loads(candidate.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError, TypeError):
            continue
        epochs = stored.get("epochs") if isinstance(stored, dict) else None
        if not isinstance(epochs, list):
            continue
        if candidate != metrics_path:
            _atomic_json_write(stored, metrics_path)
        return list(epochs)
    return []


def _run_epoch(
    model: nn.Module, loader: Iterable[Any], criterion: nn.Module, optimizer: Optimizer, scaler: torch.amp.GradScaler, device: torch.device, accumulate_steps: int, max_batches: int | None
) -> tuple[int, float]:
    model.train()
    optimizer.zero_grad(set_to_none=True)
    steps = 0
    batches = 0
    total_loss = 0.0
    total_samples = 0
    amp_enabled = device.type == "cuda"
    for batch_index, (clips, labels) in enumerate(loader):
        if max_batches is not None and batch_index >= max_batches:
            break
        clips, labels = clips.to(device), labels.to(device, dtype=torch.long)
        with torch.amp.autocast("cuda", enabled=amp_enabled):
            raw_loss = criterion(model(clips), labels)
            loss = raw_loss / accumulate_steps
        samples = int(labels.shape[0])
        total_loss += float(raw_loss.detach().cpu()) * samples
        total_samples += samples
        scaler.scale(loss).backward()
        batches += 1
        if batches % accumulate_steps == 0:
            scaler.step(optimizer)
            scaler.update()
            optimizer.zero_grad(set_to_none=True)
            steps += 1
    if batches and batches % accumulate_steps:
        # Losses in this partial window were initially divided by the configured
        # window size. Rescale its gradients so it is equivalent to division by
        # the actual number of final batches.
        remainder = batches % accumulate_steps
        for parameter in model.parameters():
            if parameter.grad is not None:
                parameter.grad.mul_(accumulate_steps / remainder)
        scaler.step(optimizer)
        scaler.update()
        optimizer.zero_grad(set_to_none=True)
        steps += 1
    return steps, total_loss / total_samples if total_samples else 0.0


@torch.inference_mode()
def _loss_only(
    model: nn.Module,
    loader: Iterable[Any],
    criterion: nn.Module,
    device: torch.device,
    max_batches: int | None,
) -> float:
    model.eval()
    total_loss = 0.0
    total_samples = 0
    for batch_index, (clips, labels) in enumerate(loader):
        if max_batches is not None and batch_index >= max_batches:
            break
        clips = clips.to(device)
        labels = labels.to(device, dtype=torch.long)
        with torch.amp.autocast("cuda", enabled=device.type == "cuda"):
            loss = criterion(model(clips), labels)
        samples = int(labels.shape[0])
        total_loss += float(loss.detach().cpu()) * samples
        total_samples += samples
    return total_loss / total_samples if total_samples else 0.0


@torch.inference_mode()
def evaluate(model: nn.Module, loader: Iterable[Any], *, device: str | torch.device | None = None, max_batches: int | None = None) -> MetricReport:
    """Evaluate an exact-label sklearn report; this path never enables CUDA AMP on CPU."""
    resolved = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
    model.to(resolved)
    model.eval()
    targets: list[int] = []
    predictions: list[int] = []
    amp_enabled = resolved.type == "cuda"
    for batch_index, (clips, labels) in enumerate(loader):
        if max_batches is not None and batch_index >= max_batches:
            break
        with torch.amp.autocast("cuda", enabled=amp_enabled):
            logits = model(clips.to(resolved))
        predictions.extend(torch.argmax(logits, dim=1).cpu().tolist())
        targets.extend(labels.to(dtype=torch.long).cpu().tolist())
    return compute_metrics(targets, predictions)


def train(config: TrainConfig, *, train_loader: Iterable[Any], val_loader: Iterable[Any], model: nn.Module | None = None, resume: bool = True) -> TrainingResult:
    """Train head-only then layer4+head, saving fully resumable state each epoch."""
    if iter(train_loader) is train_loader or iter(val_loader) is val_loader:
        raise ValueError("train_loader and val_loader must be re-iterable DataLoader objects, not one-shot iterators")
    set_deterministic(config.seed)
    artifact_ledger = (
        ManagedArtifactLedger(
            [Path(root) for root in config.managed_artifact_roots],
            limit_bytes=config.managed_limit_bytes,
            state_path=Path(config.managed_artifact_roots[0])
            / ".managed-artifact-ledger.json",
        )
        if config.managed_artifact_roots
        else None
    )
    config.run_dir.mkdir(parents=True, exist_ok=True)
    device = _device(config)
    last_path, best_path = config.run_dir / "last.pth", config.run_dir / "best.pth"
    metrics_path = config.run_dir / "training_metrics.json"
    loss_curve_path = config.run_dir / "loss_curve.json"
    matrix_path = config.run_dir / "training_confusion_matrix.png"
    history = _load_training_history(config.run_dir, metrics_path)
    payload = _load_resume(last_path, device) if resume and last_path.exists() else None
    if payload is not None and int(payload["no_improvement"]) >= config.patience:
        return TrainingResult(
            best_path,
            last_path,
            metrics_path,
            loss_curve_path,
            matrix_path,
            float(payload["best_score"]),
            int(payload["epoch"]),
            0,
            True,
        )
    if model is None:
        model = build_model(pretrained=config.pretrained)
    model.to(device)
    start_epoch = int(payload["epoch"]) + 1 if payload is not None else 1
    if payload is not None:
        model.load_state_dict(payload["model"])
    best_score = float(payload["best_score"]) if payload is not None else float("-inf")
    no_improvement = int(payload["no_improvement"]) if payload is not None else 0
    best_validation_report = (
        dict(payload.get("best_validation_report", {}))
        if payload is not None
        else {}
    )
    total_steps = 0
    stopped_early = False
    current_phase: str | None = None
    optimizer: Optimizer | None = None
    scheduler: StepLR | None = None
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")
    if payload is not None and payload["scaler"]:
        # Scaler state is independent of the optimizer parameter groups, so it
        # survives a legitimate head-to-layer4 optimizer rebuild. A disabled
        # CPU scaler serializes to {}, which must not be loaded into CUDA AMP.
        scaler.load_state_dict(payload["scaler"])
    for epoch in range(start_epoch, config.epochs + 1):
        for loader in (train_loader, val_loader):
            set_epoch = getattr(getattr(loader, "dataset", None), "set_epoch", None)
            if callable(set_epoch):
                set_epoch(epoch)
        phase = _phase_for_epoch(epoch, config)
        if phase != current_phase:
            _configure_phase(model, phase)
            optimizer, scheduler = _optimizer_and_scheduler(model, config)
            current_phase = phase
            # Optimizer state is only compatible when resuming inside the same phase.
            if payload is not None and epoch == start_epoch and payload["phase"] == phase:
                optimizer.load_state_dict(payload["optimizer"])
                scheduler.load_state_dict(payload["scheduler"])
        assert optimizer is not None and scheduler is not None
        criterion = nn.CrossEntropyLoss(
            weight=_class_weights(config, train_loader, device)
        )
        epoch_steps, train_loss = _run_epoch(
            model,
            train_loader,
            criterion,
            optimizer,
            scaler,
            device,
            config.accumulate_steps,
            config.max_train_batches,
        )
        total_steps += epoch_steps
        report = evaluate(model, val_loader, device=device, max_batches=config.max_val_batches)
        val_loss = _loss_only(
            model,
            val_loader,
            criterion,
            device,
            config.max_val_batches,
        )
        scheduler.step()
        improved = report.macro_f1 > best_score
        if improved:
            best_score, no_improvement = report.macro_f1, 0
            best_validation_report = report.to_dict()
        else:
            no_improvement += 1
        record = {
            "epoch": epoch,
            "phase": phase,
            "train_loss": float(train_loss),
            "val_loss": float(val_loss),
            "val": report.to_dict(),
            "best_macro_f1": float(best_score),
            "no_improvement": no_improvement,
        }
        history = [item for item in history if item.get("epoch") != epoch] + [record]
        _atomic_json_write(
            {"config": _serializable_config(config), "epochs": history},
            metrics_path,
            artifact_ledger,
        )
        ordered_history = sorted(history, key=lambda item: int(item["epoch"]))
        _atomic_json_write(
            {
                "epochs": [int(item["epoch"]) for item in ordered_history],
                "train_loss": [float(item["train_loss"]) for item in ordered_history],
                "val_loss": [float(item["val_loss"]) for item in ordered_history],
            },
            loss_curve_path,
            artifact_ledger,
        )
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
            temporary_matrix = Path(handle.name)
        try:
            write_confusion_matrix(report, temporary_matrix)
            atomic_copy(
                temporary_matrix,
                matrix_path,
                artifact_ledger=artifact_ledger,
            )
        finally:
            temporary_matrix.unlink(missing_ok=True)
        checkpoint = _checkpoint_payload(model=model, optimizer=optimizer, scheduler=scheduler, scaler=scaler, phase=phase, epoch=epoch, best_score=best_score, no_improvement=no_improvement, config=config, best_validation_report=best_validation_report, current_validation_report=report.to_dict())
        _atomic_torch_save(checkpoint, last_path, artifact_ledger)
        if improved:
            _atomic_torch_save(checkpoint, best_path, artifact_ledger)
        if no_improvement >= config.patience:
            stopped_early = True
            break
    completed = min(config.epochs, max(0, start_epoch - 1 if not history else max(int(row["epoch"]) for row in history)))
    return TrainingResult(best_path, last_path, metrics_path, loss_curve_path, matrix_path, best_score, completed, total_steps, stopped_early)
