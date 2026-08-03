from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from math import hypot

from .domain import TrackObservation, TrajectoryPoint


@dataclass(slots=True)
class TrackState:
    track_id: int
    points: deque[TrajectoryPoint] = field(default_factory=deque)

    @property
    def first_seen(self) -> float:
        return self.points[0].timestamp

    @property
    def last_seen(self) -> float:
        return self.points[-1].timestamp

    @property
    def duration(self) -> float:
        if len(self.points) < 2:
            return 0.0
        return self.last_seen - self.first_seen

    @property
    def path_length(self) -> float:
        return sum(
            hypot(current.x - previous.x, current.y - previous.y)
            for previous, current in zip(self.points, list(self.points)[1:])
        )

    @property
    def net_displacement(self) -> float:
        if len(self.points) < 2:
            return 0.0
        return hypot(
            self.points[-1].x - self.points[0].x,
            self.points[-1].y - self.points[0].y,
        )

    @property
    def current_speed(self) -> float:
        if len(self.points) < 2:
            return 0.0
        previous, current = self.points[-2], self.points[-1]
        elapsed = current.timestamp - previous.timestamp
        if elapsed <= 0:
            return 0.0
        return hypot(current.x - previous.x, current.y - previous.y) / elapsed

    @property
    def latest(self) -> TrajectoryPoint:
        return self.points[-1]


class TrajectoryStore:
    def __init__(
        self,
        retention_seconds: float = 120.0,
        stale_after_seconds: float = 4.0,
    ) -> None:
        self.retention_seconds = retention_seconds
        self.stale_after_seconds = stale_after_seconds
        self._states: dict[int, TrackState] = {}

    def update(self, observation: TrackObservation) -> TrackState:
        state = self._states.setdefault(
            observation.track_id,
            TrackState(track_id=observation.track_id),
        )
        foot_x, foot_y = observation.foot_point
        point = TrajectoryPoint(
            timestamp=observation.timestamp,
            x=foot_x,
            y=foot_y,
            bbox=observation.bbox,
            confidence=observation.confidence,
            keypoints=observation.keypoints,
        )

        if not state.points or observation.timestamp >= state.points[-1].timestamp:
            state.points.append(point)
        else:
            ordered = sorted((*state.points, point), key=lambda item: item.timestamp)
            state.points = deque(ordered)

        cutoff = observation.timestamp - self.retention_seconds
        while state.points and state.points[0].timestamp < cutoff:
            state.points.popleft()
        return state

    def get(self, track_id: int) -> TrackState | None:
        return self._states.get(track_id)

    def discard(self, track_id: int) -> None:
        """Remove one track so a recycled numeric ID starts a fresh path."""
        self._states.pop(track_id, None)

    def active_states(self, timestamp: float) -> list[TrackState]:
        return [
            state
            for state in self._states.values()
            if state.points
            and timestamp - state.last_seen <= self.stale_after_seconds
        ]

    def all_states(self) -> list[TrackState]:
        return list(self._states.values())
