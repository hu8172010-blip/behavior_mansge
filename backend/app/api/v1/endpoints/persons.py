from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_account
from app.db.session import get_db
from app.models import (
    Device,
    DmAlertStatus,
    DmAnonymousPerson,
    DmBehaviorType,
    DmSeverityLevel,
    FaAbnormalBehavior,
    SysAccount,
    TrackPassChain,
)
from app.schemas.common import ok, page_result
from app.services.log_service import write_log

router = APIRouter()


def fmt(dt: datetime | None) -> str | None:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


@router.get("")
async def list_persons(
    keyword: str | None = Query(default=None),
    is_focused: int | None = Query(default=None),
    include_lab: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: SysAccount = Depends(get_current_account),
):
    behavior_cnt = (
        select(func.count())
        .select_from(FaAbnormalBehavior)
        .where(FaAbnormalBehavior.person_id == DmAnonymousPerson.person_id)
        .correlate(DmAnonymousPerson)
        .scalar_subquery()
    )
    track_cnt = (
        select(func.count())
        .select_from(TrackPassChain)
        .where(TrackPassChain.person_id == DmAnonymousPerson.person_id)
        .correlate(DmAnonymousPerson)
        .scalar_subquery()
    )
    matched_account = SysAccount.__table__.alias("matched_account")
    stmt = select(
        DmAnonymousPerson,
        behavior_cnt.label("behavior_count"),
        track_cnt.label("track_count"),
        matched_account.c.real_name.label("matched_user_name"),
    ).outerjoin(matched_account, matched_account.c.account_id == DmAnonymousPerson.matched_user_id)
    count_stmt = select(func.count()).select_from(DmAnonymousPerson)
    if not include_lab:
        stmt = stmt.where(DmAnonymousPerson.is_lab == 0)
        count_stmt = count_stmt.where(DmAnonymousPerson.is_lab == 0)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(DmAnonymousPerson.appearance_desc.like(like))
        count_stmt = count_stmt.where(DmAnonymousPerson.appearance_desc.like(like))
    if is_focused is not None:
        stmt = stmt.where(DmAnonymousPerson.is_focused == is_focused)
        count_stmt = count_stmt.where(DmAnonymousPerson.is_focused == is_focused)
    total = (await db.execute(count_stmt)).scalar_one()
    rows = (
        await db.execute(stmt.order_by(DmAnonymousPerson.last_seen_at.desc()).offset((page - 1) * size).limit(size))
    ).all()
    items = [
        {
            "person_id": row[0].person_id,
            "appearance_desc": row[0].appearance_desc,
            "first_seen_at": fmt(row[0].first_seen_at),
            "last_seen_at": fmt(row[0].last_seen_at),
            "is_focused": row[0].is_focused,
            "risk_level_id": row[0].risk_level_id,
            "matched_user_id": row[0].matched_user_id,
            "matched_user_name": row[3],
            "match_confidence": float(row[0].match_confidence) if row[0].match_confidence is not None else None,
            "behavior_count": row[1],
            "track_count": row[2],
            "is_lab": row[0].is_lab,
        }
        for row in rows
    ]
    return ok(page_result(items, total, page, size))


class FocusBody(BaseModel):
    is_focused: int


@router.get("/{person_id}")
async def person_detail(person_id: int, db: AsyncSession = Depends(get_db), _: SysAccount = Depends(get_current_account)):
    person = (
        await db.execute(select(DmAnonymousPerson).where(DmAnonymousPerson.person_id == person_id))
    ).scalar_one_or_none()
    if person is None:
        raise HTTPException(status_code=404, detail="人员不存在")
    matched_account = SysAccount.__table__.alias("matched_account")
    matched_name = None
    if person.matched_user_id:
        matched_name = (
            await db.execute(select(matched_account.c.real_name).where(matched_account.c.account_id == person.matched_user_id))
        ).scalar_one_or_none()
    behavior_count = (
        await db.execute(select(func.count()).select_from(FaAbnormalBehavior).where(FaAbnormalBehavior.person_id == person_id))
    ).scalar_one()
    track_count = (
        await db.execute(select(func.count()).select_from(TrackPassChain).where(TrackPassChain.person_id == person_id))
    ).scalar_one()
    recent_rows = (
        await db.execute(
            select(
                FaAbnormalBehavior.behavior_id,
                FaAbnormalBehavior.detected_at,
                FaAbnormalBehavior.description,
                FaAbnormalBehavior.confidence_score,
                FaAbnormalBehavior.track_id,
                DmBehaviorType.type_name,
                DmSeverityLevel.level_name,
                DmAlertStatus.status_name,
                Device.device_name,
                Device.region_name,
            )
            .join(DmBehaviorType, DmBehaviorType.behavior_type_id == FaAbnormalBehavior.behavior_type_id)
            .join(DmSeverityLevel, DmSeverityLevel.severity_level_id == FaAbnormalBehavior.severity_level_id)
            .join(DmAlertStatus, DmAlertStatus.alert_status_id == FaAbnormalBehavior.alert_status_id)
            .outerjoin(Device, Device.id == FaAbnormalBehavior.camera_id)
            .where(FaAbnormalBehavior.person_id == person_id)
            .order_by(FaAbnormalBehavior.detected_at.desc())
            .limit(20)
        )
    ).all()
    recent_behaviors = [
        {
            "behavior_id": row.behavior_id,
            "detected_at": fmt(row.detected_at),
            "type_name": row.type_name,
            "level_name": row.level_name,
            "status_name": row.status_name,
            "description": row.description,
            "confidence_score": float(row.confidence_score) if row.confidence_score is not None else None,
            "track_id": row.track_id,
            "device_name": row.device_name,
            "region_name": row.region_name,
        }
        for row in recent_rows
    ]
    return ok(
        {
            "person_id": person.person_id,
            "appearance_desc": person.appearance_desc,
            "first_seen_at": fmt(person.first_seen_at),
            "last_seen_at": fmt(person.last_seen_at),
            "is_focused": person.is_focused,
            "risk_level_id": person.risk_level_id,
            "matched_user_id": person.matched_user_id,
            "matched_user_name": matched_name,
            "match_confidence": float(person.match_confidence) if person.match_confidence is not None else None,
            "behavior_count": behavior_count,
            "track_count": track_count,
            "recent_behaviors": recent_behaviors,
        }
    )


@router.put("/{person_id}/focus")
async def toggle_focus(person_id: int, body: FocusBody, db: AsyncSession = Depends(get_db), account: SysAccount = Depends(get_current_account)):
    if body.is_focused not in (0, 1):
        raise HTTPException(status_code=400, detail="is_focused 仅支持 0 或 1")
    person = (
        await db.execute(select(DmAnonymousPerson).where(DmAnonymousPerson.person_id == person_id))
    ).scalar_one_or_none()
    if person is None:
        raise HTTPException(status_code=404, detail="人员不存在")
    person.is_focused = body.is_focused
    await write_log(db, "ABNORMAL_BEHAVIOR", "UPDATE", account, person_id, "BEHAVIOR", {"action": "toggle_focus", "is_focused": body.is_focused})
    await db.commit()
    return ok(message="已标记重点关注" if body.is_focused == 1 else "已取消重点关注")
