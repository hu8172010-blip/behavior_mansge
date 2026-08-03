import json
import mimetypes
import time
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings


class AnomalyClient:
    """HTTP client for the local anomaly_tracker inference service."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.anomaly_tracker_url).rstrip("/")

    def submit(self, video_path: str | Path, calibration: dict[str, Any] | None = None) -> str:
        payload = {"calibration": json.dumps(calibration or {})}
        with httpx.Client(timeout=60.0) as client:
            with open(video_path, "rb") as f:
                name = Path(video_path).name
                content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
                files = {"video": (name, f, content_type)}
                resp = client.post(f"{self.base_url}/api/jobs", data=payload, files=files)
            resp.raise_for_status()
            return resp.json()["job_id"]

    def status(self, job_id: str) -> dict[str, Any]:
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(f"{self.base_url}/api/jobs/{job_id}")
            resp.raise_for_status()
            return resp.json()

    def result(self, job_id: str) -> dict[str, Any]:
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(f"{self.base_url}/api/jobs/{job_id}/result")
            resp.raise_for_status()
            return resp.json()

    def wait(self, job_id: str, poll_interval: float = 1.0, timeout: float = 1800.0) -> dict[str, Any]:
        start = time.time()
        while time.time() - start < timeout:
            st = self.status(job_id)
            status = st.get("status")
            if status == "completed":
                return self.result(job_id)
            if status in ("failed", "error"):
                raise RuntimeError(st.get("error", "推理失败"))
            if status == "cancelled":
                raise RuntimeError("推理任务已取消")
            time.sleep(poll_interval)
        raise TimeoutError("推理等待超时")

    def analyze(self, video_path: str | Path, calibration: dict[str, Any] | None = None) -> dict[str, Any]:
        job_id = self.submit(video_path, calibration)
        return self.wait(job_id)
