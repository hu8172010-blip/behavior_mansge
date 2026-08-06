"""设备维修工单归档后的设备状态恢复服务。

业务规则：
1. 工单归档完成需要联动更新设备台账；
2. 只有该设备全部关联故障工单均归档完成，设备状态才由【故障】更新为【在线正常】；
3. 设备恢复同时刷新设备健康分、最近心跳；
4. 如果设备仍存在其他未完结故障工单，即使当前工单归档，设备依旧保持故障状态，不做恢复。

实现要点：
- 用单条带 NOT EXISTS 子查询的 UPDATE 把"是否还有未完结工单"的判定下沉到 DB，
  与外层 UPDATE 原子执行，从根本上消除多工单并发归档时的检查-更新竞态；
- 返回 rowcount > 0 表示设备真正发生恢复，调用方据此决定是否向上层轨迹模块发通知；
- 设备已删除（is_deleted=1）时不恢复，返回 False，由调用方记录告警日志。
"""

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

# 未完结工单状态：归档完成判定时排除这些状态以外的工单
OPEN_REPAIR_STATUSES = ("PENDING", "REPAIRING")


async def try_restore_device(
    db: AsyncSession,
    *,
    device_id: int,
    current_order_id: int,
    operator_id: int,
    operator_name: str,
    now: datetime,
) -> bool:
    """尝试将设备从 FAULT 恢复为 ONLINE。

    仅当该设备不存在其他未完结（PENDING/REPAIRING）维修工单时才真正更新；
    否则 UPDATE 影响 0 行，设备保持故障状态，符合业务规则 7。
    返回 True 表示设备状态确实由 FAULT 恢复为 ONLINE。
    """
    stmt = text(
        """
        UPDATE device
        SET status = :status,
            health_score = :health_score,
            last_heartbeat_time = :now,
            operator_id = :operator_id,
            operator_name = :operator_name,
            update_time = :now
        WHERE id = :device_id
          AND is_deleted = 0
          AND status = 'FAULT'
          AND NOT EXISTS (
              SELECT 1 FROM device_repair_order ro
              WHERE ro.device_id = :device_id
                AND ro.is_deleted = 0
                AND ro.id <> :current_order_id
                AND ro.status IN (:open_status_1, :open_status_2)
          )
        """
    )
    result = await db.execute(
        stmt,
        {
            "status": settings.repair_restore_status,
            "health_score": settings.repair_restore_health_score,
            "now": now,
            "operator_id": operator_id,
            "operator_name": operator_name,
            "device_id": device_id,
            "current_order_id": current_order_id,
            "open_status_1": OPEN_REPAIR_STATUSES[0],
            "open_status_2": OPEN_REPAIR_STATUSES[1],
        },
    )
    return (result.rowcount or 0) > 0


async def device_exists_and_active(db: AsyncSession, device_id: int) -> bool:
    """设备是否存在且未被软删除。"""
    row = (
        await db.execute(
            text("SELECT 1 FROM device WHERE id = :did AND is_deleted = 0 LIMIT 1"),
            {"did": device_id},
        )
    ).first()
    return row is not None


__all__ = ["try_restore_device", "device_exists_and_active", "OPEN_REPAIR_STATUSES"]
