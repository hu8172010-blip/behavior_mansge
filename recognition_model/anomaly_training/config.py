from pathlib import Path


DATA_ROOT = Path(r"D:\datasets\abnormal_behavior")
MAX_DATA_BYTES = 10 * 1024**3
LABELS = {"normal": 0, "violence": 1, "fall": 2}
FRAME_COUNT = 16
