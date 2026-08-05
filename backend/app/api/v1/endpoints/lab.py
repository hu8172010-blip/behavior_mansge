import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
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
from app.services.ingest import ingest_anomaly_result

router = APIRouter()

STORAGE_DIR = Path("./storage/lab").resolve()
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

MAX_RESULT_MB = 50


@router.post("/publish")
async def publish_model_result(
    payload: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    account: SysAccount = Depends(get_current_account),
):
    """接收前端从远端模型推理服务获取的识别结果，保存模拟记录并发布到业务库。"""
    result = payload.get("result")
    if not isinstance(result, dict):
        raise HTTPException(status_code=422, detail="缺少 result 字段")

    device_id = payload.get("device_id") or None
    if device_id:
        exists = (await db.execute(select(Device.id).where(Device.id == device_id, Device.is_deleted == 0))).scalar_one_or_none()
        if not exists:
            raise HTTPException(status_code=400, detail="设备不存在")

    record_name = payload.get("record_name") or "模拟识别结果"
    video_filename = payload.get("video_filename") or ""

    record = LabRecord(
        record_name=record_name,
        account_id=account.account_id,
        device_id=device_id,
        video_filename=video_filename,
        video_path="",
        result_path="",
        model_version=None,
        event_count=len(result.get("events") or []),
        track_count=len(result.get("tracks") or []),
        status=1,
        is_published=0,
    )
    db.add(record)
    await db.flush()

    record_dir = STORAGE_DIR / str(record.record_id)
    record_dir.mkdir(parents=True, exist_ok=True)
    result_path = record_dir / "result.json"
    content = json.dumps(result, ensure_ascii=False, default=str)
    if len(content) > MAX_RESULT_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"结果文件超过 {MAX_RESULT_MB}MB")
    result_path.write_text(content, encoding="utf-8")
    record.result_path = str(result_path)

    counts = await ingest_anomaly_result(
        db,
        result,
        device_id=device_id,
        account_id=account.account_id,
        create_work_orders=True,
        is_lab=True,
    )
    record.is_published = 1
    record.published_at = datetime.now()
    await db.commit()
    return ok({"record_id": record.record_id, "published": True, "counts": counts})


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
