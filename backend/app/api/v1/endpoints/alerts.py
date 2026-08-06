import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_account
from app.db.session import get_db
from app.models import (
    Device,
    DmAlertStatus,
    DmBehaviorType,
    DmSeverityLevel,
    FaAbnormalBehavior,
    FaBehaviorAlert,
    SysAccount,
    TrackPassChain,
)
from app.schemas.common import ok, page_result
from app.services.log_service import write_log

router = APIRouter()


def alert_select():
    return (
        select(
            FaBehaviorAlert.alert_id,
            FaBehaviorAlert.behavior_id,
            FaBehaviorAlert.lab_record_id,
            FaBehaviorAlert.camera_a_id,
            FaBehaviorAlert.camera_b_id,
            FaBehaviorAlert.is_dual_video,
            FaBehaviorAlert.video_path,
            FaBehaviorAlert.video_path_b,
            FaBehaviorAlert.video_job_id,
            FaBehaviorAlert.video_job_id_b,
            FaBehaviorAlert.false_positive,
            FaBehaviorAlert.person_identity,
            FaBehaviorAlert.reviewed_by,
            FaBehaviorAlert.reviewed_at,
            FaBehaviorAlert.alert_time,
            FaBehaviorAlert.alert_status_id,
            FaBehaviorAlert.is_marked_focus,
            FaBehaviorAlert.is_lab,
            FaAbnormalBehavior.description,
            FaAbnormalBehavior.confidence_score,
            FaAbnormalBehavior.track_id,
            DmBehaviorType.type_name,
            DmSeverityLevel.level_name,
            DmAlertStatus.status_name,
            Device.device_name,
            Device.device_code,
            Device.region_name,
        )
        .join(FaAbnormalBehavior, FaAbnormalBehavior.behavior_id == FaBehaviorAlert.behavior_id)
        .join(DmBehaviorType, DmBehaviorType.behavior_type_id == FaAbnormalBehavior.behavior_type_id)
        .join(DmSeverityLevel, DmSeverityLevel.severity_level_id == FaBehaviorAlert.severity_level_id)
        .join(DmAlertStatus, DmAlertStatus.alert_status_id == FaBehaviorAlert.alert_status_id)
        .outerjoin(Device, Device.id == FaAbnormalBehavior.camera_id)
    )


def row_to_dict(row) -> dict:
    return {
        "alert_id": row.alert_id,
        "behavior_id": row.behavior_id,
        "lab_record_id": row.lab_record_id,
        "camera_a_id": row.camera_a_id,
        "camera_b_id": row.camera_b_id,
        "is_dual_video": row.is_dual_video,
        "video_path": row.video_path,
        "video_path_b": row.video_path_b,
        "video_job_id": row.video_job_id,
        "video_job_id_b": row.video_job_id_b,
        "false_positive": row.false_positive,
        "person_identity": row.person_identity,
        "reviewed_by": row.reviewed_by,
        "reviewed_at": row.reviewed_at.strftime("%Y-%m-%d %H:%M:%S") if row.reviewed_at else None,
        "alert_time": row.alert_time.strftime("%Y-%m-%d %H:%M:%S"),
        "alert_status_id": row.alert_status_id,
        "status_name": row.status_name,
        "is_marked_focus": row.is_marked_focus,
        "type_name": row.type_name,
        "level_name": row.level_name,
        "description": row.description,
        "confidence_score": float(row.confidence_score) if row.confidence_score is not None else None,
        "track_id": row.track_id,
        "device_name": row.device_name,
        "device_code": row.device_code,
        "region_name": row.region_name,
        "is_lab": row.is_lab,
    }


@router.get("")
async def list_alerts(
    status_id: int | None = Query(default=None),
    severity_id: int | None = Query(default=None),
    keyword: str | None = Query(default=None),
    include_lab: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: SysAccount = Depends(get_current_account),
):
    stmt = alert_select()
    if not include_lab:
        stmt = stmt.where(FaBehaviorAlert.is_lab == 0)
    count_stmt = select(func.count()).select_from(FaBehaviorAlert).join(
        FaAbnormalBehavior, FaAbnormalBehavior.behavior_id == FaBehaviorAlert.behavior_id
    ).join(DmBehaviorType, DmBehaviorType.behavior_type_id == FaAbnormalBehavior.behavior_type_id) \
        .outerjoin(Device, Device.id == FaAbnormalBehavior.camera_id)
    if not include_lab:
        count_stmt = count_stmt.where(FaBehaviorAlert.is_lab == 0)
    if status_id is not None:
        stmt = stmt.where(FaBehaviorAlert.alert_status_id == status_id)
        count_stmt = count_stmt.where(FaBehaviorAlert.alert_status_id == status_id)
    if severity_id is not None:
        stmt = stmt.where(FaBehaviorAlert.severity_level_id == severity_id)
        count_stmt = count_stmt.where(FaBehaviorAlert.severity_level_id == severity_id)
    if keyword:
        like = f"%{keyword}%"
        cond = or_(
            DmBehaviorType.type_name.like(like),
            FaAbnormalBehavior.description.like(like),
            Device.device_name.like(like),
            Device.region_name.like(like),
        )
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    total = (await db.execute(count_stmt)).scalar_one()
    rows = (
        await db.execute(stmt.order_by(FaBehaviorAlert.alert_time.desc()).offset((page - 1) * size).limit(size))
    ).all()
    return ok(page_result([row_to_dict(row) for row in rows], total, page, size))


@router.get("/todo-count")
async def todo_count(
    include_lab: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    _: SysAccount = Depends(get_current_account),
):
    stmt = select(func.count()).select_from(FaBehaviorAlert).where(FaBehaviorAlert.alert_status_id == 1)
    if not include_lab:
        stmt = stmt.where(FaBehaviorAlert.is_lab == 0)
    count = (await db.execute(stmt)).scalar_one()
    return ok({"count": count})


async def load_alert(db: AsyncSession, alert_id: int) -> FaBehaviorAlert:
    alert = (
        await db.execute(select(FaBehaviorAlert).where(FaBehaviorAlert.alert_id == alert_id))
    ).scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="预警不存在")
    return alert


@router.post("/{alert_id}/confirm")
async def confirm_alert(alert_id: int, db: AsyncSession = Depends(get_db), account: SysAccount = Depends(get_current_account)):
    alert = await load_alert(db, alert_id)
    if alert.alert_status_id != 1:
        raise HTTPException(status_code=400, detail="仅待确认状态的预警可以确认")
    behavior = (
        await db.execute(select(FaAbnormalBehavior).where(FaAbnormalBehavior.behavior_id == alert.behavior_id))
    ).scalar_one()
    alert.alert_status_id = 2
    alert.confirmed_at = datetime.now()
    alert.confirmed_by = account.account_id
    behavior.alert_status_id = 2
    await write_log(db, "ABNORMAL_BEHAVIOR", "UPDATE", account, alert.behavior_id, "BEHAVIOR", {"action": "confirm_alert", "alert_id": alert_id})
    await db.commit()
    return ok(message="告警已确认")


class IgnoreBody(BaseModel):
    note: str | None = None


class ReviewBody(BaseModel):
    false_positive: bool = False
    person_identity: str = "stranger"
    note: str | None = None


@router.post("/{alert_id}/ignore")
async def ignore_alert(alert_id: int, body: IgnoreBody, db: AsyncSession = Depends(get_db), account: SysAccount = Depends(get_current_account)):
    alert = await load_alert(db, alert_id)
    if alert.alert_status_id != 1:
        raise HTTPException(status_code=400, detail="仅待确认状态的预警可以忽略")
    behavior = (
        await db.execute(select(FaAbnormalBehavior).where(FaAbnormalBehavior.behavior_id == alert.behavior_id))
    ).scalar_one()
    alert.alert_status_id = 6
    alert.confirmed_at = datetime.now()
    alert.confirmed_by = account.account_id
    alert.resolved_at = datetime.now()
    behavior.alert_status_id = 6
    if body.note:
        behavior.description = f"误报：{body.note}"
    await write_log(db, "ABNORMAL_BEHAVIOR", "UPDATE", account, alert.behavior_id, "BEHAVIOR", {"action": "ignore", "alert_id": alert_id, "note": body.note})
    await db.commit()
    return ok(message="告警已忽略（误报）")


@router.post("/{alert_id}/review")
async def review_alert(
    alert_id: int,
    body: ReviewBody,
    db: AsyncSession = Depends(get_db),
    account: SysAccount = Depends(get_current_account),
):
    alert = await load_alert(db, alert_id)
    if alert.alert_status_id != 1:
        raise HTTPException(status_code=400, detail="仅待确认状态的预警可以复核")
    behavior = (
        await db.execute(select(FaAbnormalBehavior).where(FaAbnormalBehavior.behavior_id == alert.behavior_id))
    ).scalar_one()

    now = datetime.now()
    alert.alert_status_id = 6
    alert.confirmed_at = now
    alert.confirmed_by = account.account_id
    alert.resolved_at = now
    alert.reviewed_by = account.account_id
    alert.reviewed_at = now
    alert.false_positive = 1 if body.false_positive else 0
    alert.person_identity = body.person_identity

    behavior.alert_status_id = 6
    behavior.is_archived = 1
    behavior.false_positive = 1 if body.false_positive else 0
    behavior.person_identity = body.person_identity
    behavior.reviewed_by = account.account_id
    behavior.reviewed_at = now
    if body.note:
        behavior.description = f"{behavior.description or ''}\n复核备注：{body.note}".strip()[:500]

    if behavior.track_id:
        chain = await db.execute(select(TrackPassChain).where(TrackPassChain.id == behavior.track_id))
        chain = chain.scalar_one_or_none()
        if chain:
            chain.is_archived = 1

    await write_log(
        db,
        "BEHAVIOR_REVIEW",
        "CREATE",
        account,
        alert.behavior_id,
        "BEHAVIOR",
        {
            "alert_id": alert_id,
            "false_positive": body.false_positive,
            "person_identity": body.person_identity,
            "note": body.note,
        },
    )
    await db.commit()
    return ok(message="复核完成并已归档")


@router.get("/export")
async def export_alerts(
    status_id: int | None = Query(default=None),
    severity_id: int | None = Query(default=None),
    keyword: str | None = Query(default=None),
    include_lab: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    _: SysAccount = Depends(get_current_account),
):
    stmt = alert_select()
    if not include_lab:
        stmt = stmt.where(FaBehaviorAlert.is_lab == 0)
    if status_id is not None:
        stmt = stmt.where(FaBehaviorAlert.alert_status_id == status_id)
    if severity_id is not None:
        stmt = stmt.where(FaBehaviorAlert.severity_level_id == severity_id)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(or_(DmBehaviorType.type_name.like(like), FaAbnormalBehavior.description.like(like)))
    rows = (
        await db.execute(stmt.order_by(FaBehaviorAlert.alert_time.desc()).limit(5000))
    ).all()
    buffer = io.StringIO()
    buffer.write("﻿")
    writer = csv.writer(buffer)
    writer.writerow(["告警ID", "行为ID", "告警时间", "行为类型", "严重等级", "状态", "设备", "设备编号", "区域", "轨迹ID", "描述", "置信度"])
    for row in rows:
        writer.writerow([
            row.alert_id,
            row.behavior_id,
            row.alert_time.strftime("%Y-%m-%d %H:%M:%S"),
            row.type_name,
            row.level_name,
            row.status_name,
            row.device_name or "",
            row.device_code or "",
            row.region_name or "",
            row.track_id or "",
            (row.description or "").replace("\n", " "),
            float(row.confidence_score) if row.confidence_score is not None else "",
        ])
    buffer.seek(0)
    filename = f"behavior_alerts_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
