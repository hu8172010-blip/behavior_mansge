"""Single source of truth for the approved three-class training baseline."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Iterable, Mapping

from .config import LABELS

CANONICAL_SEED = 42
CANONICAL_PER_CLASS = 30
CANONICAL_SPLIT_COUNTS = {"train": 63, "val": 13, "test": 14}
CANONICAL_CLASS_COUNTS = {
    "train": {"normal": 21, "violence": 21, "fall": 21},
    "val": {"normal": 5, "violence": 4, "fall": 4},
    "test": {"normal": 4, "violence": 5, "fall": 5},
}
_IDENTITY_FIELDS = ("path", "label", "source", "group_id", "subject_id")


def _stable_digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def _relative_members() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(1, CANONICAL_PER_CLASS + 1):
        group = f"NV_{index}"
        rows.append(
            {
                "relative_path": f"rlvs/Real Life Violence Dataset/NonViolence/{group}.mp4",
                "label": LABELS["normal"],
                "source": "rlvs",
                "group_id": group,
                "subject_id": group,
            }
        )
    for index in range(1, CANONICAL_PER_CLASS + 1):
        group = f"V_{index}"
        rows.append(
            {
                "relative_path": f"rlvs/Real Life Violence Dataset/Violence/{group}.mp4",
                "label": LABELS["violence"],
                "source": "rlvs",
                "group_id": group,
                "subject_id": group,
            }
        )
    for index in range(1, CANONICAL_PER_CLASS + 1):
        group = f"fall-{index:02d}"
        rows.append(
            {
                "relative_path": f"urfall/fall/{group}-cam0.mp4",
                "label": LABELS["fall"],
                "source": "urfall",
                "group_id": group,
                "subject_id": group,
            }
        )
    return rows


def canonical_spec_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "seed": CANONICAL_SEED,
        "per_class": CANONICAL_PER_CLASS,
        "labels": dict(LABELS),
        "split_counts": CANONICAL_SPLIT_COUNTS,
        "class_counts": CANONICAL_CLASS_COUNTS,
        "members": _relative_members(),
    }


def canonical_spec_digest() -> str:
    return _stable_digest(canonical_spec_payload())


def canonical_selection(root: Path) -> list[dict[str, object]]:
    root = Path(root).resolve()
    return [
        {
            "path": (root / str(item["relative_path"])).resolve().as_posix(),
            **{field: item[field] for field in _IDENTITY_FIELDS if field != "path"},
        }
        for item in _relative_members()
    ]


def normalize_selection(
    records: Iterable[Mapping[str, object]],
) -> list[dict[str, object]]:
    normalized = [
        {
            "path": Path(str(record["path"])).resolve().as_posix(),
            "label": int(record["label"]),
            "source": str(record["source"]),
            "group_id": str(record["group_id"]),
            "subject_id": str(record["subject_id"]),
        }
        for record in records
    ]
    return sorted(normalized, key=lambda row: tuple(str(row[field]) for field in _IDENTITY_FIELDS))


def selection_digest(records: Iterable[Mapping[str, object]]) -> str:
    return _stable_digest(normalize_selection(records))


def validate_canonical_selection(
    root: Path,
    records: Iterable[Mapping[str, object]],
) -> list[dict[str, object]]:
    normalized = normalize_selection(records)
    expected = normalize_selection(canonical_selection(root))
    if normalized != expected:
        raise ValueError("selection does not match the exact canonical 90-member specification")
    return normalized


def canonical_split_rows(root: Path) -> dict[str, list[dict[str, object]]]:
    from .manifest import RawVideo, build_splits

    records = canonical_selection(root)
    videos = [
        RawVideo(
            path=str(record["path"]),
            label=int(record["label"]),
            source=str(record["source"]),
            group_id=str(record["group_id"]),
            subject_id=str(record["subject_id"]),
        )
        for record in records
    ]
    splits = build_splits(videos, seed=CANONICAL_SEED)
    return {
        split: normalize_selection(
            {
                "path": row.path,
                "label": row.label,
                "source": row.source,
                "group_id": row.group_id,
                "subject_id": row.subject_id,
            }
            for row in rows
        )
        for split, rows in splits.items()
    }
