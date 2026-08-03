from __future__ import annotations

import os
from typing import Protocol

import numpy as np

from .domain import TrackObservation


class PersonTracker(Protocol):
    def track(
        self,
        frame: np.ndarray,
        timestamp: float,
    ) -> list[TrackObservation]: ...


class UltralyticsPersonTracker:
    """Lazy-loaded YOLO Pose + BoT-SORT adapter."""

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or os.getenv(
            "ANOMALY_MODEL",
            "yolo26n-pose.pt",
        )
        self._model = None

    def _load_model(self):
        if self._model is None:
            try:
                from ultralytics import YOLO
            except ImportError as error:
                raise RuntimeError(
                    "缺少 ultralytics，请先执行 pip install -r requirements.txt"
                ) from error
            self._model = YOLO(self.model_name)
        return self._model

    def track(
        self,
        frame: np.ndarray,
        timestamp: float,
    ) -> list[TrackObservation]:
        model = self._load_model()
        result = model.track(
            frame,
            persist=True,
            tracker="botsort.yaml",
            classes=[0],
            verbose=False,
        )[0]
        if result.boxes is None or result.boxes.id is None:
            return []

        boxes = result.boxes.xyxy.cpu().tolist()
        track_ids = result.boxes.id.int().cpu().tolist()
        confidences = result.boxes.conf.cpu().tolist()
        pose_data = None
        if result.keypoints is not None and result.keypoints.data is not None:
            pose_data = result.keypoints.data.cpu().tolist()

        observations: list[TrackObservation] = []
        for index, (track_id, box, confidence) in enumerate(
            zip(track_ids, boxes, confidences)
        ):
            keypoints = ()
            if pose_data is not None and index < len(pose_data):
                keypoints = tuple(
                    (float(point[0]), float(point[1]), float(point[2]))
                    for point in pose_data[index]
                )
            observations.append(
                TrackObservation(
                    track_id=int(track_id),
                    timestamp=timestamp,
                    bbox=tuple(float(value) for value in box),
                    confidence=float(confidence),
                    keypoints=keypoints,
                )
            )
        return observations
