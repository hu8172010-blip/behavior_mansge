"""Exact three-class sklearn metrics and a dependency-light PNG heatmap."""

from __future__ import annotations

import struct
import zlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from sklearn.metrics import confusion_matrix, precision_recall_fscore_support


CLASS_NAMES = ("normal", "violence", "fall")
LABELS = (0, 1, 2)


@dataclass(frozen=True, slots=True)
class MetricReport:
    per_class: dict[str, dict[str, float | int]]
    macro_precision: float
    macro_recall: float
    macro_f1: float
    confusion_matrix: list[list[int]]
    accepted: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "per_class": self.per_class,
            "macro_precision": self.macro_precision,
            "macro_recall": self.macro_recall,
            "macro_f1": self.macro_f1,
            "confusion_matrix": self.confusion_matrix,
            "accepted": self.accepted,
        }


def compute_metrics(targets: Iterable[int], predictions: Iterable[int]) -> MetricReport:
    """Calculate robust metrics for all labels even if a class is absent."""
    truth, predicted = list(targets), list(predictions)
    precision, recall, f1, support = precision_recall_fscore_support(
        truth, predicted, labels=LABELS, zero_division=0
    )
    per_class = {
        name: {
            "precision": float(precision[index]),
            "recall": float(recall[index]),
            "f1": float(f1[index]),
            "support": int(support[index]),
        }
        for index, name in enumerate(CLASS_NAMES)
    }
    macro_precision = float(sum(precision) / len(LABELS))
    macro_recall = float(sum(recall) / len(LABELS))
    macro_f1 = float(sum(f1) / len(LABELS))
    matrix = confusion_matrix(truth, predicted, labels=LABELS).astype(int).tolist()
    accepted = macro_f1 >= 0.75 and per_class["violence"]["recall"] >= 0.80 and per_class["fall"]["recall"] >= 0.80
    return MetricReport(per_class, macro_precision, macro_recall, macro_f1, matrix, bool(accepted))


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)


def write_confusion_matrix(report: MetricReport, path: str | Path) -> Path:
    """Write a valid RGB PNG heatmap without imposing a matplotlib runtime dependency."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    cell, margin = 64, 4
    width = height = cell * 3 + margin * 4
    maximum = max(1, *(value for row in report.confusion_matrix for value in row))
    rows: list[bytes] = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            column = (x - margin) // (cell + margin)
            line = (y - margin) // (cell + margin)
            inside = 0 <= column < 3 and 0 <= line < 3 and (x - margin) % (cell + margin) < cell and (y - margin) % (cell + margin) < cell
            if inside:
                intensity = round(255 * report.confusion_matrix[line][column] / maximum)
                row.extend((255 - intensity, 255 - intensity // 2, 255))
            else:
                row.extend((245, 245, 245))
        rows.append(b"\x00" + bytes(row))
    data = b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + _png_chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + _png_chunk(b"IEND", b"")
    temporary = target.with_name(f".{target.name}.tmp")
    try:
        temporary.write_bytes(data)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target
