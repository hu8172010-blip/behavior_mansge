from __future__ import annotations

import inspect
import json
import os
from copy import deepcopy
from collections.abc import Callable, Mapping, Sequence
from math import ceil, floor, hypot, isfinite
from numbers import Integral
from pathlib import Path
from threading import Lock

import cv2
import numpy as np

from .classifier import OptionalClipClassifier
from .domain import AnomalyEvent, Box, TrackObservation
from .fusion import CLASS_NAMES, TemporalFusion, TrackClipBuffer
from .rules import AnomalyEngine, RuleConfig, rule_config_dict
from .tracker import PersonTracker, UltralyticsPersonTracker
from .trajectory import TrackState, TrajectoryStore


ProgressCallback = Callable[[float], None]
DEFAULT_CHECKPOINT = Path("models/best.pth")
CLASSIFIER_CROP_SIZE = 128


class _RulesOnlyClassifierSession:
    available = False
    status = {
        "mode": "rules_only",
        "error": "classifier session unavailable",
    }


class VideoProcessor:
    def __init__(
        self,
        tracker: PersonTracker | None = None,
        rule_config: RuleConfig | None = None,
        *,
        classifier: object | None = None,
        classifier_factory: Callable[[], object] | None = None,
        checkpoint_path: str | Path | None = None,
        classifier_stride: int = 8,
        max_video_frames: int = 45_000,
        max_duration_seconds: float = 1_800.0,
        max_diagnostic_records: int = 10_000,
    ) -> None:
        if (
            classifier_stride <= 0
            or max_video_frames <= 0
            or max_duration_seconds <= 0
            or max_diagnostic_records <= 0
        ):
            raise ValueError("processor limits must be positive")
        if classifier is not None and classifier_factory is not None:
            raise ValueError(
                "provide classifier or classifier_factory, not both"
            )
        self.tracker = tracker or UltralyticsPersonTracker()
        self._tracker_was_provided = tracker is not None
        self.rule_config = rule_config or RuleConfig()
        configured_checkpoint = (
            checkpoint_path
            if checkpoint_path is not None
            else os.environ.get(
                "ANOMALY_CLASSIFIER_CHECKPOINT",
                str(DEFAULT_CHECKPOINT),
            )
        )
        self.checkpoint_path = Path(configured_checkpoint)
        self.classifier = classifier
        self._classifier_factory = classifier_factory
        self._classifier_was_provided = classifier is not None
        self.classifier_stride = classifier_stride
        self.max_video_frames = max_video_frames
        self.max_duration_seconds = max_duration_seconds
        self.max_diagnostic_records = max_diagnostic_records
        self._process_lock = Lock()

    def process(
        self,
        input_path: str | Path,
        output_dir: str | Path,
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, object]:
        if not self._process_lock.acquire(blocking=False):
            raise RuntimeError("processor is already processing a video")
        try:
            return self._process_video(
                input_path,
                output_dir,
                progress_callback,
            )
        finally:
            self._process_lock.release()

    def _process_video(
        self,
        input_path: str | Path,
        output_dir: str | Path,
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, object]:
        tracker = self._new_tracker_session()
        classifier = self._new_classifier_session()
        source = Path(input_path)
        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)

        capture = cv2.VideoCapture(str(source))
        if not capture.isOpened():
            capture.release()
            raise ValueError(f"无法读取视频：{source.name}")

        fps = capture.get(cv2.CAP_PROP_FPS)
        if not fps or fps <= 0:
            fps = 25.0
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if width <= 0 or height <= 0:
            capture.release()
            raise ValueError(f"无法读取视频尺寸：{source.name}")

        if frame_count > self.max_video_frames:
            capture.release()
            raise ValueError("video frame limit exceeded")
        if frame_count > 0 and frame_count / fps > self.max_duration_seconds:
            capture.release()
            raise ValueError("video duration limit exceeded")

        # All temporal state is scoped to this one process() call. Track IDs are
        # never carried into another uploaded video.
        stale_after_seconds = 4.0
        store = TrajectoryStore(
            retention_seconds=120.0,
            stale_after_seconds=stale_after_seconds,
        )
        engine = AnomalyEngine(self.rule_config)
        clip_buffer = TrackClipBuffer(
            frame_count=16,
            stride=self.classifier_stride,
            stale_after_seconds=stale_after_seconds,
        )
        fusion = TemporalFusion(
            stale_after_seconds=stale_after_seconds,
        )
        smoothed_by_track: dict[int, dict[str, float]] = {}
        generation_by_track: dict[int, int] = {}
        retired_tracks: list[tuple[int, TrackState]] = []
        events: list[AnomalyEvent] = []
        classifier_predictions: list[dict[str, object]] = []
        tracking_error_records: list[dict[str, object]] = []
        annotation_observations: list[list[TrackObservation]] = []
        abnormal_track_ids: set[int] = set()
        frame_index = 0
        classifier_errors = 0
        tracking_errors = 0
        classifier_prediction_count = 0
        classifier_enabled = bool(
            getattr(classifier, "available", False)
        )
        healthy_device = self._status_device(classifier)

        try:
            while True:
                cancellation = getattr(self, "cancellation_event", None)
                if cancellation is not None and cancellation.is_set():
                    raise TimeoutError("video processing cancelled")
                ok, frame = capture.read()
                if not ok:
                    break
                if frame_index >= self.max_video_frames:
                    raise ValueError("video frame limit exceeded")
                timestamp = frame_index / fps
                if timestamp > self.max_duration_seconds:
                    raise ValueError("video duration limit exceeded")
                observations = tracker.track(frame, timestamp)

                stale_ids = {
                    state.track_id
                    for state in store.all_states()
                    if timestamp - state.last_seen > stale_after_seconds
                }
                if stale_ids:
                    for track_id in stale_ids:
                        retired_state = store.get(track_id)
                        if retired_state is not None:
                            retired_tracks.append(
                                (
                                    generation_by_track.get(
                                        track_id,
                                        0,
                                    ),
                                    retired_state,
                                )
                            )
                        generation_by_track[track_id] = (
                            generation_by_track.get(track_id, 0) + 1
                        )
                        store.discard(track_id)
                        clip_buffer.discard(track_id)
                        fusion.discard(track_id)
                        smoothed_by_track.pop(track_id, None)
                    engine.discard_tracks(stale_ids)

                valid_observations: list[TrackObservation] = []
                for observation in observations:
                    try:
                        self._validate_observation(frame, observation)
                        generation_by_track.setdefault(
                            observation.track_id,
                            0,
                        )
                        store.update(observation)
                        valid_observations.append(observation)
                    except Exception:
                        tracking_errors += 1
                        if (
                            len(tracking_error_records)
                            < self.max_diagnostic_records
                        ):
                            tracking_error_records.append(
                                self._tracking_error_record(
                                    getattr(observation, "track_id", -1),
                                    timestamp,
                                )
                            )
                annotation_observations.append(list(valid_observations))

                active_states = store.active_states(timestamp)
                new_rule_events = [
                    self._with_evidence_source(
                        event,
                        "rules",
                        generation_by_track,
                    )
                    for event in engine.evaluate(timestamp, active_states)
                ]
                for event in new_rule_events:
                    self._merge_event(events, event)

                if classifier_enabled:
                    observed_track_ids = {
                        observation.track_id
                        for observation in valid_observations
                    }
                    for observation in valid_observations:
                        window = None
                        try:
                            crop = self._prepare_person_crop(
                                frame,
                                observation.bbox,
                            )
                            if crop is None:
                                raise ValueError(
                                    "person box does not intersect frame"
                                )
                            window = clip_buffer.add(
                                observation.track_id,
                                timestamp,
                                crop,
                            )
                            if window is None:
                                continue
                            prediction = self._predict_window(
                                classifier,
                                window.frames,
                                window.timestamps[0],
                                window.timestamps[-1],
                            )
                            raw = self._prediction_probabilities(prediction)
                            if raw is None:
                                raise ValueError("classifier returned no prediction")
                            previous = smoothed_by_track.get(
                                observation.track_id
                            )
                            smoothed = (
                                raw.copy()
                                if previous is None
                                else {
                                    name: (
                                        0.5 * raw[name]
                                        + 0.5 * previous[name]
                                    )
                                    for name in CLASS_NAMES
                                }
                            )
                            smoothed_by_track[observation.track_id] = smoothed
                            classifier_prediction_count += 1
                            if (
                                len(classifier_predictions)
                                < self.max_diagnostic_records
                            ):
                                classifier_predictions.append(
                                    self._prediction_record(
                                        observation.track_id,
                                        window.timestamps[0],
                                        window.timestamps[-1],
                                        raw,
                                        smoothed,
                                    )
                                )
                            model_events = fusion.update(
                                observation.track_id,
                                window.timestamps[-1],
                                raw,
                                store.get(observation.track_id),
                                horizontal_pose=self._is_horizontal(
                                    observation
                                ),
                            )
                            for model_event in model_events:
                                enriched = self._enrich_model_event(
                                    model_event,
                                    raw,
                                    smoothed,
                                    window.timestamps[0],
                                    window.timestamps[-1],
                                    active_states,
                                    observed_track_ids,
                                    generation_by_track,
                                )
                                if enriched is not None:
                                    self._merge_event(events, enriched)
                        except Exception:
                            classifier_errors += 1
                            error_start = (
                                window.timestamps[0]
                                if window is not None
                                else timestamp
                            )
                            error_end = (
                                window.timestamps[-1]
                                if window is not None
                                else timestamp
                            )
                            classifier_prediction_count += 1
                            if (
                                len(classifier_predictions)
                                < self.max_diagnostic_records
                            ):
                                classifier_predictions.append(
                                    self._error_prediction_record(
                                        observation.track_id,
                                        error_start,
                                        error_end,
                                        "classifier inference failed",
                                    )
                                )
                            classifier_enabled = bool(
                                getattr(
                                    classifier,
                                    "available",
                                    classifier_enabled,
                                )
                            )

                # TrackClipBuffer performs this check on add; invoking it once per
                # frame also retires tracks while the scene has no observations.
                clip_buffer.evict_stale(timestamp)
                fusion.evict_stale(timestamp)
                active_ids = set(clip_buffer.track_ids)
                for track_id in list(smoothed_by_track):
                    if track_id not in active_ids:
                        smoothed_by_track.pop(track_id, None)

                frame_index += 1
                if progress_callback and frame_count > 0:
                    progress_callback(
                        min(0.79, 0.79 * frame_index / frame_count)
                    )
        finally:
            capture.release()

        if frame_index == 0:
            raise ValueError(f"视频中没有可读取的帧：{source.name}")
        self._render_annotated_video(
            source,
            destination / "annotated.mp4",
            fps=fps,
            size=(width, height),
            observations_by_frame=annotation_observations,
            events=events,
            progress_callback=progress_callback,
        )

        model_status = self._model_status(
            classifier=classifier,
            healthy_device=healthy_device,
            track_errors=classifier_errors,
            successful_predictions=max(
                0,
                classifier_prediction_count - classifier_errors,
            ),
        )
        active_tracks = [
            (
                generation_by_track.get(state.track_id, 0),
                state,
            )
            for state in store.all_states()
        ]
        all_track_generations = sorted(
            (*retired_tracks, *active_tracks),
            key=lambda item: (item[1].track_id, item[0]),
        )
        event_payloads = [
            self._serialize_event(event)
            for event in events
        ]
        abnormal_track_generations = {
            (
                int(reference["track_id"]),
                int(reference["generation"]),
            )
            for payload in event_payloads
            for reference in payload["track_references"]
        }
        result = {
            "effective_rule_config": rule_config_dict(self.rule_config),
            "video": {
                "source_name": source.name,
                "fps": round(float(fps), 3),
                "width": width,
                "height": height,
                "frames_processed": frame_index,
                "duration_seconds": round(frame_index / fps, 3),
            },
            "summary": {
                "people_tracked": len(all_track_generations),
                "events_detected": len(events),
                "requires_human_review": bool(events),
                "tracking_errors": tracking_errors,
                "classifier_prediction_records": classifier_prediction_count,
            },
            "model_status": model_status,
            "tracking_status": {
                "errors": tracking_errors,
                "records_truncated": (
                    tracking_errors > len(tracking_error_records)
                ),
                "warning": (
                    "one or more invalid track observations were ignored"
                    if tracking_errors
                    else None
                ),
            },
            "tracking_errors": tracking_error_records,
            "classifier_predictions": classifier_predictions,
            "events": event_payloads,
            "tracks": [
                self._serialize_track(
                    state,
                    generation,
                    abnormal_track_generations,
                    event_payloads,
                )
                for generation, state in all_track_generations
            ],
        }
        (destination / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if progress_callback:
            progress_callback(1.0)
        return result

    def _new_tracker_session(self) -> PersonTracker:
        if not self._tracker_was_provided:
            model_name = getattr(self.tracker, "model_name", None)
            return UltralyticsPersonTracker(model_name)
        new_session = getattr(self.tracker, "new_session", None)
        if callable(new_session):
            return new_session()
        try:
            return deepcopy(self.tracker)
        except Exception:
            reset = getattr(self.tracker, "reset", None)
            if callable(reset):
                reset()
                return self.tracker
            raise RuntimeError(
                "tracker must support independent video sessions"
            )

    def _new_classifier_session(self) -> object:
        if self._classifier_factory is not None:
            try:
                session = self._classifier_factory()
            except Exception:
                return _RulesOnlyClassifierSession()
            if session is None:
                return _RulesOnlyClassifierSession()
            return session
        if not self._classifier_was_provided:
            return OptionalClipClassifier(self.checkpoint_path)
        new_session = getattr(self.classifier, "new_session", None)
        if callable(new_session):
            try:
                session = new_session()
                if session is not self.classifier:
                    return session
            except Exception:
                return _RulesOnlyClassifierSession()
        try:
            session = deepcopy(self.classifier)
        except Exception:
            return _RulesOnlyClassifierSession()
        if session is self.classifier:
            return _RulesOnlyClassifierSession()
        return session

    def _predict_window(
        self,
        classifier: object,
        frames: Sequence[np.ndarray],
        start_time: float,
        end_time: float,
    ) -> object:
        predict = getattr(classifier, "predict")
        try:
            parameters = inspect.signature(predict).parameters.values()
            accepts_times = any(
                parameter.kind is inspect.Parameter.VAR_KEYWORD
                for parameter in parameters
            ) or {
                "start_time",
                "end_time",
            }.issubset(
                {
                    parameter.name
                    for parameter in parameters
                }
            )
        except (TypeError, ValueError):
            accepts_times = False
        if accepts_times:
            return predict(
                frames,
                start_time=start_time,
                end_time=end_time,
            )
        return predict(frames)

    @staticmethod
    def _prediction_probabilities(
        prediction: object,
    ) -> dict[str, float] | None:
        if prediction is None:
            return None
        candidate: object = (
            prediction
            if isinstance(prediction, Mapping)
            else getattr(prediction, "probabilities", None)
        )
        if not isinstance(candidate, Mapping):
            raise ValueError("classifier returned an invalid prediction")
        if set(candidate) != set(CLASS_NAMES):
            raise ValueError("classifier returned invalid labels")
        probabilities = {
            name: float(candidate[name])
            for name in CLASS_NAMES
        }
        if not all(
            isfinite(value) and 0.0 <= value <= 1.0
            for value in probabilities.values()
        ):
            raise ValueError("classifier returned invalid probabilities")
        if abs(sum(probabilities.values()) - 1.0) > 1e-5:
            raise ValueError("classifier probabilities must sum to one")
        return probabilities

    @staticmethod
    def _prediction_record(
        track_id: int,
        start_time: float,
        end_time: float,
        raw: Mapping[str, float],
        smoothed: Mapping[str, float],
    ) -> dict[str, object]:
        return {
            "track_id": int(track_id),
            "start_time": round(start_time, 3),
            "end_time": round(end_time, 3),
            "status": "ok",
            "raw_probabilities": {
                name: round(float(raw[name]), 6)
                for name in CLASS_NAMES
            },
            "smoothed_probabilities": {
                name: round(float(smoothed[name]), 6)
                for name in CLASS_NAMES
            },
            "evidence": {
                "source": "model",
                "requires_review": True,
            },
        }

    @staticmethod
    def _error_prediction_record(
        track_id: object,
        start_time: float,
        end_time: float,
        warning: str,
    ) -> dict[str, object]:
        safe_track_id = (
            int(track_id)
            if isinstance(track_id, Integral)
            else -1
        )
        return {
            "track_id": safe_track_id,
            "start_time": round(float(start_time), 3),
            "end_time": round(float(end_time), 3),
            "status": "error",
            "raw_probabilities": None,
            "smoothed_probabilities": None,
            "evidence": {
                "source": "model",
                "warning": warning,
                "requires_review": True,
            },
        }

    @staticmethod
    def _tracking_error_record(
        track_id: object,
        timestamp: float,
    ) -> dict[str, object]:
        safe_track_id = (
            int(track_id)
            if isinstance(track_id, Integral)
            else -1
        )
        return {
            "track_id": safe_track_id,
            "timestamp": round(float(timestamp), 3),
            "evidence": {
                "category": "tracking",
                "warning": "invalid track observation ignored",
            },
        }

    @staticmethod
    def _validate_observation(
        frame: np.ndarray,
        observation: TrackObservation,
    ) -> None:
        array = np.asarray(frame)
        if (
            array.ndim != 3
            or array.shape[2] != 3
            or min(array.shape[:2]) <= 0
            or array.dtype != np.uint8
        ):
            raise ValueError("invalid video frame")
        if (
            not isinstance(observation.track_id, Integral)
            or int(observation.track_id) < 0
            or not isfinite(float(observation.confidence))
        ):
            raise ValueError("invalid track metadata")
        if len(observation.bbox) != 4:
            raise ValueError("invalid track box")
        coordinates = tuple(float(value) for value in observation.bbox)
        if not all(isfinite(value) for value in coordinates):
            raise ValueError("invalid track box")
        x1, y1, x2, y2 = coordinates
        if x2 <= x1 or y2 <= y1:
            raise ValueError("invalid track box")
        height, width = array.shape[:2]
        if x2 <= 0 or y2 <= 0 or x1 >= width or y1 >= height:
            raise ValueError("track box does not intersect frame")

    def _model_status(
        self,
        *,
        track_errors: int,
        successful_predictions: int,
        classifier: object | None = None,
        healthy_device: str | None = None,
    ) -> dict[str, object]:
        target = classifier if classifier is not None else self.classifier
        classifier_status = getattr(target, "status", {})
        source = (
            dict(classifier_status)
            if isinstance(classifier_status, Mapping)
            else {}
        )
        available = bool(getattr(target, "available", False))
        mode = "hybrid" if available else "rules_only"
        if not available and successful_predictions:
            mode = "hybrid_degraded"
        status: dict[str, object] = {
            "mode": mode,
            "classifier": "r3d18",
            "checkpoint": self._display_checkpoint(self.checkpoint_path),
        }
        device = self._status_device(target) or healthy_device
        if device:
            status["device"] = device
        error = source.get("error")
        if not available and error:
            status["error"] = self._safe_status_message(error)
        if track_errors:
            status["track_errors"] = track_errors
            status["warning"] = (
                "one or more track windows could not be classified"
            )
        return status

    @staticmethod
    def _status_device(classifier: object) -> str | None:
        classifier_status = getattr(classifier, "status", {})
        if not isinstance(classifier_status, Mapping):
            return None
        device = classifier_status.get("device")
        if not isinstance(device, str) or not device:
            return None
        return "cuda:0" if device == "cuda" else device

    @staticmethod
    def _safe_status_message(message: object) -> str:
        text = str(message)
        if (
            len(text) > 160
            or "\\" in text
            or "/" in text
            or ":" in text
        ):
            return "classifier unavailable"
        return text

    @staticmethod
    def _display_checkpoint(path: Path) -> str:
        if path.is_absolute() or path.drive:
            return path.name or "checkpoint.pth"
        safe_parts = [
            part
            for part in path.parts
            if part not in {"", ".", ".."}
        ]
        return Path(*safe_parts).as_posix() if safe_parts else "checkpoint.pth"

    @staticmethod
    def _prepare_person_crop(
        frame: np.ndarray,
        bbox: Box,
    ) -> np.ndarray | None:
        array = np.asarray(frame)
        if (
            array.ndim != 3
            or array.shape[2] != 3
            or min(array.shape[:2]) <= 0
            or array.dtype != np.uint8
        ):
            raise ValueError("invalid video frame")
        frame_height, frame_width = array.shape[:2]
        x1, y1, x2, y2 = (float(value) for value in bbox)
        if not all(isfinite(value) for value in (x1, y1, x2, y2)):
            raise ValueError("invalid track box")
        box_width = x2 - x1
        box_height = y2 - y1
        if box_width <= 0 or box_height <= 0:
            return None
        x1 = max(0, floor(x1 - 0.25 * box_width))
        y1 = max(0, floor(y1 - 0.25 * box_height))
        x2 = min(frame_width, ceil(x2 + 0.25 * box_width))
        y2 = min(frame_height, ceil(y2 + 0.25 * box_height))
        if x2 <= x1 or y2 <= y1:
            return None
        rgb = cv2.cvtColor(array[y1:y2, x1:x2], cv2.COLOR_BGR2RGB)
        scale = min(
            CLASSIFIER_CROP_SIZE / rgb.shape[1],
            CLASSIFIER_CROP_SIZE / rgb.shape[0],
        )
        resized_width = max(1, min(
            CLASSIFIER_CROP_SIZE,
            round(rgb.shape[1] * scale),
        ))
        resized_height = max(1, min(
            CLASSIFIER_CROP_SIZE,
            round(rgb.shape[0] * scale),
        ))
        resized = cv2.resize(
            rgb,
            (resized_width, resized_height),
            interpolation=cv2.INTER_LINEAR,
        )
        output = np.zeros(
            (CLASSIFIER_CROP_SIZE, CLASSIFIER_CROP_SIZE, 3),
            dtype=np.uint8,
        )
        top = (CLASSIFIER_CROP_SIZE - resized_height) // 2
        left = (CLASSIFIER_CROP_SIZE - resized_width) // 2
        output[
            top : top + resized_height,
            left : left + resized_width,
        ] = resized
        return np.ascontiguousarray(output)

    def _enrich_model_event(
        self,
        event: AnomalyEvent,
        raw: Mapping[str, float],
        smoothed: Mapping[str, float],
        window_start: float,
        window_end: float,
        active_states: list[TrackState],
        observed_track_ids: set[int],
        generation_by_track: Mapping[int, int],
    ) -> AnomalyEvent | None:
        label = event.event_type.removeprefix("suspected_")
        evidence = {
            **event.evidence,
            "source": "model",
            "raw_probability": round(float(raw[label]), 4),
            "smoothed_probability": round(
                float(smoothed[label]),
                4,
            ),
            "window_start": round(window_start, 3),
            "window_end": round(window_end, 3),
            "warning": "model candidate; requires human review",
            "track_generations": {
                str(track_id): generation_by_track.get(track_id, 0)
                for track_id in event.track_ids
            },
        }
        track_ids = event.track_ids
        if event.event_type == "suspected_fall":
            state = next(
                (
                    state
                    for state in active_states
                    if state.track_id == event.track_ids[0]
                ),
                None,
            )
            if (
                state is not None
                and self._state_is_horizontal(state)
            ):
                evidence["source"] = "both"
                evidence["rule"] = (
                    "horizontal posture corroborated model fall"
                )
                evidence["aspect_ratio"] = round(
                    self._state_aspect_ratio(state),
                    3,
                )
        if event.event_type == "suspected_violence":
            pair = self._violence_pair(
                event.track_ids[0],
                active_states,
                observed_track_ids=observed_track_ids,
            )
            if pair is None:
                return None
            other_id, pair_evidence = pair
            track_ids = tuple(
                sorted((event.track_ids[0], other_id))
            )
            evidence.update(pair_evidence)
            evidence["source"] = "both"
            evidence["track_generations"] = {
                str(track_id): generation_by_track.get(
                    track_id,
                    0,
                )
                for track_id in track_ids
            }
        return AnomalyEvent(
            event_type=event.event_type,
            track_ids=track_ids,
            start_time=event.start_time,
            end_time=event.end_time,
            confidence=event.confidence,
            evidence=evidence,
            requires_review=True,
        )

    def _violence_pair(
        self,
        primary_id: int,
        states: list[TrackState],
        *,
        observed_track_ids: set[int] | None = None,
    ) -> tuple[int, dict[str, object]] | None:
        endpoint_ids = (
            observed_track_ids
            if observed_track_ids is not None
            else {state.track_id for state in states}
        )
        if primary_id not in endpoint_ids:
            return None
        primary = next(
            (
                state
                for state in states
                if state.track_id == primary_id
            ),
            None,
        )
        if (
            primary is None
            or primary.current_speed
            < self.rule_config.interaction_speed_px_s
        ):
            return None
        candidates: list[tuple[float, TrackState]] = []
        for state in states:
            if (
                state.track_id == primary_id
                or state.track_id not in endpoint_ids
                or state.current_speed
                < self.rule_config.interaction_speed_px_s
            ):
                continue
            distance = hypot(
                primary.latest.x - state.latest.x,
                primary.latest.y - state.latest.y,
            )
            if distance <= self.rule_config.interaction_distance_px:
                candidates.append((distance, state))
        if not candidates:
            return None
        distance, other = min(
            candidates,
            key=lambda item: (item[0], item[1].track_id),
        )
        return (
            other.track_id,
            {
                "pairing": "proximity_and_motion",
                "distance_px": round(distance, 2),
                "primary_speed_px_s": round(
                    primary.current_speed,
                    2,
                ),
                "second_speed_px_s": round(
                    other.current_speed,
                    2,
                ),
                "rule": (
                    "second track is close and both tracks have high motion"
                ),
            },
        )

    @staticmethod
    def _with_evidence_source(
        event: AnomalyEvent,
        source: str,
        generation_by_track: Mapping[int, int] | None = None,
    ) -> AnomalyEvent:
        generations = generation_by_track or {}
        return AnomalyEvent(
            event_type=event.event_type,
            track_ids=event.track_ids,
            start_time=event.start_time,
            end_time=event.end_time,
            confidence=event.confidence,
            evidence={
                **event.evidence,
                "source": source,
                "warning": (
                    "rule candidate; requires human review"
                ),
                "track_generations": {
                    str(track_id): generations.get(track_id, 0)
                    for track_id in event.track_ids
                },
            },
            requires_review=True,
        )

    def _merge_event(
        self,
        events: list[AnomalyEvent],
        candidate: AnomalyEvent,
    ) -> None:
        candidate_ids = tuple(sorted(candidate.track_ids))
        candidate_generation = self._event_generation(candidate)
        pair_event_types = {
            "suspected_violence",
            "suspected_intense_interaction",
        }
        if (
            candidate.event_type in pair_event_types
            and len(candidate_ids) == 2
        ):
            for index in range(len(events) - 1, -1, -1):
                existing = events[index]
                existing_generation = self._event_generation(existing)
                if (
                    existing.event_type not in pair_event_types
                    or existing.event_type == candidate.event_type
                    or tuple(sorted(existing.track_ids))
                    != candidate_ids
                    or (
                        candidate_generation is not None
                        and existing_generation is not None
                        and candidate_generation != existing_generation
                    )
                ):
                    continue
                gap = max(
                    candidate.start_time - existing.end_time,
                    existing.start_time - candidate.end_time,
                    0.0,
                )
                if gap > self.rule_config.cooldown_seconds:
                    continue
                events[index] = AnomalyEvent(
                    event_type="suspected_violence",
                    track_ids=candidate_ids,
                    start_time=min(
                        existing.start_time,
                        candidate.start_time,
                    ),
                    end_time=max(
                        existing.end_time,
                        candidate.end_time,
                    ),
                    confidence=max(
                        existing.confidence,
                        candidate.confidence,
                    ),
                    evidence={
                        **existing.evidence,
                        **candidate.evidence,
                        "source": "both",
                    },
                    requires_review=True,
                )
                return
        for index in range(len(events) - 1, -1, -1):
            existing = events[index]
            existing_generation = self._event_generation(existing)
            if (
                existing.event_type != candidate.event_type
                or tuple(sorted(existing.track_ids)) != candidate_ids
                or (
                    candidate_generation is not None
                    and existing_generation is not None
                    and candidate_generation != existing_generation
                )
            ):
                continue
            gap = max(
                candidate.start_time - existing.end_time,
                existing.start_time - candidate.end_time,
                0.0,
            )
            if gap > self.rule_config.cooldown_seconds:
                continue
            sources = {
                str(existing.evidence.get("source", "rules")),
                str(candidate.evidence.get("source", "model")),
            }
            combined_source = (
                "both"
                if "both" in sources or len(sources) > 1
                else sources.pop()
            )
            events[index] = AnomalyEvent(
                event_type=candidate.event_type,
                track_ids=candidate_ids,
                start_time=min(
                    existing.start_time,
                    candidate.start_time,
                ),
                end_time=max(
                    existing.end_time,
                    candidate.end_time,
                ),
                confidence=max(
                    existing.confidence,
                    candidate.confidence,
                ),
                evidence={
                    **existing.evidence,
                    **candidate.evidence,
                    "source": combined_source,
                },
                requires_review=True,
            )
            return
        if candidate.track_ids != candidate_ids:
            candidate = AnomalyEvent(
                event_type=candidate.event_type,
                track_ids=candidate_ids,
                start_time=candidate.start_time,
                end_time=candidate.end_time,
                confidence=candidate.confidence,
                evidence=candidate.evidence,
                requires_review=True,
            )
        events.append(candidate)

    @staticmethod
    def _event_generation(
        event: AnomalyEvent,
    ) -> tuple[tuple[str, int], ...] | None:
        value = event.evidence.get("track_generations")
        if not isinstance(value, Mapping):
            return None
        try:
            return tuple(
                sorted(
                    (str(track_id), int(generation))
                    for track_id, generation in value.items()
                )
            )
        except (TypeError, ValueError):
            return None

    def _is_horizontal(self, observation: TrackObservation) -> bool:
        return (
            observation.width / max(1.0, observation.height)
            >= self.rule_config.fall_aspect_ratio
        )

    def _state_is_horizontal(self, state: TrackState) -> bool:
        return (
            self._state_aspect_ratio(state)
            >= self.rule_config.fall_aspect_ratio
        )

    @staticmethod
    def _state_aspect_ratio(state: TrackState) -> float:
        x1, y1, x2, y2 = state.latest.bbox
        return max(0.0, x2 - x1) / max(1.0, y2 - y1)

    @staticmethod
    def _serialize_event(
        event: AnomalyEvent,
    ) -> dict[str, object]:
        payload = event.to_dict()
        generations = event.evidence.get("track_generations")
        generation_map = (
            generations
            if isinstance(generations, Mapping)
            else {}
        )
        references: list[dict[str, int]] = []
        for track_id in event.track_ids:
            try:
                generation = int(
                    generation_map.get(str(track_id), 0)
                )
            except (TypeError, ValueError):
                generation = 0
            references.append(
                {
                    "track_id": int(track_id),
                    "generation": generation,
                }
            )
        payload["track_references"] = references
        return payload

    @staticmethod
    def _serialize_track(
        state: TrackState,
        generation: int,
        abnormal_track_generations: set[tuple[int, int]],
        event_payloads: Sequence[Mapping[str, object]],
    ) -> dict[str, object]:
        track_key = (state.track_id, generation)
        event_types = sorted(
            {
                str(payload["event_type"])
                for payload in event_payloads
                if any(
                    (
                        int(reference.get("track_id", -1)),
                        int(reference.get("generation", -1)),
                    )
                    == track_key
                    for reference in payload.get(
                        "track_references",
                        [],
                    )
                    if isinstance(reference, Mapping)
                )
            }
        )
        return {
            "track_id": state.track_id,
            "generation": generation,
            "abnormal": track_key in abnormal_track_generations,
            "event_types": event_types,
            "first_seen": round(state.first_seen, 3),
            "last_seen": round(state.last_seen, 3),
            "path_length_px": round(state.path_length, 2),
            "net_displacement_px": round(state.net_displacement, 2),
            "points": [
                {
                    "timestamp": round(point.timestamp, 3),
                    "x": round(point.x, 2),
                    "y": round(point.y, 2),
                }
                for point in state.points
            ],
        }

    def _render_annotated_video(
        self,
        source: Path,
        destination: Path,
        *,
        fps: float,
        size: tuple[int, int],
        observations_by_frame: Sequence[Sequence[TrackObservation]],
        events: list[AnomalyEvent],
        progress_callback: ProgressCallback | None,
    ) -> None:
        """Render once all event intervals are final.

        Tracking and classification happen in the first pass. Deferring drawing
        prevents an event discovered near the end of its evidence window from
        leaving earlier frames in that finalized interval green.
        """
        capture = cv2.VideoCapture(str(source))
        writer = cv2.VideoWriter(
            str(destination),
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            size,
        )
        if not capture.isOpened() or not writer.isOpened():
            capture.release()
            writer.release()
            destination.unlink(missing_ok=True)
            raise RuntimeError("无法创建标注视频")
        annotation_store = TrajectoryStore(
            retention_seconds=max(120.0, len(observations_by_frame) / fps + 1),
            stale_after_seconds=4.0,
        )
        total = max(1, len(observations_by_frame))
        try:
            for frame_index, observations in enumerate(observations_by_frame):
                cancellation = getattr(self, "cancellation_event", None)
                if cancellation is not None and cancellation.is_set():
                    raise TimeoutError("video annotation cancelled")
                ok, frame = capture.read()
                if not ok:
                    raise ValueError("video changed or became unreadable during annotation")
                for observation in observations:
                    annotation_store.update(observation)
                self._draw_frame(
                    frame,
                    list(observations),
                    annotation_store,
                    {
                        track_id
                        for event in events
                        for track_id in event.track_ids
                    },
                    events,
                    timestamp=frame_index / fps,
                )
                writer.write(frame)
                if progress_callback:
                    progress_callback(
                        min(0.99, 0.8 + 0.19 * (frame_index + 1) / total)
                    )
        except Exception:
            writer.release()
            destination.unlink(missing_ok=True)
            raise
        finally:
            capture.release()
            writer.release()

    @staticmethod
    def _draw_frame(
        frame: np.ndarray,
        observations: list[TrackObservation],
        store: TrajectoryStore,
        abnormal_track_ids: set[int],
        events: list[AnomalyEvent],
        *,
        timestamp: float,
    ) -> None:
        del abnormal_track_ids  # Historical events remain in JSON, not frame color.
        active_events = [
            event
            for event in events
            if event.start_time <= timestamp <= event.end_time
        ]
        event_labels: dict[int, tuple[str, float]] = {}
        for event in active_events:
            for track_id in event.track_ids:
                previous = event_labels.get(track_id)
                if previous is None or event.confidence > previous[1]:
                    event_labels[track_id] = (
                        event.event_type,
                        event.confidence,
                    )
        active_event_track_ids = set(event_labels)

        for observation in observations:
            is_abnormal = observation.track_id in active_event_track_ids
            color = (0, 0, 255) if is_abnormal else (0, 200, 0)
            x1, y1, x2, y2 = (
                int(value) for value in observation.bbox
            )
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            label = f"ID {observation.track_id}"
            if is_abnormal:
                event_type, confidence = event_labels.get(
                    observation.track_id,
                    ("suspected", 0.0),
                )
                label += f" | {event_type} | {confidence:.3f}"
            cv2.putText(
                frame,
                label,
                (x1, max(18, y1 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                2,
                cv2.LINE_AA,
            )

            if is_abnormal:
                state = store.get(observation.track_id)
                if state and len(state.points) >= 2:
                    trajectory = np.array(
                        [
                            [int(point.x), int(point.y)]
                            for point in state.points
                        ],
                        dtype=np.int32,
                    ).reshape((-1, 1, 2))
                    cv2.polylines(
                        frame,
                        [trajectory],
                        False,
                        color,
                        3,
                        cv2.LINE_AA,
                    )
