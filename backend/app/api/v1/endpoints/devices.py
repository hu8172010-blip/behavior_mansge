from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_account
from app.db.session import get_db
from app.models import Device, FaultRecord, SysAccount
from app.schemas.common import ok, page_result
from app.services.log_service import write_log

router = APIRouter()


def fmt(dt: datetime | None) -> str | None:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


def device_to_dict(d: Device) -> dict:
    return {
        "id": d.id,
        "device_code": d.device_code,
        "device_name": d.device_name,
        "device_type": d.device_type,
        "location_text": d.location_text,
        "region_code": d.region_code,
        "region_name": d.region_name,
        "status": d.status,
        "health_score": d.health_score,
        "video_quality": d.video_quality,
        "last_heartbeat_time": fmt(d.last_heartbeat_time),
        "channel_count": d.channel_count,
        "ip_address": d.ip_address,
        "port": d.port,
        "manufacturer": d.manufacturer,
        "model": d.model,
        "install_time": fmt(d.install_time),
        "remark": d.remark,
        "operator_name": d.operator_name,
    }


@router.get("")
async def list_devices(
    status: str | None = Query(default=None),
    device_type: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: SysAccount = Depends(get_current_account),
):
    stmt = select(Device).where(Device.is_deleted == 0)
    count_stmt = select(func.count()).select_from(Device).where(Device.is_deleted == 0)
    if status:
        stmt = stmt.where(Device.status == status)
        count_stmt = count_stmt.where(Device.status == status)
    if device_type:
        stmt = stmt.where(Device.device_type == device_type)
        count_stmt = count_stmt.where(Device.device_type == device_type)
    if keyword:
        like = f"%{keyword}%"
        cond = or_(Device.device_name.like(like), Device.device_code.like(like), Device.location_text.like(like))
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    total = (await db.execute(count_stmt)).scalar_one()
    rows = (await db.execute(stmt.order_by(Device.id).offset((page - 1) * size).limit(size))).scalars().all()
    return ok(page_result([device_to_dict(d) for d in rows], total, page, size))


class DeviceBody(BaseModel):
    device_code: str
    device_name: str
    device_type: str = "CAMERA"
    location_text: str | None = None
    region_code: str | None = None
    region_name: str | None = None
    ip_address: str | None = None
    port: int | None = None
    manufacturer: str | None = None
    model: str | None = None
    remark: str | None = None


@router.post("")
async def create_device(body: DeviceBody, db: AsyncSession = Depends(get_db), account: SysAccount = Depends(get_current_account)):
    exists = (
        await db.execute(select(Device.id).where(Device.device_code == body.device_code, Device.is_deleted == 0))
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=400, detail="设备编号已存在")
    if body.device_type not in ("CAMERA", "NVR", "EDGE"):
        raise HTTPException(status_code=400, detail="设备类型不合法")
    device = Device(
        device_code=body.device_code,
        device_name=body.device_name,
        device_type=body.device_type,
        location_text=body.location_text,
        region_code=body.region_code,
        region_name=body.region_name,
        ip_address=body.ip_address,
        port=body.port,
        manufacturer=body.manufacturer,
        model=body.model,
        remark=body.remark,
        status="ONLINE",
        health_score=100,
        video_quality="HD" if body.device_type == "CAMERA" else None,
        channel_count=1,
        last_heartbeat_time=datetime.now(),
        operator_id=account.account_id,
        operator_name=account.real_name,
    )
    db.add(device)
    await db.flush()
    await write_log(db, "DEVICE", "UPDATE", account, device.id, "DEVICE", {"action": "create", "device_code": device.device_code})
    await db.commit()
    return ok({"id": device.id}, "设备已新增")


class DeviceUpdateBody(BaseModel):
    device_name: str | None = None
    location_text: str | None = None
    region_code: str | None = None
    region_name: str | None = None
    status: str | None = None
    video_quality: str | None = None
    ip_address: str | None = None
    port: int | None = None
    manufacturer: str | None = None
    model: str | None = None
    remark: str | None = None


@router.put("/{device_id}")
async def update_device(device_id: int, body: DeviceUpdateBody, db: AsyncSession = Depends(get_db), account: SysAccount = Depends(get_current_account)):
    device = (
        await db.execute(select(Device).where(Device.id == device_id, Device.is_deleted == 0))
    ).scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")
    if body.status is not None and body.status not in ("ONLINE", "OFFLINE", "FAULT", "DISABLED"):
        raise HTTPException(status_code=400, detail="设备状态不合法")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(device, field, value)
    device.operator_id = account.account_id
    device.operator_name = account.real_name
    await write_log(db, "DEVICE", "UPDATE", account, device.id, "DEVICE", {"action": "update", "fields": list(body.model_dump(exclude_unset=True).keys())})
    await db.commit()
    return ok(message="设备已更新")


@router.get("/faults/list")
async def list_faults(
    device_id: int | None = Query(default=None),
    disposal_status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: SysAccount = Depends(get_current_account),
):
    stmt = (
        select(FaultRecord, Device.device_name)
        .join(Device, Device.id == FaultRecord.device_id)
        .where(FaultRecord.is_deleted == 0)
    )
    count_stmt = select(func.count()).select_from(FaultRecord).where(FaultRecord.is_deleted == 0)
    if device_id is not None:
        stmt = stmt.where(FaultRecord.device_id == device_id)
        count_stmt = count_stmt.where(FaultRecord.device_id == device_id)
    if disposal_status:
        stmt = stmt.where(FaultRecord.disposal_status == disposal_status)
        count_stmt = count_stmt.where(FaultRecord.disposal_status == disposal_status)
    total = (await db.execute(count_stmt)).scalar_one()
    rows = (
        await db.execute(stmt.order_by(FaultRecord.occurrence_time.desc()).offset((page - 1) * size).limit(size))
    ).all()
    items = [
        {
            "id": row[0].id,
            "device_id": row[0].device_id,
            "device_code": row[0].device_code,
            "device_name": row[1],
            "fault_type": row[0].fault_type,
            "fault_level": row[0].fault_level,
            "fault_desc": row[0].fault_desc,
            "occurrence_time": fmt(row[0].occurrence_time),
            "recovery_time": fmt(row[0].recovery_time),
            "disposal_status": row[0].disposal_status,
            "assigned_name": row[0].assigned_name,
            "repair_result": row[0].repair_result,
            "repair_remark": row[0].repair_remark,
        }
        for row in rows
    ]
    return ok(page_result(items, total, page, size))


@router.put("/faults/{fault_id}/close")
async def close_fault(fault_id: int, db: AsyncSession = Depends(get_db), account: SysAccount = Depends(get_current_account)):
    fault = (
        await db.execute(select(FaultRecord).where(FaultRecord.id == fault_id, FaultRecord.is_deleted == 0))
    ).scalar_one_or_none()
    if fault is None:
        raise HTTPException(status_code=404, detail="故障记录不存在")
    if fault.disposal_status == "CLOSED":
        raise HTTPException(status_code=400, detail="该故障已关闭")
    fault.disposal_status = "CLOSED"
    fault.closed_at = datetime.now()
    fault.closed_by = account.account_id
    fault.closed_name = account.real_name
    if fault.recovery_time is None:
        fault.recovery_time = datetime.now()
    await write_log(db, "DEVICE", "UPDATE", account, fault.id, "DEVICE", {"action": "close_fault", "device_code": fault.device_code})
    await db.commit()
    return ok(message="故障已关闭")
