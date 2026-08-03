# 跨摄像头异常行为轨迹分析系统 Mock 数据字段设计

## 1. 设计范围

本设计依据调研报告中的“标准接入、边缘感知、跨域轨迹、异常预警、告警处置、合规审计”业务链路，以及现有前端页面清单，作为前端本地 Mock、后续 FastAPI 接口 Schema 和数据库模型的统一字段基线。

### 1.1 统一约定

| 约定 | 规则 |
| --- | --- |
| 主键 | 所有实体使用字符串 ID，例如 `CAM-000023`、`AL-20260727-0001` |
| 时间 | API 使用 ISO 8601 格式：`2026-07-27T10:42:18+08:00`；页面展示时再格式化 |
| 枚举 | API 保存英文编码，前端通过字典显示中文；例如 `pending` 显示为“待处理” |
| 空值 | 不适用字段返回 `null`，不要使用 `—`；`—`仅用于展示层 |
| 脱敏 | 目标对象默认只保存 `target_code` 和 ReID 特征引用，不保存真实姓名、人脸图片或原始人脸特征 |
| 分页 | 列表接口统一返回 `items`、`total`、`page`、`page_size` |
| 多租户 | 业务数据统一带 `workspace_id`，用于工作空间和数据权限隔离 |
| 审计 | 新增、修改、删除、导出、查看敏感数据均应产生 `operation_log` |

## 2. 实体关系

```text
workspace
  ├── area ──< camera ──< camera_relation >── camera
  ├── edge_node ──< camera
  ├── target ──< trajectory ──< trajectory_point >── camera
  ├── behavior_event ──< alert ──0..1 work_order
  ├── user >── role >── permission
  ├── user ──< consent_record
  └── user ──< operation_log
```

## 3. 工作空间与区域

### 3.1 `workspace` 工作空间

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 工作空间 ID |
| `name` | string | 是 | 工作空间名称，例如“城市治理示范区” |
| `code` | string | 是 | 唯一编码 |
| `customer_type` | enum | 是 | `public_security` 公安政法、`traffic` 交通、`park` 园区工厂、`school_hospital` 学校医院商业 |
| `deployment_mode` | enum | 是 | `private` 私有化、`hybrid` 混合部署、`saas` SaaS |
| `address` | string | 否 | 工作空间地址 |
| `timezone` | string | 是 | 默认 `Asia/Shanghai` |
| `data_level` | enum | 是 | `general`、`sensitive`、`important` |
| `status` | enum | 是 | `active`、`disabled` |
| `created_at` | datetime | 是 | 创建时间 |
| `updated_at` | datetime | 是 | 更新时间 |

### 3.2 `area` 区域

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 区域 ID |
| `workspace_id` | string | 是 | 所属工作空间 |
| `parent_id` | string/null | 否 | 上级区域 ID |
| `name` | string | 是 | 区域名称，例如“南门仓储区” |
| `area_type` | enum | 是 | `gate` 门岗、`warehouse` 仓储、`office` 办公、`workshop` 车间、`road` 道路、`restricted` 禁行区 |
| `geojson` | object | 否 | 区域边界，用于地图和电子围栏 |
| `security_level` | enum | 是 | `high`、`medium`、`low` |
| `camera_count` | number | 是 | 关联摄像头数，列表统计字段 |
| `status` | enum | 是 | `active`、`disabled` |

## 4. 视频接入与设备

### 4.1 `camera` 摄像头

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 摄像头 ID，例如 `CAM-023` |
| `workspace_id` | string | 是 | 所属工作空间 |
| `area_id` | string | 是 | 所属区域 |
| `name` | string | 是 | 摄像头名称 |
| `device_type` | enum | 是 | `fixed` 固定枪机、`dome` 球机、`panoramic` 全景、`face_gate` 卡口、`edge_box` 边缘盒 |
| `vendor` | string | 是 | 厂商名称 |
| `model` | string | 否 | 设备型号 |
| `serial_number` | string | 否 | 序列号 |
| `protocol` | enum | 是 | `gb28181`、`rtsp`、`onvif`、`http` |
| `stream_url_masked` | string | 否 | 脱敏后的流地址，Mock 不放真实密钥 |
| `resolution` | string | 是 | 例如 `1920x1080` |
| `frame_rate` | number | 是 | 帧率 |
| `is_reid_enabled` | boolean | 是 | 是否启用 ReID |
| `is_behavior_enabled` | boolean | 是 | 是否启用异常行为检测 |
| `edge_node_id` | string/null | 否 | 所属边缘节点 |
| `status` | enum | 是 | `online`、`unstable`、`offline`、`maintenance` |
| `health_score` | number | 是 | 0-100 健康度 |
| `last_heartbeat_at` | datetime | 否 | 最近心跳 |
| `last_fault_at` | datetime/null | 否 | 最近故障时间 |
| `installed_at` | date | 否 | 安装日期 |
| `created_at` | datetime | 是 | 创建时间 |
| `updated_at` | datetime | 是 | 更新时间 |

### 4.2 `edge_node` 边缘 AI 节点

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 节点 ID，例如 `EDGE-001` |
| `workspace_id` | string | 是 | 所属工作空间 |
| `name` | string | 是 | 节点名称 |
| `ip_address` | string | 否 | 内网 IP，展示时可脱敏 |
| `vendor` | string | 是 | 设备厂商 |
| `compute_type` | enum | 是 | `gpu`、`npu`、`cpu` |
| `compute_model` | string | 是 | 例如“昇腾 310” |
| `camera_count` | number | 是 | 接入路数 |
| `cpu_usage` | number | 是 | CPU 使用率 |
| `gpu_usage` | number | 否 | GPU/NPU 使用率 |
| `storage_usage` | number | 是 | 存储使用率 |
| `algorithm_version` | string | 是 | 当前算法版本 |
| `status` | enum | 是 | `online`、`degraded`、`offline`、`maintenance` |
| `last_heartbeat_at` | datetime | 是 | 最近心跳 |

### 4.3 `camera_relation` 摄像头拓扑关系

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 关系 ID |
| `workspace_id` | string | 是 | 所属工作空间 |
| `source_camera_id` | string | 是 | 起始摄像头 |
| `target_camera_id` | string | 是 | 目标摄像头 |
| `relation_type` | enum | 是 | `overlap` 重叠、`handoff` 衔接、`blind_gap` 盲区 |
| `distance_meters` | number | 否 | 摄像头覆盖区域距离 |
| `expected_handoff_seconds` | number | 否 | 预计接力时间 |
| `confidence` | number | 是 | 0-1 关系置信度 |
| `status` | enum | 是 | `active`、`pending_review`、`disabled` |
| `calibrated_at` | datetime | 否 | 最近标定时间 |

## 5. 目标与跨摄像头轨迹

### 5.1 `target` 目标对象

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 目标 ID，例如 `TGT-20260727-0001` |
| `workspace_id` | string | 是 | 所属工作空间 |
| `target_type` | enum | 是 | `person` 人员、`vehicle` 车辆、`non_motor_vehicle` 非机动车、`unknown` 未知 |
| `target_code` | string | 是 | 脱敏目标编号，前端展示使用 |
| `reid_feature_id` | string/null | 是 | ReID 特征引用；Mock 只放引用，不放向量原文 |
| `appearance_tags` | string[] | 否 | 服装、颜色、携带物等外观标签 |
| `vehicle_plate_masked` | string/null | 否 | 脱敏车牌，仅车辆目标可用 |
| `first_seen_at` | datetime | 是 | 首次出现时间 |
| `last_seen_at` | datetime | 是 | 最近出现时间 |
| `first_camera_id` | string | 是 | 首次出现摄像头 |
| `last_camera_id` | string | 是 | 最近出现摄像头 |
| `match_confidence` | number | 是 | 目标关联置信度，0-1 |
| `privacy_level` | enum | 是 | `anonymous`、`masked`、`restricted` |
| `status` | enum | 是 | `active`、`ended`、`expired` |

### 5.2 `trajectory` 轨迹主记录

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 轨迹 ID，例如 `TRK-20260727-0001` |
| `workspace_id` | string | 是 | 所属工作空间 |
| `target_id` | string | 是 | 关联目标 |
| `query_type` | enum | 是 | `realtime` 实时、`history` 历史、`event_related` 事件关联 |
| `start_time` | datetime | 是 | 轨迹开始时间 |
| `end_time` | datetime | 是 | 轨迹结束时间 |
| `camera_ids` | string[] | 是 | 经过摄像头 ID 列表 |
| `point_count` | number | 是 | 轨迹点数量 |
| `distance_meters` | number | 否 | 总移动距离 |
| `continuity_score` | number | 是 | 轨迹连续率，0-1 |
| `algorithm_mode` | enum | 是 | `reid`、`spatial_geometry`、`fusion` |
| `status` | enum | 是 | `tracking`、`completed`、`partial`、`failed` |
| `created_by` | string | 否 | 发起查询的用户 ID |
| `created_at` | datetime | 是 | 创建时间 |

### 5.3 `trajectory_point` 轨迹点

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 轨迹点 ID |
| `trajectory_id` | string | 是 | 所属轨迹 |
| `target_id` | string | 是 | 关联目标 |
| `camera_id` | string | 是 | 采集摄像头 |
| `area_id` | string | 是 | 所属区域 |
| `captured_at` | datetime | 是 | 抓拍时间 |
| `dwell_seconds` | number | 否 | 在该点停留时长 |
| `bbox` | object | 否 | `{x, y, width, height}`，相对视频帧坐标 |
| `position` | object | 否 | `{longitude, latitude}` |
| `world_position` | object | 否 | `{x, y, z}`，视频孪生坐标 |
| `source_snapshot_url` | string/null | 是 | 脱敏截图地址；Mock 可为 null |
| `confidence` | number | 是 | 点位置信度 |
| `is_handoff_point` | boolean | 是 | 是否为跨镜接力点 |

## 6. 异常行为、告警与工单

### 6.1 `behavior_event` 异常行为事件

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 事件 ID，例如 `EVT-20260727-0001` |
| `workspace_id` | string | 是 | 所属工作空间 |
| `event_type` | enum | 是 | `intrusion` 闯入、`loitering` 徘徊、`fight` 斗殴、`fall` 跌倒、`crowd` 聚集、`smoke_fire` 烟火、`reverse_traffic` 逆行、`obstruction` 占用、`missing_protective_equipment` 未戴护具 |
| `event_name` | string | 是 | 中文事件名称 |
| `camera_id` | string | 是 | 首发摄像头 |
| `area_id` | string | 是 | 发生区域 |
| `target_id` | string/null | 否 | 关联目标 |
| `trajectory_id` | string/null | 否 | 关联轨迹 |
| `detected_at` | datetime | 是 | 检测时间 |
| `ended_at` | datetime/null | 否 | 结束时间 |
| `model_name` | string | 是 | 检测模型 |
| `model_version` | string | 是 | 模型版本 |
| `small_model_score` | number | 是 | 边缘小模型初筛分数 |
| `large_model_score` | number/null | 否 | 云端大模型复检分数 |
| `context_score` | number/null | 否 | 时空上下文分数 |
| `risk_level` | enum | 是 | `high`、`medium`、`low` |
| `is_false_positive` | boolean | 是 | 是否误报 |
| `review_status` | enum | 是 | `unreviewed`、`confirmed`、`false_positive`、`ignored` |
| `evidence_count` | number | 是 | 证据数量 |
| `created_at` | datetime | 是 | 创建时间 |

### 6.2 `alert` 告警

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 告警编号，例如 `AL-20260727-0001` |
| `event_id` | string | 是 | 关联异常事件 |
| `title` | string | 是 | 告警标题 |
| `type` | string | 是 | 告警类型 |
| `camera_id` | string | 是 | 主摄像头 |
| `nearby_camera_ids` | string[] | 否 | 周边二次核验摄像头 |
| `area_id` | string | 是 | 位置区域 |
| `occurred_at` | datetime | 是 | 发生时间 |
| `level` | enum | 是 | `high`、`medium`、`low` |
| `status` | enum | 是 | `pending`、`processing`、`confirmed`、`false_positive`、`closed` |
| `assigned_to` | string/null | 否 | 当前处置人 |
| `review_note` | string/null | 否 | 审核备注 |
| `evidence_urls` | string[] | 否 | 证据截图或视频地址 |
| `work_order_id` | string/null | 否 | 真实告警对应工单 |
| `created_at` | datetime | 是 | 创建时间 |
| `updated_at` | datetime | 是 | 更新时间 |

### 6.3 `work_order` 处置工单

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 工单编号，例如 `WO-20260727-0001` |
| `alert_id` | string | 是 | 来源告警 |
| `title` | string | 是 | 工单标题 |
| `priority` | enum | 是 | `urgent`、`high`、`normal`、`low` |
| `status` | enum | 是 | `created`、`assigned`、`processing`、`resolved`、`archived` |
| `assignee_id` | string | 否 | 处置人员 |
| `deadline_at` | datetime | 否 | 处置时限 |
| `dispatch_at` | datetime | 否 | 派单时间 |
| `resolved_at` | datetime/null | 否 | 完成时间 |
| `resolution` | string/null | 否 | 处置结果 |
| `resolution_type` | enum/null | 否 | `verified`、`warning`、`evacuated`、`repair`、`other` |
| `attachments` | string[] | 否 | 现场照片、报告地址 |
| `archived_by` | string/null | 否 | 归档人 |
| `created_at` | datetime | 是 | 创建时间 |
| `updated_at` | datetime | 是 | 更新时间 |

## 7. 用户、角色、权限与隐私授权

### 7.1 `user` 用户账号

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 用户 ID |
| `workspace_id` | string | 是 | 所属工作空间 |
| `username` | string | 是 | 登录账号，唯一 |
| `display_name` | string | 是 | 展示姓名 |
| `password` | string | 否 | 仅登录 Mock 使用；真实接口禁止返回 |
| `role_ids` | string[] | 是 | 角色 ID 列表 |
| `department` | string | 否 | 部门 |
| `phone_masked` | string | 否 | 脱敏手机号 |
| `data_scope` | enum | 是 | `workspace` 全量、`area` 指定区域、`department` 本部门、`self` 仅本人 |
| `area_ids` | string[] | 否 | 指定辖区 |
| `status` | enum | 是 | `active`、`disabled`、`locked` |
| `last_login_at` | datetime/null | 否 | 最近登录时间 |
| `created_at` | datetime | 是 | 创建时间 |

### 7.2 `role` 与 `permission`

`role` 字段：`id`、`key`、`name`、`description`、`data_scope`、`permission_ids`、`status`、`created_at`、`updated_at`。

建议 Mock 角色：

| `key` | 名称 | 数据范围 |
| --- | --- | --- |
| `super_admin` | 超级管理员 | `workspace` |
| `security_lead` | 园区安全负责人 | `workspace` |
| `guard` | 安保/巡检人员 | `area` |
| `counselor` | 心理辅导员(EAP) | `self` |
| `supervisor` | 部门主管 | `department` |
| `employee` | 员工本人 | `self` |
| `auditor` | 合规审计员 | `workspace` |

`permission` 字段：`id`、`key`、`name`、`group`、`action`、`resource`、`status`。

建议权限编码：

```text
 dashboard:view
 camera:view / camera:create / camera:update / camera:control
 trajectory:realtime / trajectory:history / trajectory:export
 behavior:view / behavior:review / behavior:export
 alert:view / alert:confirm / alert:close
 workorder:view / workorder:create / workorder:assign / workorder:archive
 user:view / user:create / user:update / user:disable
 role:view / role:create / role:update
 audit:view / audit:export
 consent:view / consent:manage
 backup:view / backup:create / backup:restore
```

### 7.3 `consent_record` 隐私授权记录

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 授权记录 ID |
| `workspace_id` | string | 是 | 所属工作空间 |
| `subject_user_id` | string | 是 | 授权主体用户 |
| `purpose` | enum | 是 | `security` 安全管理、`safety` 生产安全、`access` 访问授权、`research` 算法优化 |
| `scope` | string[] | 是 | 授权的数据范围 |
| `legal_basis` | string | 是 | 授权依据 |
| `status` | enum | 是 | `pending`、`active`、`withdrawn`、`expired` |
| `effective_at` | datetime | 否 | 生效时间 |
| `expires_at` | datetime/null | 否 | 失效时间 |
| `withdrawn_at` | datetime/null | 否 | 撤回时间 |
| `operator_id` | string | 是 | 操作人 |
| `created_at` | datetime | 是 | 创建时间 |

## 8. 数据管理与审计

### 8.1 `operation_log` 系统操作日志

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 日志编号，例如 `LOG-20260727-0001` |
| `workspace_id` | string | 是 | 所属工作空间 |
| `operator_id` | string | 是 | 操作用户 ID |
| `account` | string | 是 | 操作账号快照 |
| `operator_name` | string | 是 | 操作人姓名快照 |
| `module` | string | 是 | 模块名称 |
| `action` | string | 是 | 操作内容 |
| `resource_type` | string | 否 | 资源类型 |
| `resource_id` | string | 否 | 资源 ID |
| `request_method` | enum | 是 | `GET`、`POST`、`PUT`、`DELETE` |
| `request_path` | string | 是 | 请求路径 |
| `ip_address` | string | 否 | 操作 IP |
| `user_agent` | string | 否 | 客户端信息 |
| `before_snapshot` | object/null | 否 | 修改前快照，敏感字段脱敏 |
| `after_snapshot` | object/null | 否 | 修改后快照，敏感字段脱敏 |
| `result` | enum | 是 | `success`、`failed`、`denied` |
| `error_message` | string/null | 否 | 失败原因 |
| `occurred_at` | datetime | 是 | 操作时间 |

### 8.2 `backup_record` 数据备份记录

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 备份 ID |
| `workspace_id` | string | 是 | 所属工作空间 |
| `backup_no` | string | 是 | 备份编号 |
| `backup_type` | enum | 是 | `full` 全量、`incremental` 增量 |
| `trigger_type` | enum | 是 | `scheduled` 定时、`manual` 手动 |
| `data_scope` | string[] | 是 | 备份数据模块 |
| `file_name` | string | 是 | 文件名 |
| `file_size_bytes` | number | 是 | 文件大小 |
| `checksum` | string | 是 | 校验值，Mock 可使用短字符串 |
| `status` | enum | 是 | `running`、`success`、`failed`、`restored` |
| `created_by` | string | 是 | 发起人 |
| `started_at` | datetime | 是 | 开始时间 |
| `completed_at` | datetime/null | 否 | 完成时间 |
| `retention_until` | datetime | 否 | 保留截止时间 |

### 8.3 `dashboard_snapshot` 看板聚合数据

用于 `/dashboard`，避免前端自行从明细数据计算大盘指标。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `workspace_id` | string | 工作空间 |
| `stat_date` | date | 统计日期 |
| `recognized_event_count` | number | 识别事件数 |
| `pending_alert_count` | number | 待处理告警数 |
| `active_target_count` | number | 活跃目标数 |
| `online_camera_count` | number | 在线摄像头数 |
| `total_camera_count` | number | 摄像头总数 |
| `online_rate` | number | 在线率 |
| `unstable_camera_count` | number | 连接波动设备数 |
| `offline_camera_count` | number | 离线设备数 |
| `event_trend` | object[] | `[{time, recognized_count, valid_alert_count}]` |
| `risk_distribution` | object[] | `[{level, count}]` |
| `top_areas` | object[] | `[{area_id, area_name, event_count}]` |
| `generated_at` | datetime | 生成时间 |

## 9. 统一接口 Mock 返回结构

### 9.1 列表接口

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "items": [],
    "total": 0,
    "page": 1,
    "page_size": 20
  },
  "request_id": "REQ-20260727-0001"
}
```

### 9.2 详情接口

```json
{
  "code": 0,
  "message": "ok",
  "data": {},
  "request_id": "REQ-20260727-0002"
}
```

### 9.3 业务错误

```json
{
  "code": 40301,
  "message": "当前角色无权访问该数据",
  "data": null,
  "request_id": "REQ-20260727-0003"
}
```

## 10. 按页面的最小 Mock 数据集

| 页面 | 最少需要的数据 |
| --- | --- |
| `/login` | `user`、`role`、`permission` |
| `/dashboard` | `dashboard_snapshot`、`alert`、`camera` |
| `/track/realtime` | `camera`、`target`、实时 `trajectory`、`trajectory_point`、`alert` |
| `/track/history` | `target`、`trajectory`、`trajectory_point`、`camera_relation` |
| `/device/list` | `camera`、`edge_node`、设备故障信息 |
| `/data/abnormal-record` | `behavior_event`、`alert`、`camera`、`area` |
| `/data/track-record` | `trajectory`、`trajectory_point`、`target` |
| `/data/backup` | `backup_record` |
| `/data/user-profile` | `user`、`consent_record` |
| `/data/operation-log` | `operation_log` |
| `/alarm/todo` | `alert`、`behavior_event`、`camera`、`work_order` |
| `/workorder/detail/:orderId` | `work_order`、`alert`、`behavior_event`、`operation_log` |
| `/system/role` | `role`、`permission` |
| `/system/user` | `user`、`role`、`permission` |

## 11. 现有原型字段映射

| 当前前端字段 | 建议统一字段 | 备注 |
| --- | --- | --- |
| `alert.id` | `alert.id` | 建议由数字改为业务编号字符串 |
| `alert.camera` | `alert.camera_id` | 名称通过摄像头关联查询 |
| `alert.location` | `area.name` | 位置归一到区域表 |
| `alert.time` | `alert.occurred_at` | 从时分秒升级为完整时间 |
| `alert.level` | `alert.level` | 前端显示中文，接口保存英文枚举 |
| `alert.status` | `alert.status` | 增加处理中、误报、已关闭 |
| `device.code` | `camera.id` | 设备编码统一为摄像头 ID |
| `device.area` | `camera.area_id` | 通过区域关联显示名称 |
| `device.health` | `camera.health_score` | 后端保存数字，前端格式化百分比 |
| `log.account` | `operation_log.account` | 保留账号快照 |
| `log.module` | `operation_log.module` | 保留页面模块 |
| `log.action` | `operation_log.action` | 保留用户可读操作内容 |
| `log.time` | `operation_log.occurred_at` | 使用标准时间格式 |
| `log.result` | `operation_log.result` | 建议使用 `success/failed/denied` |

## 12. 推荐 Mock 数据量

| 数据类型 | 推荐条数 | 目的 |
| --- | ---: | --- |
| 工作空间 | 2 | 验证工作空间切换和租户隔离 |
| 区域 | 8-12 | 覆盖门岗、办公、车间、道路、禁区 |
| 摄像头 | 24-40 | 覆盖在线、波动、离线、维护状态 |
| 边缘节点 | 3-5 | 覆盖 CPU/GPU/NPU 和节点故障 |
| 摄像头关系 | 30-60 | 展示重叠、衔接、盲区拓扑 |
| 目标 | 20-50 | 覆盖人员、车辆、非机动车 |
| 轨迹 | 30-80 | 覆盖实时、历史、部分中断轨迹 |
| 异常事件 | 50-100 | 覆盖多类异常和误报样本 |
| 告警 | 20-40 | 覆盖各风险等级和处置状态 |
| 工单 | 8-15 | 覆盖派单、处理中、已归档 |
| 用户 | 7-12 | 覆盖现有七类角色 |
| 操作日志 | 50-100 | 支持关键字、时间、结果筛选 |
| 备份记录 | 5-10 | 覆盖成功、失败、恢复状态 |

## 13. Mock 数据生成注意事项

1. 告警必须能沿 `alert -> behavior_event -> trajectory -> target -> camera -> area` 追溯，不能只生成展示字段。
2. 至少准备一条跨 3 个摄像头的连续轨迹、一条经过盲区的部分轨迹和一条低置信度轨迹，用于验证轨迹回放与异常状态。
3. 告警状态至少覆盖待处理、处理中、已确认、误报、已关闭；风险等级至少覆盖高、中、低。
4. 摄像头状态至少覆盖在线、连接波动、离线、维护，且 `health_score` 与状态保持一致。
5. 目标数据默认采用匿名编号和脱敏外观标签，Mock 不生成真实个人信息、真实车牌或人脸特征。
6. 告警确认、误报提交、工单创建、工单归档、设备编辑、权限保存和日志导出都应生成新的 `operation_log`。
7. 角色权限不仅控制菜单显示，还应在接口 Mock 层校验 `data_scope`，分别测试全量、区域、本部门和本人数据范围。
8. 日期建议统一使用当前演示日 `2026-07-27`，避免页面顶部日期、趋势数据、告警时间和日志时间不一致。
