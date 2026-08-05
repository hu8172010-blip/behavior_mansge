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
    TrackPassItem,
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
    "reid_cross_camera": ("跨摄像头关联", 2),
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
    device_ids: list[int] | None = None,
    lab_record_id: int | None = None,
    video_path: str | None = None,
    video_path_b: str | None = None,
    video_job_id: str | None = None,
    create_work_orders: bool = True,
    video_start: datetime | None = None,
    is_lab: bool = False,
) -> dict[str, int]:
    """Write an anomaly_tracker result into the business tables."""
    events = result.get("events", [])
    tracks = result.get("tracks", [])
    if not video_start:
        video_start = datetime.now()

    if device_ids:
        valid = []
        for did in device_ids:
            if not did:
                continue
            exists = (await db.execute(select(Device.id).where(Device.id == did))).scalar_one_or_none()
            if exists:
                valid.append(did)
        resolved_device_ids = valid if valid else [await _resolve_device_id(db, device_id)]
    else:
        resolved_device_ids = [await _resolve_device_id(db, device_id)]

    is_dual = len(resolved_device_ids) > 1
    camera_a = resolved_device_ids[0]
    camera_b = resolved_device_ids[1] if is_dual else None
    device_route = "-".join(str(d) for d in resolved_device_ids)

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
            device_route=device_route,
            first_device_id=camera_a,
            last_device_id=camera_b if camera_b else camera_a,
            chain_start_time=video_start + timedelta(seconds=first_seen),
            chain_end_time=video_start + timedelta(seconds=last_seen),
            total_duration_sec=int(last_seen - first_seen),
            chain_status=1,
            is_lab=is_lab_value,
            lab_record_id=lab_record_id,
            is_archived=0 if is_lab_value else 1,
        )
        db.add(chain)
        await db.flush()
        track_to_chain[track_id] = chain.id

    behaviors: list[FaAbnormalBehavior] = []
    alerts: list[FaBehaviorAlert] = []
    work_orders: list[FaWorkOrder] = []

    is_first_alert = True
    model_result_json = json.dumps(result, ensure_ascii=False, default=str) if is_lab_value else None
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
            camera_id=camera_a,
            camera_b_id=camera_b,
            lab_record_id=lab_record_id,
            confidence_score=Decimal(str(round(confidence, 4))) if confidence is not None else None,
            is_lab=is_lab_value,
            is_archived=0 if is_lab_value else 1,
            model_evidence=json.dumps(event, ensure_ascii=False, default=str)[:2000],
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
            lab_record_id=lab_record_id,
            camera_a_id=camera_a,
            camera_b_id=camera_b,
            is_dual_video=1 if is_dual else 0,
            video_path=video_path,
            video_path_b=video_path_b,
            video_job_id=video_job_id,
            model_result_json=model_result_json if is_first_alert else None,
            severity_level_id=behavior.severity_level_id,
            alert_status_id=1,
            alert_time=detected_at,
            is_marked_focus=0,
            is_lab=is_lab_value,
        )
        is_first_alert = False
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


async def ingest_collection_result(
    db: AsyncSession,
    result: dict[str, Any],
    device_ids: list[int],
    account_id: int | None,
    lab_record_id: int | None,
    video_path: str | None = None,
    video_path_b: str | None = None,
    video_job_id: str | None = None,
    video_job_id_b: str | None = None,
    video_start: datetime | None = None,
    is_lab: bool = False,
) -> dict[str, int]:
    """Convert a ReID collection result into the business tables.

    The collection result contains matched persons across multiple videos.
    Each person becomes a cross-camera track chain; any events inside the
    person (or a synthetic cross-camera event) become abnormal behaviors.
    """
    persons = result.get("persons") or []
    videos = result.get("videos") or []
    if not video_start:
        video_start = datetime.now()

    # Map each video's job_id to the selected camera device id (upload order)
    job_to_device: dict[str, int | None] = {}
    for idx, video in enumerate(videos):
        job_id = str(video.get("job_id", ""))
        if job_id:
            job_to_device[job_id] = device_ids[idx] if idx < len(device_ids) else None

    is_lab_value = 1 if is_lab else 0
    model_result_json = json.dumps(result, ensure_ascii=False, default=str)
    first_alert = True
    behaviors: list[FaAbnormalBehavior] = []
    alerts: list[FaBehaviorAlert] = []

    for person in persons:
        global_id = str(person.get("global_person_id", ""))
        segments = sorted(
            person.get("trajectory_segments") or [],
            key=lambda s: float(s.get("start_time", 0.0)),
        )
        if not segments:
            continue

        first_seen = float(segments[0].get("start_time", 0.0))
        last_seen = float(segments[-1].get("end_time", 0.0))

        anon = DmAnonymousPerson(
            appearance_desc=f"ReID 全局人员 {global_id}",
            first_seen_at=video_start + timedelta(seconds=first_seen),
            last_seen_at=video_start + timedelta(seconds=last_seen),
            is_focused=0,
            is_lab=is_lab_value,
        )
        db.add(anon)
        await db.flush()

        device_route_ids: list[int] = []
        chain_items: list[tuple[int, int, datetime, datetime | None, int]] = []
        for sort, seg in enumerate(segments, start=1):
            job_id = str(seg.get("job_id", ""))
            device_id = job_to_device.get(job_id)
            if not device_id:
                device_id = device_ids[0] if device_ids else await _resolve_device_id(db, None)
            device_route_ids.append(int(device_id))

            seg_start = float(seg.get("start_time", 0.0))
            seg_end = float(seg.get("end_time", 0.0))
            appear = video_start + timedelta(seconds=seg_start)
            disappear = video_start + timedelta(seconds=seg_end)
            stay = int(seg_end - seg_start)
            chain_items.append((int(device_id), sort, appear, disappear, stay))

        chain = TrackPassChain(
            chain_unique_id=f"reid_{global_id}_{uuid.uuid4().hex[:8]}",
            person_id=anon.person_id,
            confidence=Decimal("0.8"),
            device_route="-".join(str(d) for d in device_route_ids),
            first_device_id=device_route_ids[0],
            last_device_id=device_route_ids[-1],
            chain_start_time=video_start + timedelta(seconds=first_seen),
            chain_end_time=video_start + timedelta(seconds=last_seen),
            total_duration_sec=int(last_seen - first_seen),
            chain_status=1,
            is_lab=is_lab_value,
            lab_record_id=lab_record_id,
            is_archived=0 if is_lab else 1,
        )
        db.add(chain)
        await db.flush()

        for device_id, sort, appear, disappear, stay in chain_items:
            item = TrackPassItem(
                chain_id=chain.id,
                device_id=device_id,
                sort=sort,
                appear_time=appear,
                disappear_time=disappear,
                stay_duration_sec=stay,
            )
            db.add(item)

        # Use events from the person, or synthesize a cross-camera event
        person_events = person.get("events") or []
        if not person_events:
            person_events = [
                {
                    "event_type": "reid_cross_camera",
                    "start_time": first_seen,
                    "end_time": last_seen,
                    "confidence": 0.8,
                    "track_ids": [chain.id],
                }
            ]

        for event in person_events:
            event_type = str(event.get("event_type", "reid_cross_camera"))
            cn_name, default_sev = EVENT_TYPE_MAP.get(event_type, (event_type, 2))
            behavior_type = await _get_or_create_behavior_type(db, cn_name, default_sev)

            start_sec = float(event.get("start_time", first_seen))
            end_sec = float(event.get("end_time", last_seen))
            confidence = float(event.get("confidence", 0.8))
            detected_at = video_start + timedelta(seconds=start_sec)

            behavior = FaAbnormalBehavior(
                behavior_type_id=behavior_type.behavior_type_id,
                person_id=anon.person_id,
                track_id=chain.id,
                severity_level_id=behavior_type.default_severity_level_id or default_sev,
                alert_status_id=1,
                detected_at=detected_at,
                camera_id=device_route_ids[0],
                camera_b_id=device_route_ids[-1] if len(device_route_ids) > 1 else None,
                lab_record_id=lab_record_id,
                confidence_score=Decimal(str(round(confidence, 4))) if confidence is not None else None,
                is_lab=is_lab_value,
                is_archived=0 if is_lab else 1,
                reid_result=json.dumps(person, ensure_ascii=False, default=str)[:2000],
                model_evidence=json.dumps(event, ensure_ascii=False, default=str)[:2000],
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
                lab_record_id=lab_record_id,
                camera_a_id=device_route_ids[0],
                camera_b_id=device_route_ids[-1] if len(device_route_ids) > 1 else None,
                is_dual_video=1,
                video_path=video_path,
                video_path_b=video_path_b,
                video_job_id=video_job_id,
                video_job_id_b=video_job_id_b,
                model_result_json=model_result_json if first_alert else None,
                severity_level_id=behavior.severity_level_id,
                alert_status_id=1,
                alert_time=detected_at,
                is_marked_focus=0,
                is_lab=is_lab_value,
            )
            db.add(alert)
            await db.flush()
            alerts.append(alert)
            first_alert = False

    await db.commit()
    return {
        "behavior_count": len(behaviors),
        "alert_count": len(alerts),
        "work_order_count": 0,
    }
