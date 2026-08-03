"""Fixed-length, reproducible OpenCV clips for three-class training manifests."""

from __future__ import annotations

import csv
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import numpy as np
import torch
from torch.utils.data import Dataset, get_worker_info


# torchvision's Kinetics-400 VideoClassification preset statistics.
KINETICS400_MEAN = (0.45, 0.45, 0.45)
KINETICS400_STD = (0.225, 0.225, 0.225)
VALID_LABELS = frozenset((0, 1, 2))


class VideoDecodeError(RuntimeError):
    """The requested interval did not yield a decodable video frame."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        super().__init__(f"could not decode any frames from: {self.path}")


@dataclass(frozen=True, slots=True)
class ManifestRow:
    path: Path
    start_seconds: float
    end_seconds: float
    label: int
    source: str
    group_id: str
    boxes: Sequence[Sequence[float] | None] | None = None

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "ManifestRow":
        required = ("path", "start_seconds", "end_seconds", "label", "source", "group_id")
        def missing_value(value: Any) -> bool:
            return value is None or (isinstance(value, str) and value.strip().casefold() in {"", "null", "none"})

        missing = [name for name in required if name not in row or missing_value(row[name])]
        if missing:
            raise ValueError(f"manifest row is missing required fields: {', '.join(missing)}")
        try:
            start, end, label = float(row["start_seconds"]), float(row["end_seconds"]), int(row["label"])
        except (TypeError, ValueError) as error:
            raise ValueError("manifest row has invalid start_seconds, end_seconds, or label") from error
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end < start:
            raise ValueError("manifest interval must satisfy 0 <= start_seconds <= end_seconds")
        if label not in VALID_LABELS:
            raise ValueError(f"manifest label must be one of 0, 1, 2; got {label!r}")
        boxes = row.get("boxes")
        if isinstance(boxes, str):
            try:
                boxes = json.loads(boxes) if boxes.strip() else None
            except json.JSONDecodeError as error:
                raise ValueError("manifest boxes must be valid JSON") from error
        if boxes is not None and not isinstance(boxes, list):
            raise ValueError("manifest boxes must be a JSON list")
        return cls(
            Path(str(row["path"])),
            start,
            end,
            label,
            str(row["source"]),
            str(row["group_id"]),
            boxes,
        )


def select_temporal_indices(start_index: int, end_index: int, frame_count: int = 16) -> list[int]:
    """Select evenly spaced, inclusive source indexes; pad a short interval at its end."""
    if frame_count <= 0:
        raise ValueError("frame_count must be positive")
    if end_index < start_index:
        return []
    available = end_index - start_index + 1
    if available < frame_count:
        return list(range(start_index, end_index + 1)) + [end_index] * (frame_count - available)
    return [start_index + round(position * (available - 1) / (frame_count - 1)) for position in range(frame_count)] if frame_count > 1 else [start_index]


def _requested_bounds(path: str | Path, start_seconds: float | None, end_seconds: float | None) -> tuple[int, int | None]:
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise VideoDecodeError(path)
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        if not math.isfinite(fps) or fps <= 0:
            raise VideoDecodeError(path)
        first = max(0, math.ceil((start_seconds or 0.0) * fps - 1e-9))
        last = math.floor(end_seconds * fps + 1e-9) if end_seconds is not None else None
        if last is not None and last < first:
            raise VideoDecodeError(path)
        return first, last
    finally:
        capture.release()


def _count_requested_frames(path: str | Path, first: int, last: int | None) -> int:
    """First decode pass: count valid interval frames without retaining images."""
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise VideoDecodeError(path)
        count, index = 0, 0
        while True:
            ok, _ = capture.read()
            if not ok:
                break
            if index >= first and (last is None or index <= last):
                count += 1
            if last is not None and index >= last:
                break
            index += 1
        if not count:
            raise VideoDecodeError(path)
        return count
    finally:
        capture.release()


def _decode_sampled_frames(path: str | Path, first: int, last: int | None, target_ordinals: Sequence[int]) -> tuple[list[np.ndarray], list[int]]:
    """Second decode pass retaining only requested frames (at most 16)."""
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise VideoDecodeError(path)
        # Sequential decoding deliberately avoids CAP_PROP_POS_FRAMES seeking
        # inaccuracies seen with variable-frame-count streams.
        frames: list[np.ndarray] = []
        source_indexes: list[int] = []
        index, ordinal, target_position = 0, 0, 0
        latest_frame: np.ndarray | None = None
        latest_source_index: int | None = None
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if index >= first and (last is None or index <= last):
                # Keep one terminal frame even when it is not a sampling target.
                # This is the only extra retained image beyond the 16 targets.
                latest_frame, latest_source_index = frame, index
                while target_position < len(target_ordinals) and target_ordinals[target_position] == ordinal:
                    frames.append(frame)
                    source_indexes.append(index)
                    target_position += 1
                ordinal += 1
            if last is not None and index >= last:
                break
            index += 1
        if not frames:
            raise VideoDecodeError(path)
        # A stream which ends differently on pass two stays inside its interval:
        # missing targets are explicitly padded by the last second-pass frame.
        while len(frames) < len(target_ordinals):
            frames.append(latest_frame if latest_frame is not None else frames[-1])
            source_indexes.append(latest_source_index if latest_source_index is not None else source_indexes[-1])
        return frames, source_indexes
    finally:
        capture.release()


def _valid_box(value: Sequence[float] | None, width: int, height: int) -> tuple[int, int, int, int] | None:
    if value is None or len(value) != 4:
        return None
    try:
        left, top, right, bottom = (float(item) for item in value)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(item) for item in (left, top, right, bottom)):
        return None
    # Accept the documented x1/y1/x2/y2 representation only.
    if right <= left or bottom <= top:
        return None
    expand_x, expand_y = (right - left) * 0.25, (bottom - top) * 0.25
    left, top = max(0, math.floor(left - expand_x)), max(0, math.floor(top - expand_y))
    right, bottom = min(width, math.ceil(right + expand_x)), min(height, math.ceil(bottom + expand_y))
    return (left, top, right, bottom) if right > left and bottom > top else None


def _person_boxes(
    boxes: Sequence[Sequence[float] | None] | None,
    source_indexes: Sequence[int],
    width: int,
    height: int,
) -> tuple[list[tuple[int, int, int, int] | None], str]:
    selected = [
        (
            _valid_box(boxes[index], width, height)
            if boxes is not None and index < len(boxes)
            else None
        )
        for index in source_indexes
    ]
    found = sum(box is not None for box in selected)
    if found * 2 < len(source_indexes):
        return [None] * len(source_indexes), "full_frame_fallback"
    return selected, "person_per_frame"


def _letterbox_person(
    frame: np.ndarray,
    box: tuple[int, int, int, int],
    size: int = 128,
) -> np.ndarray:
    left, top, right, bottom = box
    crop = frame[top:bottom, left:right]
    height, width = crop.shape[:2]
    scale = min(size / width, size / height)
    resized_width = max(1, min(size, round(width * scale)))
    resized_height = max(1, min(size, round(height * scale)))
    resized = cv2.resize(
        crop,
        (resized_width, resized_height),
        interpolation=cv2.INTER_LINEAR,
    )
    output = np.zeros((size, size, 3), dtype=np.uint8)
    offset_y = (size - resized_height) // 2
    offset_x = (size - resized_width) // 2
    output[
        offset_y : offset_y + resized_height,
        offset_x : offset_x + resized_width,
    ] = resized
    return output


def _resize_crop(frame: np.ndarray, size: int, training: bool, rng: random.Random) -> np.ndarray:
    height, width = frame.shape[:2]
    scale = 128 / min(height, width)
    resized = cv2.resize(frame, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_LINEAR)
    resized_height, resized_width = resized.shape[:2]
    max_y, max_x = resized_height - size, resized_width - size
    if training:
        top, left = rng.randint(0, max_y), rng.randint(0, max_x)
        flip = rng.random() < 0.5
    else:
        top, left, flip = max_y // 2, max_x // 2, False
    cropped = resized[top : top + size, left : left + size]
    return np.ascontiguousarray(cropped[:, ::-1] if flip else cropped)


def decode_clip(
    path: str | Path,
    *,
    start_seconds: float | None = None,
    end_seconds: float | None = None,
    frame_count: int = 16,
    size: int = 112,
    training: bool = False,
    seed: int | None = None,
    boxes: Sequence[Sequence[float] | None] | None = None,
    return_metadata: bool = False,
) -> torch.Tensor | tuple[torch.Tensor, dict[str, Any]]:
    """Decode one interval into exactly ``(3, frame_count, size, size)`` floats.

    If a stream ends during an interval, only successfully decoded interval frames
    are sampled and its last one is repeated. No frames before/after the interval
    are substituted.
    """
    if frame_count <= 0 or size <= 0:
        raise ValueError("frame_count and size must be positive")
    first, last = _requested_bounds(path, start_seconds, end_seconds)
    available = _count_requested_frames(path, first, last)
    positions = select_temporal_indices(0, available - 1, frame_count)
    selected, selected_indexes = _decode_sampled_frames(path, first, last, positions)
    height, width = selected[0].shape[:2]
    crop_boxes, crop_mode = _person_boxes(
        boxes,
        selected_indexes,
        width,
        height,
    )
    fallback_frames = sum(box is None for box in crop_boxes)
    if crop_mode == "person_per_frame":
        selected = [
            _letterbox_person(frame, box)
            if box is not None
            else frame
            for frame, box in zip(selected, crop_boxes)
        ]
    rng = random.Random(seed) if seed is not None else random.Random()
    processed = [_resize_crop(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), size, training, rng) for frame in selected]
    array = np.stack(processed, axis=0).astype(np.float32) / 255.0
    tensor = torch.from_numpy(array).permute(3, 0, 1, 2)
    mean = torch.tensor(KINETICS400_MEAN, dtype=tensor.dtype).view(3, 1, 1, 1)
    std = torch.tensor(KINETICS400_STD, dtype=tensor.dtype).view(3, 1, 1, 1)
    tensor = (tensor - mean) / std
    metadata = {
        "crop_mode": crop_mode,
        "crop_box": None,
        "crop_boxes": crop_boxes,
        "fallback_frames": fallback_frames,
        "fallback_frequency": fallback_frames / len(selected_indexes),
        "source_indices": selected_indexes,
    }
    return (tensor, metadata) if return_metadata else tensor


class VideoClipDataset(Dataset[tuple[torch.Tensor, int]]):
    """Manifest-backed dataset; :meth:`metadata_for` decodes on demand in its caller."""

    def __init__(self, rows: Sequence[ManifestRow | Mapping[str, Any]] | str | Path, *, split: str = "train", seed: int = 0):
        if split not in {"train", "val", "test"}:
            raise ValueError("split must be train, val, or test")
        if isinstance(rows, (str, Path)):
            with Path(rows).open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
        self.rows = [row if isinstance(row, ManifestRow) else ManifestRow.from_mapping(row) for row in rows]
        self.split, self.seed, self.epoch = split, seed, 0

    def __len__(self) -> int:
        return len(self.rows)

    def set_epoch(self, epoch: int) -> None:
        self.epoch = epoch

    def _seed_for(self, index: int) -> int:
        worker = get_worker_info()
        worker_seed = worker.seed if worker is not None else self.seed
        return int(worker_seed + self.epoch * 1_000_003 + index)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, int]:
        row = self.rows[index]
        clip = decode_clip(row.path, start_seconds=row.start_seconds, end_seconds=row.end_seconds, training=self.split == "train", seed=self._seed_for(index), boxes=row.boxes)
        return clip, row.label

    def metadata_for(self, index: int) -> dict[str, Any]:
        """Decode and return crop metadata in this process (an extra decode pass)."""
        row = self.rows[index]
        _, metadata = decode_clip(row.path, start_seconds=row.start_seconds, end_seconds=row.end_seconds, boxes=row.boxes, return_metadata=True)
        return metadata


def seeded_worker_init_fn(worker_id: int) -> None:
    """Seed Python and NumPy augmentation sources from PyTorch's worker seed."""
    seed = torch.initial_seed() % (2**32)
    random.seed(seed)
    np.random.seed(seed)
