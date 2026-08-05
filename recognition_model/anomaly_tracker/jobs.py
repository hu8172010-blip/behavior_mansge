from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path
import shutil
from threading import Lock
import time
from uuid import uuid4

from anomaly_training.storage import ManagedArtifactLedger


@dataclass(frozen=True, slots=True)
class JobRecord:
    job_id: str
    status: str
    progress: float
    input_path: Path
    output_dir: Path
    original_name: str
    created_at: float
    updated_at: float
    error: dict[str, str] | None = None
    model_status: dict[str, object] | None = None

    def public_dict(self) -> dict[str, object]:
        # 内部使用 "running"，对外统一暴露为 "processing"，与前端状态约定一致
        public_status = "processing" if self.status == "running" else self.status
        return {
            "job_id": self.job_id,
            "status": public_status,
            "progress": round(self.progress, 4),
            "original_name": self.original_name,
            "error": deepcopy(self.error),
            "model_status": deepcopy(self.model_status),
            "result_url": (
                f"/api/jobs/{self.job_id}/result"
                if self.status == "completed"
                else None
            ),
            "video_url": (
                f"/api/jobs/{self.job_id}/video"
                if self.status == "completed"
                else None
            ),
        }


class JobStore:
    def __init__(
        self,
        runs_dir: str | Path,
        *,
        max_total_bytes: int = 4 * 1024 * 1024 * 1024,
        ttl_seconds: float = 24 * 60 * 60,
        artifact_ledger: ManagedArtifactLedger | None = None,
    ) -> None:
        if max_total_bytes <= 0 or ttl_seconds < 0:
            raise ValueError("job storage limits are invalid")
        self.runs_dir = Path(runs_dir).resolve()
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.max_total_bytes = max_total_bytes
        self.ttl_seconds = ttl_seconds
        self.artifact_ledger = artifact_ledger
        self._jobs: dict[str, JobRecord] = {}
        self._reservations: dict[str, int] = {}
        self._lock = Lock()

    def _disk_size(self) -> int:
        total = sum(
            path.stat().st_size
            for path in self.runs_dir.rglob("*")
            if path.is_file()
        )
        if self.artifact_ledger is not None:
            for bookkeeping in (
                self.artifact_ledger.state_path,
                self.artifact_ledger.lock_path,
            ):
                if (
                    bookkeeping is not None
                    and bookkeeping.is_file()
                    and (
                        bookkeeping == self.runs_dir
                        or self.runs_dir in bookkeeping.parents
                    )
                ):
                    total -= bookkeeping.stat().st_size
        return max(0, total)

    @staticmethod
    def _snapshot(record: JobRecord) -> JobRecord:
        return replace(
            record,
            error=deepcopy(record.error),
            model_status=deepcopy(record.model_status),
        )

    def create(self, suffix: str, original_name: str) -> JobRecord:
        job_id = uuid4().hex
        output_dir = self.runs_dir / job_id
        output_dir.mkdir(parents=True, exist_ok=False)
        now = time.time()
        record = JobRecord(
            job_id=job_id,
            status="queued",
            progress=0.0,
            input_path=output_dir / f"input{suffix}",
            output_dir=output_dir,
            original_name=original_name,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._jobs[job_id] = record
            self._reservations[job_id] = 0
            return self._snapshot(record)

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            record = self._jobs.get(job_id)
            return (
                self._snapshot(record)
                if record is not None
                else None
            )

    def public_dict(self, job_id: str) -> dict[str, object] | None:
        with self._lock:
            record = self._jobs.get(job_id)
            return (
                record.public_dict()
                if record is not None
                else None
            )

    def update(self, job_id: str, **changes: object) -> JobRecord:
        with self._lock:
            record = self._jobs[job_id]
            copied_changes = {
                key: deepcopy(value)
                for key, value in changes.items()
            }
            copied_changes["updated_at"] = time.time()
            updated = replace(record, **copied_changes)
            self._jobs[job_id] = updated
            return self._snapshot(updated)

    def delete(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)
            self._reservations.pop(job_id, None)

    def reserve_bytes(self, job_id: str, amount: int) -> None:
        if amount < 0:
            raise ValueError("reservation amount must not be negative")
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(job_id)
            total = self._disk_size() + sum(self._reservations.values())
            if total + amount > self.max_total_bytes:
                raise OSError("run storage quota exceeded")
            if self.artifact_ledger is not None:
                try:
                    self.artifact_ledger.reserve(amount)
                except Exception as error:
                    raise OSError("managed artifact quota exceeded") from error
            self._reservations[job_id] += amount

    def release_bytes(self, job_id: str, amount: int | None = None) -> None:
        with self._lock:
            current = self._reservations.get(job_id)
            if current is None:
                return
            self._reservations[job_id] = (
                0 if amount is None else max(0, current - amount)
            )

    def cleanup_expired(self, now: float | None = None) -> list[str]:
        current = time.time() if now is None else now
        terminal = {"completed", "failed"}
        with self._lock:
            expired = [
                job_id
                for job_id, record in self._jobs.items()
                if record.status in terminal
                and current - record.updated_at >= self.ttl_seconds
            ]
            directories = [
                self._jobs[job_id].output_dir
                for job_id in expired
            ]
            for job_id in expired:
                self._jobs.pop(job_id, None)
                self._reservations.pop(job_id, None)
        for directory in directories:
            shutil.rmtree(directory, ignore_errors=True)
        return sorted(expired)
