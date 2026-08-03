"""Safe optional R3D-18 inference for fixed RGB video clips."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import cv2
import numpy as np
import torch
from torch import nn

from anomaly_training.dataset import KINETICS400_MEAN, KINETICS400_STD
from anomaly_training.model import CLASS_NAMES, load_checkpoint


FRAME_COUNT = 16
IMAGE_SIZE = 112
_RESIZE_SHORT_EDGE = 128


@dataclass(frozen=True, slots=True)
class ClipPrediction:
    """Classifier probabilities tied to the source interval that produced them."""

    probabilities: dict[str, float]
    label: str
    confidence: float
    start_time: float | None = None
    end_time: float | None = None


def _resize_center_crop(frame: np.ndarray) -> np.ndarray:
    height, width = frame.shape[:2]
    scale = _RESIZE_SHORT_EDGE / min(height, width)
    resized = cv2.resize(
        frame,
        (round(width * scale), round(height * scale)),
        interpolation=cv2.INTER_LINEAR,
    )
    top = (resized.shape[0] - IMAGE_SIZE) // 2
    left = (resized.shape[1] - IMAGE_SIZE) // 2
    return np.ascontiguousarray(resized[top : top + IMAGE_SIZE, left : left + IMAGE_SIZE])


def preprocess_rgb_frames(frames: Sequence[np.ndarray]) -> torch.Tensor:
    """Apply the dataset's deterministic evaluation transform to RGB frames."""
    if len(frames) != FRAME_COUNT:
        raise ValueError(f"expected exactly {FRAME_COUNT} RGB frames")
    processed: list[np.ndarray] = []
    for frame in frames:
        array = np.asarray(frame)
        if array.ndim != 3 or array.shape[2] != 3 or min(array.shape[:2]) <= 0:
            raise ValueError("each frame must have shape (height, width, 3) in RGB order")
        if array.dtype != np.uint8:
            raise ValueError("RGB frames must be uint8 RGB values in the range 0..255")
        processed.append(_resize_center_crop(array))
    array = np.stack(processed, axis=0).astype(np.float32) / 255.0
    clip = torch.from_numpy(array).permute(3, 0, 1, 2)
    mean = torch.tensor(KINETICS400_MEAN, dtype=clip.dtype).view(3, 1, 1, 1)
    std = torch.tensor(KINETICS400_STD, dtype=clip.dtype).view(3, 1, 1, 1)
    return ((clip - mean) / std).unsqueeze(0)


class R3D18ClipClassifier:
    """A loaded model with deterministic, no-grad clip prediction."""

    def __init__(self, model: nn.Module, device: str | torch.device = "cpu") -> None:
        self.device = torch.device(device)
        self.model = model.to(self.device).eval()

    def predict(
        self,
        frames: Sequence[np.ndarray],
        *,
        start_time: float | None = None,
        end_time: float | None = None,
    ) -> ClipPrediction:
        clip = preprocess_rgb_frames(frames).to(self.device)
        with torch.inference_mode():
            probabilities = torch.softmax(self.model(clip), dim=1)
        if probabilities.shape != (1, len(CLASS_NAMES)):
            raise ValueError("classifier returned an invalid probability shape")
        if (
            not torch.isfinite(probabilities).all()
            or not torch.all((probabilities >= 0) & (probabilities <= 1))
            or not torch.isclose(
                probabilities.sum(dim=1),
                torch.ones(1, device=probabilities.device),
                rtol=0.0,
                atol=1e-5,
            ).all()
        ):
            raise ValueError("classifier returned invalid probabilities")
        values = probabilities[0].detach().to("cpu").tolist()
        named = {name: float(value) for name, value in zip(CLASS_NAMES, values)}
        label = max(named, key=named.__getitem__)
        return ClipPrediction(named, label, named[label], start_time, end_time)


def _valid_labels(metadata: Mapping[str, object]) -> bool:
    expected = {name: index for index, name in enumerate(CLASS_NAMES)}
    labels = metadata.get("label_mapping")
    architecture = metadata.get("architecture")
    if labels is None and architecture is None:
        return False
    if labels is not None:
        if not isinstance(labels, Mapping):
            return False
        try:
            if {str(name): int(index) for name, index in labels.items()} != expected:
                return False
        except (TypeError, ValueError):
            return False
    if architecture is not None:
        if not isinstance(architecture, Mapping):
            return False
        if (
            architecture.get("name") != "r3d_18"
            or architecture.get("num_classes") != 3
            or tuple(architecture.get("classes", ())) != CLASS_NAMES
        ):
            return False
    return True


class OptionalClipClassifier:
    """Best-effort checkpoint loading that safely leaves rule-only processing alive."""

    def __init__(self, checkpoint_path: str | Path) -> None:
        self.checkpoint_path = Path(checkpoint_path)
        self.available = False
        self._classifier: R3D18ClipClassifier | None = None
        self.status: dict[str, str] = {"mode": "rules_only", "error": "checkpoint not found"}
        if not self.checkpoint_path.is_file():
            return
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        try:
            model, metadata = load_checkpoint(self.checkpoint_path, device=device)
            if not _valid_labels(metadata):
                self.status["error"] = "invalid checkpoint labels"
                return
            self._classifier = R3D18ClipClassifier(model, device)
        except (ValueError, RuntimeError, TypeError):
            # Deliberately do not expose checkpoint paths, exception text, or host details.
            self.status["error"] = "invalid checkpoint data; export a Task 5 R3D-18 checkpoint"
            return
        except Exception:
            self.status["error"] = "checkpoint unreadable; provide a valid Task 5 checkpoint"
            return
        self.available = True
        self.status = {"mode": "classifier", "device": str(device)}

    def new_session(self) -> "OptionalClipClassifier":
        """Return a fresh wrapper whose mutable fallback state is video-local."""
        return type(self)(self.checkpoint_path)

    def predict(
        self,
        frames: Sequence[np.ndarray],
        *,
        start_time: float | None = None,
        end_time: float | None = None,
    ) -> ClipPrediction | None:
        if not self.available or self._classifier is None:
            return None
        try:
            return self._classifier.predict(frames, start_time=start_time, end_time=end_time)
        except ValueError as error:
            self.available = False
            self._classifier = None
            message = "classifier produced invalid probabilities" if str(error) == "classifier returned invalid probabilities" else "classifier inference failed"
            self.status = {"mode": "rules_only", "error": message}
            return None
        except Exception:
            self.available = False
            self._classifier = None
            self.status = {"mode": "rules_only", "error": "classifier inference failed"}
            return None
