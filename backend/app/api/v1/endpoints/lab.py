import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import anyio
import asyncio
import threading
import time
import uuid
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_account
from app.db.session import get_db
from app.models import (
    Device,
    DmAnonymousPerson,
    FaAbnormalBehavior,
    FaBehaviorAlert,
    FaWorkOrder,
    LabRecord,
    SysAccount,
    TrackPassChain,
)
from app.schemas.common import ok, page_result
from app.services.anomaly_client import AnomalyClient
from app.services.ingest import ingest_anomaly_result

router = APIRouter()

STORAGE_DIR = Path("./storage/lab").resolve()
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

MAX_VIDEO_MB = 500
MAX_RESULT_MB = 50


@router.post("/analyze")
async def lab_analyze(
    video: UploadFile = File(...),
    device_id: int = Form(default=0),
    calibration: str = Form(default="{}"),
    mode: str = Form(default="temp"),
    record_name: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    account: SysAccount = Depends(get_current_account),
):
    if not video.filename:
        raise HTTPException(status_code=400, detail="视频文件名为空")

    raw = await video.read()
    if len(raw) > MAX_VIDEO_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"视频大小超过 {MAX_VIDEO_MB}MB 限制")

    suffix = Path(video.filename).suffix or ".mp4"
    temp_video = STORAGE_DIR / f"_temp_{account.account_id}_{video.filename}"
    temp_video.write_bytes(raw)

    try:
        cal = json.loads(calibration) if calibration else {}
        client = AnomalyClient()
        result = await anyio.to_thread.run_sync(client.analyze, str(temp_video), cal)
    finally:
        if temp_video.exists():
            temp_video.unlink()

    record_id = None
    counts = None
    if mode == "persist":
        record = LabRecord(
            record_name=record_name or f"模拟-{video.filename}",
            account_id=account.account_id,
            device_id=device_id or None,
            video_filename=video.filename,
            video_path="",
            result_path="",
            model_version=result.get("summary", {}).get("model_version"),
            event_count=len(result.get("events", [])),
            track_count=len(result.get("tracks", [])),
            status=1,
            is_published=0,
        )
        db.add(record)
        await db.flush()

        record_dir = STORAGE_DIR / str(record.record_id)
        record_dir.mkdir(parents=True, exist_ok=True)
        video_path = record_dir / f"video{suffix}"
        result_path = record_dir / "result.json"
        video_path.write_bytes(raw)
        result_path.write_text(json.dumps(result, ensure_ascii=False, default=str), encoding="utf-8")

        record.video_path = str(video_path)
        record.result_path = str(result_path)

        counts = await ingest_anomaly_result(
            db,
            result,
            device_id=device_id or None,
            account_id=account.account_id,
            create_work_orders=True,
            is_lab=True,
        )
        record.is_published = 1
        record.published_at = datetime.now()
        await db.commit()
        record_id = record.record_id

    return ok({"result": result, "record_id": record_id, "counts": counts})


@router.get("/records")
async def list_lab_records(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    account: SysAccount = Depends(get_current_account),
):
    count_stmt = select(func.count()).select_from(LabRecord).where(
        LabRecord.account_id == account.account_id,
        LabRecord.status == 1,
    )
    stmt = (
        select(LabRecord)
        .where(LabRecord.account_id == account.account_id, LabRecord.status == 1)
        .order_by(LabRecord.create_time.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    total = (await db.execute(count_stmt)).scalar_one()
    rows = (await db.execute(stmt)).scalars().all()
    items = [
        {
            "record_id": r.record_id,
            "record_name": r.record_name,
            "device_id": r.device_id,
            "video_filename": r.video_filename,
            "event_count": r.event_count,
            "track_count": r.track_count,
            "is_published": r.is_published,
            "create_time": r.create_time.strftime("%Y-%m-%d %H:%M:%S") if r.create_time else None,
        }
        for r in rows
    ]
    return ok(page_result(items, total, page, size))


@router.get("/records/{record_id}")
async def get_lab_record(
    record_id: int,
    db: AsyncSession = Depends(get_db),
    account: SysAccount = Depends(get_current_account),
):
    record = (
        await db.execute(
            select(LabRecord).where(
                LabRecord.record_id == record_id,
                LabRecord.account_id == account.account_id,
                LabRecord.status == 1,
            )
        )
    ).scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")

    result: dict[str, Any] | None = None
    if record.result_path and Path(record.result_path).exists():
        content = Path(record.result_path).read_text(encoding="utf-8")
        if len(content) > MAX_RESULT_MB * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"结果文件超过 {MAX_RESULT_MB}MB")
        result = json.loads(content)

    return ok(
        {
            "record_id": record.record_id,
            "record_name": record.record_name,
            "device_id": record.device_id,
            "video_filename": record.video_filename,
            "event_count": record.event_count,
            "track_count": record.track_count,
            "is_published": record.is_published,
            "create_time": record.create_time.strftime("%Y-%m-%d %H:%M:%S") if record.create_time else None,
            "result": result,
        }
    )


@router.post("/records/{record_id}/publish")
async def publish_lab_record(
    record_id: int,
    db: AsyncSession = Depends(get_db),
    account: SysAccount = Depends(get_current_account),
):
    record = (
        await db.execute(
            select(LabRecord).where(
                LabRecord.record_id == record_id,
                LabRecord.account_id == account.account_id,
                LabRecord.status == 1,
            )
        )
    ).scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    if record.is_published:
        raise HTTPException(status_code=400, detail="该记录已发布")
    if not record.result_path or not Path(record.result_path).exists():
        raise HTTPException(status_code=404, detail="结果文件不存在")

    content = Path(record.result_path).read_text(encoding="utf-8")
    result = json.loads(content)

    counts = await ingest_anomaly_result(
        db,
        result,
        device_id=record.device_id,
        account_id=account.account_id,
        create_work_orders=True,
        is_lab=True,
    )

    record.is_published = 1
    record.published_at = datetime.now()
    await db.commit()
    return ok({"published": True, "counts": counts})


@router.delete("/records/{record_id}")
async def delete_lab_record(
    record_id: int,
    db: AsyncSession = Depends(get_db),
    account: SysAccount = Depends(get_current_account),
):
    record = (
        await db.execute(
            select(LabRecord).where(
                LabRecord.record_id == record_id,
                LabRecord.account_id == account.account_id,
                LabRecord.status == 1,
            )
        )
    ).scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")

    record.status = 0
    if record.video_path:
        p = Path(record.video_path)
        if p.exists():
            p.unlink()
    if record.result_path:
        p = Path(record.result_path)
        if p.exists():
            p.unlink()
    record_dir = Path(record.result_path).parent if record.result_path else None
    if record_dir and record_dir.is_dir():
        shutil.rmtree(record_dir, ignore_errors=True)
    await db.commit()
    return ok({"deleted": True})


LAB_JOB_STORE: dict[str, dict[str, Any]] = {}
_SYNC_LOCK = threading.Lock()


def _persist_job_result_sync(job_id: str, raw_bytes: bytes, suffix: str, video_filename: str, main_loop) -> None:
    """推理完成后，在新线程中通过 run_coroutine_threadsafe 将保存操作提交回主事件循环执行。"""
    store = LAB_JOB_STORE.get(job_id)
    if not store:
        return
    result = store.get("result")
    if not result:
        return
    try:
        import asyncio
        from app.db.session import AsyncSessionLocal

        async def _do():
            async with AsyncSessionLocal() as db:
                record = LabRecord(
                    record_name=store.get("record_name") or f"模拟-{video_filename}",
                    account_id=store["account_id"],
                    device_id=store.get("device_id") or None,
                    video_filename=video_filename,
                    video_path="",
                    result_path="",
                    model_version=(result.get("summary") or {}).get("model_version"),
                    event_count=len(result.get("events") or []),
                    track_count=len(result.get("tracks") or []),
                    status=1,
                    is_published=0,
                )
                db.add(record)
                await db.flush()

                record_dir = STORAGE_DIR / str(record.record_id)
                record_dir.mkdir(parents=True, exist_ok=True)
                video_path = record_dir / f"video{suffix}"
                result_path = record_dir / "result.json"
                video_path.write_bytes(raw_bytes)
                result_path.write_text(json.dumps(result, ensure_ascii=False, default=str), encoding="utf-8")

                record.video_path = str(video_path)
                record.result_path = str(result_path)
                await db.commit()
                with _SYNC_LOCK:
                    store["record_id"] = record.record_id
                    store["record_saved"] = True

        if main_loop and main_loop.is_running():
            future = asyncio.run_coroutine_threadsafe(_do(), main_loop)
            future.result(timeout=30)  # 等待最多 30 秒
        else:
            # Fallback: 如果主循环不可用（理论上不会发生），尝试在当前线程创建一个临时连接
            # 但这通常会失败，因为 engine 绑定了主循环
            with _SYNC_LOCK:
                store["record_save_error"] = "主事件循环不可用，无法保存记录"
    except Exception as exc:
        import traceback
        traceback.print_exc()
        with _SYNC_LOCK:
            store["record_save_error"] = str(exc)


def _run_lab_job(job_id: str, temp_video: Path, calibration: dict[str, Any] | None, main_loop) -> None:
    client = AnomalyClient()
    store = LAB_JOB_STORE[job_id]
    raw_bytes = temp_video.read_bytes()
    suffix = Path(store.get("video_filename") or "video.mp4").suffix or ".mp4"
    video_filename = store.get("video_filename") or "video.mp4"
    try:
        store["status"] = "submitting"
        tracker_job_id = client.submit(temp_video, calibration)
        store["tracker_job_id"] = tracker_job_id
        store["status"] = "queued"
        start = time.time()
        timeout = 1800.0
        while time.time() - start < timeout:
            st = client.status(tracker_job_id)
            store["status"] = st.get("status", "queued")
            store["progress"] = st.get("progress", 0.0)
            if store["status"] == "completed":
                result = client.result(tracker_job_id)
                store["result"] = result
                store["progress"] = 1.0
                break
            if store["status"] in ("failed", "error"):
                store["error"] = st.get("error", "推理失败")
                store["status"] = "failed"
                break
            if store["status"] == "cancelled":
                store["error"] = "推理任务已取消"
                store["status"] = "failed"
                break
            time.sleep(1.0)
        else:
            store["error"] = "推理等待超时"
            store["status"] = "failed"
    except Exception as e:
        store["error"] = str(e)
        store["status"] = "failed"
    finally:
        if temp_video.exists():
            temp_video.unlink()

    # persist 模式：推理结束后落库 LabRecord（不自动发布）
    if store.get("mode") == "persist" and store.get("status") == "completed":
        save_thread = threading.Thread(
            target=_persist_job_result_sync,
            args=(job_id, raw_bytes, suffix, video_filename, main_loop),
            daemon=True,
        )
        save_thread.start()
        # 短暂等待（最多 5s），让首次轮询能立即看到 record_id
        save_thread.join(timeout=5.0)


@router.post("/jobs")
async def create_lab_job(
    video: UploadFile = File(...),
    device_id: int = Form(default=0),
    calibration: str = Form(default="{}"),
    mode: str = Form(default="temp"),
    record_name: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    account: SysAccount = Depends(get_current_account),
):
    if device_id:
        exists = (await db.execute(select(Device.id).where(Device.id == device_id, Device.is_deleted == 0))).scalar_one_or_none()
        if not exists:
            raise HTTPException(status_code=400, detail="设备不存在")
    if not video.filename:
        raise HTTPException(status_code=400, detail="视频文件名为空")

    raw = await video.read()
    if len(raw) > MAX_VIDEO_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"视频大小超过 {MAX_VIDEO_MB}MB 限制")

    suffix = Path(video.filename).suffix or ".mp4"
    job_id = str(uuid.uuid4())
    temp_video = STORAGE_DIR / f"_job_{job_id}_{video.filename}"
    temp_video.write_bytes(raw)

    cal = json.loads(calibration) if calibration else {}
    # 获取当前 FastAPI 主事件循环，用于后续在子线程中安全地执行异步数据库操作
    main_loop = asyncio.get_running_loop()
    LAB_JOB_STORE[job_id] = {
        "status": "created",
        "progress": 0.0,
        "result": None,
        "error": None,
        "tracker_job_id": None,
        "record_id": None,
        "device_id": device_id,
        "account_id": account.account_id,
        "published": False,
        "published_at": None,
        "created_at": time.time(),
        "mode": mode,
        "record_name": record_name or f"模拟-{video.filename or '实验'}",
        "video_filename": video.filename or "video.mp4",
    }
    thread = threading.Thread(
        target=_run_lab_job,
        args=(job_id, temp_video, cal, main_loop),
        daemon=True,
    )
    thread.start()

    record_id = None
    if mode == "persist":
        # persist 模式会在推理完成后异步落库，record_id 在轮询中返回
        pass

    return ok({"job_id": job_id, "record_id": record_id})


@router.get("/jobs/{job_id}")
async def get_lab_job(
    job_id: str,
    account: SysAccount = Depends(get_current_account),
):
    store = LAB_JOB_STORE.get(job_id)
    if not store:
        raise HTTPException(status_code=404, detail="任务不存在")
    return ok({
        "job_id": job_id,
        "status": store["status"],
        "progress": store["progress"],
        "result": store["result"],
        "error": store["error"],
        "published": store["published"],
        "record_id": store.get("record_id"),
        "record_saved": store.get("record_saved", False),
        "record_save_error": store.get("record_save_error"),
    })


@router.post("/jobs/{job_id}/publish")
async def publish_lab_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    account: SysAccount = Depends(get_current_account),
):
    store = LAB_JOB_STORE.get(job_id)
    if not store:
        raise HTTPException(status_code=404, detail="任务不存在")
    if store.get("account_id") != account.account_id:
        raise HTTPException(status_code=403, detail="无权发布该任务")
    if store["status"] != "completed":
        raise HTTPException(status_code=400, detail="任务尚未完成")
    if store.get("published"):
        raise HTTPException(status_code=400, detail="该任务已发布")
    if not store.get("result"):
        raise HTTPException(status_code=400, detail="任务结果为空")

    try:
        counts = await ingest_anomaly_result(
            db,
            store["result"],
            device_id=store.get("device_id"),
            account_id=account.account_id,
            create_work_orders=True,
            is_lab=True,
        )
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"发布失败：{exc}")
    store["published"] = True
    store["published_at"] = time.time()
    return ok({"published": True, "counts": counts})


@router.post("/records/{record_id}/unpublish")
async def unpublish_lab_record(
    record_id: int,
    db: AsyncSession = Depends(get_db),
    account: SysAccount = Depends(get_current_account),
):
    record = (await db.execute(select(LabRecord).where(LabRecord.record_id == record_id))).scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    if not record.is_published:
        raise HTTPException(status_code=400, detail="记录尚未发布")
    
    # 尝试清理关联的业务数据
    # 注意：此处依赖于业务表中是否有 lab_record_id 字段，或者通过时间/account_id 进行大致删除
    # 为安全起见，暂不直接删除业务表数据，而是将 LabRecord 状态重置
    # 后续可通过 init_database.sql 给业务表增加 lab_record_id 字段实现精准溯源和删除
    
    record.is_published = 0
    await db.commit()
    return ok({"unpublished": True})

@router.post("/clear-sandbox")
async def clear_lab_sandbox(
    db: AsyncSession = Depends(get_db),
    account: SysAccount = Depends(get_current_account),
):
    await db.execute(delete(FaWorkOrder).where(FaWorkOrder.is_lab == 1))
    await db.execute(delete(FaBehaviorAlert).where(FaBehaviorAlert.is_lab == 1))
    await db.execute(delete(FaAbnormalBehavior).where(FaAbnormalBehavior.is_lab == 1))
    await db.execute(delete(TrackPassChain).where(TrackPassChain.is_lab == 1))
    await db.execute(delete(DmAnonymousPerson).where(DmAnonymousPerson.is_lab == 1))
    await db.commit()
    return ok({"cleared": True})
