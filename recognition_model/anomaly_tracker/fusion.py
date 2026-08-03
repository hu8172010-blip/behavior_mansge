"""Per-track fixed clip buffering and conservative temporal event fusion."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from math import isfinite
from typing import Mapping

import numpy as np

from .domain import AnomalyEvent
from .trajectory import TrackState


CLASS_NAMES = ("normal", "violence", "fall")


@dataclass(frozen=True, slots=True)
class ClipWindow:
    frames: tuple[np.ndarray, ...]
    timestamps: tuple[float, ...]


@dataclass(slots=True)
class _BufferState:
    frames: deque[np.ndarray] = field(default_factory=deque)
    timestamps: deque[float] = field(default_factory=deque)
    since_emit: int = 0


class TrackClipBuffer:
    """Bounded clip windows, never shared between IDs or separated appearances."""

    def __init__(
        self,
        *,
        frame_count: int = 16,
        stride: int = 8,
        max_tracks: int = 128,
        stale_after_seconds: float = 4.0,
    ) -> None:
        if frame_count <= 0 or stride <= 0 or max_tracks <= 0 or stale_after_seconds <= 0:
            raise ValueError("buffer limits must be positive")
        self.frame_count = frame_count
        self.stride = stride
        self.max_tracks = max_tracks
        self.stale_after_seconds = stale_after_seconds
        self._tracks: dict[int, _BufferState] = {}

    @property
    def track_ids(self) -> tuple[int, ...]:
        return tuple(self._tracks)

    def _evict_stale(self, timestamp: float) -> None:
        for track_id, state in list(self._tracks.items()):
            if state.timestamps and timestamp - state.timestamps[-1] > self.stale_after_seconds:
                self._tracks.pop(track_id, None)

    def evict_stale(self, timestamp: float) -> None:
        if isfinite(timestamp) and timestamp >= 0:
            self._evict_stale(timestamp)

    def _make_room(self) -> None:
        while len(self._tracks) >= self.max_tracks:
            oldest = min(self._tracks, key=lambda key: self._tracks[key].timestamps[-1])
            self._tracks.pop(oldest, None)

    def discard(self, track_id: int) -> None:
        """Forget every buffered frame for one tracker-ID generation."""
        self._tracks.pop(track_id, None)

    def add(self, track_id: int, timestamp: float, frame: np.ndarray) -> ClipWindow | None:
        if not isfinite(timestamp) or timestamp < 0:
            return None
        array = np.asarray(frame)
        if array.ndim != 3 or array.shape[2] != 3:
            raise ValueError("frame must have shape (height, width, 3)")
        self._evict_stale(timestamp)
        state = self._tracks.get(track_id)
        if state is None:
            self._make_room()
            state = self._tracks.setdefault(track_id, _BufferState())
        elif state.timestamps and timestamp <= state.timestamps[-1]:
            return None
        state.frames.append(np.array(array, copy=True, order="C"))
        state.timestamps.append(float(timestamp))
        while len(state.frames) > self.frame_count:
            state.frames.popleft()
            state.timestamps.popleft()
        state.since_emit += 1
        if len(state.frames) != self.frame_count:
            return None
        if state.since_emit < self.stride and state.since_emit != self.frame_count:
            return None
        state.since_emit = 0
        return ClipWindow(
            tuple(np.array(frame, copy=True, order="C") for frame in state.frames),
            tuple(state.timestamps),
        )


@dataclass(slots=True)
class _FusionState:
    probabilities: dict[str, float]
    last_seen: float
    consecutive: dict[str, int] = field(default_factory=lambda: {"violence": 0, "fall": 0})
    candidate_starts: dict[str, float] = field(default_factory=dict)
    last_emitted: dict[str, float] = field(default_factory=dict)


class TemporalFusion:
    """EMA plus consecutive-window voting, isolated by track and event type."""

    def __init__(
        self,
        *,
        min_windows: int = 3,
        probability_threshold: float = 0.75,
        ema_alpha: float = 0.5,
        cooldown_seconds: float = 8.0,
        stale_after_seconds: float = 30.0,
    ) -> None:
        if min_windows <= 0 or not 0 < probability_threshold <= 1 or not 0 < ema_alpha <= 1:
            raise ValueError("invalid fusion thresholds")
        if cooldown_seconds < 0 or stale_after_seconds <= 0:
            raise ValueError("invalid fusion retention")
        self.min_windows = min_windows
        self.probability_threshold = probability_threshold
        self.ema_alpha = ema_alpha
        self.cooldown_seconds = cooldown_seconds
        self.stale_after_seconds = stale_after_seconds
        self._tracks: dict[int, _FusionState] = {}

    @property
    def track_ids(self) -> tuple[int, ...]:
        return tuple(self._tracks)

    def evict_stale(self, timestamp: float) -> None:
        if not isfinite(timestamp) or timestamp < 0:
            return
        for track_id, state in list(self._tracks.items()):
            if timestamp - state.last_seen > self.stale_after_seconds:
                self._tracks.pop(track_id, None)

    def discard(self, track_id: int) -> None:
        """Forget EMA, voting, and cooldown state for one track generation."""
        self._tracks.pop(track_id, None)

    @staticmethod
    def _checked_probabilities(probabilities: Mapping[str, float]) -> dict[str, float]:
        if set(probabilities) != set(CLASS_NAMES):
            raise ValueError("probabilities must contain normal, violence, and fall")
        checked = {name: float(probabilities[name]) for name in CLASS_NAMES}
        if not all(isfinite(value) and 0 <= value <= 1 for value in checked.values()):
            raise ValueError("probabilities must be finite values between zero and one")
        if abs(sum(checked.values()) - 1.0) > 1e-5:
            raise ValueError("probabilities must sum to one")
        return checked

    @staticmethod
    def _horizontal(trajectory_state: TrackState | None, horizontal_pose: bool | None) -> bool:
        if horizontal_pose is not None:
            return horizontal_pose
        if trajectory_state is None or not trajectory_state.points:
            return False
        x1, y1, x2, y2 = trajectory_state.latest.bbox
        return (x2 - x1) / max(1.0, y2 - y1) >= 1.2

    def update(
        self,
        track_id: int,
        timestamp: float,
        probabilities: Mapping[str, float],
        trajectory_state: TrackState | None = None,
        *,
        horizontal_pose: bool | None = None,
    ) -> list[AnomalyEvent]:
        if not isfinite(timestamp) or timestamp < 0:
            return []
        raw = self._checked_probabilities(probabilities)
        self.evict_stale(timestamp)
        state = self._tracks.get(track_id)
        if state is not None and timestamp <= state.last_seen:
            return []
        if state is None:
            state = _FusionState(raw.copy(), float(timestamp))
            self._tracks[track_id] = state
        else:
            state.probabilities = {
                name: self.ema_alpha * raw[name] + (1.0 - self.ema_alpha) * state.probabilities[name]
                for name in CLASS_NAMES
            }
            state.last_seen = float(timestamp)

        events: list[AnomalyEvent] = []
        for label in ("violence", "fall"):
            smoothed = state.probabilities[label]
            qualifies = smoothed >= self.probability_threshold
            if label == "fall":
                qualifies = qualifies and (self._horizontal(trajectory_state, horizontal_pose) or raw[label] >= 0.90)
            if not qualifies:
                state.consecutive[label] = 0
                state.candidate_starts.pop(label, None)
                continue
            state.consecutive[label] += 1
            state.candidate_starts.setdefault(label, float(timestamp))
            last = state.last_emitted.get(label)
            if state.consecutive[label] < self.min_windows or (last is not None and timestamp - last < self.cooldown_seconds):
                continue
            state.last_emitted[label] = float(timestamp)
            events.append(
                AnomalyEvent(
                    event_type=f"suspected_{label}",
                    track_ids=(track_id,),
                    start_time=state.candidate_starts[label],
                    end_time=float(timestamp),
                    confidence=smoothed,
                    evidence={
                        "raw_probability": round(raw[label], 4),
                        "smoothed_probability": round(smoothed, 4),
                        "consecutive_windows": state.consecutive[label],
                        "warning": "model candidate; requires human review",
                    },
                    requires_review=True,
                )
            )
        return events
