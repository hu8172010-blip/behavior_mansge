import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
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
    SysAccount,
)
from app.schemas.common import ok, page_result

router = APIRouter()


@router.get("")
async def list_behaviors(
    type_id: int | None = Query(default=None),
    severity_id: int | None = Query(default=None),
    status_id: int | None = Query(default=None),
    camera_id: int | None = Query(default=None),
    region_name: str | None = Query(default=None),
    start_time: datetime | None = Query(default=None, description="检出时间起始（含）"),
    end_time: datetime | None = Query(default=None, description="检出时间截止（含）"),
    keyword: str | None = Query(default=None),
    include_lab: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: SysAccount = Depends(get_current_account),
):
    stmt = (
        select(
            FaAbnormalBehavior.behavior_id,
            FaAbnormalBehavior.detected_at,
            FaAbnormalBehavior.description,
            FaAbnormalBehavior.confidence_score,
            FaAbnormalBehavior.person_id,
            FaAbnormalBehavior.track_id,
            FaAbnormalBehavior.alert_status_id,
            FaAbnormalBehavior.is_lab,
            DmBehaviorType.type_name,
            DmSeverityLevel.level_name,
            DmAlertStatus.status_name,
            Device.device_name,
            Device.device_code,
            Device.region_name,
        )
        .join(DmBehaviorType, DmBehaviorType.behavior_type_id == FaAbnormalBehavior.behavior_type_id)
        .join(DmSeverityLevel, DmSeverityLevel.severity_level_id == FaAbnormalBehavior.severity_level_id)
        .join(DmAlertStatus, DmAlertStatus.alert_status_id == FaAbnormalBehavior.alert_status_id)
        .outerjoin(Device, Device.id == FaAbnormalBehavior.camera_id)
    )
    count_stmt = select(func.count()).select_from(FaAbnormalBehavior).join(
        DmBehaviorType, DmBehaviorType.behavior_type_id == FaAbnormalBehavior.behavior_type_id
    ).outerjoin(Device, Device.id == FaAbnormalBehavior.camera_id)
    filters = [FaAbnormalBehavior.is_lab == 0] if not include_lab else []
    if type_id is not None:
        filters.append(FaAbnormalBehavior.behavior_type_id == type_id)
    if severity_id is not None:
        filters.append(FaAbnormalBehavior.severity_level_id == severity_id)
    if status_id is not None:
        filters.append(FaAbnormalBehavior.alert_status_id == status_id)
    if camera_id is not None:
        filters.append(FaAbnormalBehavior.camera_id == camera_id)
    if region_name:
        filters.append(Device.region_name == region_name)
    if start_time is not None:
        filters.append(FaAbnormalBehavior.detected_at >= start_time)
    if end_time is not None:
        filters.append(FaAbnormalBehavior.detected_at <= end_time)
    if keyword:
        like = f"%{keyword}%"
        filters.append(or_(DmBehaviorType.type_name.like(like), FaAbnormalBehavior.description.like(like)))
    for cond in filters:
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    total = (await db.execute(count_stmt)).scalar_one()
    rows = (
        await db.execute(stmt.order_by(FaAbnormalBehavior.detected_at.desc()).offset((page - 1) * size).limit(size))
    ).all()
    items = [
        {
            "behavior_id": row.behavior_id,
            "detected_at": row.detected_at.strftime("%Y-%m-%d %H:%M:%S"),
            "type_name": row.type_name,
            "level_name": row.level_name,
            "alert_status_id": row.alert_status_id,
            "status_name": row.status_name,
            "description": row.description,
            "confidence_score": float(row.confidence_score) if row.confidence_score is not None else None,
            "person_id": row.person_id,
            "track_id": row.track_id,
            "device_name": row.device_name,
            "device_code": row.device_code,
            "region_name": row.region_name,
            "is_lab": row.is_lab,
        }
        for row in rows
    ]
    return ok(page_result(items, total, page, size))


@router.get("/export")
async def export_behaviors(
    type_id: int | None = Query(default=None),
    severity_id: int | None = Query(default=None),
    status_id: int | None = Query(default=None),
    camera_id: int | None = Query(default=None),
    region_name: str | None = Query(default=None),
    start_time: datetime | None = Query(default=None, description="检出时间起始（含）"),
    end_time: datetime | None = Query(default=None, description="检出时间截止（含）"),
    keyword: str | None = Query(default=None),
    include_lab: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    _: SysAccount = Depends(get_current_account),
):
    stmt = (
        select(
            FaAbnormalBehavior.behavior_id,
            FaAbnormalBehavior.detected_at,
            DmBehaviorType.type_name,
            DmSeverityLevel.level_name,
            DmAlertStatus.status_name,
            FaAbnormalBehavior.description,
            FaAbnormalBehavior.confidence_score,
            FaAbnormalBehavior.person_id,
            FaAbnormalBehavior.track_id,
            Device.device_name,
            Device.device_code,
            Device.region_name,
        )
        .join(DmBehaviorType, DmBehaviorType.behavior_type_id == FaAbnormalBehavior.behavior_type_id)
        .join(DmSeverityLevel, DmSeverityLevel.severity_level_id == FaAbnormalBehavior.severity_level_id)
        .join(DmAlertStatus, DmAlertStatus.alert_status_id == FaAbnormalBehavior.alert_status_id)
        .outerjoin(Device, Device.id == FaAbnormalBehavior.camera_id)
    )
    filters = [FaAbnormalBehavior.is_lab == 0] if not include_lab else []
    if type_id is not None:
        filters.append(FaAbnormalBehavior.behavior_type_id == type_id)
    if severity_id is not None:
        filters.append(FaAbnormalBehavior.severity_level_id == severity_id)
    if status_id is not None:
        filters.append(FaAbnormalBehavior.alert_status_id == status_id)
    if camera_id is not None:
        filters.append(FaAbnormalBehavior.camera_id == camera_id)
    if region_name:
        filters.append(Device.region_name == region_name)
    if start_time is not None:
        filters.append(FaAbnormalBehavior.detected_at >= start_time)
    if end_time is not None:
        filters.append(FaAbnormalBehavior.detected_at <= end_time)
    if keyword:
        like = f"%{keyword}%"
        filters.append(or_(DmBehaviorType.type_name.like(like), FaAbnormalBehavior.description.like(like)))
    for cond in filters:
        stmt = stmt.where(cond)
    rows = (
        await db.execute(stmt.order_by(FaAbnormalBehavior.detected_at.desc()).limit(5000))
    ).all()
    buffer = io.StringIO()
    buffer.write("﻿")
    writer = csv.writer(buffer)
    writer.writerow(["行为ID", "检测时间", "行为类型", "严重等级", "预警状态", "人员ID", "轨迹ID", "设备", "设备编号", "区域", "描述", "置信度"])
    for row in rows:
        writer.writerow([
            row.behavior_id,
            row.detected_at.strftime("%Y-%m-%d %H:%M:%S"),
            row.type_name,
            row.level_name,
            row.status_name,
            row.person_id or "",
            row.track_id or "",
            row.device_name or "",
            row.device_code or "",
            row.region_name or "",
            (row.description or "").replace("\n", " "),
            float(row.confidence_score) if row.confidence_score is not None else "",
        ])
    buffer.seek(0)
    filename = f"abnormal_behaviors_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
