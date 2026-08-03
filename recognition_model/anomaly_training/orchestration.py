"""End-to-end dataset acquisition, preparation, and audit orchestration."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil
from typing import Any, Iterable
import urllib.request
from urllib.parse import quote
from uuid import uuid4

from .config import DATA_ROOT, LABELS, MAX_DATA_BYTES
from .canonical_spec import (
    CANONICAL_CLASS_COUNTS,
    CANONICAL_PER_CLASS,
    CANONICAL_SEED,
    CANONICAL_SPLIT_COUNTS,
    canonical_selection,
    canonical_spec_digest,
    canonical_spec_payload,
    canonical_split_rows,
    normalize_selection,
    selection_digest,
    validate_canonical_selection,
)
from .downloads import (
    DownloadResult,
    StorageBudgetError,
    _check,
    _http_download,
    _root_size,
    download_source,
    migrate_http_integrity_from_receipt,
    verified_receipt_result,
    write_source_receipt,
)
from .manifest import (
    RawVideo,
    scan_avenue,
    scan_rlvs,
    scan_urfall,
    write_calibration_manifest,
    write_manifests,
)
from .sources import SOURCES
from .storage import atomic_json_write, digest, inside
from .storage import atomic_copy


UR_FALL_BASE = "https://fenix.ur.edu.pl/mkepski/ds/data"
UR_FALL_LICENSE = (
    "Official UR Fall Detection Dataset RGB camera-0 videos; the official page "
    "states CC BY-NC-SA 4.0. Preserve attribution and use non-commercially."
)
EXPECTED_SOURCES = frozenset({"rlvs", "urfall", "avenue", "avenue_ground_truth"})
_KAGGLE_MEMBER_METADATA: dict[str, dict[str, dict[str, Any]]] = {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _protected_protocol_digest(payload: dict[str, Any]) -> str:
    frozen = dict(payload)
    frozen.pop("frozen_protocol_sha256", None)
    frozen["test_access_count"] = 0
    frozen["test_accessed_at_utc"] = None
    return sha256(
        json.dumps(
            frozen,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def managed_root_for_path(path: Path, root: Path | None = None) -> Path | None:
    candidate_root = Path(root) if root is not None else DATA_ROOT
    resolved_root = candidate_root.resolve()
    resolved_path = Path(path).resolve()
    if resolved_path == resolved_root or resolved_root in resolved_path.parents:
        return candidate_root
    return None


def _atomic_json(
    payload: dict[str, Any],
    path: Path,
    *,
    managed_root: Path | None = None,
) -> None:
    atomic_json_write(
        path,
        payload,
        managed_root=managed_root,
        limit_bytes=MAX_DATA_BYTES,
    )


def _read_source_manifest(root: Path) -> dict[str, Any]:
    path = root / "source-manifest.json"
    if not path.exists():
        return {
            "managed_root": str(root.resolve()),
            "budget_bytes": MAX_DATA_BYTES,
            "sources": {},
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("sources"), dict):
        raise ValueError("source-manifest.json has an invalid structure")
    return payload


def _write_source_manifest(root: Path, payload: dict[str, Any]) -> Path:
    payload["managed_root"] = str(root.resolve())
    payload["budget_bytes"] = MAX_DATA_BYTES
    payload["root_size_bytes"] = _root_size(root)
    payload["updated_at_utc"] = _utc_now()
    if payload["root_size_bytes"] > MAX_DATA_BYTES:
        raise StorageBudgetError("Data-root budget would be exceeded.")
    path = root / "source-manifest.json"
    _atomic_json(payload, path, managed_root=root)
    # The manifest itself counts toward the managed root. Re-write until the
    # recorded total includes the newly published JSON bytes (normally once).
    for _ in range(3):
        actual = _root_size(root)
        if payload["root_size_bytes"] == actual:
            break
        payload["root_size_bytes"] = actual
        _atomic_json(payload, path, managed_root=root)
    _check(root)
    return path


def _download_official_urfall(root: Path) -> DownloadResult:
    files: list[Path] = []
    urls: dict[str, str] = {}
    dataset_dir = root / "urfall"
    for prefix, count in (("fall", 30), ("adl", 40)):
        category = dataset_dir / prefix
        category.mkdir(parents=True, exist_ok=True)
        for index in range(1, count + 1):
            name = f"{prefix}-{index:02d}-cam0.mp4"
            url = f"{UR_FALL_BASE}/{name}"
            target, resolved = _http_download(url, root, f"urfall/{prefix}/{name}")
            files.append(target)
            urls[target.resolve().relative_to(root.resolve()).as_posix()] = resolved
    result = DownloadResult(
        key="urfall",
        files=tuple(files),
        source_url="https://fenix.ur.edu.pl/mkepski/ds/uf.html",
        homepage="https://fenix.ur.edu.pl/mkepski/ds/uf.html",
        research_use_note=UR_FALL_LICENSE,
        downloaded_at=datetime.now(timezone.utc),
        original_locator=f"{UR_FALL_BASE}/{{fall-01..30,adl-01..40}}-cam0.mp4",
        root=root,
        file_urls=urls,
    )
    write_source_receipt(result, root / "receipts" / "urfall")
    return result


def _kaggle_catalog_size(source: Any) -> int:
    api = f"https://www.kaggle.com/api/v1/datasets/view/{source.locator}"
    with urllib.request.urlopen(urllib.request.Request(api, method="GET")) as response:
        metadata = json.loads(response.read().decode("utf-8"))
    value = metadata.get("totalBytes")
    if not isinstance(value, int) or value <= 0:
        raise StorageBudgetError("Kaggle did not report a valid catalog size.")
    entries = metadata.get("datasetFiles") or metadata.get("files") or []
    members: dict[str, dict[str, Any]] = {}
    for item in entries:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("path")
        if not isinstance(name, str):
            continue
        members[name] = {
            "size_bytes": item.get("totalBytes") or item.get("size"),
            "sha256": item.get("sha256"),
        }
    _KAGGLE_MEMBER_METADATA[source.locator] = members
    return value


def _kaggle_member_metadata(source: Any, member: str) -> dict[str, Any]:
    return _KAGGLE_MEMBER_METADATA.get(source.locator, {}).get(member, {})


def _download_rlvs_subset(root: Path, count: int = 30) -> DownloadResult:
    """Download a deterministic balanced first subset from public Kaggle."""
    source = SOURCES["rlvs"]
    catalog_size = _kaggle_catalog_size(source)
    # The entire catalog size is a conservative upper bound for this 30-file
    # subset. Refuse before giving KaggleHub any output path.
    _check(root, catalog_size)
    destination = root / "rlvs"
    destination.mkdir(parents=True, exist_ok=True)
    import kagglehub

    handle = f"{source.locator}/versions/1"
    files: list[Path] = []
    urls: dict[str, str] = {}
    members = [
        f"Real Life Violence Dataset/NonViolence/NV_{index}.mp4"
        for index in range(1, count + 1)
    ] + [
        f"Real Life Violence Dataset/Violence/V_{index}.mp4"
        for index in range(1, count + 1)
    ]
    for member in members:
        from requests import RequestException

        location: Path | None = None
        force_download = False
        staging = root / ".kaggle-staging" / uuid4().hex
        expected_staged = staging / member
        for attempt in range(8):
            try:
                kwargs = {
                    "path": member,
                    "output_dir": str(staging),
                }
                if force_download:
                    kwargs["force_download"] = True
                location = Path(kagglehub.dataset_download(handle, **kwargs))
                break
            except FileExistsError:
                # KaggleHub uses the final path for an interrupted individual
                # file. Replace only the exact member it identifies as partial.
                force_download = True
            except (OSError, RequestException):
                if attempt == 7:
                    raise
        if location is None:
            raise AssertionError("unreachable Kaggle retry loop")
        resolved = location.resolve()
        if resolved != expected_staged.resolve() or not resolved.is_file():
            shutil.rmtree(staging, ignore_errors=True)
            raise ValueError("KaggleHub returned a path other than the exact requested member.")
        metadata = _kaggle_member_metadata(source, member)
        expected_size = metadata.get("size_bytes")
        expected_checksum = metadata.get("sha256")
        if isinstance(expected_size, int) and resolved.stat().st_size != expected_size:
            shutil.rmtree(staging, ignore_errors=True)
            raise ValueError("Kaggle member size does not match catalog metadata.")
        if isinstance(expected_checksum, str) and digest(resolved) != expected_checksum:
            shutil.rmtree(staging, ignore_errors=True)
            raise ValueError("Kaggle member checksum does not match catalog metadata.")
        target = destination / member
        try:
            atomic_copy(resolved, target, managed_root=root, limit_bytes=MAX_DATA_BYTES)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        _check(root)
        files.append(target)
        relative = target.resolve().relative_to(root.resolve()).as_posix()
        urls[relative] = f"{source.homepage}/data?select={quote(member)}"
    result = DownloadResult(
        key="rlvs",
        files=tuple(files),
        source_url=source.homepage,
        homepage=source.homepage,
        research_use_note=(
            source.research_use_note
            + f" Deterministic balanced first baseline downloads NonViolence/NV_1..NV_{count}.mp4 "
            f"and Violence/V_1..V_{count}.mp4."
        ),
        downloaded_at=datetime.now(timezone.utc),
        original_locator=(
            f"{source.locator}/versions/1:"
            f"NonViolence/NV_1..NV_{count}.mp4,Violence/V_1..V_{count}.mp4"
        ),
        root=root,
        file_urls=urls,
    )
    write_source_receipt(result, root / "receipts" / "rlvs")
    return result


def download_datasets(keys: Iterable[str], root: Path = DATA_ROOT) -> dict[str, Any]:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    _check(root)
    manifest = _read_source_manifest(root)
    requested = list(dict.fromkeys(keys))
    unknown = sorted(set(requested) - {"rlvs", "urfall", "avenue"})
    if unknown:
        raise ValueError(f"unsupported first-round datasets: {', '.join(unknown)}")
    for key in requested:
        before = _root_size(root)
        try:
            reused = verified_receipt_result(key, root)
            if reused is not None:
                migrate_http_integrity_from_receipt(key, root)
                result = reused
            elif key == "urfall":
                result = _download_official_urfall(root)
            elif key == "rlvs":
                result = _download_rlvs_subset(root)
            else:
                result = download_source(SOURCES[key], root)
            manifest["sources"][key] = {
                "status": "acquired",
                "receipt": f"receipts/{key}/source.json",
                "files": len(result.files),
                "bytes_before": before,
                "bytes_after": _root_size(root),
                "homepage": result.homepage,
                "reused": reused is not None,
            }
        except Exception as error:
            manifest["sources"][key] = {
                "status": "failed",
                "error": f"{type(error).__name__}: {error}",
                "bytes_before": before,
                "bytes_after": _root_size(root),
                "homepage": SOURCES[key].homepage,
            }
        _write_source_manifest(root, manifest)
    if "avenue" in requested and manifest["sources"].get("avenue", {}).get("status") == "acquired":
        key = "avenue_ground_truth"
        before = _root_size(root)
        try:
            reused = verified_receipt_result(key, root)
            if reused is not None:
                migrate_http_integrity_from_receipt(key, root)
                result = reused
            else:
                result = download_source(SOURCES[key], root)
            manifest["sources"][key] = {
                "status": "acquired",
                "receipt": f"receipts/{key}/source.json",
                "files": len(result.files),
                "bytes_before": before,
                "bytes_after": _root_size(root),
                "homepage": result.homepage,
                "reused": reused is not None,
            }
        except Exception as error:
            manifest["sources"][key] = {
                "status": "failed",
                "error": f"{type(error).__name__}: {error}",
                "bytes_before": before,
                "bytes_after": _root_size(root),
                "homepage": SOURCES[key].homepage,
            }
        _write_source_manifest(root, manifest)
    return manifest


def verify_sources(root: Path = DATA_ROOT) -> dict[str, Any]:
    root = Path(root)
    manifest = _read_source_manifest(root)
    report: dict[str, Any] = {
        "ok": True,
        "root_size_bytes": _root_size(root),
        "budget_bytes": MAX_DATA_BYTES,
        "sources": {},
    }
    if report["root_size_bytes"] > MAX_DATA_BYTES:
        report["ok"] = False
    actual_sources = set(manifest["sources"])
    report["missing_sources"] = sorted(EXPECTED_SOURCES - actual_sources)
    report["unexpected_sources"] = sorted(actual_sources - EXPECTED_SOURCES)
    if report["missing_sources"] or report["unexpected_sources"]:
        report["ok"] = False
    for key, status in sorted(manifest["sources"].items()):
        entry = {"verified": False, "status": status.get("status")}
        if status.get("status") != "acquired":
            entry["error"] = status.get("error", "source was not acquired")
            report["ok"] = False
            report["sources"][key] = entry
            continue
        receipt_path = root / status.get("receipt", f"receipts/{key}/source.json")
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if not receipt.get("homepage") or not receipt.get("research_use_note"):
                raise ValueError("receipt lacks homepage or usage note")
            checked = 0
            for item in receipt.get("files", []):
                path = (root / item["path"]).resolve()
                if root.resolve() not in path.parents:
                    raise ValueError("receipt path escapes managed root")
                data_digest = sha256()
                with path.open("rb") as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        data_digest.update(block)
                if path.stat().st_size != item["size_bytes"] or data_digest.hexdigest() != item["sha256"]:
                    raise ValueError(f"checksum or size mismatch: {item['path']}")
                checked += 1
            if checked == 0:
                raise ValueError("receipt has no files")
            entry.update({"verified": True, "files": checked, "receipt": str(receipt_path)})
        except Exception as error:
            entry["error"] = f"{type(error).__name__}: {error}"
            report["ok"] = False
        report["sources"][key] = entry
    _write_source_manifest(root, manifest)
    report["root_size_bytes"] = manifest["root_size_bytes"]
    return report


def _as_raw_video(row: Any) -> RawVideo:
    if isinstance(row, RawVideo):
        return row
    return RawVideo(row.path, row.label, row.source, row.group_id, row.subject_id)


def _select_per_class(rows: Iterable[Any], per_class: int) -> list[RawVideo]:
    selected: list[RawVideo] = []
    for label in LABELS.values():
        candidates = sorted(
            (_as_raw_video(row) for row in rows if row.label == label),
            key=lambda row: str(row.path).replace("\\", "/").lower(),
        )
        if len(candidates) < per_class:
            raise ValueError(
                f"label {label} has only {len(candidates)} usable source videos; {per_class} are required"
            )
        selected.extend(candidates[:per_class])
    return sorted(selected, key=lambda row: str(row.path).replace("\\", "/").lower())


def _assert_canonical_training_layout(
    root: Path,
    rlvs_rows: list[RawVideo],
    urfall_rows: list[RawVideo],
) -> None:
    rlvs_base = root / "rlvs" / "Real Life Violence Dataset"
    expected_rlvs = {
        *(str((rlvs_base / "NonViolence" / f"NV_{index}.mp4").resolve()).lower() for index in range(1, 31)),
        *(str((rlvs_base / "Violence" / f"V_{index}.mp4").resolve()).lower() for index in range(1, 31)),
    }
    urfall_base = root / "urfall"
    expected_urfall = {
        *(str((urfall_base / "fall" / f"fall-{index:02d}-cam0.mp4").resolve()).lower() for index in range(1, 31)),
        *(str((urfall_base / "adl" / f"adl-{index:02d}-cam0.mp4").resolve()).lower() for index in range(1, 41)),
    }
    actual_rlvs = {str(Path(row.path).resolve()).lower() for row in rlvs_rows}
    actual_urfall = {str(Path(row.path).resolve()).lower() for row in urfall_rows}
    if actual_rlvs != expected_rlvs:
        raise ValueError("RLVS canonical 30+30 member layout is incomplete or contains unexpected videos")
    if actual_urfall != expected_urfall:
        raise ValueError("UR Fall canonical cam0 30-fall+40-ADL layout is incomplete or unexpected")


def prepare_manifests(
    root: Path = DATA_ROOT,
    *,
    output_dir: Path | None = None,
    per_class: int = 30,
    seed: int = 42,
) -> dict[str, Any]:
    root = Path(root)
    output = Path(output_dir) if output_dir else root / "manifests"
    canonical_output = (root / "manifests").resolve()
    resolved_output = output.resolve()
    canonical = resolved_output == canonical_output
    if canonical_output in resolved_output.parents:
        raise ValueError("experimental output must be outside the canonical manifests directory")
    if canonical and (
        seed != CANONICAL_SEED or per_class != CANONICAL_PER_CLASS
    ):
        raise ValueError("canonical manifests require seed=42 and per_class=30")
    try:
        inside(root, output)
        managed_root: Path | None = root
    except ValueError:
        managed_root = None
    rlvs_rows = scan_rlvs(root / "rlvs")
    urfall_rows = scan_urfall(root / "urfall")
    _assert_canonical_training_layout(root, rlvs_rows, urfall_rows)
    candidates = [
        *rlvs_rows,
        *(row for row in urfall_rows if row.label == LABELS["fall"]),
    ]
    selected = _select_per_class(candidates, per_class)
    selected_records = normalize_selection(
        {
            "path": row.path,
            "label": row.label,
            "source": row.source,
            "group_id": row.group_id,
            "subject_id": row.subject_id,
        }
        for row in selected
    )
    if canonical:
        validate_canonical_selection(root, selected_records)
    splits = write_manifests(
        selected,
        output,
        seed=seed,
        managed_root=managed_root,
        include_person_boxes=canonical,
    )
    calibration = write_calibration_manifest(
        scan_avenue(root / "avenue"),
        output / "avenue",
        managed_root=managed_root,
    )
    selected_counts = {
        name: sum(row.label == label for row in selected) for name, label in LABELS.items()
    }
    report = {
        "seed": seed,
        "per_class": per_class,
        "promotable": canonical,
        "schema_version": 1,
        "canonical_spec": canonical_spec_payload(),
        "canonical_spec_sha256": canonical_spec_digest(),
        "selection_sha256": selection_digest(selected_records),
        "selected_counts": selected_counts,
        "split_counts": {name: len(rows) for name, rows in splits.items()},
        "avenue_calibration_count": len(calibration),
        "selection": selected_records,
    }
    if canonical:
        box_rows: list[dict[str, str]] = []
        for split in ("train", "val", "test"):
            with (output / f"{split}.csv").open(
                newline="",
                encoding="utf-8",
            ) as stream:
                box_rows.extend(csv.DictReader(stream))
        fallback_frames = sum(
            int(row["box_fallback_frames"])
            for row in box_rows
        )
        total_frames = sum(int(row["frame_count"]) for row in box_rows)
        report["person_box_trace"] = {
            "detector": sorted(
                {row["box_detector"] for row in box_rows}
            ),
            "fallback_frames": fallback_frames,
            "total_frames": total_frames,
            "fallback_frequency": (
                fallback_frames / total_frames if total_frames else 1.0
            ),
        }
    if canonical:
        if report["split_counts"] != CANONICAL_SPLIT_COUNTS:
            raise ValueError("canonical preparation produced noncanonical split counts")
        produced_class_counts = {
            split: {
                name: sum(row.label == label for row in rows)
                for name, label in LABELS.items()
            }
            for split, rows in splits.items()
        }
        if produced_class_counts != CANONICAL_CLASS_COUNTS:
            raise ValueError("canonical preparation produced noncanonical class counts")
    _atomic_json(report, output / "selection.json", managed_root=managed_root)
    return report


def audit_splits(
    manifest_dir: Path | None = None,
    *,
    managed_root: Path | None = None,
) -> dict[str, Any]:
    directory = Path(manifest_dir) if manifest_dir else DATA_ROOT / "manifests"
    root = Path(managed_root) if managed_root is not None else DATA_ROOT
    canonical = directory.resolve() == (root / "manifests").resolve()
    selection_path = directory / "selection.json"
    try:
        selection_payload = json.loads(selection_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError) as error:
        raise ValueError("selection.json is required for split audit") from error
    if not isinstance(selection_payload, dict) or not isinstance(
        selection_payload.get("selection"), list
    ):
        raise ValueError("selection.json has an invalid selection")
    selection_rows = normalize_selection(selection_payload["selection"])
    protected_v4 = selection_payload.get("schema_version") == 4
    if len({json.dumps(row, sort_keys=True) for row in selection_rows}) != len(selection_rows):
        raise ValueError("selection contains duplicate records")
    if protected_v4:
        if (
            selection_payload.get("frozen") is not True
            or selection_payload.get("frozen_protocol_sha256")
            != _protected_protocol_digest(selection_payload)
        ):
            raise ValueError("protected protocol digest does not match")
    else:
        if selection_payload.get("canonical_spec") != canonical_spec_payload():
            raise ValueError("selection canonical spec payload does not match")
        if selection_payload.get("canonical_spec_sha256") != canonical_spec_digest():
            raise ValueError("selection canonical spec digest does not match")
    computed_selection_digest = selection_digest(selection_rows)
    if (
        selection_payload.get("selection_sha256")
        != computed_selection_digest
    ):
        raise ValueError("selection digest does not match its records")
    if canonical:
        if not protected_v4 and (
            selection_payload.get("seed") != CANONICAL_SEED
            or selection_payload.get("per_class") != CANONICAL_PER_CLASS
            or selection_payload.get("promotable") is not True
        ):
            raise ValueError("canonical selection metadata is not promotable")
        if not protected_v4:
            validate_canonical_selection(root, selection_rows)
    rows: dict[str, list[dict[str, str]]] = {}
    class_counts: dict[str, dict[str, int]] = {}
    groups: dict[str, set[tuple[str, str]]] = {}
    subjects: dict[str, set[tuple[str, str]]] = {}
    paths: dict[str, set[str]] = {}
    content_digests: dict[str, set[str]] = {}
    source_file_sha256: dict[str, str] = {}
    manifest_sha256: dict[str, str] = {}
    for split in ("train", "val", "test"):
        manifest_path = directory / f"{split}.csv"
        with manifest_path.open(newline="", encoding="utf-8") as stream:
            rows[split] = list(csv.DictReader(stream))
        manifest_sha256[split] = digest(manifest_path)
        class_counts[split] = {
            name: sum(int(row["label"]) == label for row in rows[split])
            for name, label in LABELS.items()
        }
        missing = [name for name, count in class_counts[split].items() if count == 0]
        if missing:
            raise ValueError(f"{split} is missing classes: {', '.join(missing)}")
        groups[split] = {(row["source"], row["group_id"]) for row in rows[split]}
        subjects[split] = {(row["source"], row["subject_id"]) for row in rows[split]}
        paths[split] = {str(Path(row["path"]).resolve()).lower() for row in rows[split]}
        if len(paths[split]) != len(rows[split]):
            raise ValueError(f"{split} contains duplicate paths")
        content_digests[split] = set()
        for row in rows[split]:
            source_path = Path(row["path"]).resolve()
            if not source_path.is_file():
                raise ValueError(f"selected source file is missing: {source_path}")
            current_digest = digest(source_path)
            source_file_sha256[str(source_path)] = current_digest
            content_digests[split].add(current_digest)
        if len(content_digests[split]) != len(rows[split]):
            raise ValueError(f"{split} contains duplicate file content")
    intersections: dict[str, list[str]] = {}
    subject_intersections: dict[str, list[str]] = {}
    path_intersections: dict[str, list[str]] = {}
    digest_intersections: dict[str, list[str]] = {}
    for left, right in (("train", "val"), ("train", "test"), ("val", "test")):
        key = f"{left}:{right}"
        intersections[key] = sorted(f"{source}:{value}" for source, value in groups[left] & groups[right])
        subject_intersections[key] = sorted(
            f"{source}:{value}" for source, value in subjects[left] & subjects[right]
        )
        path_intersections[key] = sorted(paths[left] & paths[right])
        digest_intersections[key] = sorted(
            content_digests[left] & content_digests[right]
        )
    if any(intersections.values()) or any(subject_intersections.values()):
        raise ValueError("split leakage detected in group_id or subject_id")
    if any(path_intersections.values()):
        raise ValueError("split path leakage detected")
    if any(digest_intersections.values()):
        raise ValueError("split content digest leakage detected")
    split_identity = {
        split: normalize_selection(values)
        for split, values in rows.items()
    }
    union = normalize_selection(
        row for values in split_identity.values() for row in values
    )
    if union != selection_rows:
        raise ValueError("split union does not exactly match selection")
    if canonical:
        if protected_v4:
            declared = {
                split: normalize_selection(
                    row
                    for row in selection_payload["selection"]
                    if row.get("split") == split
                )
                for split in ("train", "val", "test")
            }
            if split_identity != declared:
                raise ValueError(
                    "split membership does not match protected protocol"
                )
            for row in selection_payload["selection"]:
                path = Path(str(row["path"])).resolve()
                if row.get("sha256") != source_file_sha256.get(str(path)):
                    raise ValueError("protected member source digest changed")
            retired = set(
                selection_payload.get("retired_test_members_sha256", [])
            )
            if retired & set(source_file_sha256.values()):
                raise ValueError(
                    "retired exposed test content entered protected protocol"
                )
        else:
            expected_splits = canonical_split_rows(root)
            if split_identity != expected_splits:
                raise ValueError("split membership does not match the canonical seed-42 baseline")
            if {split: len(value) for split, value in rows.items()} != CANONICAL_SPLIT_COUNTS:
                raise ValueError("canonical split counts do not match")
            if class_counts != CANONICAL_CLASS_COUNTS:
                raise ValueError("canonical per-class split counts do not match")
    report = {
        "ok": True,
        "promotable": canonical,
        "class_counts": class_counts,
        "split_counts": {split: len(value) for split, value in rows.items()},
        "group_intersections": intersections,
        "subject_intersections": subject_intersections,
        "path_intersections": path_intersections,
        "content_digest_intersections": digest_intersections,
        "source_file_sha256": source_file_sha256,
        "manifest_sha256": manifest_sha256,
        "selection_file_sha256": digest(selection_path),
        "selection_sha256": computed_selection_digest,
        "canonical_spec_sha256": (
            None if protected_v4 else canonical_spec_digest()
        ),
        "protected_protocol_sha256": (
            selection_payload.get("frozen_protocol_sha256")
            if protected_v4
            else None
        ),
        "audited_at_utc": _utc_now(),
    }
    effective_root = managed_root or managed_root_for_path(directory)
    _atomic_json(
        report,
        directory / "audit.json",
        managed_root=effective_root,
    )
    return report


def promotion_eligibility(
    split: str,
    manifest: Path,
    root: Path = DATA_ROOT,
) -> tuple[bool, str]:
    """Return whether evaluation may atomically promote its checkpoint."""
    root = Path(root)
    if split != "test":
        return False, "promotion requires split=test"
    canonical_dir = root / "manifests"
    canonical = canonical_dir / "test.csv"
    if Path(manifest).resolve() != canonical.resolve():
        return False, "promotion requires the canonical managed test manifest"
    try:
        audit = json.loads((canonical_dir / "audit.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False, "promotion requires a successful current split audit"
    if audit.get("ok") is not True or not isinstance(audit.get("manifest_sha256"), dict):
        return False, "promotion requires a successful current split audit"
    if audit.get("promotable") is not True:
        return False, "promotion requires a promotable canonical audit"
    for name in ("train", "val", "test"):
        current = canonical_dir / f"{name}.csv"
        if not current.is_file() or audit["manifest_sha256"].get(name) != digest(current):
            return False, f"canonical {name} manifest changed after audit"
    selection_path = canonical_dir / "selection.json"
    if (
        not selection_path.is_file()
        or audit.get("selection_file_sha256") != digest(selection_path)
    ):
        return False, "canonical selection changed after audit"
    try:
        selection_payload = json.loads(selection_path.read_text(encoding="utf-8"))
        selection_rows = normalize_selection(selection_payload["selection"])
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
        return False, "canonical selection is invalid"
    protected_v4 = selection_payload.get("schema_version") == 4
    if protected_v4:
        if (
            selection_payload.get("frozen") is not True
            or selection_payload.get("test_access_count") != 0
            or selection_payload.get("frozen_protocol_sha256")
            != _protected_protocol_digest(selection_payload)
            or selection_payload.get("selection_sha256")
            != selection_digest(selection_rows)
            or audit.get("selection_sha256")
            != selection_digest(selection_rows)
            or audit.get("protected_protocol_sha256")
            != selection_payload.get("frozen_protocol_sha256")
        ):
            return False, "protected protocol is changed or test was already accessed"
        declared = {
            name: normalize_selection(
                row
                for row in selection_payload["selection"]
                if row.get("split") == name
            )
            for name in ("train", "val", "test")
        }
        try:
            current_splits = {}
            for name in ("train", "val", "test"):
                with (canonical_dir / f"{name}.csv").open(
                    newline="", encoding="utf-8"
                ) as stream:
                    current_splits[name] = normalize_selection(
                        list(csv.DictReader(stream))
                    )
        except (OSError, ValueError, KeyError):
            return False, "protected split records are invalid"
        if current_splits != declared:
            return False, "protected split membership changed"
        return True, "frozen protected test is ready for its single access"
    try:
        validate_canonical_selection(root, selection_rows)
    except ValueError:
        return False, "canonical selection is invalid"
    if (
        selection_payload.get("promotable") is not True
        or selection_payload.get("seed") != CANONICAL_SEED
        or selection_payload.get("per_class") != CANONICAL_PER_CLASS
        or selection_payload.get("canonical_spec") != canonical_spec_payload()
        or selection_payload.get("canonical_spec_sha256") != canonical_spec_digest()
        or selection_payload.get("selection_sha256") != selection_digest(selection_rows)
        or audit.get("selection_sha256") != selection_digest(selection_rows)
        or audit.get("canonical_spec_sha256") != canonical_spec_digest()
    ):
        return False, "canonical selection or specification digest does not match"
    current_splits: dict[str, list[dict[str, object]]] = {}
    try:
        for name in ("train", "val", "test"):
            with (canonical_dir / f"{name}.csv").open(
                newline="", encoding="utf-8"
            ) as stream:
                current_splits[name] = normalize_selection(list(csv.DictReader(stream)))
    except (OSError, ValueError, KeyError):
        return False, "canonical split records are invalid"
    if current_splits != canonical_split_rows(root):
        return False, "canonical split membership does not match specification"
    return True, "canonical audited test manifest"


def consume_protected_test(
    manifest: Path,
    root: Path = DATA_ROOT,
) -> dict[str, Any]:
    """Atomically burn the single protected-test access before decoding."""
    root = Path(root)
    canonical_dir = root / "manifests"
    if Path(manifest).resolve() != (canonical_dir / "test.csv").resolve():
        raise ValueError("single-use access requires protected test manifest")
    path = canonical_dir / "selection.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        payload.get("schema_version") != 4
        or payload.get("test_access_count") != 0
        or payload.get("frozen_protocol_sha256")
        != _protected_protocol_digest(payload)
    ):
        raise ValueError("protected test is not available for first access")
    payload["test_access_count"] = 1
    payload["test_accessed_at_utc"] = _utc_now()
    _atomic_json(payload, path, managed_root=root)
    return payload


def canonical_training_provenance(
    train_manifest: Path,
    val_manifest: Path,
    root: Path = DATA_ROOT,
) -> dict[str, Any]:
    """Bind a training run to the current audited canonical inputs."""
    root = Path(root)
    canonical_dir = root / "manifests"
    if (
        Path(train_manifest).resolve()
        != (canonical_dir / "train.csv").resolve()
        or Path(val_manifest).resolve()
        != (canonical_dir / "val.csv").resolve()
    ):
        return {
            "promotable": False,
            "reason": "training did not use canonical train/validation manifests",
        }
    eligible, reason = promotion_eligibility(
        "test",
        canonical_dir / "test.csv",
        root,
    )
    if not eligible:
        raise ValueError(reason)
    audit = json.loads(
        (canonical_dir / "audit.json").read_text(encoding="utf-8")
    )
    selection_path = canonical_dir / "selection.json"
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    receipt_hashes: dict[str, str] = {}
    for receipt_path in (root / "receipts").glob("*/source.json"):
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for item in receipt.get("files", []):
            if (
                isinstance(item, dict)
                and isinstance(item.get("path"), str)
                and isinstance(item.get("sha256"), str)
            ):
                receipt_hashes[
                    str((root / item["path"]).resolve())
                ] = item["sha256"]
    source_hashes: dict[str, str] = {}
    missing: list[str] = []
    for row in selection["selection"]:
        path = Path(str(row["path"])).resolve()
        if not path.is_file():
            missing.append(str(path))
            continue
        current_sha256 = digest(path)
        receipt_sha256 = receipt_hashes.get(str(path))
        if (
            receipt_sha256 is not None
            and receipt_sha256 != current_sha256
        ):
            raise ValueError(f"source file differs from receipt: {path}")
        audited_sha256 = audit.get("source_file_sha256", {}).get(str(path))
        if (
            not isinstance(audited_sha256, str)
            or audited_sha256 != current_sha256
        ):
            raise ValueError(f"source file differs from current audit: {path}")
        source_hashes[str(path)] = current_sha256
    box_total = 0
    box_fallback = 0
    detectors: set[str] = set()
    rows_with_boxes = 0
    for split in ("train", "val", "test"):
        with (canonical_dir / f"{split}.csv").open(
            newline="",
            encoding="utf-8",
        ) as stream:
            for row in csv.DictReader(stream):
                if row.get("boxes"):
                    rows_with_boxes += 1
                if row.get("box_detector"):
                    detectors.add(row["box_detector"])
                if row.get("frame_count"):
                    box_total += int(row["frame_count"])
                if row.get("box_fallback_frames"):
                    box_fallback += int(row["box_fallback_frames"])
    return {
        "schema_version": 2,
        "promotable": True,
        "manifest_sha256": dict(audit["manifest_sha256"]),
        "selection_file_sha256": digest(selection_path),
        "selection_sha256": audit["selection_sha256"],
        "canonical_spec_sha256": audit["canonical_spec_sha256"],
        "protected_protocol_sha256": audit.get(
            "protected_protocol_sha256"
        ),
        "source_file_sha256": source_hashes,
        "missing_source_files": sorted(missing),
        "person_crop": {
            "convention": "per-frame 25%-padded person box, RGB letterbox-128, crop-112",
            "detectors": sorted(detectors),
            "rows_with_boxes": rows_with_boxes,
            "rows_total": sum(audit["split_counts"].values()),
            "fallback_frames": box_fallback,
            "total_frames": box_total,
            "fallback_frequency": (
                box_fallback / box_total if box_total else 1.0
            ),
        },
    }


def checkpoint_promotion_eligibility(
    checkpoint_metadata: dict[str, Any],
    root: Path = DATA_ROOT,
) -> tuple[bool, str]:
    current_validation = checkpoint_metadata.get("current_validation_report")
    if (
        not isinstance(current_validation, dict)
        or current_validation.get("accepted") is not True
    ):
        return False, "checkpoint current validation report was not accepted"
    validation = checkpoint_metadata.get("best_validation_report")
    if not isinstance(validation, dict) or validation.get("accepted") is not True:
        return False, "checkpoint best validation report was not accepted"
    stored = checkpoint_metadata.get("training_provenance")
    if not isinstance(stored, dict) or stored.get("promotable") is not True:
        return False, "checkpoint lacks promotable training provenance"
    try:
        current = canonical_training_provenance(
            Path(root) / "manifests" / "train.csv",
            Path(root) / "manifests" / "val.csv",
            root,
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        return False, f"current canonical provenance is invalid: {error}"
    if current["missing_source_files"]:
        return False, "canonical source files are missing"
    if current["person_crop"]["rows_with_boxes"] != current["person_crop"]["rows_total"]:
        return False, "canonical manifests lack per-frame person boxes"
    if stored != current:
        return False, "checkpoint training provenance does not match current canonical audit"
    return True, "accepted canonical validation and matching training provenance"


def smoke_promotion_eligibility(
    smoke_path: Path,
    checkpoint: Path,
) -> tuple[bool, str]:
    try:
        smoke = json.loads(Path(smoke_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, "promotion requires a real end-to-end app smoke report"
    jobs = smoke.get("jobs")
    if (
        smoke.get("schema_version") != 2
        or smoke.get("accepted") is not True
        or smoke.get("checkpoint_sha256") != digest(Path(checkpoint))
        or not isinstance(jobs, list)
        or len(jobs) != 3
    ):
        return False, "app smoke report does not match this checkpoint"
    if {job.get("label") for job in jobs if isinstance(job, dict)} != set(
        LABELS.values()
    ):
        return False, "app smoke must contain exactly one canonical sample per class"
    identities: set[str] = set()
    source_digests: set[str] = set()
    for job in jobs:
        if not isinstance(job, dict):
            return False, "app smoke job has invalid structure"
        identity = job.get("sample_identity")
        source_sha256 = job.get("source_sha256")
        annotated_sha256 = job.get("annotated_sha256")
        if (
            not isinstance(identity, str)
            or not identity
            or not isinstance(source_sha256, str)
            or len(source_sha256) != 64
            or not isinstance(annotated_sha256, str)
            or len(annotated_sha256) != 64
            or job.get("status") != "completed"
            or job.get("mode") != "hybrid"
            or not str(job.get("device", "")).startswith("cuda")
            or not isinstance(job.get("classifier_predictions"), int)
            or job["classifier_predictions"] <= 0
            or not isinstance(job.get("tracks"), int)
            or job["tracks"] <= 0
            or job.get("annotated_playable") is not True
        ):
            return False, "app smoke job lacks required hybrid CUDA evidence"
        identities.add(identity)
        source_digests.add(source_sha256)
    if len(identities) != 3 or len(source_digests) != 3:
        return False, "app smoke sample identities and digests must be unique"
    return True, "matching end-to-end app smoke"
