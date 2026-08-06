from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_account
from app.db.session import get_db
from app.models import (
    DmAlertStatus,
    DmBehaviorType,
    DmSeverityLevel,
    DmWorkOrderStatus,
    SysAccount,
    SysUserType,
)
from app.schemas.common import ok

router = APIRouter(dependencies=[Depends(get_current_account)])


@router.get("/enums")
async def enums(db: AsyncSession = Depends(get_db)):
    severity = (await db.execute(select(DmSeverityLevel).order_by(DmSeverityLevel.level_sort))).scalars().all()
    alert_status = (await db.execute(select(DmAlertStatus).order_by(DmAlertStatus.status_sort))).scalars().all()
    order_status = (await db.execute(select(DmWorkOrderStatus).order_by(DmWorkOrderStatus.status_sort))).scalars().all()
    behavior_types = (
        (await db.execute(select(DmBehaviorType).where(DmBehaviorType.is_enabled == 1).order_by(DmBehaviorType.behavior_type_id)))
        .scalars()
        .all()
    )
    roles = (await db.execute(select(SysUserType).where(SysUserType.type_id != 1).order_by(SysUserType.type_id))).scalars().all()
    handlers = (
        (
            await db.execute(
                select(SysAccount.account_id, SysAccount.real_name, SysAccount.type_id).where(
                    SysAccount.status == 1, SysAccount.type_id != 1
                )
            )
        )
        .all()
    )
    return ok(
        {
            "severity_levels": [{"id": s.severity_level_id, "name": s.level_name} for s in severity],
            "alert_statuses": [{"id": s.alert_status_id, "name": s.status_name} for s in alert_status],
            "work_order_statuses": [{"id": s.work_order_status_id, "name": s.status_name} for s in order_status],
            "behavior_types": [{"id": t.behavior_type_id, "name": t.type_name} for t in behavior_types],
            "roles": [{"id": r.type_id, "name": r.type_name, "desc": r.type_desc} for r in roles],
            "handlers": [{"account_id": h.account_id, "real_name": h.real_name} for h in handlers],
        }
    )
