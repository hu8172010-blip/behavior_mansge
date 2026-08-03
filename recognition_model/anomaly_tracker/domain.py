from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


Box = tuple[float, float, float, float]
Keypoint = tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class TrackObservation:
    track_id: int
    timestamp: float
    bbox: Box
    confidence: float
    keypoints: Sequence[Keypoint] = field(default_factory=tuple)

    @property
    def width(self) -> float:
        return max(0.0, self.bbox[2] - self.bbox[0])

    @property
    def height(self) -> float:
        return max(0.0, self.bbox[3] - self.bbox[1])

    @property
    def foot_point(self) -> tuple[float, float]:
        return ((self.bbox[0] + self.bbox[2]) / 2.0, self.bbox[3])


@dataclass(frozen=True, slots=True)
class TrajectoryPoint:
    timestamp: float
    x: float
    y: float
    bbox: Box
    confidence: float
    keypoints: Sequence[Keypoint] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class AnomalyEvent:
    event_type: str
    track_ids: tuple[int, ...]
    start_time: float
    end_time: float
    confidence: float
    evidence: dict[str, object]
    requires_review: bool = True

    @property
    def duration_seconds(self) -> float:
        return max(0.0, self.end_time - self.start_time)

    def to_dict(self) -> dict[str, object]:
        return {
            "event_type": self.event_type,
            "track_ids": list(self.track_ids),
            "start_time": round(self.start_time, 3),
            "end_time": round(self.end_time, 3),
            "duration_seconds": round(self.duration_seconds, 3),
            "confidence": round(self.confidence, 4),
            "evidence": self.evidence,
            "requires_review": self.requires_review,
        }
