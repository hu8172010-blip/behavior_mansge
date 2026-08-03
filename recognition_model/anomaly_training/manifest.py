"""Leakage-safe manifests for the first-round three-class video data.

This module only reads local data.  Dataset acquisition remains the responsibility
of :mod:`anomaly_training.downloads` and is deliberately not triggered here.
"""

from __future__ import annotations

import csv
import io
import json
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from anomaly_training.config import LABELS
from anomaly_training.storage import atomic_text_write, digest


VIDEO_EXTENSIONS = {".avi", ".mp4", ".mov", ".mkv", ".mpeg", ".mpg", ".m4v"}
SPLIT_NAMES = ("train", "val", "test")


@dataclass(frozen=True, slots=True)
class RawVideo:
    path: str | Path
    label: int
    source: str
    group_id: str
    subject_id: str


@dataclass(frozen=True, slots=True)
class VideoMetadata:
    frame_count: int
    fps: float
    width: int
    height: int
    duration: float


@dataclass(frozen=True, slots=True)
class PersonBoxTrace:
    boxes: tuple[tuple[float, float, float, float] | None, ...]
    detector: str

    @property
    def fallback_frames(self) -> int:
        return sum(box is None for box in self.boxes)


def extract_person_boxes(
    path: str | Path,
    *,
    model: Any | None = None,
    model_name: str = "yolo26n-pose.pt",
) -> PersonBoxTrace:
    """Detect one primary person box for every decoded frame."""
    if model is None:
        from ultralytics import YOLO

        model = YOLO(model_name)
    import cv2

    capture = cv2.VideoCapture(str(path))
    boxes: list[tuple[float, float, float, float] | None] = []
    try:
        if not capture.isOpened():
            raise VideoValidationError(f"undecodable video: {path}")
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            results = model.predict(
                frame,
                classes=[0],
                verbose=False,
            )
            candidates: list[tuple[float, tuple[float, float, float, float]]] = []
            if results and results[0].boxes is not None:
                xyxy = results[0].boxes.xyxy.cpu().tolist()
                confidence = results[0].boxes.conf.cpu().tolist()
                for raw_box, score in zip(xyxy, confidence):
                    left, top, right, bottom = (float(value) for value in raw_box)
                    area = max(0.0, right - left) * max(0.0, bottom - top)
                    candidates.append(
                        (
                            float(score) * area,
                            (left, top, right, bottom),
                        )
                    )
            boxes.append(max(candidates, default=(0.0, None), key=lambda item: item[0])[1])
    finally:
        capture.release()
    if not boxes:
        raise VideoValidationError(f"undecodable video: {path}")
    return PersonBoxTrace(tuple(boxes), model_name)


class VideoValidationError(ValueError):
    """Raised when OpenCV cannot decode a usable local video."""


def _path_key(video: RawVideo) -> str:
    return str(Path(video.path)).replace("\\", "/")


def _sort_key(video: RawVideo) -> tuple[str, str, str, str, int]:
    return (_path_key(video), video.source, str(video.group_id), str(video.subject_id), video.label)


def _validate_raw_videos(videos: list[RawVideo]) -> None:
    known_labels = set(LABELS.values())
    duplicate_paths: dict[str, RawVideo] = {}
    group_labels: dict[tuple[str, str], int] = {}
    for video in videos:
        if video.label not in known_labels:
            raise ValueError(f"unknown label {video.label!r} for {_path_key(video)}")
        if video.source == "avenue_calibration":
            raise ValueError("Avenue calibration videos cannot enter a three-class training split")
        if not video.group_id or not video.subject_id:
            raise ValueError(f"group_id and subject_id are required for {_path_key(video)}")
        old = duplicate_paths.setdefault(_path_key(video), video)
        if old != video:
            raise ValueError(f"conflicting metadata for duplicate path {_path_key(video)}")
        group_key = (video.source, str(video.group_id))
        old_label = group_labels.setdefault(group_key, video.label)
        if old_label != video.label:
            raise ValueError(f"conflicting labels in source/group {group_key}: {old_label} and {video.label}")


class _DisjointSet:
    def __init__(self, size: int):
        self.parent = list(range(size))

    def find(self, value: int) -> int:
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, left: int, right: int) -> None:
        left, right = self.find(left), self.find(right)
        if left != right:
            self.parent[right] = left


def _leakage_groups(videos: list[RawVideo]) -> list[str]:
    """Join samples sharing identity metadata or exact current file content."""
    groups = _DisjointSet(len(videos))
    seen: dict[tuple[str, str, str], int] = {}
    content_seen: dict[str, int] = {}
    content_labels: dict[str, int] = {}
    for index, video in enumerate(videos):
        # Prefixes prevent a value used as both a group and a subject from joining
        # unrelated rows.  Source is part of each key so source-specific IDs cannot
        # collide accidentally.
        for kind, value in (("group", str(video.group_id)), ("subject", str(video.subject_id))):
            key = (video.source, kind, value)
            if key in seen:
                groups.union(index, seen[key])
            else:
                seen[key] = index
        path = Path(video.path)
        if path.is_file():
            content_sha256 = digest(path)
            old_label = content_labels.setdefault(content_sha256, video.label)
            if old_label != video.label:
                raise ValueError(
                    "identical content has conflicting labels: "
                    f"{content_sha256}"
                )
            if content_sha256 in content_seen:
                groups.union(index, content_seen[content_sha256])
            else:
                content_seen[content_sha256] = index
    return [str(groups.find(index)) for index in range(len(videos))]


def _component_assignment(videos: list[RawVideo], group_ids: list[str], seed: int) -> dict[str, str]:
    """Incrementally optimize direct 70/15/15 grouped allocation.

    Candidate placement updates only the affected split score; coverage repair
    similarly updates two split counters. This keeps allocation linear in the
    number of components per restart rather than rebuilding every aggregate.
    """
    components: dict[str, list[RawVideo]] = {}
    for video, component in zip(videos, group_ids):
        components.setdefault(component, []).append(video)
    component_counts = {
        component: [sum(row.label == label for row in rows) for label in LABELS.values()]
        for component, rows in components.items()
    }
    labels = tuple(LABELS.values())
    total_count = len(videos)
    total_by_label = [sum(row.label == label for row in videos) for label in labels]
    targets = {"train": 0.70, "val": 0.15, "test": 0.15}

    def score_split(split: str, size: int, classes: list[int]) -> float:
        ratio = targets[split]
        score = ((size - total_count * ratio) / max(1, total_count * ratio)) ** 2
        return score + sum(((classes[i] - total_by_label[i] * ratio) / max(1, total_by_label[i] * ratio)) ** 2 for i in range(len(labels)))

    def missing_count(classes: dict[str, list[int]]) -> int:
        return sum(value == 0 for split in SPLIT_NAMES for value in classes[split])

    best: dict[str, str] | None = None
    best_score = float("inf")
    for attempt in range(32):
        rng = random.Random(f"{seed}:{attempt}")
        order = list(components)
        ties = {component: rng.random() for component in order}
        order.sort(key=lambda component: (-len(components[component]), -sum(value > 0 for value in component_counts[component]), ties[component]))
        assigned: dict[str, str] = {}
        sizes = {split: 0 for split in SPLIT_NAMES}
        classes = {split: [0] * len(labels) for split in SPLIT_NAMES}
        split_scores = {split: score_split(split, 0, classes[split]) for split in SPLIT_NAMES}
        current_score = sum(split_scores.values())
        for component in order:
            vector = component_counts[component]
            amount = len(components[component])
            choices = []
            for split in SPLIT_NAMES:
                new_classes = [classes[split][i] + vector[i] for i in range(len(labels))]
                new_split_score = score_split(split, sizes[split] + amount, new_classes)
                choices.append((current_score - split_scores[split] + new_split_score, rng.random(), split, new_classes, new_split_score))
            _, _, split, new_classes, new_split_score = min(choices)
            assigned[component] = split
            sizes[split] += amount
            classes[split] = new_classes
            current_score += new_split_score - split_scores[split]
            split_scores[split] = new_split_score
        # Bounded repair: there are only nine split/class coverage cells. Each
        # accepted move strictly lowers missing cells, so this loop is finite.
        while missing_count(classes):
            before = missing_count(classes)
            moves = []
            for component, source in assigned.items():
                vector = component_counts[component]
                amount = len(components[component])
                for destination in SPLIT_NAMES:
                    if source == destination:
                        continue
                    source_classes = [classes[source][i] - vector[i] for i in range(len(labels))]
                    destination_classes = [classes[destination][i] + vector[i] for i in range(len(labels))]
                    candidate_classes = {**classes, source: source_classes, destination: destination_classes}
                    if missing_count(candidate_classes) >= before:
                        continue
                    source_score = score_split(source, sizes[source] - amount, source_classes)
                    destination_score = score_split(destination, sizes[destination] + amount, destination_classes)
                    moves.append((current_score - split_scores[source] - split_scores[destination] + source_score + destination_score, rng.random(), component, source, destination, source_classes, destination_classes, source_score, destination_score))
            if not moves:
                break
            _, _, component, source, destination, source_classes, destination_classes, source_score, destination_score = min(moves)
            amount = len(components[component])
            assigned[component] = destination
            sizes[source] -= amount
            sizes[destination] += amount
            classes[source], classes[destination] = source_classes, destination_classes
            current_score += source_score + destination_score - split_scores[source] - split_scores[destination]
            split_scores[source], split_scores[destination] = source_score, destination_score
        if missing_count(classes) == 0 and current_score < best_score:
            best, best_score = assigned, current_score
    if best is None:
        raise ValueError("grouped class coverage is impossible across train/val/test")
    # Validate incrementally-derived assignments against the documented
    # indivisible-component tolerance.
    max_size = max(len(rows) for rows in components.values())
    small_data_allowance = total_count * 0.35 if total_count <= 12 else 0
    for split in SPLIT_NAMES:
        actual_size = sum(len(components[item]) for item, value in best.items() if value == split)
        if abs(actual_size - total_count * targets[split]) > max_size + total_count * 0.05 + small_data_allowance:
            raise ValueError("grouped split cannot meet the 70/15/15 sample tolerance")
        for index, label in enumerate(labels):
            actual = sum(component_counts[item][index] for item, value in best.items() if value == split)
            granularity = max(vector[index] for vector in component_counts.values())
            if abs(actual - total_by_label[index] * targets[split]) > granularity + total_by_label[index] * 0.05 + small_data_allowance:
                raise ValueError(f"grouped split cannot meet the 70/15/15 class tolerance for label {label}")
    return best


def build_splits(videos: Iterable[RawVideo], seed: int = 42) -> dict[str, list[RawVideo]]:
    """Return deterministic direct 70/15/15, leakage-safe three-class splits.

    Original-video groups and subjects are indivisible components. Every configured
    class must have three independent components so train, validation, and test
    all retain class coverage; otherwise this function fails instead of leaking or
    silently producing an unstratified split.
    """
    ordered = sorted(list(videos), key=_sort_key)
    _validate_raw_videos(ordered)
    if not ordered:
        return {name: [] for name in SPLIT_NAMES}
    group_ids = _leakage_groups(ordered)
    present_labels = {video.label for video in ordered}
    missing_labels = sorted(set(LABELS.values()) - present_labels)
    if missing_labels:
        raise ValueError(f"missing configured labels for three-class stratification: {missing_labels}")
    for label in LABELS.values():
        distinct = {group for video, group in zip(ordered, group_ids) if video.label == label}
        if len(distinct) < 3:
            raise ValueError(f"label {label} needs at least three groups for three-way stratification")
    membership_by_group = _component_assignment(ordered, group_ids, seed)
    splits = {name: [] for name in SPLIT_NAMES}
    for index, video in enumerate(ordered):
        splits[membership_by_group[group_ids[index]]].append(video)
    _assert_no_leakage(splits)
    if any({row.label for row in rows} != set(LABELS.values()) for rows in splits.values()):
        raise AssertionError("post-split class coverage check failed")
    return splits


def _assert_no_leakage(splits: dict[str, list[RawVideo]]) -> None:
    locations: dict[tuple[str, str, str], str] = {}
    for split, rows in splits.items():
        for video in rows:
            for kind, value in (("group", str(video.group_id)), ("subject", str(video.subject_id))):
                key = (video.source, kind, value)
                previous = locations.setdefault(key, split)
                if previous != split:
                    raise AssertionError(f"leakage detected for {key}: {previous} and {split}")


def validate_video(path: str | Path) -> VideoMetadata:
    """Decode *path* with OpenCV and return the usable stream metadata."""
    try:
        import cv2
    except ImportError as error:  # pragma: no cover - depends on optional runtime
        raise VideoValidationError("OpenCV (cv2) is required for video validation") from error
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise VideoValidationError(f"undecodable video: {path}")
        frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if frames <= 0 or fps <= 0 or width <= 0 or height <= 0:
            raise VideoValidationError(f"invalid video metadata: {path}")
        return VideoMetadata(frames, fps, width, height, frames / fps)
    finally:
        capture.release()


def _video_files(root: str | Path) -> list[Path]:
    base = Path(root)
    if not base.exists():
        return []
    return sorted((path for path in base.rglob("*") if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS), key=lambda path: str(path).lower())


def _ancestor_named(path: Path, choices: set[str]) -> Path | None:
    for parent in path.parents:
        if parent.name.casefold() in choices:
            return parent
    return None


def scan_rlvs(root: str | Path) -> list[RawVideo]:
    """Scan RLVS class folders without assuming one fixed archive layout."""
    labels = {"violence": LABELS["violence"], "nonviolence": LABELS["normal"]}
    result: list[RawVideo] = []
    for path in _video_files(root):
        folder = _ancestor_named(path, set(labels))
        if folder is None:
            continue
        result.append(RawVideo(path, labels[folder.name.casefold()], "rlvs", path.stem, path.stem))
    return sorted(result, key=_sort_key)


def scan_urfall(root: str | Path) -> list[RawVideo]:
    """Scan UR Fall sequence and ADL/non-fall directories."""
    normal_markers = {"adl", "nonfall", "non-fall", "activities"}
    result: list[RawVideo] = []
    for path in _video_files(root):
        names = [parent.name.casefold() for parent in path.parents]
        normal = any(any(marker in name for marker in normal_markers) for name in names)
        fall = any("fall" in name for name in names)
        if not (normal or fall):
            continue
        label = LABELS["normal"] if normal else LABELS["fall"]
        stem_sequence = re.sub(r"[-_]?cam\d+$", "", path.stem, flags=re.IGNORECASE)
        if "fall" in stem_sequence.casefold() or "adl" in stem_sequence.casefold():
            sequence = stem_sequence
        else:
            sequence = next(
                (
                    parent.name
                    for parent in path.parents
                    if "fall" in parent.name.casefold() or "adl" in parent.name.casefold()
                ),
                path.stem,
            )
        result.append(RawVideo(path, label, "urfall", sequence, sequence))
    return sorted(result, key=_sort_key)


def scan_avenue(root: str | Path) -> list[RawVideo]:
    """Return Avenue videos solely for calibration; never pass them to build_splits."""
    return [RawVideo(path, LABELS["normal"], "avenue_calibration", path.stem, path.stem) for path in _video_files(root)]


def scan_deferred_source(root: str | Path, source: str) -> list[RawVideo]:
    """Explicit placeholder scanner for a later expansion; it never downloads data."""
    if source not in {"le2i", "iitb_corridor", "ucf_crime"}:
        raise ValueError(f"unsupported deferred source: {source}")
    return []


def _render_csv(fieldnames: tuple[str, ...], rows: Iterable[dict[str, object]]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def _write_rows(
    path: Path,
    rows: list[RawVideo],
    metadata: dict[str, VideoMetadata],
    *,
    managed_root: Path | None = None,
    box_traces: dict[str, PersonBoxTrace] | None = None,
) -> None:
    fieldnames = ("path", "start_seconds", "end_seconds", "label", "source", "group_id", "subject_id", "frame_count", "fps", "width", "height", "duration", "boxes", "box_detector", "box_fallback_frames", "box_fallback_frequency")
    rendered = (
        {
            "path": _path_key(video),
            "start_seconds": 0.0,
            "end_seconds": metadata[_path_key(video)].duration,
            "label": video.label,
            "source": video.source,
            "group_id": video.group_id,
            "subject_id": video.subject_id,
            "frame_count": metadata[_path_key(video)].frame_count,
            "fps": metadata[_path_key(video)].fps,
            "width": metadata[_path_key(video)].width,
            "height": metadata[_path_key(video)].height,
            "duration": metadata[_path_key(video)].duration,
            "boxes": (
                json.dumps(
                    box_traces[_path_key(video)].boxes,
                    separators=(",", ":"),
                )
                if box_traces and _path_key(video) in box_traces
                else ""
            ),
            "box_detector": (
                box_traces[_path_key(video)].detector
                if box_traces and _path_key(video) in box_traces
                else ""
            ),
            "box_fallback_frames": (
                box_traces[_path_key(video)].fallback_frames
                if box_traces and _path_key(video) in box_traces
                else ""
            ),
            "box_fallback_frequency": (
                box_traces[_path_key(video)].fallback_frames
                / len(box_traces[_path_key(video)].boxes)
                if box_traces and _path_key(video) in box_traces
                else ""
            ),
        }
        for video in sorted(rows, key=_sort_key)
    )
    atomic_text_write(path, _render_csv(fieldnames, rendered), managed_root=managed_root)


def write_manifests(
    videos: Iterable[RawVideo],
    output_dir: str | Path,
    seed: int = 42,
    *,
    managed_root: Path | None = None,
    include_person_boxes: bool = False,
    person_box_extractor: Callable[[str | Path], PersonBoxTrace] | None = None,
) -> dict[str, list[RawVideo]]:
    """Validate local videos, emit bad_videos.csv, and write training split CSVs."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    valid: list[RawVideo] = []
    metadata: dict[str, VideoMetadata] = {}
    bad: list[tuple[RawVideo, str]] = []
    for video in sorted(videos, key=_sort_key):
        try:
            metadata[_path_key(video)] = validate_video(video.path)
            valid.append(video)
        except VideoValidationError as error:
            bad.append((video, str(error)))
    bad_fields = ("path", "label", "source", "group_id", "subject_id", "reason")
    bad_rows = (
        {"path": _path_key(video), "label": video.label, "source": video.source, "group_id": video.group_id, "subject_id": video.subject_id, "reason": reason}
        for video, reason in bad
    )
    atomic_text_write(
        output / "bad_videos.csv",
        _render_csv(bad_fields, bad_rows),
        managed_root=managed_root,
    )
    splits = build_splits(valid, seed=seed)
    traces: dict[str, PersonBoxTrace] | None = None
    if include_person_boxes:
        extractor = person_box_extractor or extract_person_boxes
        traces = {
            _path_key(video): extractor(video.path)
            for video in valid
        }
    for name, rows in splits.items():
        _write_rows(
            output / f"{name}.csv",
            rows,
            metadata,
            managed_root=managed_root,
            box_traces=traces,
        )
    return splits


def write_calibration_manifest(
    videos: Iterable[RawVideo],
    output_dir: str | Path,
    *,
    managed_root: Path | None = None,
) -> list[RawVideo]:
    """Validate Avenue-only videos and write a deterministic calibration manifest.

    Calibration deliberately has no train/validation/test allocation and never
    calls :func:`build_splits`.
    """
    ordered = sorted(list(videos), key=_sort_key)
    if any(video.source != "avenue_calibration" or video.label != LABELS["normal"] for video in ordered):
        raise ValueError("calibration manifest accepts only Avenue normal videos")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    valid: list[RawVideo] = []
    metadata: dict[str, VideoMetadata] = {}
    bad: list[tuple[RawVideo, str]] = []
    for video in ordered:
        try:
            metadata[_path_key(video)] = validate_video(video.path)
            valid.append(video)
        except VideoValidationError as error:
            bad.append((video, str(error)))
    bad_fields = ("path", "label", "source", "group_id", "subject_id", "reason")
    bad_rows = (
        {"path": _path_key(video), "label": video.label, "source": video.source, "group_id": video.group_id, "subject_id": video.subject_id, "reason": reason}
        for video, reason in bad
    )
    atomic_text_write(
        output / "bad_videos.csv",
        _render_csv(bad_fields, bad_rows),
        managed_root=managed_root,
    )
    _write_rows(
        output / "calibration.csv",
        valid,
        metadata,
        managed_root=managed_root,
    )
    return valid
