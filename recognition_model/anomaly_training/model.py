"""R3D-18 construction, phase freezing, and portable checkpoint loading."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import torch
from torch import nn
from torchvision.models.video import R3D_18_Weights, r3d_18


CLASS_NAMES = ("normal", "violence", "fall")


def build_model(num_classes: int = 3, pretrained: bool = True) -> nn.Module:
    """Build the Kinetics-400 R3D-18 backbone with exactly the requested head."""
    if num_classes != 3:
        raise ValueError("this classifier is defined for exactly 3 classes: normal, violence, fall")
    weights = R3D_18_Weights.KINETICS400_V1 if pretrained else None
    model = r3d_18(weights=weights)
    model.fc = nn.Linear(model.fc.in_features, num_classes)
    return model


def _set_trainable(model: nn.Module, prefixes: tuple[str, ...]) -> None:
    for name, parameter in model.named_parameters():
        parameter.requires_grad = name.startswith(prefixes)


def configure_head_training(model: nn.Module) -> None:
    """Freeze the backbone and leave only the R3D classification head trainable."""
    _set_trainable(model, ("fc.",))


def configure_layer4_training(model: nn.Module) -> None:
    """Freeze early R3D layers and finetune ``layer4`` together with ``fc``."""
    _set_trainable(model, ("layer4.", "fc."))


def _load_raw_checkpoint(path: str | Path, device: str | torch.device) -> Mapping[str, Any]:
    # Checkpoints contain tensors and primitive metadata only. ``weights_only``
    # avoids unpickling arbitrary code when evaluation receives an external path.
    # map_location keeps CPU evaluation safe for CUDA-created checkpoints.
    payload = torch.load(Path(path), map_location=torch.device(device), weights_only=True)
    if not isinstance(payload, Mapping) or "model" not in payload:
        raise ValueError("checkpoint must be a mapping containing a 'model' state dict")
    return payload


def load_checkpoint(path: str | Path, device: str | torch.device = "cpu") -> tuple[nn.Module, dict[str, Any]]:
    """Restore an R3D-18 state dict and its JSON-like metadata onto ``device``."""
    payload = _load_raw_checkpoint(path, device)
    architecture = payload.get("architecture", {})
    num_classes = int(architecture.get("num_classes", 3)) if isinstance(architecture, Mapping) else 3
    state = payload["model"]
    if not isinstance(state, Mapping):
        raise ValueError("checkpoint 'model' is not a state dict")
    if "fc.weight" in state:
        num_classes = int(state["fc.weight"].shape[0])
    model = build_model(num_classes=num_classes, pretrained=False)
    model.load_state_dict(state)
    model.to(torch.device(device))
    metadata = {key: value for key, value in payload.items() if key != "model"}
    return model, metadata
