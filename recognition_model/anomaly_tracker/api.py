from __future__ import annotations

import json
import logging
import multiprocessing
import os
import shutil
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from queue import Empty
from threading import BoundedSemaphore, Lock

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .jobs import JobRecord, JobStore
from .processor import VideoProcessor
from .rules import RuleConfig, rule_config_from_mapping
from anomaly_training.config import DATA_ROOT, MAX_DATA_BYTES
from anomaly_training.storage import ManagedArtifactLedger


LOGGER = logging.getLogger(__name__)
ALLOWED_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
MIME_BY_EXTENSION = {
    ".mp4": {"video/mp4"},
    ".avi": {"video/x-msvideo", "video/avi"},
    ".mov": {"video/quicktime"},
    ".mkv": {"video/x-matroska", "video/matroska"},
    ".webm": {"video/webm"},
}
MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024
PUBLIC_PROCESSING_ERROR = {
    "code": "processing_failed",
    "message": "视频处理失败",
}
PUBLIC_SHUTDOWN_ERROR = {
    "code": "service_shutdown",
    "message": "服务关闭，任务未执行",
}
PUBLIC_TIMEOUT_ERROR = {
    "code": "processing_timeout",
    "message": "视频处理超过时间限制",
}
PUBLIC_PROGRESS_TIMEOUT_ERROR = {
    "code": "progress_timeout",
    "message": "推理过程长时间没有进展，任务被判定为卡死",
}
ProcessorFactory = Callable[[], VideoProcessor]


class BoundedJobExecutor:
    """Thread pool with a strict running-plus-queued capacity."""

    def __init__(self, *, max_workers: int, max_queued_jobs: int) -> None:
        if max_workers <= 0 or max_queued_jobs < 0:
            raise ValueError("invalid job executor capacity")
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="video-job",
        )
        self._slots = BoundedSemaphore(
            max_workers + max_queued_jobs
        )
        self._lock = Lock()
        self._accepting = True
        self._futures: set[Future[object]] = set()

    def submit(
        self,
        callback: Callable[..., object],
        *args: object,
        on_cancel: Callable[[], None] | None = None,
    ) -> bool:
        if not self.reserve():
            return False
        try:
            self.submit_reserved(callback, *args, on_cancel=on_cancel)
        except Exception:
            self.release_reservation()
            raise
        return True

    def reserve(self) -> bool:
        with self._lock:
            if not self._accepting:
                return False
            if not self._slots.acquire(blocking=False):
                return False
            return True

    def release_reservation(self) -> None:
        self._slots.release()

    def submit_reserved(
        self,
        callback: Callable[..., object],
        *args: object,
        on_cancel: Callable[[], None] | None = None,
    ) -> None:
        with self._lock:
            if not self._accepting:
                raise RuntimeError("executor is shutting down")
            try:
                future = self._pool.submit(callback, *args)
            except Exception:
                raise
            self._futures.add(future)

        def finished(completed: Future[object]) -> None:
            try:
                if completed.cancelled() and on_cancel is not None:
                    on_cancel()
            finally:
                with self._lock:
                    self._futures.discard(completed)
                self._slots.release()

        future.add_done_callback(finished)

    def shutdown(self) -> None:
        with self._lock:
            self._accepting = False
        self._pool.shutdown(wait=True, cancel_futures=True)


class UploadAdmissionMiddleware:
    """Reserve a queue slot before multipart parsing consumes the request body."""

    def __init__(self, app, *, executor: BoundedJobExecutor) -> None:
        self.app = app
        self.executor = executor

    async def __call__(self, scope, receive, send) -> None:
        reserved = False
        if (
            scope.get("type") == "http"
            and scope.get("method") == "POST"
            and scope.get("path") == "/api/jobs"
        ):
            reserved = self.executor.reserve()
            if not reserved:
                await JSONResponse(
                    status_code=503,
                    content={"detail": "处理队列已满，请稍后重试"},
                )(scope, receive, send)
                return
            scope.setdefault("state", {})[
                "upload_admission_reserved"
            ] = True
        try:
            await self.app(scope, receive, send)
        finally:
            state = scope.get("state", {})
            if reserved and state.pop("upload_admission_reserved", False):
                self.executor.release_reservation()


def create_app(
    runs_dir: str | Path = "runs",
    processor_factory: ProcessorFactory = VideoProcessor,
    *,
    max_workers: int = 2,
    max_queued_jobs: int = 8,
    max_upload_bytes: int = MAX_UPLOAD_BYTES,
    max_runs_bytes: int = 4 * 1024 * 1024 * 1024,
    output_reservation_bytes: int = 512 * 1024 * 1024,
    run_ttl_seconds: float = 24 * 60 * 60,
    processing_timeout_seconds: float = 30 * 60,
    progress_timeout_seconds: float = 10 * 60,
    managed_artifact_limit_bytes: int = MAX_DATA_BYTES,
    managed_ledger_path: str | Path | None = None,
) -> FastAPI:
    if (
        max_upload_bytes <= 0
        or max_runs_bytes <= 0
        or output_reservation_bytes < 0
        or run_ttl_seconds < 0
        or processing_timeout_seconds <= 0
        or managed_artifact_limit_bytes <= 0
    ):
        raise ValueError("API resource limits are invalid")
    artifact_ledger = ManagedArtifactLedger(
        [
            DATA_ROOT,
            Path(runs_dir),
            Path("training_runs"),
            Path("models"),
        ],
        limit_bytes=managed_artifact_limit_bytes,
        state_path=(
            Path(managed_ledger_path)
            if managed_ledger_path is not None
            else Path(runs_dir) / ".managed-artifact-ledger.json"
        ),
    )
    store = JobStore(
        runs_dir,
        max_total_bytes=max_runs_bytes,
        ttl_seconds=run_ttl_seconds,
        artifact_ledger=artifact_ledger,
    )
    executor = BoundedJobExecutor(
        max_workers=max_workers,
        max_queued_jobs=max_queued_jobs,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            executor.shutdown()

    app = FastAPI(
        title="人员异常行为与轨迹确认",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.job_store = store
    app.state.processor_factory = processor_factory
    app.state.job_executor = executor
    app.add_middleware(UploadAdmissionMiddleware, executor=executor)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/jobs", status_code=status.HTTP_202_ACCEPTED)
    async def create_job(
        request: Request,
        video: UploadFile = File(...),
        calibration: str | None = Form(None),
    ) -> dict[str, object]:
        store.cleanup_expired()
        original_name = video.filename or "video"
        suffix = Path(original_name).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail="仅支持 MP4、AVI、MOV、MKV 和 WEBM 视频",
            )
        media_type = (video.content_type or "").split(";", 1)[0].lower()
        if media_type not in MIME_BY_EXTENSION[suffix]:
            raise HTTPException(
                status_code=400,
                detail="视频扩展名与 MIME 类型不匹配",
            )
        rule_config: RuleConfig | None = None
        if calibration:
            try:
                profile = json.loads(calibration)
                if not isinstance(profile, dict):
                    raise ValueError("calibration must be a JSON object")
                rule_config = rule_config_from_mapping(profile)
            except (ValueError, TypeError, json.JSONDecodeError) as error:
                raise HTTPException(
                    status_code=422,
                    detail=f"invalid calibration profile: {error}",
                ) from error

        record = store.create(suffix, Path(original_name).name)
        total = 0
        header = bytearray()
        try:
            with record.input_path.open("wb") as target:
                while chunk := await video.read(1024 * 1024):
                    total += len(chunk)
                    if total > max_upload_bytes:
                        raise HTTPException(
                            status_code=413,
                            detail="视频超过上传大小限制",
                        )
                    if len(header) < 64:
                        header.extend(chunk[: 64 - len(header)])
                    try:
                        store.reserve_bytes(record.job_id, len(chunk))
                    except OSError as error:
                        raise HTTPException(
                            status_code=507,
                            detail="运行目录存储配额不足",
                        ) from error
                    try:
                        target.write(chunk)
                    finally:
                        store.release_bytes(record.job_id, len(chunk))
        except Exception:
            _delete_job_files(store, record)
            raise
        finally:
            await video.close()

        if total == 0:
            _delete_job_files(store, record)
            raise HTTPException(
                status_code=400,
                detail="上传的视频为空",
            )
        if not _has_video_signature(suffix, bytes(header)):
            _delete_job_files(store, record)
            raise HTTPException(
                status_code=400,
                detail="视频容器签名无效",
            )

        LOGGER.info(
            "Job %s created: name=%s size=%d bytes suffix=%s calibration=%s",
            record.job_id,
            original_name,
            total,
            suffix,
            bool(calibration),
        )

        try:
            store.reserve_bytes(record.job_id, output_reservation_bytes)
            executor.submit_reserved(
                _run_job,
                store,
                processor_factory,
                record,
                processing_timeout_seconds,
                progress_timeout_seconds,
                output_reservation_bytes,
                rule_config,
                on_cancel=lambda: _cancel_job(store, record.job_id),
            )
            request.scope["state"]["upload_admission_reserved"] = False
        except Exception as error:
            store.release_bytes(record.job_id)
            _delete_job_files(store, record)
            raise HTTPException(
                status_code=503,
                detail="任务无法进入处理队列",
            ) from error
        payload = store.public_dict(record.job_id)
        if payload is None:
            raise HTTPException(status_code=503, detail="任务未能创建")
        return payload

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, object]:
        store.cleanup_expired()
        payload = store.public_dict(job_id)
        if payload is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        return payload

    @app.delete("/api/jobs/{job_id}", status_code=204)
    def delete_job(job_id: str) -> Response:
        record = _require_job(store, job_id)
        if record.status not in {"completed", "failed"}:
            raise HTTPException(status_code=409, detail="运行中的任务不能清理")
        _delete_job_files(store, record)
        return Response(status_code=204)

    @app.get("/api/jobs/{job_id}/result")
    def get_result(job_id: str):
        record = _require_job(store, job_id)
        if record.status != "completed":
            raise HTTPException(status_code=409, detail="任务尚未完成")
        result_path = record.output_dir / "result.json"
        if not result_path.is_file():
            raise HTTPException(status_code=404, detail="结果文件不存在")
        return json.loads(result_path.read_text(encoding="utf-8"))

    @app.get("/api/jobs/{job_id}/video")
    def get_video(job_id: str) -> FileResponse:
        record = _require_job(store, job_id)
        if record.status != "completed":
            raise HTTPException(status_code=409, detail="任务尚未完成")
        video_path = record.output_dir / "annotated.mp4"
        if not video_path.is_file():
            raise HTTPException(status_code=404, detail="标注视频不存在")
        return FileResponse(
            video_path,
            media_type="video/mp4",
            filename=f"{record.job_id}-annotated.mp4",
        )

    static_dir = Path(__file__).with_name("static")
    app.mount(
        "/static",
        StaticFiles(directory=static_dir),
        name="static",
    )

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    return app


def _has_video_signature(suffix: str, header: bytes) -> bool:
    if suffix in {".mp4", ".mov"}:
        return len(header) >= 12 and header[4:8] == b"ftyp"
    if suffix == ".avi":
        return (
            len(header) >= 12
            and header[:4] == b"RIFF"
            and header[8:12] == b"AVI "
        )
    if suffix in {".mkv", ".webm"}:
        return header.startswith(b"\x1a\x45\xdf\xa3")
    return False


def _delete_job_files(store: JobStore, record: JobRecord) -> None:
    store.delete(record.job_id)
    shutil.rmtree(record.output_dir, ignore_errors=True)


def _require_job(store: JobStore, job_id: str) -> JobRecord:
    record = store.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return record


def _cancel_job(store: JobStore, job_id: str) -> None:
    record = store.get(job_id)
    if record is not None and record.status == "queued":
        store.update(
            job_id,
            status="failed",
            error=PUBLIC_SHUTDOWN_ERROR,
        )


def _run_job(
    store: JobStore,
    processor_factory: ProcessorFactory,
    record: JobRecord,
    processing_timeout_seconds: float,
    progress_timeout_seconds: float,
    output_reservation_bytes: int,
    rule_config: RuleConfig | None = None,
) -> None:
    staging_dir = record.output_dir / ".processing"
    shutil.rmtree(staging_dir, ignore_errors=True)
    context = multiprocessing.get_context("spawn")
    messages = context.Queue()
    worker = context.Process(
        target=_processor_child,
        args=(
            processor_factory,
            record.input_path,
            staging_dir,
            rule_config,
            messages,
        ),
        name=f"processor-{record.job_id[:8]}",
    )
    try:
        store.update(record.job_id, status="running", progress=0.01)
        worker.start()
        LOGGER.info("Job %s worker started (pid %s)", record.job_id, worker.pid)
        deadline = time.monotonic() + processing_timeout_seconds
        result: dict[str, object] | None = None
        error_message: str | None = None
        last_progress_time = time.monotonic()
        while (
            worker.is_alive()
            and time.monotonic() < deadline
            and time.monotonic() - last_progress_time < progress_timeout_seconds
        ):
            worker.join(
                timeout=min(
                    0.05,
                    max(0.0, deadline - time.monotonic()),
                )
            )
            new_result, new_error, received = _drain_processor_messages(
                messages,
                store,
                record.job_id,
                result,
                error_message,
            )
            if received:
                last_progress_time = time.monotonic()
            if new_result is not None:
                result = new_result
            if new_error is not None:
                error_message = new_error
        if worker.is_alive():
            no_progress = (
                time.monotonic() - last_progress_time
            ) >= progress_timeout_seconds
            error = (
                PUBLIC_PROGRESS_TIMEOUT_ERROR
                if no_progress
                else PUBLIC_TIMEOUT_ERROR
            )
            LOGGER.warning(
                "Job %s timed out: no_progress=%s deadline_reached=%s",
                record.job_id,
                no_progress,
                time.monotonic() >= deadline,
            )
            worker.terminate()
            worker.join(timeout=5.0)
            if worker.is_alive():
                worker.kill()
                worker.join(timeout=5.0)
            if worker.is_alive():
                raise RuntimeError("processor worker could not be terminated")
            store.update(
                record.job_id,
                status="failed",
                error=error,
            )
            return
        result, error_message, _ = _drain_processor_messages(
            messages,
            store,
            record.job_id,
            result,
            error_message,
            wait_seconds=2.0,
        )
        if error_message is not None:
            raise RuntimeError(error_message)
        if not isinstance(result, dict):
            raise TypeError("processor returned an invalid result")
        store.release_bytes(record.job_id, output_reservation_bytes)
        store.reserve_bytes(record.job_id, 0)
        _publish_staged_outputs(staging_dir, record.output_dir)
        model_status = result.get("model_status")
        store.update(
            record.job_id,
            status="completed",
            progress=1.0,
            model_status=(
                dict(model_status)
                if isinstance(model_status, dict)
                else None
            ),
        )
    except Exception:
        LOGGER.exception("Video job %s failed", record.job_id)
        store.update(
            record.job_id,
            status="failed",
            error=PUBLIC_PROCESSING_ERROR,
        )
    finally:
        if worker.is_alive():
            worker.terminate()
            worker.join(timeout=5.0)
        shutil.rmtree(staging_dir, ignore_errors=True)
        messages.close()
        messages.join_thread()
        store.release_bytes(record.job_id)


def _processor_child(
    processor_factory: ProcessorFactory,
    input_path: Path,
    staging_dir: Path,
    rule_config: RuleConfig | None,
    messages,
) -> None:
    try:
        processor = processor_factory()
        if rule_config is not None:
            setattr(processor, "rule_config", rule_config)
        result = processor.process(
            input_path,
            staging_dir,
            lambda value: messages.put(("progress", float(value))),
        )
        messages.put(("result", result))
    except BaseException as error:
        messages.put(("error", f"{type(error).__name__}: {error}"))


def _drain_processor_messages(
    messages,
    store: JobStore,
    job_id: str,
    result: dict[str, object] | None,
    error_message: str | None,
    wait_seconds: float = 0.0,
) -> tuple[dict[str, object] | None, str | None, int]:
    first = True
    received = 0
    while True:
        try:
            kind, payload = messages.get(
                timeout=wait_seconds if first else 0.0
            )
        except Empty:
            break
        first = False
        received += 1
        if kind == "progress":
            store.update(job_id, progress=float(payload))
        elif kind == "result" and isinstance(payload, dict):
            result = payload
        elif kind == "error":
            error_message = str(payload)
    return result, error_message, received


def _publish_staged_outputs(staging_dir: Path, output_dir: Path) -> None:
    required = {"result.json", "annotated.mp4"}
    staged = {
        path.relative_to(staging_dir).as_posix(): path
        for path in staging_dir.rglob("*")
        if path.is_file()
    }
    if not required.issubset(staged):
        raise RuntimeError("processor did not produce required outputs")
    for relative, source in sorted(staged.items()):
        destination = output_dir / Path(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, destination)


app = create_app(
    managed_ledger_path=DATA_ROOT / ".managed-artifact-ledger.json"
)
