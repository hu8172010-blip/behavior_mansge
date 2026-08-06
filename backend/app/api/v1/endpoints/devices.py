import csv
import io
import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.connection import notifier
from app.core.security import require_permission
from app.db.session import get_db
from app.models import (
    Device,
    FaOperationLog,
    FaultRecord,
    RepairDispatchLog,
    RepairOrder,
    SysAccount,
    SysAccountPermission,
    SysPermission,
    SysTypePermission,
)
from app.schemas.common import ok, page_result
from app.services.device_restore_service import try_restore_device
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
    _: SysAccount = Depends(require_permission("device:info:view")),
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


@router.get("/export")
async def export_devices(
    status: str | None = Query(default=None),
    device_type: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: SysAccount = Depends(require_permission("device:info:view")),
):
    stmt = select(Device).where(Device.is_deleted == 0)
    if status:
        stmt = stmt.where(Device.status == status)
    if device_type:
        stmt = stmt.where(Device.device_type == device_type)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(or_(Device.device_name.like(like), Device.device_code.like(like), Device.location_text.like(like)))
    rows = (await db.execute(stmt.order_by(Device.id).limit(5000))).scalars().all()
    status_map = {"ONLINE": "在线", "OFFLINE": "离线", "FAULT": "故障", "DISABLED": "停用"}
    type_map = {"CAMERA": "摄像头", "NVR": "录像机", "EDGE": "边缘分析盒"}
    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.writer(buffer)
    writer.writerow(["ID", "设备编号", "设备名称", "设备类型", "安装位置", "所属区域", "状态", "健康分", "最近心跳", "通道数", "IP地址", "端口", "厂商", "型号", "安装时间", "备注", "操作人"])
    for d in rows:
        writer.writerow([
            d.id, d.device_code, d.device_name, type_map.get(d.device_type, d.device_type),
            d.location_text or "", d.region_name or "", status_map.get(d.status, d.status),
            d.health_score, fmt(d.last_heartbeat_time) or "", d.channel_count or "",
            d.ip_address or "", d.port or "", d.manufacturer or "", d.model or "",
            fmt(d.install_time) or "", d.remark or "", d.operator_name or "",
        ])
    return StreamingResponse(iter([buffer.getvalue()]), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=devices.csv"})


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
async def create_device(body: DeviceBody, db: AsyncSession = Depends(get_db), account: SysAccount = Depends(require_permission("device:create"))):
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
async def update_device(device_id: int, body: DeviceUpdateBody, db: AsyncSession = Depends(get_db), account: SysAccount = Depends(require_permission("device:update"))):
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
    _: SysAccount = Depends(require_permission("device:info:view")),
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


@router.get("/faults/export")
async def export_faults(
    device_id: int | None = Query(default=None),
    disposal_status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: SysAccount = Depends(require_permission("device:info:view")),
):
    stmt = (
        select(FaultRecord, Device.device_name)
        .join(Device, Device.id == FaultRecord.device_id)
        .where(FaultRecord.is_deleted == 0)
    )
    if device_id is not None:
        stmt = stmt.where(FaultRecord.device_id == device_id)
    if disposal_status:
        stmt = stmt.where(FaultRecord.disposal_status == disposal_status)
    rows = (
        await db.execute(stmt.order_by(FaultRecord.occurrence_time.desc()).limit(5000))
    ).all()
    status_map = {"PENDING": "待处理", "ASSIGNED": "已派单", "REPAIRED": "已修复", "AUTO_RECOVERED": "自动恢复", "CLOSED": "已关闭"}
    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.writer(buffer)
    writer.writerow(["ID", "设备ID", "设备编号", "设备名称", "故障类型", "故障级别", "故障描述", "发生时间", "恢复时间", "处置状态", "维修负责人", "维修结果", "维修备注"])
    for row in rows:
        f = row[0]
        writer.writerow([
            f.id, f.device_id, f.device_code, row[1], f.fault_type, f.fault_level,
            f.fault_desc or "", fmt(f.occurrence_time) or "", fmt(f.recovery_time) or "",
            status_map.get(f.disposal_status, f.disposal_status), f.assigned_name or "",
            f.repair_result or "", f.repair_remark or "",
        ])
    return StreamingResponse(iter([buffer.getvalue()]), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=faults.csv"})


@router.put("/faults/{fault_id}/close")
async def close_fault(fault_id: int, db: AsyncSession = Depends(get_db), account: SysAccount = Depends(require_permission("device:update"))):
    fault = (
        await db.execute(select(FaultRecord).where(FaultRecord.id == fault_id, FaultRecord.is_deleted == 0))
    ).scalar_one_or_none()
    if fault is None:
        raise HTTPException(status_code=404, detail="故障记录不存在")
    if fault.disposal_status == "CLOSED":
        raise HTTPException(status_code=400, detail="该故障已关闭")
    if fault.disposal_status == "REPAIRED":
        raise HTTPException(status_code=400, detail="该故障已由维修工单闭环，不可重复关闭")
    # 仅允许关闭未派单或已派单但无未完结维修工单的故障，避免与 finish_repair_order 双写冲突
    open_order = (
        await db.execute(
            select(RepairOrder.id)
            .where(
                RepairOrder.fault_id == fault.id,
                RepairOrder.is_deleted == 0,
                RepairOrder.status.in_(("PENDING", "REPAIRING")),
            )
            .limit(1)
        )
    ).first()
    if open_order is not None:
        raise HTTPException(status_code=400, detail="该故障存在未完结维修工单，请先归档工单")
    fault.disposal_status = "CLOSED"
    fault.closed_at = datetime.now()
    fault.closed_by = account.account_id
    fault.closed_name = account.real_name
    if fault.recovery_time is None:
        fault.recovery_time = datetime.now()
    await write_log(db, "DEVICE", "UPDATE", account, fault.id, "DEVICE", {"action": "close_fault", "device_code": fault.device_code})
    await db.commit()
    return ok(message="故障已关闭")


# ============================================================
# 设备维修工单：模拟故障触发 + 自动派单 + 维修全流程
# ============================================================

FAULT_TYPES = ("HEARTBEAT_TIMEOUT", "VIDEO_ABNORMAL", "HARDWARE", "NETWORK", "OTHER")
FAULT_LEVELS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
SIMULATE_HEALTH_COST = 40


async def load_repair_candidates(db: AsyncSession) -> list[SysAccount]:
    """候选人员池：拥有 device:repair 权限且启用的账号（不含超管，判定语义与 load_permission_keys 一致）。"""
    perm_id = (
        await db.execute(select(SysPermission.perm_id).where(SysPermission.perm_key == "device:repair"))
    ).scalar_one_or_none()
    if perm_id is None:
        return []
    role_type_ids = set(
        (await db.execute(select(SysTypePermission.type_id).where(SysTypePermission.perm_id == perm_id))).scalars().all()
    )
    custom_rows = (await db.execute(select(SysAccountPermission.account_id, SysAccountPermission.perm_id))).all()
    custom_any: set[int] = set()
    custom_repair: set[int] = set()
    for account_id, perm in custom_rows:
        custom_any.add(account_id)
        if perm == perm_id:
            custom_repair.add(account_id)
    accounts = (
        await db.execute(select(SysAccount).where(SysAccount.status == 1, SysAccount.type_id != 1))
    ).scalars().all()
    return [
        a
        for a in accounts
        if a.account_id in custom_repair or (a.account_id not in custom_any and a.type_id in role_type_ids)
    ]


async def candidate_loads(db: AsyncSession, candidates: list[SysAccount]) -> dict[int, int]:
    """候选人当前负载：未完成维修工单（待处理 + 维修中）数量。"""
    loads = {a.account_id: 0 for a in candidates}
    if not candidates:
        return loads
    rows = (
        await db.execute(
            select(RepairOrder.assigned_to, func.count())
            .where(
                RepairOrder.is_deleted == 0,
                RepairOrder.status.in_(("PENDING", "REPAIRING")),
                RepairOrder.assigned_to.in_(list(loads.keys())),
            )
            .group_by(RepairOrder.assigned_to)
        )
    ).all()
    for account_id, cnt in rows:
        loads[account_id] = cnt
    return loads


async def next_repair_order_no(db: AsyncSession) -> str:
    prefix = f"RO{datetime.now().strftime('%Y%m%d')}"
    last_no = (
        await db.execute(
            select(RepairOrder.order_no).where(RepairOrder.order_no.like(f"{prefix}%")).order_by(RepairOrder.order_no.desc()).limit(1)
        )
    ).scalar_one_or_none()
    seq = int(last_no[-4:]) + 1 if last_no else 1
    return f"{prefix}{seq:04d}"


async def auto_dispatch_repair_order(db: AsyncSession, device: Device, fault: FaultRecord) -> RepairOrder:
    """自动派发维修工单：平均负载策略（未完成工单最少优先），负载相同按账号ID稳定排序。"""
    now = datetime.now()
    order = RepairOrder(
        order_no=await next_repair_order_no(db),
        fault_id=fault.id,
        device_id=device.id,
        device_code=device.device_code,
        device_name=device.device_name,
        status="PENDING",
        assigned_at=now,
        plan_finish_time=now + timedelta(hours=24),
    )
    candidates = await load_repair_candidates(db)
    loads = await candidate_loads(db, candidates)
    winner = min(candidates, key=lambda a: (loads[a.account_id], a.account_id), default=None)
    if winner is not None:
        order.assigned_to = winner.account_id
        order.assigned_name = winner.real_name
        order.dispatch_strategy = "LEAST_LOAD"
        fault.disposal_status = "ASSIGNED"
        fault.assigned_to = winner.account_id
        fault.assigned_name = winner.real_name
    db.add(order)
    await db.flush()
    snapshot = {str(a.account_id): loads[a.account_id] for a in candidates}
    db.add(
        RepairDispatchLog(
            order_id=order.id,
            fault_id=fault.id,
            device_id=device.id,
            strategy="LEAST_LOAD",
            candidate_count=len(candidates),
            load_snapshot=json.dumps(snapshot, ensure_ascii=False),
            winner_id=winner.account_id if winner else None,
            winner_name=winner.real_name if winner else None,
            result="SUCCESS" if winner else "NO_CANDIDATE",
            remark=None if winner else "无可用维修人员（需拥有 device:repair 权限且账号启用），工单待处理",
        )
    )
    return order


class SimulateFaultBody(BaseModel):
    fault_type: str = "HARDWARE"
    fault_level: str = "HIGH"
    fault_desc: str | None = None


@router.post("/{device_id}/simulate-fault")
async def simulate_fault(device_id: int, body: SimulateFaultBody, db: AsyncSession = Depends(get_db), account: SysAccount = Depends(require_permission("device:update"))):
    device = (
        await db.execute(select(Device).where(Device.id == device_id, Device.is_deleted == 0))
    ).scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")
    if device.status == "FAULT":
        raise HTTPException(status_code=400, detail="设备已处于故障状态，请等待当前故障处理完成")
    if body.fault_type not in FAULT_TYPES:
        raise HTTPException(status_code=400, detail="故障类型不合法")
    if body.fault_level not in FAULT_LEVELS:
        raise HTTPException(status_code=400, detail="故障级别不合法")
    now = datetime.now()
    fault = FaultRecord(
        device_id=device.id,
        device_code=device.device_code,
        fault_type=body.fault_type,
        fault_level=body.fault_level,
        fault_desc=body.fault_desc or "人工模拟设备故障",
        occurrence_time=now,
        disposal_status="PENDING",
        auto_recovery=0,
        operator_id=account.account_id,
        operator_name=account.real_name,
    )
    db.add(fault)
    device.status = "FAULT"
    device.health_score = max(0, (device.health_score if device.health_score is not None else 100) - SIMULATE_HEALTH_COST)
    device.operator_id = account.account_id
    device.operator_name = account.real_name
    await db.flush()
    order = await auto_dispatch_repair_order(db, device, fault)
    await write_log(db, "DEVICE", "UPDATE", account, device.id, "DEVICE", {"action": "simulate_fault", "fault_id": fault.id, "order_no": order.order_no, "assigned_to": order.assigned_to})
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail="该故障已派发维修工单，请勿重复操作") from exc
    if order.assigned_to is not None:
        await notifier.send_to_account(
            order.assigned_to,
            {"type": "REPAIR_ORDER_ASSIGNED", "order_id": order.id, "order_no": order.order_no, "device_name": device.device_name},
        )
    return ok(
        {"fault_id": fault.id, "order_id": order.id, "order_no": order.order_no, "assigned_to": order.assigned_to, "assigned_name": order.assigned_name},
        "模拟故障已生成并自动派发维修工单" if order.assigned_to is not None else "模拟故障已生成，但无可用维修人员，工单待处理",
    )


def repair_row_to_dict(row) -> dict:
    order: RepairOrder = row[0]
    return {
        "id": order.id,
        "order_no": order.order_no,
        "fault_id": order.fault_id,
        "device_id": order.device_id,
        "device_code": order.device_code,
        "device_name": order.device_name,
        "status": order.status,
        "fault_type": row[1],
        "fault_level": row[2],
        "fault_desc": row[3],
        "damage_cause": order.damage_cause,
        "repair_detail": order.repair_detail,
        "assigned_to": order.assigned_to,
        "assigned_name": order.assigned_name,
        "dispatch_strategy": order.dispatch_strategy,
        "assigned_at": fmt(order.assigned_at),
        "plan_finish_time": fmt(order.plan_finish_time),
        "started_at": fmt(order.started_at),
        "completed_at": fmt(order.completed_at),
        "create_time": fmt(order.create_time),
    }


def parse_query_dt(value: str, end_of_day: bool = False) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            dt = datetime.strptime(value, "%Y-%m-%d")
            return dt.replace(hour=23, minute=59, second=59) if end_of_day else dt
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="时间格式不正确，应为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS") from exc


@router.get("/repair-orders")
async def list_repair_orders(
    status: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    fault_id: int | None = Query(default=None),
    assigned_to: int | None = Query(default=None),
    assigned_name: str | None = Query(default=None, description="按维修负责人姓名模糊搜索"),
    start_time: str | None = Query(default=None),
    end_time: str | None = Query(default=None),
    only_mine: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    account: SysAccount = Depends(require_permission("device:repair")),
):
    stmt = (
        select(RepairOrder, FaultRecord.fault_type, FaultRecord.fault_level, FaultRecord.fault_desc)
        .join(FaultRecord, FaultRecord.id == RepairOrder.fault_id)
        .where(RepairOrder.is_deleted == 0)
    )
    count_stmt = select(func.count()).select_from(RepairOrder).where(RepairOrder.is_deleted == 0)
    if status:
        stmt = stmt.where(RepairOrder.status == status)
        count_stmt = count_stmt.where(RepairOrder.status == status)
    if fault_id is not None:
        stmt = stmt.where(RepairOrder.fault_id == fault_id)
        count_stmt = count_stmt.where(RepairOrder.fault_id == fault_id)
    if assigned_to is not None:
        stmt = stmt.where(RepairOrder.assigned_to == assigned_to)
        count_stmt = count_stmt.where(RepairOrder.assigned_to == assigned_to)
    if assigned_name:
        stmt = stmt.join(SysAccount, SysAccount.account_id == RepairOrder.assigned_to).where(SysAccount.real_name.like(f"%{assigned_name}%"))
        count_stmt = count_stmt.join(SysAccount, SysAccount.account_id == RepairOrder.assigned_to).where(SysAccount.real_name.like(f"%{assigned_name}%"))
    if only_mine:
        stmt = stmt.where(RepairOrder.assigned_to == account.account_id)
        count_stmt = count_stmt.where(RepairOrder.assigned_to == account.account_id)
    if start_time:
        dt = parse_query_dt(start_time)
        stmt = stmt.where(RepairOrder.create_time >= dt)
        count_stmt = count_stmt.where(RepairOrder.create_time >= dt)
    if end_time:
        dt = parse_query_dt(end_time, end_of_day=True)
        stmt = stmt.where(RepairOrder.create_time <= dt)
        count_stmt = count_stmt.where(RepairOrder.create_time <= dt)
    if keyword:
        like = f"%{keyword}%"
        cond = or_(
            RepairOrder.order_no.like(like),
            RepairOrder.device_name.like(like),
            RepairOrder.device_code.like(like),
            Device.location_text.like(like),
        )
        stmt = stmt.outerjoin(Device, Device.id == RepairOrder.device_id).where(cond)
        count_stmt = count_stmt.outerjoin(Device, Device.id == RepairOrder.device_id).where(cond)
    total = (await db.execute(count_stmt)).scalar_one()
    rows = (
        await db.execute(stmt.order_by(RepairOrder.create_time.desc()).offset((page - 1) * size).limit(size))
    ).all()
    return ok(page_result([repair_row_to_dict(row) for row in rows], total, page, size))


@router.get("/repair-orders/export")
async def export_repair_orders(
    status: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    fault_id: int | None = Query(default=None),
    assigned_to: int | None = Query(default=None),
    assigned_name: str | None = Query(default=None),
    start_time: str | None = Query(default=None),
    end_time: str | None = Query(default=None),
    only_mine: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    account: SysAccount = Depends(require_permission("device:repair")),
):
    stmt = (
        select(RepairOrder, FaultRecord.fault_type, FaultRecord.fault_level, FaultRecord.fault_desc)
        .join(FaultRecord, FaultRecord.id == RepairOrder.fault_id)
        .where(RepairOrder.is_deleted == 0)
    )
    if status:
        stmt = stmt.where(RepairOrder.status == status)
    if fault_id is not None:
        stmt = stmt.where(RepairOrder.fault_id == fault_id)
    if assigned_to is not None:
        stmt = stmt.where(RepairOrder.assigned_to == assigned_to)
    if assigned_name:
        stmt = stmt.join(SysAccount, SysAccount.account_id == RepairOrder.assigned_to).where(SysAccount.real_name.like(f"%{assigned_name}%"))
    if only_mine:
        stmt = stmt.where(RepairOrder.assigned_to == account.account_id)
    if start_time:
        stmt = stmt.where(RepairOrder.create_time >= parse_query_dt(start_time))
    if end_time:
        stmt = stmt.where(RepairOrder.create_time <= parse_query_dt(end_time, end_of_day=True))
    if keyword:
        like = f"%{keyword}%"
        cond = or_(
            RepairOrder.order_no.like(like),
            RepairOrder.device_name.like(like),
            RepairOrder.device_code.like(like),
            Device.location_text.like(like),
        )
        stmt = stmt.outerjoin(Device, Device.id == RepairOrder.device_id).where(cond)
    rows = (
        await db.execute(stmt.order_by(RepairOrder.create_time.desc()).limit(5000))
    ).all()
    status_map = {"PENDING": "待处理", "REPAIRING": "维修中", "COMPLETED": "已完成"}
    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.writer(buffer)
    writer.writerow(["工单号", "关联故障ID", "设备编号", "设备名称", "状态", "故障类型", "故障级别", "故障描述", "损坏原因", "维修情况", "维修负责人", "派单策略", "派单时间", "计划完成时间", "开始时间", "完成时间", "创建时间"])
    for row in rows:
        o = row[0]
        writer.writerow([
            o.order_no, o.fault_id, o.device_code, o.device_name,
            status_map.get(o.status, o.status), row[1], row[2], row[3] or "",
            o.damage_cause or "", o.repair_detail or "", o.assigned_name or "",
            o.dispatch_strategy or "", fmt(o.assigned_at) or "", fmt(o.plan_finish_time) or "",
            fmt(o.started_at) or "", fmt(o.completed_at) or "", fmt(o.create_time) or "",
        ])
    return StreamingResponse(iter([buffer.getvalue()]), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=repair_orders.csv"})


@router.get("/repair-candidates")
async def list_repair_candidates(db: AsyncSession = Depends(get_db), _: SysAccount = Depends(require_permission("device:repair"))):
    candidates = await load_repair_candidates(db)
    return ok([{"account_id": a.account_id, "real_name": a.real_name, "dept": a.dept} for a in candidates])


@router.post("/repair-orders/{order_id}/accept")
async def accept_repair_order(order_id: int, db: AsyncSession = Depends(get_db), account: SysAccount = Depends(require_permission("device:repair"))):
    order = (
        await db.execute(select(RepairOrder).where(RepairOrder.id == order_id, RepairOrder.is_deleted == 0))
    ).scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail="维修工单不存在")
    if order.status != "PENDING":
        raise HTTPException(status_code=400, detail="仅待处理的工单可以接单")
    # 自动派单无候选人时 assigned_to 为空，此时允许任意拥有 device:repair 权限的员工接单，
    # 避免工单永久卡在 PENDING；有负责人时仅负责人或管理员可接单
    if order.assigned_to is not None and account.type_id != 1 and order.assigned_to != account.account_id:
        raise HTTPException(status_code=403, detail="仅维修负责人或管理员可以接单")
    order.status = "REPAIRING"
    order.started_at = datetime.now()
    # 自动派单无候选人时 assigned_to 为空，接单时补登记为实际接单人，便于后续归档权限校验
    if order.assigned_to is None:
        order.assigned_to = account.account_id
        order.assigned_name = account.real_name
    order.operator_id = account.account_id
    order.operator_name = account.real_name
    await write_log(db, "DEVICE", "UPDATE", account, order.id, "DEVICE", {"action": "accept_repair_order", "order_no": order.order_no})
    await db.commit()
    return ok(message="已接单，工单进入维修中")


class RepairFinishBody(BaseModel):
    damage_cause: str
    repair_detail: str


@router.put("/repair-orders/{order_id}/finish")
async def finish_repair_order(order_id: int, body: RepairFinishBody, db: AsyncSession = Depends(get_db), account: SysAccount = Depends(require_permission("device:repair"))):
    order = (
        await db.execute(select(RepairOrder).where(RepairOrder.id == order_id, RepairOrder.is_deleted == 0))
    ).scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail="维修工单不存在")
    if order.status != "REPAIRING":
        raise HTTPException(status_code=400, detail="仅维修中的工单可以完成归档")
    if account.type_id != 1 and order.assigned_to != account.account_id:
        raise HTTPException(status_code=403, detail="仅维修负责人或管理员可以归档工单")
    damage_cause = body.damage_cause.strip()
    repair_detail = body.repair_detail.strip()
    if not damage_cause or not repair_detail:
        raise HTTPException(status_code=400, detail="损坏原因与维修情况为必填项")
    now = datetime.now()
    # 1. 工单归档
    order.status = "COMPLETED"
    order.completed_at = now
    order.damage_cause = damage_cause
    order.repair_detail = repair_detail
    order.operator_id = account.account_id
    order.operator_name = account.real_name
    # 2. 故障记录闭环
    fault = (
        await db.execute(select(FaultRecord).where(FaultRecord.id == order.fault_id, FaultRecord.is_deleted == 0))
    ).scalar_one_or_none()
    fault_missing = fault is None
    if fault is not None:
        fault.disposal_status = "REPAIRED"
        fault.recovery_time = now
        fault.repair_result = "PASS"
        fault.repair_remark = repair_detail
        fault.operator_id = account.account_id
        fault.operator_name = account.real_name
    # 3. 设备状态恢复：仅当该设备无其他未完结故障工单时才由 FAULT 恢复为 ONLINE
    #    用带 NOT EXISTS 子查询的原子 UPDATE 规避多工单并发归档竞态
    device = (
        await db.execute(select(Device).where(Device.id == order.device_id, Device.is_deleted == 0))
    ).scalar_one_or_none()
    device_restored = False
    device_missing = device is None
    if device is not None:
        device_restored = await try_restore_device(
            db,
            device_id=order.device_id,
            current_order_id=order.id,
            operator_id=account.account_id,
            operator_name=account.real_name,
            now=now,
        )
    # 4. 操作日志（记录恢复结果与边界情况，便于排查脏数据）
    log_remark = {
        "action": "finish_repair_order",
        "order_no": order.order_no,
        "device_restored": device_restored,
    }
    if fault_missing:
        log_remark["fault_missing"] = True
    if device_missing:
        log_remark["device_missing"] = "关联设备已删除，跳过设备状态恢复"
    elif not device_restored:
        log_remark["device_kept_fault"] = "设备仍存在其他未完结故障工单，保持故障状态"
    await write_log(db, "DEVICE", "UPDATE", account, order.id, "DEVICE", log_remark)
    # 5. 单事务原子提交：工单/故障/设备任一失败整体回滚，杜绝"工单已归档但设备未恢复"脏数据
    await db.commit()
    # 6. 事务提交后异步通知上层轨迹模块（仅当设备真正恢复，避免外部依赖拖垮主事务）
    if device_restored:
        try:
            await notifier.broadcast_all(
                {
                    "type": "DEVICE_STATUS_RESTORED",
                    "device_id": order.device_id,
                    "device_code": order.device_code,
                    "old_status": "FAULT",
                    "new_status": settings.repair_restore_status,
                    "restored_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
        except Exception:
            # 通知失败不影响主流程，仅记录到日志上下文
            pass
    if device_missing:
        msg = "工单已归档，关联设备已删除，跳过设备状态恢复"
    elif device_restored:
        msg = "工单已完成归档，设备状态已恢复"
    else:
        msg = "工单已归档，设备仍存在其他未完结故障工单，保持故障状态"
    return ok(message=msg)


@router.get("/repair-orders/dispatch-logs")
async def list_repair_dispatch_logs(
    order_id: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: SysAccount = Depends(require_permission("device:info:view")),
):
    stmt = select(RepairDispatchLog)
    count_stmt = select(func.count()).select_from(RepairDispatchLog)
    if order_id is not None:
        stmt = stmt.where(RepairDispatchLog.order_id == order_id)
        count_stmt = count_stmt.where(RepairDispatchLog.order_id == order_id)
    total = (await db.execute(count_stmt)).scalar_one()
    rows = (
        await db.execute(stmt.order_by(RepairDispatchLog.id.desc()).offset((page - 1) * size).limit(size))
    ).scalars().all()
    items = [
        {
            "id": log.id,
            "order_id": log.order_id,
            "fault_id": log.fault_id,
            "device_id": log.device_id,
            "strategy": log.strategy,
            "candidate_count": log.candidate_count,
            "load_snapshot": log.load_snapshot,
            "winner_id": log.winner_id,
            "winner_name": log.winner_name,
            "result": log.result,
            "remark": log.remark,
            "create_time": fmt(log.create_time),
        }
        for log in rows
    ]
    return ok(page_result(items, total, page, size))


@router.get("/repair-orders/{order_id}")
async def repair_order_detail(order_id: int, db: AsyncSession = Depends(get_db), _: SysAccount = Depends(require_permission("device:repair"))):
    row = (
        await db.execute(
            select(RepairOrder, FaultRecord)
            .join(FaultRecord, FaultRecord.id == RepairOrder.fault_id)
            .where(RepairOrder.id == order_id, RepairOrder.is_deleted == 0)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="维修工单不存在")
    order, fault = row
    device = (await db.execute(select(Device).where(Device.id == order.device_id))).scalar_one_or_none()
    dispatch_log = (
        await db.execute(
            select(RepairDispatchLog).where(RepairDispatchLog.order_id == order.id).order_by(RepairDispatchLog.id.desc()).limit(1)
        )
    ).scalar_one_or_none()
    log_rows = (
        await db.execute(
            select(FaOperationLog, SysAccount.real_name)
            .outerjoin(SysAccount, SysAccount.account_id == FaOperationLog.operator_id)
            .where(
                FaOperationLog.module_code == "DEVICE",
                FaOperationLog.target_id == order.id,
                FaOperationLog.target_type == "DEVICE",
            )
            .order_by(FaOperationLog.log_id)
        )
    ).all()
    history = [
        {
            "status": "PENDING",
            "status_name": "待处理",
            "time": fmt(order.assigned_at or order.create_time),
            "operator": f"系统自动派发 → {order.assigned_name}" if order.assigned_name else "系统自动派单（无候选维修人员）",
        }
    ]
    if order.started_at is not None:
        history.append({"status": "REPAIRING", "status_name": "维修中", "time": fmt(order.started_at), "operator": order.assigned_name})
    if order.completed_at is not None:
        history.append({"status": "COMPLETED", "status_name": "已完成", "time": fmt(order.completed_at), "operator": order.operator_name})
    logs = []
    for op_log, real_name in log_rows:
        action = None
        if op_log.operation_content:
            try:
                action = json.loads(op_log.operation_content).get("action")
            except (json.JSONDecodeError, AttributeError):
                action = None
        logs.append({"operator_name": real_name or "系统", "operated_at": fmt(op_log.operated_at), "action": action, "content": op_log.operation_content})
    return ok(
        {
            "id": order.id,
            "order_no": order.order_no,
            "fault_id": order.fault_id,
            "device_id": order.device_id,
            "device_code": order.device_code,
            "device_name": order.device_name,
            "status": order.status,
            "damage_cause": order.damage_cause,
            "repair_detail": order.repair_detail,
            "assigned_to": order.assigned_to,
            "assigned_name": order.assigned_name,
            "dispatch_strategy": order.dispatch_strategy,
            "assigned_at": fmt(order.assigned_at),
            "plan_finish_time": fmt(order.plan_finish_time),
            "started_at": fmt(order.started_at),
            "completed_at": fmt(order.completed_at),
            "create_time": fmt(order.create_time),
            "operator_name": order.operator_name,
            "fault_type": fault.fault_type,
            "fault_level": fault.fault_level,
            "fault_desc": fault.fault_desc,
            "fault_occurrence_time": fmt(fault.occurrence_time),
            "fault_disposal_status": fault.disposal_status,
            "device_type": device.device_type if device else None,
            "device_ip": device.ip_address if device else None,
            "device_location": device.location_text if device else None,
            "device_region": device.region_name if device else None,
            "dispatch_rule_desc": "平均负载派发：优先派给当前未完成维修工单数量最少的员工，负载相同按员工ID稳定排序" if order.dispatch_strategy == "LEAST_LOAD" else None,
            "dispatch_result": dispatch_log.result if dispatch_log else None,
            "candidate_count": dispatch_log.candidate_count if dispatch_log else None,
            "load_snapshot": dispatch_log.load_snapshot if dispatch_log else None,
            "history": history,
            "logs": logs,
        }
    )
