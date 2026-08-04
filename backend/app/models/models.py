from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Integer, Numeric, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SysUserType(Base):
    __tablename__ = "sys_user_type"

    type_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type_name: Mapped[str] = mapped_column(String(64))
    type_desc: Mapped[str | None] = mapped_column(String(255))
    create_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class SysPermission(Base):
    __tablename__ = "sys_permission"

    perm_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    perm_name: Mapped[str] = mapped_column(String(64))
    perm_key: Mapped[str] = mapped_column(String(64))
    perm_type: Mapped[int] = mapped_column(SmallInteger)
    parent_id: Mapped[int] = mapped_column(BigInteger, default=0)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    create_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())


class SysAccount(Base):
    __tablename__ = "sys_account"

    account_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    login_name: Mapped[str] = mapped_column(String(64))
    password: Mapped[str] = mapped_column(String(255))
    real_name: Mapped[str] = mapped_column(String(64))
    dept: Mapped[str | None] = mapped_column(String(64))
    phone: Mapped[str | None] = mapped_column(String(32))
    type_id: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[int] = mapped_column(SmallInteger, default=1)
    last_login_time: Mapped[datetime | None] = mapped_column(DateTime)
    create_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class SysTypePermission(Base):
    __tablename__ = "sys_type_permission"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type_id: Mapped[int] = mapped_column(BigInteger)
    perm_id: Mapped[int] = mapped_column(BigInteger)


class SysAccountPermission(Base):
    __tablename__ = "sys_account_permission"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(BigInteger)
    perm_id: Mapped[int] = mapped_column(BigInteger)


class Device(Base):
    __tablename__ = "device"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    device_code: Mapped[str] = mapped_column(String(32))
    device_name: Mapped[str] = mapped_column(String(128))
    device_type: Mapped[str] = mapped_column(String(32))
    location_text: Mapped[str | None] = mapped_column(String(255))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    region_code: Mapped[str | None] = mapped_column(String(64))
    region_name: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    health_score: Mapped[int | None] = mapped_column(Integer)
    video_quality: Mapped[str | None] = mapped_column(String(32))
    last_heartbeat_time: Mapped[datetime | None] = mapped_column(DateTime)
    channel_count: Mapped[int | None] = mapped_column(Integer)
    capability: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    port: Mapped[int | None] = mapped_column(Integer)
    manufacturer: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(64))
    firmware_version: Mapped[str | None] = mapped_column(String(64))
    install_time: Mapped[datetime | None] = mapped_column(DateTime)
    remark: Mapped[str | None] = mapped_column(String(500))
    operator_id: Mapped[int | None] = mapped_column(BigInteger)
    operator_name: Mapped[str | None] = mapped_column(String(64))
    is_deleted: Mapped[int] = mapped_column(SmallInteger, default=0)
    create_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class FaultRecord(Base):
    __tablename__ = "fault_record"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(BigInteger)
    device_code: Mapped[str] = mapped_column(String(32))
    fault_type: Mapped[str] = mapped_column(String(32))
    fault_level: Mapped[str] = mapped_column(String(32))
    fault_desc: Mapped[str | None] = mapped_column(String(500))
    occurrence_time: Mapped[datetime] = mapped_column(DateTime)
    recovery_time: Mapped[datetime | None] = mapped_column(DateTime)
    auto_recovery_time: Mapped[datetime | None] = mapped_column(DateTime)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    disposal_status: Mapped[str] = mapped_column(String(32))
    assigned_to: Mapped[int | None] = mapped_column(BigInteger)
    assigned_name: Mapped[str | None] = mapped_column(String(64))
    auto_recovery: Mapped[int] = mapped_column(SmallInteger, default=0)
    repair_result: Mapped[str | None] = mapped_column(String(32))
    repair_remark: Mapped[str | None] = mapped_column(String(500))
    closed_by: Mapped[int | None] = mapped_column(BigInteger)
    closed_name: Mapped[str | None] = mapped_column(String(64))
    operator_id: Mapped[int | None] = mapped_column(BigInteger)
    operator_name: Mapped[str | None] = mapped_column(String(64))
    is_deleted: Mapped[int] = mapped_column(SmallInteger, default=0)
    create_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class TrackPassChain(Base):
    __tablename__ = "track_pass_chain"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chain_unique_id: Mapped[str] = mapped_column(String(32))
    person_id: Mapped[int | None] = mapped_column(BigInteger)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    device_route: Mapped[str] = mapped_column(String(512))
    first_device_id: Mapped[int] = mapped_column(BigInteger)
    last_device_id: Mapped[int] = mapped_column(BigInteger)
    chain_start_time: Mapped[datetime] = mapped_column(DateTime)
    chain_end_time: Mapped[datetime | None] = mapped_column(DateTime)
    total_duration_sec: Mapped[int] = mapped_column(Integer, default=0)
    chain_status: Mapped[int] = mapped_column(SmallInteger, default=1)
    is_lab: Mapped[int] = mapped_column(SmallInteger, default=0)
    create_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())


class TrackPassItem(Base):
    __tablename__ = "track_pass_item"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chain_id: Mapped[int] = mapped_column(BigInteger)
    device_id: Mapped[int] = mapped_column(BigInteger)
    sort: Mapped[int] = mapped_column(Integer)
    appear_time: Mapped[datetime] = mapped_column(DateTime)
    disappear_time: Mapped[datetime | None] = mapped_column(DateTime)
    stay_duration_sec: Mapped[int] = mapped_column(Integer, default=0)


class DmSeverityLevel(Base):
    __tablename__ = "dm_severity_level"

    severity_level_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    level_name: Mapped[str] = mapped_column(String(16))
    level_sort: Mapped[int] = mapped_column(Integer)


class DmAlertStatus(Base):
    __tablename__ = "dm_alert_status"

    alert_status_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    status_name: Mapped[str] = mapped_column(String(16))
    status_sort: Mapped[int] = mapped_column(Integer)


class DmWorkOrderStatus(Base):
    __tablename__ = "dm_work_order_status"

    work_order_status_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    status_name: Mapped[str] = mapped_column(String(16))
    status_sort: Mapped[int] = mapped_column(Integer)


class DmAnonymousPerson(Base):
    __tablename__ = "dm_anonymous_person"

    person_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    appearance_desc: Mapped[str | None] = mapped_column(String(500))
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime)
    is_focused: Mapped[int] = mapped_column(SmallInteger, default=0)
    is_lab: Mapped[int] = mapped_column(SmallInteger, default=0)
    risk_level_id: Mapped[int | None] = mapped_column(BigInteger)
    matched_user_id: Mapped[int | None] = mapped_column(BigInteger)
    match_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    create_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class DmBehaviorType(Base):
    __tablename__ = "dm_behavior_type"

    behavior_type_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type_name: Mapped[str] = mapped_column(String(32))
    default_severity_level_id: Mapped[int | None] = mapped_column(BigInteger)
    description: Mapped[str | None] = mapped_column(String(255))
    is_enabled: Mapped[int] = mapped_column(SmallInteger, default=1)


class FaAbnormalBehavior(Base):
    __tablename__ = "fa_abnormal_behavior"

    behavior_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    behavior_type_id: Mapped[int] = mapped_column(BigInteger)
    person_id: Mapped[int | None] = mapped_column(BigInteger)
    track_id: Mapped[int | None] = mapped_column(BigInteger)
    severity_level_id: Mapped[int] = mapped_column(BigInteger)
    alert_status_id: Mapped[int] = mapped_column(BigInteger)
    detected_at: Mapped[datetime] = mapped_column(DateTime)
    camera_id: Mapped[int | None] = mapped_column(BigInteger)
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    description: Mapped[str | None] = mapped_column(String(500))
    is_lab: Mapped[int] = mapped_column(SmallInteger, default=0)
    create_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class FaBehaviorAlert(Base):
    __tablename__ = "fa_behavior_alert"

    alert_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    behavior_id: Mapped[int] = mapped_column(BigInteger)
    severity_level_id: Mapped[int] = mapped_column(BigInteger)
    alert_status_id: Mapped[int] = mapped_column(BigInteger)
    alert_time: Mapped[datetime] = mapped_column(DateTime)
    notify_method: Mapped[str | None] = mapped_column(String(100))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)
    confirmed_by: Mapped[int | None] = mapped_column(BigInteger)
    is_marked_focus: Mapped[int] = mapped_column(SmallInteger, default=0)
    is_lab: Mapped[int] = mapped_column(SmallInteger, default=0)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    create_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class FaWorkOrder(Base):
    __tablename__ = "fa_work_order"

    work_order_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    work_order_no: Mapped[str] = mapped_column(String(20))
    alert_id: Mapped[int] = mapped_column(BigInteger)
    behavior_id: Mapped[int] = mapped_column(BigInteger)
    work_order_status_id: Mapped[int] = mapped_column(BigInteger)
    assigned_to: Mapped[int] = mapped_column(BigInteger)
    handler_role: Mapped[str | None] = mapped_column(String(64))
    assigned_by: Mapped[int] = mapped_column(BigInteger)
    assigned_at: Mapped[datetime] = mapped_column(DateTime)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime)
    handle_result: Mapped[str | None] = mapped_column(String(500))
    handle_duration_minutes: Mapped[int | None] = mapped_column(Integer)
    is_lab: Mapped[int] = mapped_column(SmallInteger, default=0)
    create_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class LabRecord(Base):
    __tablename__ = "lab_record"

    record_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    record_name: Mapped[str] = mapped_column(String(128))
    account_id: Mapped[int] = mapped_column(BigInteger)
    device_id: Mapped[int | None] = mapped_column(BigInteger)
    video_filename: Mapped[str] = mapped_column(String(255))
    video_path: Mapped[str] = mapped_column(String(512))
    result_path: Mapped[str] = mapped_column(String(512))
    model_version: Mapped[str | None] = mapped_column(String(64))
    event_count: Mapped[int] = mapped_column(Integer, default=0)
    track_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[int] = mapped_column(SmallInteger, default=1)
    is_published: Mapped[int] = mapped_column(SmallInteger, default=0)
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    remark: Mapped[str | None] = mapped_column(String(500))
    create_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class FaOperationLog(Base):
    __tablename__ = "fa_operation_log"

    log_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    module_code: Mapped[str] = mapped_column(String(64))
    operation_type: Mapped[str] = mapped_column(String(32))
    operator_id: Mapped[int | None] = mapped_column(BigInteger)
    operator_role: Mapped[str | None] = mapped_column(String(64))
    target_id: Mapped[int | None] = mapped_column(BigInteger)
    target_type: Mapped[str | None] = mapped_column(String(32))
    operation_content: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    operated_at: Mapped[datetime | None] = mapped_column(DateTime)


class SysDataBackup(Base):
    __tablename__ = "sys_data_backup"

    backup_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    backup_name: Mapped[str] = mapped_column(String(128))
    backup_type: Mapped[str] = mapped_column(String(16), default="MANUAL")
    strategy_desc: Mapped[str | None] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(512))
    file_size: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[str] = mapped_column(String(16), default="SUCCESS")
    operator_id: Mapped[int | None] = mapped_column(BigInteger)
    operator_name: Mapped[str | None] = mapped_column(String(64))
    create_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())


class SysDataRestoreLog(Base):
    __tablename__ = "sys_data_restore_log"

    restore_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    backup_id: Mapped[int] = mapped_column(BigInteger)
    backup_name: Mapped[str | None] = mapped_column(String(128))
    restore_status: Mapped[str] = mapped_column(String(16), default="SUCCESS")
    result_msg: Mapped[str | None] = mapped_column(String(500))
    operator_id: Mapped[int | None] = mapped_column(BigInteger)
    operator_name: Mapped[str | None] = mapped_column(String(64))
    restore_time: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
