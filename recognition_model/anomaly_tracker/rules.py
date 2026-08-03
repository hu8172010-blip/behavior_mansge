from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, fields
from itertools import combinations
import json
from math import hypot, isfinite
from typing import Mapping

from .domain import AnomalyEvent
from .trajectory import TrackState


@dataclass(frozen=True, slots=True)
class RuleConfig:
    fall_seconds: float = 1.0
    fall_aspect_ratio: float = 1.2
    stationary_seconds: float = 20.0
    stationary_radius_px: float = 20.0
    loitering_seconds: float = 30.0
    loitering_min_path_px: float = 200.0
    loitering_max_displacement_px: float = 80.0
    rapid_speed_px_s: float = 250.0
    rapid_min_seconds: float = 0.5
    interaction_distance_px: float = 140.0
    interaction_speed_px_s: float = 100.0
    interaction_seconds: float = 1.0
    entry_exit_zone: tuple[tuple[float, float], ...] = ()
    repeated_entry_exit_count: int = 4
    repeated_entry_exit_window_seconds: float = 30.0
    expected_route: tuple[tuple[float, float], ...] = ()
    route_deviation_px: float = 80.0
    route_deviation_seconds: float = 2.0
    dangerous_zones: tuple[tuple[tuple[float, float], ...], ...] = ()
    dangerous_zone_margin_px: float = 20.0
    dangerous_zone_seconds: float = 1.0
    cooldown_seconds: float = 8.0


def rule_config_from_mapping(payload: Mapping[str, object]) -> RuleConfig:
    """Validate and normalize an optional per-video calibration profile."""
    allowed = {field.name for field in fields(RuleConfig)}
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"unknown rule calibration fields: {', '.join(unknown)}")
    polygon_fields = {"entry_exit_zone", "expected_route"}
    zones_field = "dangerous_zones"
    normalized = dict(payload)
    for name in polygon_fields:
        if name in normalized:
            normalized[name] = _normalize_points(normalized[name], name)
    if zones_field in normalized:
        value = normalized[zones_field]
        if not isinstance(value, (list, tuple)):
            raise ValueError("dangerous_zones must be a list of polygons")
        normalized[zones_field] = tuple(
            _normalize_points(polygon, zones_field)
            for polygon in value
        )
    config = RuleConfig(**normalized)
    for field in fields(RuleConfig):
        value = getattr(config, field.name)
        if isinstance(value, bool):
            raise ValueError(f"{field.name} must not be boolean")
        if isinstance(value, (int, float)):
            if not isfinite(float(value)) or float(value) < 0:
                raise ValueError(f"{field.name} must be finite and nonnegative")
    return config


def rule_config_dict(config: RuleConfig) -> dict[str, object]:
    return json.loads(json.dumps(asdict(config)))


def _normalize_points(
    value: object,
    field_name: str,
) -> tuple[tuple[float, float], ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be a list of [x, y] points")
    points: list[tuple[float, float]] = []
    for point in value:
        if (
            not isinstance(point, (list, tuple))
            or len(point) != 2
            or isinstance(point[0], bool)
            or isinstance(point[1], bool)
        ):
            raise ValueError(f"{field_name} contains an invalid point")
        x, y = float(point[0]), float(point[1])
        if not isfinite(x) or not isfinite(y):
            raise ValueError(f"{field_name} points must be finite")
        points.append((x, y))
    return tuple(points)


class AnomalyEngine:
    def __init__(self, config: RuleConfig | None = None) -> None:
        self.config = config or RuleConfig()
        self._candidate_starts: dict[tuple[str, tuple[int, ...]], float] = {}
        self._last_emitted: dict[tuple[str, tuple[int, ...]], float] = {}
        self._entry_exit_inside: dict[int, bool] = {}
        self._entry_exit_transitions: dict[int, deque[float]] = {}

    def discard_tracks(self, track_ids: set[int]) -> None:
        """Clear candidates and cooldowns involving recycled tracker IDs."""
        if not track_ids:
            return
        for state in (self._candidate_starts, self._last_emitted):
            for key in list(state):
                if any(track_id in track_ids for track_id in key[1]):
                    state.pop(key, None)
        for track_id in track_ids:
            self._entry_exit_inside.pop(track_id, None)
            self._entry_exit_transitions.pop(track_id, None)

    def evaluate(
        self,
        timestamp: float,
        states: list[TrackState],
    ) -> list[AnomalyEvent]:
        events: list[AnomalyEvent] = []
        for state in states:
            events.extend(self._evaluate_track(timestamp, state))
        events.extend(self._evaluate_interactions(timestamp, states))
        return events

    def _evaluate_track(
        self,
        timestamp: float,
        state: TrackState,
    ) -> list[AnomalyEvent]:
        if not state.points:
            return []
        events: list[AnomalyEvent] = []
        fall_start = self._continuous_fall_start(state)
        if (
            fall_start is not None
            and timestamp - fall_start >= self.config.fall_seconds
        ):
            event = self._emit(
                "suspected_fall",
                (state.track_id,),
                fall_start,
                timestamp,
                0.78,
                {
                    "aspect_ratio": round(self._latest_aspect_ratio(state), 3),
                    "rule": "horizontal posture sustained over time",
                },
            )
            if event:
                events.append(event)

        if (
            state.duration >= self.config.stationary_seconds
            and self._max_radius(state) <= self.config.stationary_radius_px
        ):
            event = self._emit(
                "abnormal_staying",
                (state.track_id,),
                state.first_seen,
                timestamp,
                0.72,
                {
                    "max_radius_px": round(self._max_radius(state), 2),
                    "rule": "small movement radius over dwell threshold",
                },
            )
            if event:
                events.append(event)

        if (
            state.duration >= self.config.loitering_seconds
            and state.path_length >= self.config.loitering_min_path_px
            and state.net_displacement
            <= self.config.loitering_max_displacement_px
        ):
            event = self._emit(
                "long_loitering",
                (state.track_id,),
                state.first_seen,
                timestamp,
                0.76,
                {
                    "path_length_px": round(state.path_length, 2),
                    "net_displacement_px": round(state.net_displacement, 2),
                    "rule": "long path with small net displacement",
                },
            )
            if event:
                events.append(event)

        repeated_entry = self._evaluate_repeated_entry_exit(timestamp, state)
        if repeated_entry is not None:
            events.append(repeated_entry)

        route_deviation = self._evaluate_route_deviation(timestamp, state)
        if route_deviation is not None:
            events.append(route_deviation)

        danger_proximity = self._evaluate_dangerous_zone(timestamp, state)
        if danger_proximity is not None:
            events.append(danger_proximity)

        rapid_key = ("rapid_movement", (state.track_id,))
        if state.current_speed >= self.config.rapid_speed_px_s:
            rapid_start = self._candidate_starts.setdefault(rapid_key, timestamp)
            if timestamp - rapid_start >= self.config.rapid_min_seconds:
                event = self._emit(
                    "rapid_movement",
                    (state.track_id,),
                    rapid_start,
                    timestamp,
                    0.7,
                    {
                        "speed_px_s": round(state.current_speed, 2),
                        "rule": "image-plane speed exceeded threshold",
                    },
                )
                if event:
                    events.append(event)
        else:
            self._candidate_starts.pop(rapid_key, None)
        return events

    def _evaluate_repeated_entry_exit(
        self,
        timestamp: float,
        state: TrackState,
    ) -> AnomalyEvent | None:
        zone = self.config.entry_exit_zone
        if len(zone) < 3 or self.config.repeated_entry_exit_count < 1:
            return None
        inside = _point_in_polygon((state.latest.x, state.latest.y), zone)
        previous = self._entry_exit_inside.setdefault(state.track_id, inside)
        self._entry_exit_inside[state.track_id] = inside
        transitions = self._entry_exit_transitions.setdefault(
            state.track_id,
            deque(),
        )
        cutoff = timestamp - self.config.repeated_entry_exit_window_seconds
        while transitions and transitions[0] < cutoff:
            transitions.popleft()
        if inside == previous:
            return None
        transitions.append(timestamp)
        if len(transitions) < self.config.repeated_entry_exit_count:
            return None
        return self._emit(
            "repeated_entry_exit",
            (state.track_id,),
            transitions[0],
            timestamp,
            0.72,
            {
                "transition_count": len(transitions),
                "window_seconds": round(
                    self.config.repeated_entry_exit_window_seconds,
                    3,
                ),
                "configured_zone": "entry_exit_zone",
                "rule": "repeated boundary crossings inside the configured window",
            },
        )

    def _evaluate_route_deviation(
        self,
        timestamp: float,
        state: TrackState,
    ) -> AnomalyEvent | None:
        route = self.config.expected_route
        key = ("route_deviation", (state.track_id,))
        if len(route) < 2:
            self._candidate_starts.pop(key, None)
            return None
        distance = min(
            _point_segment_distance(
                (state.latest.x, state.latest.y),
                start,
                end,
            )
            for start, end in zip(route, route[1:])
        )
        if distance <= self.config.route_deviation_px:
            self._candidate_starts.pop(key, None)
            return None
        started = self._candidate_starts.setdefault(key, timestamp)
        if timestamp - started < self.config.route_deviation_seconds:
            return None
        return self._emit(
            "route_deviation",
            (state.track_id,),
            started,
            timestamp,
            0.7,
            {
                "distance_px": round(distance, 2),
                "threshold_px": round(self.config.route_deviation_px, 2),
                "configured_route": "expected_route",
                "rule": "sustained distance from the calibrated route",
            },
        )

    def _evaluate_dangerous_zone(
        self,
        timestamp: float,
        state: TrackState,
    ) -> AnomalyEvent | None:
        point = (state.latest.x, state.latest.y)
        nearest: tuple[float, int] | None = None
        for index, polygon in enumerate(self.config.dangerous_zones):
            if len(polygon) < 3:
                continue
            distance = _point_polygon_distance(point, polygon)
            candidate = (distance, index)
            if nearest is None or candidate < nearest:
                nearest = candidate
        key = ("dangerous_zone_proximity", (state.track_id,))
        if nearest is None or nearest[0] > self.config.dangerous_zone_margin_px:
            self._candidate_starts.pop(key, None)
            return None
        started = self._candidate_starts.setdefault(key, timestamp)
        if timestamp - started < self.config.dangerous_zone_seconds:
            return None
        distance, zone_index = nearest
        return self._emit(
            "dangerous_zone_proximity",
            (state.track_id,),
            started,
            timestamp,
            0.8,
            {
                "zone_index": zone_index,
                "distance_px": round(distance, 2),
                "margin_px": round(self.config.dangerous_zone_margin_px, 2),
                "rule": "sustained proximity to a configured dangerous zone",
            },
        )

    def _evaluate_interactions(
        self,
        timestamp: float,
        states: list[TrackState],
    ) -> list[AnomalyEvent]:
        events: list[AnomalyEvent] = []
        for left, right in combinations(states, 2):
            ids = tuple(sorted((left.track_id, right.track_id)))
            key = ("suspected_intense_interaction", ids)
            distance = hypot(
                left.latest.x - right.latest.x,
                left.latest.y - right.latest.y,
            )
            high_motion = (
                left.current_speed >= self.config.interaction_speed_px_s
                and right.current_speed >= self.config.interaction_speed_px_s
            )
            if distance <= self.config.interaction_distance_px and high_motion:
                started = self._candidate_starts.setdefault(key, timestamp)
                if timestamp - started >= self.config.interaction_seconds:
                    event = self._emit(
                        "suspected_intense_interaction",
                        ids,
                        started,
                        timestamp,
                        0.68,
                        {
                            "distance_px": round(distance, 2),
                            "left_speed_px_s": round(left.current_speed, 2),
                            "right_speed_px_s": round(right.current_speed, 2),
                            "rule": "close pair with sustained high motion",
                            "warning": "heuristic candidate; not a violence classification",
                        },
                    )
                    if event:
                        events.append(event)
            else:
                self._candidate_starts.pop(key, None)
        return events

    def _emit(
        self,
        event_type: str,
        track_ids: tuple[int, ...],
        start_time: float,
        end_time: float,
        confidence: float,
        evidence: dict[str, object],
    ) -> AnomalyEvent | None:
        key = (event_type, track_ids)
        last_emitted = self._last_emitted.get(key)
        if (
            last_emitted is not None
            and end_time - last_emitted < self.config.cooldown_seconds
        ):
            return None
        self._last_emitted[key] = end_time
        return AnomalyEvent(
            event_type=event_type,
            track_ids=track_ids,
            start_time=start_time,
            end_time=end_time,
            confidence=confidence,
            evidence=evidence,
            requires_review=True,
        )

    def _continuous_fall_start(self, state: TrackState) -> float | None:
        start: float | None = None
        for point in reversed(state.points):
            x1, y1, x2, y2 = point.bbox
            height = max(1.0, y2 - y1)
            ratio = max(0.0, x2 - x1) / height
            if ratio < self.config.fall_aspect_ratio:
                break
            start = point.timestamp
        return start

    @staticmethod
    def _latest_aspect_ratio(state: TrackState) -> float:
        x1, y1, x2, y2 = state.latest.bbox
        return max(0.0, x2 - x1) / max(1.0, y2 - y1)

    @staticmethod
    def _max_radius(state: TrackState) -> float:
        if not state.points:
            return 0.0
        origin = state.points[0]
        return max(
            hypot(point.x - origin.x, point.y - origin.y)
            for point in state.points
        )


def _point_in_polygon(
    point: tuple[float, float],
    polygon: tuple[tuple[float, float], ...],
) -> bool:
    x, y = point
    inside = False
    previous = polygon[-1]
    for current in polygon:
        x1, y1 = previous
        x2, y2 = current
        if (y1 > y) != (y2 > y):
            crossing = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x <= crossing:
                inside = not inside
        previous = current
    return inside


def _point_segment_distance(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    px, py = point
    x1, y1 = start
    x2, y2 = end
    dx, dy = x2 - x1, y2 - y1
    length_squared = dx * dx + dy * dy
    if length_squared <= 0:
        return hypot(px - x1, py - y1)
    position = max(
        0.0,
        min(1.0, ((px - x1) * dx + (py - y1) * dy) / length_squared),
    )
    return hypot(px - (x1 + position * dx), py - (y1 + position * dy))


def _point_polygon_distance(
    point: tuple[float, float],
    polygon: tuple[tuple[float, float], ...],
) -> float:
    if _point_in_polygon(point, polygon):
        return 0.0
    return min(
        _point_segment_distance(point, start, end)
        for start, end in zip(polygon, (*polygon[1:], polygon[0]))
    )
