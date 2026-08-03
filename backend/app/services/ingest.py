import json
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Device,
    DmAnonymousPerson,
    DmBehaviorType,
    DmSeverityLevel,
    FaAbnormalBehavior,
    FaBehaviorAlert,
    FaWorkOrder,
    TrackPassChain,
)

EVENT_TYPE_MAP: dict[str, tuple[str, int]] = {
    "suspected_fall": ("跌倒", 1),
    "suspected_violence": ("暴力冲突", 1),
    "suspected_intense_interaction": ("激烈互动", 2),
    "abnormal_staying": ("异常滞留", 3),
    "long_loitering": ("长时间徘徊", 2),
    "rapid_movement": ("快速移动", 3),
    "repeated_entry_exit": ("反复出入", 2),
    "route_deviation": ("路线偏离", 3),
    "dangerous_zone_proximity": ("危险区域靠近", 1),
}


async def _resolve_device_id(db: AsyncSession, device_id: int | None) -> int:
    if device_id:
        exists = (await db.execute(select(Device).where(Device.id == device_id))).scalar_one_or_none()
        if exists:
            return device_id
    any_id = (await db.execute(select(Device.id).limit(1))).scalar_one_or_none()
    if any_id is not None:
        return any_id
    device = Device(
        device_code="LAB",
        device_name="模拟实验室设备",
        device_type="camera",
        status="online",
    )
    db.add(device)
    await db.flush()
    await db.refresh(device)
    return device.id


async def _get_or_create_behavior_type(db: AsyncSession, name: str, default_severity: int) -> DmBehaviorType:
    stmt = select(DmBehaviorType).where(DmBehaviorType.type_name == name)
    result = await db.execute(stmt)
    obj = result.scalar_one_or_none()
    if obj is not None:
        return obj
    obj = DmBehaviorType(
        type_name=name,
        default_severity_level_id=default_severity,
        is_enabled=1,
    )
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    return obj


async def ingest_anomaly_result(
    db: AsyncSession,
    result: dict[str, Any],
    device_id: int | None,
    account_id: int | None,
    create_work_orders: bool = True,
    video_start: datetime | None = None,
    is_lab: bool = False,
) -> dict[str, int]:
    """Write an anomaly_tracker result into the business tables."""
    events = result.get("events", [])
    tracks = result.get("tracks", [])
    if not video_start:
        video_start = datetime.now()

    resolved_device_id = await _resolve_device_id(db, device_id)

    track_to_person: dict[int, int] = {}
    track_to_chain: dict[int, int] = {}

    is_lab_value = 1 if is_lab else 0
    for track in tracks:
        track_id = int(track.get("track_id", 0))
        if not track_id:
            continue
        first_seen = float(track.get("first_seen", 0.0))
        last_seen = float(track.get("last_seen", 0.0))
        person = DmAnonymousPerson(
            appearance_desc=None,
            first_seen_at=video_start + timedelta(seconds=first_seen),
            last_seen_at=video_start + timedelta(seconds=last_seen),
            is_focused=0,
            is_lab=is_lab_value,
        )
        db.add(person)
        await db.flush()
        track_to_person[track_id] = person.person_id

        chain = TrackPassChain(
            chain_unique_id=f"{track_id}_{uuid.uuid4().hex[:8]}",
            person_id=person.person_id,
            confidence=Decimal("0.8"),
            device_route=str(resolved_device_id),
            first_device_id=resolved_device_id,
            last_device_id=resolved_device_id,
            chain_start_time=video_start + timedelta(seconds=first_seen),
            chain_end_time=video_start + timedelta(seconds=last_seen),
            total_duration_sec=int(last_seen - first_seen),
            chain_status=1,
            is_lab=is_lab_value,
        )
        db.add(chain)
        await db.flush()
        track_to_chain[track_id] = chain.id

    behaviors: list[FaAbnormalBehavior] = []
    alerts: list[FaBehaviorAlert] = []
    work_orders: list[FaWorkOrder] = []

    for event in events:
        event_type = str(event.get("event_type", ""))
        cn_name, default_sev = EVENT_TYPE_MAP.get(event_type, (event_type, 2))
        behavior_type = await _get_or_create_behavior_type(db, cn_name, default_sev)

        track_ids = event.get("track_ids", [])
        track_id = int(track_ids[0]) if track_ids else 0
        person_id = track_to_person.get(track_id)
        chain_id = track_to_chain.get(track_id)

        start_sec = float(event.get("start_time", 0.0))
        end_sec = float(event.get("end_time", 0.0))
        confidence = float(event.get("confidence", 0.0))
        detected_at = video_start + timedelta(seconds=start_sec)

        behavior = FaAbnormalBehavior(
            behavior_type_id=behavior_type.behavior_type_id,
            person_id=person_id,
            track_id=chain_id,
            severity_level_id=behavior_type.default_severity_level_id or default_sev,
            alert_status_id=1,
            detected_at=detected_at,
            camera_id=resolved_device_id,
            confidence_score=Decimal(str(round(confidence, 4))) if confidence is not None else None,
            is_lab=is_lab_value,
            description=json.dumps(
                {
                    "event_type": event_type,
                    "start_time": start_sec,
                    "end_time": end_sec,
                    "evidence": event.get("evidence", {}),
                },
                ensure_ascii=False,
                default=str,
            )[:500],
        )
        db.add(behavior)
        await db.flush()
        behaviors.append(behavior)

        alert = FaBehaviorAlert(
            behavior_id=behavior.behavior_id,
            severity_level_id=behavior.severity_level_id,
            alert_status_id=1,
            alert_time=detected_at,
            is_marked_focus=0,
            is_lab=is_lab_value,
        )
        db.add(alert)
        await db.flush()
        alerts.append(alert)

        if create_work_orders and (behavior.severity_level_id == 1):
            ts = datetime.now().strftime("%y%m%d%H%M%S")
            wo = FaWorkOrder(
                work_order_no=f"WO{ts}{behavior.behavior_id:06d}",
                alert_id=alert.alert_id,
                behavior_id=behavior.behavior_id,
                work_order_status_id=1,
                assigned_to=account_id,
                assigned_by=account_id,
                assigned_at=detected_at,
                is_lab=is_lab_value,
            )
            db.add(wo)
            work_orders.append(wo)

    await db.commit()
    return {
        "behavior_count": len(behaviors),
        "alert_count": len(alerts),
        "work_order_count": len(work_orders),
    }
