from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_account
from app.db.session import get_db
from app.models import (
    Device,
    DmAnonymousPerson,
    DmBehaviorType,
    DmSeverityLevel,
    DmWorkOrderStatus,
    FaAbnormalBehavior,
    FaBehaviorAlert,
    FaWorkOrder,
    SysAccount,
)
from app.schemas.common import ok, page_result
from app.services.log_service import ROLE_KEY_MAP, write_log

router = APIRouter()


def order_select():
    return (
        select(
            FaWorkOrder,
            DmWorkOrderStatus.status_name,
            DmBehaviorType.type_name,
            DmSeverityLevel.level_name,
            FaAbnormalBehavior.description,
            SysAccount.real_name.label("assignee_name"),
        )
        .join(DmWorkOrderStatus, DmWorkOrderStatus.work_order_status_id == FaWorkOrder.work_order_status_id)
        .join(FaAbnormalBehavior, FaAbnormalBehavior.behavior_id == FaWorkOrder.behavior_id)
        .join(DmBehaviorType, DmBehaviorType.behavior_type_id == FaAbnormalBehavior.behavior_type_id)
        .join(DmSeverityLevel, DmSeverityLevel.severity_level_id == FaAbnormalBehavior.severity_level_id)
        .join(SysAccount, SysAccount.account_id == FaWorkOrder.assigned_to)
    )


def fmt(dt: datetime | None) -> str | None:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


def row_to_dict(row) -> dict:
    order: FaWorkOrder = row[0]
    return {
        "work_order_id": order.work_order_id,
        "work_order_no": order.work_order_no,
        "alert_id": order.alert_id,
        "behavior_id": order.behavior_id,
        "work_order_status_id": order.work_order_status_id,
        "status_name": row[1],
        "type_name": row[2],
        "level_name": row[3],
        "description": row[4],
        "assignee_name": row[5],
        "assigned_to": order.assigned_to,
        "assigned_at": fmt(order.assigned_at),
        "handled_at": fmt(order.handled_at),
        "handle_result": order.handle_result,
        "handle_duration_minutes": order.handle_duration_minutes,
        "is_lab": order.is_lab,
    }


@router.get("")
async def list_orders(
    status_id: int | None = Query(default=None),
    include_lab: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: SysAccount = Depends(get_current_account),
):
    stmt = order_select()
    count_stmt = select(func.count()).select_from(FaWorkOrder)
    if not include_lab:
        stmt = stmt.where(FaWorkOrder.is_lab == 0)
        count_stmt = count_stmt.where(FaWorkOrder.is_lab == 0)
    if status_id is not None:
        stmt = stmt.where(FaWorkOrder.work_order_status_id == status_id)
        count_stmt = count_stmt.where(FaWorkOrder.work_order_status_id == status_id)
    total = (await db.execute(count_stmt)).scalar_one()
    rows = (
        await db.execute(stmt.order_by(FaWorkOrder.assigned_at.desc()).offset((page - 1) * size).limit(size))
    ).all()
    return ok(page_result([row_to_dict(row) for row in rows], total, page, size))


@router.get("/{work_order_id}")
async def order_detail(work_order_id: int, db: AsyncSession = Depends(get_db), _: SysAccount = Depends(get_current_account)):
    row = (await db.execute(order_select().where(FaWorkOrder.work_order_id == work_order_id))).first()
    if row is None:
        raise HTTPException(status_code=404, detail="工单不存在")
    data = row_to_dict(row)
    order: FaWorkOrder = row[0]
    behavior = (
        await db.execute(select(FaAbnormalBehavior).where(FaAbnormalBehavior.behavior_id == order.behavior_id))
    ).scalar_one()
    camera = (
        await db.execute(select(Device).where(Device.id == behavior.camera_id))
    ).scalar_one_or_none() if behavior.camera_id else None
    person = (
        await db.execute(select(DmAnonymousPerson).where(DmAnonymousPerson.person_id == behavior.person_id))
    ).scalar_one_or_none() if behavior.person_id else None
    assigner = (
        await db.execute(select(SysAccount.real_name).where(SysAccount.account_id == order.assigned_by))
    ).scalar_one_or_none()
    data.update(
        {
            "detected_at": fmt(behavior.detected_at),
            "confidence_score": float(behavior.confidence_score) if behavior.confidence_score is not None else None,
            "track_id": behavior.track_id,
            "camera_name": camera.device_name if camera else None,
            "camera_code": camera.device_code if camera else None,
            "region_name": camera.region_name if camera else None,
            "person_desc": person.appearance_desc if person else None,
            "assigner_name": assigner,
        }
    )
    return ok(data)


class CreateBody(BaseModel):
    alert_id: int
    assigned_to: int


@router.post("")
async def create_order(body: CreateBody, db: AsyncSession = Depends(get_db), account: SysAccount = Depends(get_current_account)):
    alert = (
        await db.execute(select(FaBehaviorAlert).where(FaBehaviorAlert.alert_id == body.alert_id))
    ).scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="预警不存在")
    if alert.alert_status_id != 2:
        raise HTTPException(status_code=400, detail="仅已确认状态的预警可以派单")
    assignee = (
        await db.execute(select(SysAccount).where(SysAccount.account_id == body.assigned_to, SysAccount.status == 1))
    ).scalar_one_or_none()
    if assignee is None:
        raise HTTPException(status_code=400, detail="处理人不存在或已禁用")

    now = datetime.now()
    prefix = f"WO{now.strftime('%Y%m%d')}"
    last_no = (
        await db.execute(
            select(FaWorkOrder.work_order_no).where(FaWorkOrder.work_order_no.like(f"{prefix}%")).order_by(FaWorkOrder.work_order_no.desc()).limit(1)
        )
    ).scalar_one_or_none()
    seq = int(last_no[-4:]) + 1 if last_no else 1
    order = FaWorkOrder(
        work_order_no=f"{prefix}{seq:04d}",
        alert_id=alert.alert_id,
        behavior_id=alert.behavior_id,
        work_order_status_id=1,
        assigned_to=assignee.account_id,
        handler_role=ROLE_KEY_MAP.get(assignee.type_id),
        assigned_by=account.account_id,
        assigned_at=now,
    )
    db.add(order)
    alert.alert_status_id = 3
    behavior = (
        await db.execute(select(FaAbnormalBehavior).where(FaAbnormalBehavior.behavior_id == alert.behavior_id))
    ).scalar_one()
    behavior.alert_status_id = 3
    await db.flush()
    await write_log(db, "ABNORMAL_BEHAVIOR", "UPDATE", account, alert.alert_id, "BEHAVIOR", {"action": "assign", "work_order_no": order.work_order_no, "assigned_to": assignee.account_id})
    await db.commit()
    return ok({"work_order_id": order.work_order_id, "work_order_no": order.work_order_no}, "派单成功")


class HandleBody(BaseModel):
    handle_result: str


@router.put("/{work_order_id}/handle")
async def handle_order(work_order_id: int, body: HandleBody, db: AsyncSession = Depends(get_db), account: SysAccount = Depends(get_current_account)):
    order = (
        await db.execute(select(FaWorkOrder).where(FaWorkOrder.work_order_id == work_order_id))
    ).scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail="工单不存在")
    if order.work_order_status_id not in (1, 2):
        raise HTTPException(status_code=400, detail="仅待处理或处理中的工单可以提交处置结果")
    now = datetime.now()
    order.work_order_status_id = 3
    order.handled_at = now
    order.handle_result = body.handle_result
    order.handle_duration_minutes = int((now - order.assigned_at).total_seconds() // 60)
    alert = (await db.execute(select(FaBehaviorAlert).where(FaBehaviorAlert.alert_id == order.alert_id))).scalar_one()
    alert.alert_status_id = 5
    alert.resolved_at = now
    behavior = (
        await db.execute(select(FaAbnormalBehavior).where(FaAbnormalBehavior.behavior_id == order.behavior_id))
    ).scalar_one()
    behavior.alert_status_id = 5
    await write_log(db, "ABNORMAL_BEHAVIOR", "UPDATE", account, order.work_order_id, "BEHAVIOR", {"action": "resolve", "work_order_no": order.work_order_no})
    await db.commit()
    return ok(message="工单处置完成")


@router.put("/{work_order_id}/close")
async def close_order(work_order_id: int, db: AsyncSession = Depends(get_db), account: SysAccount = Depends(get_current_account)):
    order = (
        await db.execute(select(FaWorkOrder).where(FaWorkOrder.work_order_id == work_order_id))
    ).scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail="工单不存在")
    if order.work_order_status_id != 3:
        raise HTTPException(status_code=400, detail="仅已完成的工单可以关闭归档")
    order.work_order_status_id = 4
    await write_log(db, "ABNORMAL_BEHAVIOR", "UPDATE", account, order.work_order_id, "BEHAVIOR", {"action": "archive", "work_order_no": order.work_order_no})
    await db.commit()
    return ok(message="工单已关闭归档")
