from datetime import datetime, time, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_account
from app.db.session import get_db
from app.models import (
    Device,
    DmBehaviorType,
    DmSeverityLevel,
    FaAbnormalBehavior,
    FaBehaviorAlert,
    FaWorkOrder,
    SysAccount,
    TrackPassChain,
    DmAnonymousPerson,
)
from app.schemas.common import ok

router = APIRouter(dependencies=[Depends(get_current_account)])


@router.get("/summary")
async def summary(db: AsyncSession = Depends(get_db)):
    today_start = datetime.combine(datetime.now().date(), time.min)

    today_events = (
        await db.execute(select(func.count()).select_from(FaAbnormalBehavior).where(FaAbnormalBehavior.detected_at >= today_start, FaAbnormalBehavior.is_lab == 0))
    ).scalar_one()
    total_events = (await db.execute(select(func.count()).select_from(FaAbnormalBehavior).where(FaAbnormalBehavior.is_lab == 0))).scalar_one()
    pending_alerts = (
        await db.execute(select(func.count()).select_from(FaBehaviorAlert).where(FaBehaviorAlert.alert_status_id == 1, FaBehaviorAlert.is_lab == 0))
    ).scalar_one()
    active_tracks = (
        await db.execute(select(func.count()).select_from(TrackPassChain).where(TrackPassChain.chain_status == 1, TrackPassChain.is_lab == 0))
    ).scalar_one()

    device_total = (await db.execute(select(func.count()).select_from(Device).where(Device.is_deleted == 0))).scalar_one()
    device_online = (
        await db.execute(
            select(func.count()).select_from(Device).where(Device.is_deleted == 0, Device.status == "ONLINE")
        )
    ).scalar_one()
    online_rate = round(device_online / device_total * 100, 1) if device_total else 0.0

    status_rows = (
        await db.execute(select(Device.status, func.count()).where(Device.is_deleted == 0).group_by(Device.status))
    ).all()
    device_health = {row[0]: row[1] for row in status_rows}

    trend_rows = (
        await db.execute(
            select(func.hour(FaAbnormalBehavior.detected_at).label("hour"), func.count())
            .where(FaAbnormalBehavior.detected_at >= today_start, FaAbnormalBehavior.is_lab == 0)
            .group_by("hour")
            .order_by("hour")
        )
    ).all()
    trend = [{"hour": row[0], "count": row[1]} for row in trend_rows]

    latest_rows = (
        await db.execute(
            select(
                FaBehaviorAlert.alert_id,
                FaBehaviorAlert.alert_time,
                DmBehaviorType.type_name,
                DmSeverityLevel.level_name,
                Device.device_name,
                Device.region_name,
            )
            .join(FaAbnormalBehavior, FaAbnormalBehavior.behavior_id == FaBehaviorAlert.behavior_id)
            .join(DmBehaviorType, DmBehaviorType.behavior_type_id == FaAbnormalBehavior.behavior_type_id)
            .join(DmSeverityLevel, DmSeverityLevel.severity_level_id == FaBehaviorAlert.severity_level_id)
            .outerjoin(Device, Device.id == FaAbnormalBehavior.camera_id)
            .where(FaBehaviorAlert.alert_status_id == 1, FaBehaviorAlert.is_lab == 0)
            .order_by(FaBehaviorAlert.alert_time.desc())
            .limit(5)
        )
    ).all()
    latest_alerts = [
        {
            "alert_id": row.alert_id,
            "alert_time": row.alert_time.strftime("%Y-%m-%d %H:%M:%S"),
            "type_name": row.type_name,
            "level_name": row.level_name,
            "device_name": row.device_name,
            "region_name": row.region_name,
        }
        for row in latest_rows
    ]

    return ok(
        {
            "today_events": today_events,
            "total_events": total_events,
            "pending_alerts": pending_alerts,
            "active_tracks": active_tracks,
            "device_online_rate": online_rate,
            "device_health": device_health,
            "device_total": device_total,
            "trend": trend,
            "latest_alerts": latest_alerts,
        }
    )


@router.get("/data-index")
async def data_index(db: AsyncSession = Depends(get_db)):
    behavior_total = (await db.execute(select(func.count()).select_from(FaAbnormalBehavior).where(FaAbnormalBehavior.is_lab == 0))).scalar_one()
    track_total = (await db.execute(select(func.count()).select_from(TrackPassChain).where(TrackPassChain.is_lab == 0))).scalar_one()
    alert_total = (await db.execute(select(func.count()).select_from(FaBehaviorAlert).where(FaBehaviorAlert.is_lab == 0))).scalar_one()
    work_order_total = (await db.execute(select(func.count()).select_from(FaWorkOrder).where(FaWorkOrder.is_lab == 0))).scalar_one()
    person_total = (await db.execute(select(func.count()).select_from(DmAnonymousPerson).where(DmAnonymousPerson.is_lab == 0))).scalar_one()
    device_total = (await db.execute(select(func.count()).select_from(Device).where(Device.is_deleted == 0))).scalar_one()

    type_rows = (
        await db.execute(
            select(DmBehaviorType.behavior_type_id, DmBehaviorType.type_name, func.count(FaAbnormalBehavior.behavior_id))
            .join(FaAbnormalBehavior, FaAbnormalBehavior.behavior_type_id == DmBehaviorType.behavior_type_id)
            .where(FaAbnormalBehavior.is_lab == 0)
            .group_by(DmBehaviorType.behavior_type_id)
            .order_by(func.count(FaAbnormalBehavior.behavior_id).desc())
        )
    ).all()
    type_distribution = [{"id": row[0], "name": row[1], "value": row[2]} for row in type_rows]

    region_rows = (
        await db.execute(
            select(Device.region_name, func.count(FaAbnormalBehavior.behavior_id))
            .join(Device, Device.id == FaAbnormalBehavior.camera_id)
            .where(Device.is_deleted == 0, FaAbnormalBehavior.is_lab == 0)
            .group_by(Device.region_name)
            .order_by(func.count(FaAbnormalBehavior.behavior_id).desc())
        )
    ).all()
    region_distribution = [{"name": row[0] or "未知区域", "value": row[1]} for row in region_rows]

    week_start = datetime.combine(datetime.now().date() - timedelta(days=6), time.min)
    trend_rows = (
        await db.execute(
            select(func.date(FaAbnormalBehavior.detected_at).label("day"), func.count())
            .where(FaAbnormalBehavior.detected_at >= week_start, FaAbnormalBehavior.is_lab == 0)
            .group_by("day")
            .order_by("day")
        )
    ).all()
    trend = [{"date": row[0].strftime("%Y-%m-%d"), "count": row[1]} for row in trend_rows]

    return ok(
        {
            "total": {
                "behavior_count": behavior_total,
                "track_count": track_total,
                "alert_count": alert_total,
                "work_order_count": work_order_total,
                "person_count": person_total,
                "device_count": device_total,
            },
            "type_distribution": type_distribution,
            "region_distribution": region_distribution,
            "seven_day_trend": trend,
        }
    )
