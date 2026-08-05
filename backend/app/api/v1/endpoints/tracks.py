import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_account
from app.db.session import get_db
from app.models import Device, DmAnonymousPerson, SysAccount, TrackPassChain, TrackPassItem
from app.schemas.common import ok, page_result

router = APIRouter()


def fmt(dt: datetime | None) -> str | None:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


@router.get("")
async def list_tracks(
    chain_status: int | None = Query(default=None),
    keyword: str | None = Query(default=None),
    start_time: str | None = Query(default=None),
    end_time: str | None = Query(default=None),
    include_lab: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: SysAccount = Depends(get_current_account),
):
    first_dev = Device.__table__.alias("first_dev")
    last_dev = Device.__table__.alias("last_dev")
    stmt = (
        select(
            TrackPassChain,
            DmAnonymousPerson.appearance_desc,
            DmAnonymousPerson.is_focused,
            first_dev.c.device_name.label("first_device_name"),
            last_dev.c.device_name.label("last_device_name"),
        )
        .outerjoin(DmAnonymousPerson, DmAnonymousPerson.person_id == TrackPassChain.person_id)
        .outerjoin(first_dev, first_dev.c.id == TrackPassChain.first_device_id)
        .outerjoin(last_dev, last_dev.c.id == TrackPassChain.last_device_id)
    )
    count_stmt = select(func.count()).select_from(TrackPassChain).outerjoin(
        DmAnonymousPerson, DmAnonymousPerson.person_id == TrackPassChain.person_id
    )
    stmt = stmt.where(TrackPassChain.is_archived == 1)
    count_stmt = count_stmt.where(TrackPassChain.is_archived == 1)
    if not include_lab:
        stmt = stmt.where(TrackPassChain.is_lab == 0)
        count_stmt = count_stmt.where(TrackPassChain.is_lab == 0)
    if chain_status is not None:
        stmt = stmt.where(TrackPassChain.chain_status == chain_status)
        count_stmt = count_stmt.where(TrackPassChain.chain_status == chain_status)
    if keyword:
        like = f"%{keyword}%"
        cond = or_(TrackPassChain.chain_unique_id.like(like), DmAnonymousPerson.appearance_desc.like(like))
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    if start_time:
        stmt = stmt.where(TrackPassChain.chain_start_time >= start_time)
        count_stmt = count_stmt.where(TrackPassChain.chain_start_time >= start_time)
    if end_time:
        stmt = stmt.where(TrackPassChain.chain_start_time <= end_time)
        count_stmt = count_stmt.where(TrackPassChain.chain_start_time <= end_time)
    total = (await db.execute(count_stmt)).scalar_one()
    rows = (
        await db.execute(stmt.order_by(TrackPassChain.chain_start_time.desc()).offset((page - 1) * size).limit(size))
    ).all()
    items = []
    for row in rows:
        chain: TrackPassChain = row[0]
        hop_count = len([seg for seg in (chain.device_route or "").split("-") if seg])
        items.append(
            {
                "chain_id": chain.id,
                "chain_unique_id": chain.chain_unique_id,
                "person_id": chain.person_id,
                "appearance_desc": row[1],
                "is_focused": row[2] if row[2] is not None else 0,
                "confidence": float(chain.confidence) if chain.confidence is not None else None,
                "device_route": chain.device_route,
                "hop_count": hop_count,
                "first_device_name": row[3],
                "last_device_name": row[4],
                "chain_start_time": fmt(chain.chain_start_time),
                "chain_end_time": fmt(chain.chain_end_time),
                "total_duration_sec": chain.total_duration_sec,
                "chain_status": chain.chain_status,
                "is_lab": chain.is_lab,
            }
        )
    return ok(page_result(items, total, page, size))


@router.get("/{chain_id:int}")
async def track_detail(chain_id: int, db: AsyncSession = Depends(get_db), _: SysAccount = Depends(get_current_account)):
    chain = (
        await db.execute(select(TrackPassChain).where(TrackPassChain.id == chain_id))
    ).scalar_one_or_none()
    if chain is None:
        raise HTTPException(status_code=404, detail="轨迹链路不存在")
    person = (
        await db.execute(select(DmAnonymousPerson).where(DmAnonymousPerson.person_id == chain.person_id))
    ).scalar_one_or_none() if chain.person_id else None
    item_rows = (
        await db.execute(
            select(
                TrackPassItem,
                Device.device_name,
                Device.device_code,
                Device.region_name,
                Device.location_text,
            )
            .join(Device, Device.id == TrackPassItem.device_id)
            .where(TrackPassItem.chain_id == chain_id)
            .order_by(TrackPassItem.sort)
        )
    ).all()
    return ok(
        {
            "chain_id": chain.id,
            "chain_unique_id": chain.chain_unique_id,
            "confidence": float(chain.confidence) if chain.confidence is not None else None,
            "chain_start_time": fmt(chain.chain_start_time),
            "chain_end_time": fmt(chain.chain_end_time),
            "total_duration_sec": chain.total_duration_sec,
            "chain_status": chain.chain_status,
            "person_id": chain.person_id,
            "appearance_desc": person.appearance_desc if person else None,
            "is_focused": person.is_focused if person else 0,
            "items": [
                {
                    "item_id": row[0].id,
                    "sort": row[0].sort,
                    "device_id": row[0].device_id,
                    "device_name": row[1],
                    "device_code": row[2],
                    "region_name": row[3],
                    "location_text": row[4],
                    "appear_time": fmt(row[0].appear_time),
                    "disappear_time": fmt(row[0].disappear_time),
                    "stay_duration_sec": row[0].stay_duration_sec,
                }
                for row in item_rows
            ],
        }
    )


@router.get("/export")
async def export_tracks(
    chain_status: int | None = Query(default=None),
    keyword: str | None = Query(default=None),
    start_time: str | None = Query(default=None),
    end_time: str | None = Query(default=None),
    include_lab: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    _: SysAccount = Depends(get_current_account),
):
    first_dev = Device.__table__.alias("first_dev")
    last_dev = Device.__table__.alias("last_dev")
    stmt = (
        select(
            TrackPassChain,
            DmAnonymousPerson.appearance_desc,
            first_dev.c.device_name.label("first_device_name"),
            last_dev.c.device_name.label("last_device_name"),
        )
        .outerjoin(DmAnonymousPerson, DmAnonymousPerson.person_id == TrackPassChain.person_id)
        .outerjoin(first_dev, first_dev.c.id == TrackPassChain.first_device_id)
        .outerjoin(last_dev, last_dev.c.id == TrackPassChain.last_device_id)
        .where(TrackPassChain.is_archived == 1)
    )
    if not include_lab:
        stmt = stmt.where(TrackPassChain.is_lab == 0)
    if chain_status is not None:
        stmt = stmt.where(TrackPassChain.chain_status == chain_status)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(or_(TrackPassChain.chain_unique_id.like(like), DmAnonymousPerson.appearance_desc.like(like)))
    if start_time:
        stmt = stmt.where(TrackPassChain.chain_start_time >= start_time)
    if end_time:
        stmt = stmt.where(TrackPassChain.chain_start_time <= end_time)
    rows = (
        await db.execute(stmt.order_by(TrackPassChain.chain_start_time.desc()).limit(5000))
    ).all()
    buffer = io.StringIO()
    buffer.write("﻿")
    writer = csv.writer(buffer)
    writer.writerow(["链路ID", "链路编号", "人员ID", "人员特征", "置信度", "途经设备", "起始设备", "结束设备", "开始时间", "结束时间", "时长(秒)", "状态"])
    for row in rows:
        chain: TrackPassChain = row[0]
        writer.writerow([
            chain.id,
            chain.chain_unique_id,
            chain.person_id or "",
            (row[1] or "").replace("\n", " "),
            float(chain.confidence) if chain.confidence is not None else "",
            chain.device_route,
            row[2] or "",
            row[3] or "",
            fmt(chain.chain_start_time),
            fmt(chain.chain_end_time),
            chain.total_duration_sec,
            chain.chain_status,
        ])
    buffer.seek(0)
    filename = f"track_chains_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
