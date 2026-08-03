-- ============================================================
-- 跨摄像头异常行为轨迹分析系统 - 统一建表脚本
-- 数据库：MySQL 8.0+
-- 字符集：utf8mb4
-- 存储引擎：InnoDB
-- 日期：2026-07-28
-- ============================================================
-- 模块：
--   一、用户管理   (5 表)  — 权限系统
--   二、设备管理   (2 表)  — 设备与故障
--   三、轨迹管理   (2 表)  — 人员跨摄像头轨迹
--   四、数据管理   (9 表)  — 异常行为、预警、工单、操作日志
-- 共计 18 张表
-- ============================================================
-- 约定：
--   1. 统一使用 BIGINT UNSIGNED 作为所有主键/外键类型
--   2. 统一使用 create_time / update_time 作为审计时间字段
--   3. 含完整外键约束、索引、注释
--   4. 建表顺序按依赖关系排列（被引用表先建）
-- ============================================================

CREATE DATABASE IF NOT EXISTS `behavior_mansge`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE `behavior_mansge`;

-- ============================================================
-- 模块一：用户管理（权限系统）
-- ============================================================

-- ------------------------------------------------------------
-- 1. 用户类型表（角色表）
-- ------------------------------------------------------------
DROP TABLE IF EXISTS `sys_type_permission`;
DROP TABLE IF EXISTS `sys_account_permission`;
DROP TABLE IF EXISTS `sys_account`;
DROP TABLE IF EXISTS `sys_permission`;
DROP TABLE IF EXISTS `sys_user_type`;

CREATE TABLE `sys_user_type` (
  `type_id`      BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT  COMMENT '用户类型唯一标识',
  `type_name`    VARCHAR(64)      NOT NULL                 COMMENT '角色名称，如：超级管理员、保安、业务员',
  `type_desc`    VARCHAR(256)     DEFAULT NULL             COMMENT '用户类型备注说明',
  `create_time`  DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP  COMMENT '记录创建时间',
  `update_time`  DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
  PRIMARY KEY (`type_id`),
  UNIQUE KEY `uk_type_name` (`type_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户类型表（角色表）';

-- ------------------------------------------------------------
-- 2. 权限资源表
-- ------------------------------------------------------------
CREATE TABLE `sys_permission` (
  `perm_id`     BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT  COMMENT '权限唯一编号',
  `perm_name`   VARCHAR(128)     NOT NULL                 COMMENT '权限展示名称，例：摄像头查询',
  `perm_key`    VARCHAR(128)     NOT NULL                 COMMENT '程序鉴权编码，例：camera:query',
  `perm_type`   TINYINT          NOT NULL                 COMMENT '1=菜单权限 2=按钮操作权限 3=数据查询权限',
  `parent_id`   BIGINT UNSIGNED  NOT NULL DEFAULT 0       COMMENT '父权限ID，0代表顶级权限',
  `sort`        INT              NOT NULL DEFAULT 0       COMMENT '前端权限树形展示排序',
  `create_time` DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP  COMMENT '权限记录创建时间',
  PRIMARY KEY (`perm_id`),
  UNIQUE KEY `uk_perm_key` (`perm_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='权限资源表';

-- ------------------------------------------------------------
-- 3. 系统账号表
-- ------------------------------------------------------------
CREATE TABLE `sys_account` (
  `account_id`      BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT  COMMENT '账号唯一标识',
  `login_name`      VARCHAR(64)      NOT NULL                 COMMENT '用户登录用户名，全局唯一',
  `password`        VARCHAR(128)     NOT NULL                 COMMENT '加密存储密码',
  `real_name`       VARCHAR(64)      NOT NULL                 COMMENT '用户真实姓名',
  `dept`            VARCHAR(64)      DEFAULT NULL             COMMENT '部门信息',
  `phone`           VARCHAR(32)      DEFAULT NULL             COMMENT '用户联系电话',
  `type_id`         BIGINT UNSIGNED  NOT NULL                 COMMENT '所属用户类型ID，关联sys_user_type.type_id',
  `status`          TINYINT       NOT NULL DEFAULT 1       COMMENT '账号状态：1=启用 0=禁用',
  `create_time`     DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP  COMMENT '账号创建时间',
  `update_time`     DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '账号信息更新时间',
  `last_login_time` DATETIME         DEFAULT NULL             COMMENT '用户最近一次登录时间',
  PRIMARY KEY (`account_id`),
  UNIQUE KEY `uk_login_name` (`login_name`),
  KEY `idx_type_id` (`type_id`),
  CONSTRAINT `fk_account_type` FOREIGN KEY (`type_id`) REFERENCES `sys_user_type` (`type_id`)
    ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='系统账号表';

-- ------------------------------------------------------------
-- 4. 用户类型权限关联表（角色权限）
-- ------------------------------------------------------------
CREATE TABLE `sys_type_permission` (
  `id`      BIGINT UNSIGNED NOT NULL AUTO_INCREMENT  COMMENT '关联记录唯一ID',
  `type_id` BIGINT UNSIGNED NOT NULL                 COMMENT '用户类型ID，关联sys_user_type.type_id',
  `perm_id` BIGINT UNSIGNED NOT NULL                 COMMENT '权限ID，关联sys_permission.perm_id',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_type_perm` (`type_id`, `perm_id`),
  KEY `idx_perm_id` (`perm_id`),
  CONSTRAINT `fk_tp_type` FOREIGN KEY (`type_id`) REFERENCES `sys_user_type` (`type_id`)
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `fk_tp_perm` FOREIGN KEY (`perm_id`) REFERENCES `sys_permission` (`perm_id`)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户类型权限关联表（角色权限）';

-- ------------------------------------------------------------
-- 5. 账号独立权限关联表（单人自定义权限）
-- ------------------------------------------------------------
CREATE TABLE `sys_account_permission` (
  `id`         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT  COMMENT '关联记录唯一ID',
  `account_id` BIGINT UNSIGNED NOT NULL                 COMMENT '账号ID，关联sys_account.account_id',
  `perm_id`    BIGINT UNSIGNED NOT NULL                 COMMENT '权限ID，关联sys_permission.perm_id',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_account_perm` (`account_id`, `perm_id`),
  KEY `idx_perm_id` (`perm_id`),
  CONSTRAINT `fk_ap_account` FOREIGN KEY (`account_id`) REFERENCES `sys_account` (`account_id`)
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `fk_ap_perm` FOREIGN KEY (`perm_id`) REFERENCES `sys_permission` (`perm_id`)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='账号独立权限关联表（单人自定义权限）';

-- ============================================================
-- 模块二：设备管理
-- ============================================================

-- ------------------------------------------------------------
-- 6. 设备表
-- ------------------------------------------------------------
DROP TABLE IF EXISTS `fault_record`;
DROP TABLE IF EXISTS `device`;

CREATE TABLE `device` (
  -- 核心标识
  `id`                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT  COMMENT '自增主键',
  `device_code`         VARCHAR(64)      NOT NULL                 COMMENT '设备标号（业务唯一标识，如 CAM-001）',
  `device_name`         VARCHAR(128)     NOT NULL                 COMMENT '设备名称',
  `device_type`         VARCHAR(32)      NOT NULL DEFAULT 'CAMERA' COMMENT '设备类型：CAMERA/NVR/EDGE',
  -- 地理位置
  `location_text`       VARCHAR(255)     DEFAULT NULL             COMMENT '地理位置文本描述（如"A栋3层东侧走廊"）',
  `longitude`           DECIMAL(10,7)    DEFAULT NULL             COMMENT '经度',
  `latitude`            DECIMAL(10,7)    DEFAULT NULL             COMMENT '纬度',
  `region_code`         VARCHAR(32)      DEFAULT NULL             COMMENT '所属区域编码',
  `region_name`         VARCHAR(64)      DEFAULT NULL             COMMENT '所属区域名称',
  -- 状态与健康
  `status`              VARCHAR(16)      NOT NULL DEFAULT 'OFFLINE' COMMENT '设备状态：ONLINE/OFFLINE/DISABLED/FAULT',
  `health_score`        TINYINT UNSIGNED NOT NULL DEFAULT 100     COMMENT '健康度评分 0-100',
  `video_quality`       VARCHAR(16)      DEFAULT NULL             COMMENT '画面质量：HD/SD/FLUENT/UNKNOWN',
  `last_heartbeat_time` DATETIME         DEFAULT NULL             COMMENT '最后心跳上报时间',
  -- 设备属性
  `channel_count`       INT UNSIGNED     NOT NULL DEFAULT 1       COMMENT '通道数',
  `capability`          JSON             DEFAULT NULL             COMMENT '能力集，如 {"ptz":true,"night_vision":true}',
  `ip_address`          VARCHAR(32)      DEFAULT NULL             COMMENT '设备IP地址',
  `port`                INT UNSIGNED     DEFAULT NULL             COMMENT '端口',
  `manufacturer`        VARCHAR(64)      DEFAULT NULL             COMMENT '厂商',
  `model`               VARCHAR(64)      DEFAULT NULL             COMMENT '型号',
  `firmware_version`    VARCHAR(32)      DEFAULT NULL             COMMENT '固件版本',
  `install_time`        DATETIME         DEFAULT NULL             COMMENT '安装时间',
  -- 审计字段
  `operator_id`         BIGINT UNSIGNED  DEFAULT NULL             COMMENT '创建/最后修改人ID，关联sys_account.account_id',
  `operator_name`       VARCHAR(64)      DEFAULT NULL             COMMENT '创建/最后修改人姓名',
  `remark`              VARCHAR(500)     DEFAULT NULL             COMMENT '备注',
  `is_deleted`          TINYINT       NOT NULL DEFAULT 0       COMMENT '逻辑删除：0未删除 1已删除',
  `create_time`         DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time`         DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_device_code` (`device_code`),
  KEY `idx_status` (`status`),
  KEY `idx_region_code` (`region_code`),
  KEY `idx_last_heartbeat_time` (`last_heartbeat_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='设备表';

-- ------------------------------------------------------------
-- 7. 故障记录表
-- ------------------------------------------------------------
CREATE TABLE `fault_record` (
  -- 核心字段
  `id`               BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT  COMMENT '自增主键',
  `device_id`        BIGINT UNSIGNED  NOT NULL                 COMMENT '关联设备ID，外键→device.id',
  `device_code`      VARCHAR(64)      NOT NULL                 COMMENT '设备标号（冗余字段，方便查询）',
  `fault_type`       VARCHAR(32)      NOT NULL                 COMMENT '损坏类型：HEARTBEAT_TIMEOUT/VIDEO_ABNORMAL/…',
  `fault_level`      VARCHAR(16)      NOT NULL DEFAULT 'MEDIUM' COMMENT '故障级别：LOW/MEDIUM/HIGH/CRITICAL',
  `fault_desc`       VARCHAR(500)     DEFAULT NULL             COMMENT '故障描述',
  -- 时间字段
  `occurrence_time`     DATETIME      NOT NULL                 COMMENT '故障发生时间',
  `recovery_time`       DATETIME      DEFAULT NULL             COMMENT '故障恢复时间',
  `auto_recovery_time`  DATETIME      DEFAULT NULL             COMMENT '自动恢复尝试时间',
  `closed_at`           DATETIME      DEFAULT NULL             COMMENT '故障单关闭时间',
  -- 处置字段
  `disposal_status`  VARCHAR(16)      NOT NULL DEFAULT 'PENDING' COMMENT '处置状态：PENDING/AUTO_RECOVERED/ASSIGNED/…',
  `assigned_to`      BIGINT UNSIGNED  DEFAULT NULL             COMMENT '被指派的维修人员ID，关联sys_account.account_id',
  `assigned_name`    VARCHAR(64)      DEFAULT NULL             COMMENT '被指派的维修人员姓名',
  `auto_recovery`    TINYINT       NOT NULL DEFAULT 0       COMMENT '是否尝试过自动恢复：0否 1是',
  `repair_result`    VARCHAR(16)      DEFAULT NULL             COMMENT '维修结果：PASS复检通过/FAIL复检未通过',
  `repair_remark`    VARCHAR(500)     DEFAULT NULL             COMMENT '维修备注',
  `closed_by`        BIGINT UNSIGNED  DEFAULT NULL             COMMENT '关闭人ID，关联sys_account.account_id',
  `closed_name`      VARCHAR(64)      DEFAULT NULL             COMMENT '关闭人姓名',
  -- 审计字段
  `operator_id`      BIGINT UNSIGNED  DEFAULT NULL             COMMENT '操作人ID，关联sys_account.account_id',
  `operator_name`    VARCHAR(64)      DEFAULT NULL             COMMENT '操作人姓名',
  `is_deleted`       TINYINT       NOT NULL DEFAULT 0       COMMENT '逻辑删除：0未删除 1已删除',
  `create_time`      DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time`      DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `idx_device_id` (`device_id`),
  KEY `idx_device_code` (`device_code`),
  KEY `idx_fault_type` (`fault_type`),
  KEY `idx_disposal_status` (`disposal_status`),
  KEY `idx_occurrence_time` (`occurrence_time`),
  CONSTRAINT `fk_fault_device` FOREIGN KEY (`device_id`) REFERENCES `device` (`id`)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='故障记录表';

-- ============================================================
-- 模块三：轨迹管理（人员跨摄像头轨迹）
-- ============================================================

-- ------------------------------------------------------------
-- 8. 人员通行链路主表
-- ------------------------------------------------------------
DROP TABLE IF EXISTS `track_pass_item`;
DROP TABLE IF EXISTS `track_pass_chain`;

CREATE TABLE `track_pass_chain` (
  `id`                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT  COMMENT '链路主键ID',
  `chain_unique_id`     VARCHAR(64)      NOT NULL                 COMMENT '链路唯一编号，前端传参标识',
  `person_id`           BIGINT UNSIGNED  DEFAULT NULL             COMMENT '人员档案ID，关联dm_anonymous_person.person_id；陌生人则为NULL',
  `confidence`          DECIMAL(5,4)     NOT NULL DEFAULT 0.0000  COMMENT 'AI人脸识别匹配置信度 0~1',
  `device_route`        VARCHAR(256)     NOT NULL                 COMMENT '摄像头路径串，分隔符-，示例：1001-1002-1003',
  `first_device_id`     BIGINT UNSIGNED  NOT NULL                 COMMENT '首个摄像头设备ID，关联device.id',
  `last_device_id`      BIGINT UNSIGNED  NOT NULL                 COMMENT '末尾摄像头设备ID，关联device.id',
  `chain_start_time`    DATETIME(3)      NOT NULL                 COMMENT '人员第一次被摄像头抓拍的时间',
  `chain_end_time`      DATETIME(3)      DEFAULT NULL             COMMENT '轨迹结束时间；行进中为NULL',
  `total_duration_sec`  INT              NOT NULL DEFAULT 0       COMMENT '全程总耗时（秒）',
  `chain_status`        TINYINT          NOT NULL DEFAULT 1       COMMENT '链路状态：1=行进中 2=轨迹归档完成',
  `create_time`         DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
  `update_time`         DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_chain_unique_id` (`chain_unique_id`),
  KEY `idx_person_id` (`person_id`),
  KEY `idx_chain_start_time` (`chain_start_time`),
  KEY `idx_chain_status` (`chain_status`),
  KEY `idx_first_device_id` (`first_device_id`),
  KEY `idx_last_device_id` (`last_device_id`),
  CONSTRAINT `fk_chain_first_device` FOREIGN KEY (`first_device_id`) REFERENCES `device` (`id`)
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_chain_last_device` FOREIGN KEY (`last_device_id`) REFERENCES `device` (`id`)
    ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='人员通行链路主表';

-- ------------------------------------------------------------
-- 9. 途经摄像头明细子表
-- ------------------------------------------------------------
CREATE TABLE `track_pass_item` (
  `id`                BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT  COMMENT '明细主键ID',
  `chain_id`          BIGINT UNSIGNED  NOT NULL                 COMMENT '所属链路ID，关联track_pass_chain.id',
  `device_id`         BIGINT UNSIGNED  NOT NULL                 COMMENT '当前摄像头设备ID，关联device.id',
  `sort`              TINYINT          NOT NULL                 COMMENT '途经顺序号：1、2、3…',
  `appear_time`       DATETIME(3)      NOT NULL                 COMMENT '进入摄像头画面时间',
  `disappear_time`    DATETIME(3)      DEFAULT NULL             COMMENT '离开摄像头画面时间；未离开则为NULL',
  `stay_duration_sec` INT              NOT NULL DEFAULT 0       COMMENT '本段停留时长（秒）',
  `create_time`       DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '明细创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_chain_sort` (`chain_id`, `sort`),
  KEY `idx_device_appear` (`device_id`, `appear_time`),
  CONSTRAINT `fk_item_chain` FOREIGN KEY (`chain_id`) REFERENCES `track_pass_chain` (`id`)
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `fk_item_device` FOREIGN KEY (`device_id`) REFERENCES `device` (`id`)
    ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='途经摄像头明细子表';

-- ============================================================
-- 模块四：数据管理（异常行为、预警、工单、操作日志）
-- ============================================================

-- 建表前先清理数据管理模块所有表（按外键依赖倒序）
DROP TABLE IF EXISTS `fa_operation_log`;
DROP TABLE IF EXISTS `fa_work_order`;
DROP TABLE IF EXISTS `fa_behavior_alert`;
DROP TABLE IF EXISTS `fa_abnormal_behavior`;
DROP TABLE IF EXISTS `dm_behavior_type`;
DROP TABLE IF EXISTS `dm_anonymous_person`;
DROP TABLE IF EXISTS `dm_work_order_status`;
DROP TABLE IF EXISTS `dm_alert_status`;
DROP TABLE IF EXISTS `dm_severity_level`;

-- ------------------------------------------------------------
-- 10. 严重程度（维度表，固定枚举）
-- ------------------------------------------------------------
CREATE TABLE `dm_severity_level` (
  `severity_level_id` TINYINT UNSIGNED NOT NULL            COMMENT '主键，固定枚举：1=高 2=中 3=低',
  `level_name`        VARCHAR(16)      NOT NULL            COMMENT '等级名称：高/中/低',
  `level_sort`        TINYINT UNSIGNED NOT NULL DEFAULT 0  COMMENT '排序，高排最前',
  PRIMARY KEY (`severity_level_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='严重程度（维度表）';

-- ------------------------------------------------------------
-- 11. 预警状态（维度表，固定枚举）
-- ------------------------------------------------------------
CREATE TABLE `dm_alert_status` (
  `alert_status_id` TINYINT UNSIGNED NOT NULL            COMMENT '主键，固定枚举：1待确认/2已确认/3已派单/4处理中/5已处理/6已忽略',
  `status_name`     VARCHAR(16)      NOT NULL            COMMENT '中文状态名',
  `status_sort`     TINYINT UNSIGNED NOT NULL DEFAULT 0  COMMENT '流转排序',
  PRIMARY KEY (`alert_status_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='预警状态（维度表）';

-- ------------------------------------------------------------
-- 12. 工单状态（维度表，固定枚举）
-- ------------------------------------------------------------
CREATE TABLE `dm_work_order_status` (
  `work_order_status_id` TINYINT UNSIGNED NOT NULL            COMMENT '主键，固定枚举：1待处理/2处理中/3已完成/4已关闭',
  `status_name`          VARCHAR(16)      NOT NULL            COMMENT '中文状态名',
  `status_sort`          TINYINT UNSIGNED NOT NULL DEFAULT 0  COMMENT '流转排序',
  PRIMARY KEY (`work_order_status_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='工单状态（维度表）';

-- ------------------------------------------------------------
-- 13. 匿名异常人员（维度表）
-- ------------------------------------------------------------
CREATE TABLE `dm_anonymous_person` (
  `person_id`         BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT  COMMENT '匿名人员ID，自增主键；轨迹表据此ID建轨迹',
  `appearance_desc`   TEXT             DEFAULT NULL             COMMENT '外形描述：衣着、身高、体型、背包、颜色等',
  `first_seen_at`     DATETIME         DEFAULT NULL             COMMENT '首次发现时间',
  `last_seen_at`      DATETIME         DEFAULT NULL             COMMENT '最近一次发现时间',
  `is_focused`        TINYINT UNSIGNED NOT NULL DEFAULT 0       COMMENT '是否重点关注：0否 1是',
  `risk_level_id`     TINYINT UNSIGNED DEFAULT NULL             COMMENT '风险等级，引用dm_severity_level.severity_level_id',
  `matched_user_id`   BIGINT UNSIGNED  DEFAULT NULL             COMMENT 'AI匹配到的用户ID，引用sys_account.account_id（匹配不上则为NULL）',
  `match_confidence`  DECIMAL(5,4)     DEFAULT NULL             COMMENT 'AI匹配置信度 0~1（为空表示未匹配）',
  `create_time`       DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time`       DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`person_id`),
  KEY `idx_risk_level_id` (`risk_level_id`),
  KEY `idx_matched_user_id` (`matched_user_id`),
  CONSTRAINT `fk_anon_risk` FOREIGN KEY (`risk_level_id`) REFERENCES `dm_severity_level` (`severity_level_id`)
    ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `fk_anon_matched_user` FOREIGN KEY (`matched_user_id`) REFERENCES `sys_account` (`account_id`)
    ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='匿名异常人员（维度表）';

-- 补建 track_pass_chain → dm_anonymous_person 外键（因建表顺序，此前目标表不存在）
ALTER TABLE `track_pass_chain`
  ADD CONSTRAINT `fk_chain_person` FOREIGN KEY (`person_id`) REFERENCES `dm_anonymous_person` (`person_id`)
    ON DELETE SET NULL ON UPDATE CASCADE;

-- ------------------------------------------------------------
-- 14. 异常行为类型（维度表）
-- ------------------------------------------------------------
CREATE TABLE `dm_behavior_type` (
  `behavior_type_id`          BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT  COMMENT '异常行为类型ID，自增主键',
  `type_name`                 VARCHAR(64)      NOT NULL                 COMMENT '行为类型名称（如：跌倒、打架、闯入、聚集）',
  `default_severity_level_id` TINYINT UNSIGNED DEFAULT NULL             COMMENT '默认严重程度，引用dm_severity_level.severity_level_id',
  `description`               VARCHAR(255)     DEFAULT NULL             COMMENT '类型说明',
  `is_enabled`                TINYINT UNSIGNED NOT NULL DEFAULT 1       COMMENT '是否启用：0否 1是',
  `create_time`               DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time`               DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`behavior_type_id`),
  KEY `idx_default_severity` (`default_severity_level_id`),
  CONSTRAINT `fk_bt_severity` FOREIGN KEY (`default_severity_level_id`) REFERENCES `dm_severity_level` (`severity_level_id`)
    ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='异常行为类型（维度表）';

-- ------------------------------------------------------------
-- 15. 异常行为记录（核心事实表）
-- ------------------------------------------------------------
CREATE TABLE `fa_abnormal_behavior` (
  `behavior_id`        BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT  COMMENT '异常行为ID，自增主键',
  `behavior_type_id`   BIGINT UNSIGNED  NOT NULL                 COMMENT '异常行为类型，引用dm_behavior_type.behavior_type_id',
  `person_id`          BIGINT UNSIGNED  NOT NULL                 COMMENT '匿名异常人员，引用dm_anonymous_person.person_id',
  `track_id`           BIGINT UNSIGNED  DEFAULT NULL             COMMENT '轨迹ID，引用track_pass_chain.id（识别时轨迹可能未生成）',
  `severity_level_id`  TINYINT UNSIGNED DEFAULT NULL             COMMENT '严重程度，引用dm_severity_level.severity_level_id',
  `alert_status_id`    TINYINT UNSIGNED NOT NULL DEFAULT 1       COMMENT '当前预警状态，引用dm_alert_status.alert_status_id，默认1待确认',
  `detected_at`        DATETIME         NOT NULL                 COMMENT '算法识别时间',
  `camera_id`          BIGINT UNSIGNED  DEFAULT NULL             COMMENT '摄像头ID，引用device.id',
  `confidence_score`   DECIMAL(5,4)     DEFAULT NULL             COMMENT '行为识别置信度 0~1',
  `description`        TEXT             DEFAULT NULL             COMMENT '补充描述',
  `create_time`        DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time`        DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`behavior_id`),
  KEY `idx_behavior_type_id` (`behavior_type_id`),
  KEY `idx_person_id` (`person_id`),
  KEY `idx_track_id` (`track_id`),
  KEY `idx_alert_status_id` (`alert_status_id`),
  KEY `idx_detected_at` (`detected_at`),
  KEY `idx_type_detected` (`behavior_type_id`, `detected_at`),
  KEY `idx_person_detected` (`person_id`, `detected_at`),
  CONSTRAINT `fk_ab_type` FOREIGN KEY (`behavior_type_id`) REFERENCES `dm_behavior_type` (`behavior_type_id`)
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_ab_person` FOREIGN KEY (`person_id`) REFERENCES `dm_anonymous_person` (`person_id`)
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_ab_track` FOREIGN KEY (`track_id`) REFERENCES `track_pass_chain` (`id`)
    ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `fk_ab_severity` FOREIGN KEY (`severity_level_id`) REFERENCES `dm_severity_level` (`severity_level_id`)
    ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `fk_ab_status` FOREIGN KEY (`alert_status_id`) REFERENCES `dm_alert_status` (`alert_status_id`)
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_ab_camera` FOREIGN KEY (`camera_id`) REFERENCES `device` (`id`)
    ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='异常行为记录（核心事实表）';

-- ------------------------------------------------------------
-- 16. 行为预警（事实表）
-- ------------------------------------------------------------
CREATE TABLE `fa_behavior_alert` (
  `alert_id`          BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT  COMMENT '预警ID，自增主键',
  `behavior_id`       BIGINT UNSIGNED  NOT NULL                 COMMENT '关联异常行为记录（一对一），引用fa_abnormal_behavior.behavior_id',
  `severity_level_id` TINYINT UNSIGNED DEFAULT NULL             COMMENT '预警严重度，引用dm_severity_level.severity_level_id',
  `alert_status_id`   TINYINT UNSIGNED NOT NULL DEFAULT 1       COMMENT '预警状态，引用dm_alert_status.alert_status_id，默认1待确认',
  `alert_time`        DATETIME         NOT NULL                 COMMENT '产生告警时间',
  `notify_method`     VARCHAR(64)      DEFAULT NULL             COMMENT '通知方式：POPUP/SOUND_LIGHT/PUSH，多值逗号分隔',
  `confirmed_at`      DATETIME         DEFAULT NULL             COMMENT '确认时间',
  `confirmed_by`      BIGINT UNSIGNED  DEFAULT NULL             COMMENT '确认人用户ID，引用sys_account.account_id',
  `is_marked_focus`   TINYINT UNSIGNED NOT NULL DEFAULT 0       COMMENT '是否标记重点关注：0否 1是',
  `resolved_at`       DATETIME         DEFAULT NULL             COMMENT '闭环完成时间',
  `create_time`       DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time`       DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`alert_id`),
  UNIQUE KEY `uk_behavior_id` (`behavior_id`),
  KEY `idx_alert_status_time` (`alert_status_id`, `alert_time`),
  KEY `idx_confirmed_by` (`confirmed_by`),
  CONSTRAINT `fk_alert_behavior` FOREIGN KEY (`behavior_id`) REFERENCES `fa_abnormal_behavior` (`behavior_id`)
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `fk_alert_severity` FOREIGN KEY (`severity_level_id`) REFERENCES `dm_severity_level` (`severity_level_id`)
    ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `fk_alert_status_fk` FOREIGN KEY (`alert_status_id`) REFERENCES `dm_alert_status` (`alert_status_id`)
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_alert_confirmed_by` FOREIGN KEY (`confirmed_by`) REFERENCES `sys_account` (`account_id`)
    ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='行为预警（事实表）';

-- ------------------------------------------------------------
-- 17. 处置工单（事实表）
-- ------------------------------------------------------------
CREATE TABLE `fa_work_order` (
  `work_order_id`           BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT  COMMENT '工单ID，自增主键',
  `work_order_no`           VARCHAR(20)      NOT NULL                 COMMENT '工单编号，编码规则：WO+年月日(8位)+4位流水，如WO202507280001',
  `alert_id`                BIGINT UNSIGNED  NOT NULL                 COMMENT '关联预警，引用fa_behavior_alert.alert_id',
  `behavior_id`             BIGINT UNSIGNED  NOT NULL                 COMMENT '关联异常行为，引用fa_abnormal_behavior.behavior_id',
  `work_order_status_id`    TINYINT UNSIGNED NOT NULL DEFAULT 1       COMMENT '工单状态，引用dm_work_order_status.work_order_status_id，默认1待处理',
  `assigned_to`             BIGINT UNSIGNED  DEFAULT NULL             COMMENT '处理人用户ID，引用sys_account.account_id',
  `handler_role`            VARCHAR(32)      DEFAULT NULL             COMMENT '处理人角色编码',
  `assigned_by`             BIGINT UNSIGNED  DEFAULT NULL             COMMENT '派单人用户ID，引用sys_account.account_id',
  `assigned_at`             DATETIME         DEFAULT NULL             COMMENT '派单时间',
  `handled_at`              DATETIME         DEFAULT NULL             COMMENT '处理完成时间',
  `handle_result`           TEXT             DEFAULT NULL             COMMENT '处理结果、措施说明',
  `handle_duration_minutes` INT              DEFAULT NULL             COMMENT '处理耗时（分钟）',
  `create_time`             DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time`             DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`work_order_id`),
  UNIQUE KEY `uk_work_order_no` (`work_order_no`),
  KEY `idx_alert_id` (`alert_id`),
  KEY `idx_behavior_id` (`behavior_id`),
  KEY `idx_assigned_to_status` (`assigned_to`, `work_order_status_id`),
  KEY `idx_assigned_by` (`assigned_by`),
  CONSTRAINT `fk_wo_alert` FOREIGN KEY (`alert_id`) REFERENCES `fa_behavior_alert` (`alert_id`)
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_wo_behavior` FOREIGN KEY (`behavior_id`) REFERENCES `fa_abnormal_behavior` (`behavior_id`)
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_wo_status` FOREIGN KEY (`work_order_status_id`) REFERENCES `dm_work_order_status` (`work_order_status_id`)
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_wo_assigned_to` FOREIGN KEY (`assigned_to`) REFERENCES `sys_account` (`account_id`)
    ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `fk_wo_assigned_by` FOREIGN KEY (`assigned_by`) REFERENCES `sys_account` (`account_id`)
    ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='处置工单（事实表）';

-- ------------------------------------------------------------
-- 18. 操作日志（事实表）
-- ------------------------------------------------------------
CREATE TABLE `fa_operation_log` (
  `log_id`             BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT  COMMENT '日志ID，自增主键',
  `module_code`        VARCHAR(32)      NOT NULL                 COMMENT '模块编码：ABNORMAL_BEHAVIOR/BACKUP_RESTORE/USER_PROFILE',
  `operation_type`     VARCHAR(32)      NOT NULL                 COMMENT '操作类型：QUERY/EXPORT/BACKUP/RESTORE/UPDATE/DELETE',
  `operator_id`        BIGINT UNSIGNED  DEFAULT NULL             COMMENT '操作人用户ID，引用sys_account.account_id',
  `operator_role`      VARCHAR(32)      DEFAULT NULL             COMMENT '操作人角色编码（按当前值快照）',
  `target_id`          BIGINT UNSIGNED  DEFAULT NULL             COMMENT '被操作对象ID',
  `target_type`        VARCHAR(32)      DEFAULT NULL             COMMENT '对象类型：BEHAVIOR/USER/BACKUP',
  `operation_content`  JSON             DEFAULT NULL             COMMENT '操作详情（查询条件/导出范围/变更前后值）',
  `ip_address`         VARCHAR(64)      DEFAULT NULL             COMMENT '操作IP地址',
  `operated_at`        DATETIME         NOT NULL                 COMMENT '操作时间',
  `create_time`        DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`log_id`),
  KEY `idx_module_op_time` (`module_code`, `operation_type`, `operated_at`),
  KEY `idx_operator_id` (`operator_id`),
  CONSTRAINT `fk_log_operator` FOREIGN KEY (`operator_id`) REFERENCES `sys_account` (`account_id`)
    ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='操作日志（事实表）';

-- ============================================================
-- 初始化数据：预置维度枚举 + 超级管理员角色
-- ============================================================

-- 严重程度
INSERT INTO `dm_severity_level` (`severity_level_id`, `level_name`, `level_sort`) VALUES
(1, '高',   1),
(2, '中',   2),
(3, '低',   3);

-- 预警状态
INSERT INTO `dm_alert_status` (`alert_status_id`, `status_name`, `status_sort`) VALUES
(1, '待确认', 1),
(2, '已确认', 2),
(3, '已派单', 3),
(4, '处理中', 4),
(5, '已处理', 5),
(6, '已忽略', 6);

-- 工单状态
INSERT INTO `dm_work_order_status` (`work_order_status_id`, `status_name`, `status_sort`) VALUES
(1, '待处理', 1),
(2, '处理中', 2),
(3, '已完成', 3),
(4, '已关闭', 4);

-- 超级管理员角色（type_id 固定为 1）
INSERT INTO `sys_user_type` (`type_id`, `type_name`, `type_desc`) VALUES (1, '超级管理员', '系统预置最高权限角色，禁止删除，不配置权限直接放行全部');

-- ============================================================
-- 系统必需初始化数据：权限树 + 预置角色 + 角色权限 + 超级管理员账号
-- 说明：本部分为系统运行的最低数据要求，非演示数据
-- 注意：账号密码为 Mock 阶段明文存储，生产环境必须替换为 BCrypt 等加密串
-- ============================================================

-- ------------------------------------------------------------
-- 权限资源树（perm_type：1=菜单权限 2=按钮操作权限 3=数据查询权限）
-- ------------------------------------------------------------
INSERT INTO `sys_permission` (`perm_id`, `perm_name`, `perm_key`, `perm_type`, `parent_id`, `sort`) VALUES
-- 菜单权限（对应前端导航）
(1,  '总览看板',       'dashboard:view',     1, 0, 1),
(2,  '实时轨迹',       'track:realtime',     1, 0, 2),
(3,  '历史轨迹',       'track:history',      1, 0, 3),
(4,  '设备管理',       'device:view',        1, 0, 4),
(5,  '数据管理',       'data:view',          1, 0, 5),
(6,  '告警待办',       'alarm:view',         1, 0, 6),
(7,  '权限管理',       'system:view',        1, 0, 7),
(8,  '操作日志',       'log:view',           1, 0, 8),
-- 按钮操作权限
(11, '告警确认',       'alarm:confirm',      2, 6, 1),
(12, '告警派单',       'alarm:assign',       2, 6, 2),
(13, '工单处理',       'workorder:handle',   2, 6, 3),
(14, '日志导出',       'log:export',         2, 8, 1),
(15, '设备新增',       'device:create',      2, 4, 1),
(16, '设备编辑',       'device:update',      2, 4, 2),
(17, '数据导出',       'data:export',        2, 5, 1),
(18, '账号新增',       'system:user:create', 2, 7, 1),
(19, '角色权限配置',   'system:role:config', 2, 7, 2),
-- 数据查询权限
(21, '轨迹数据查询',   'track:query',        3, 2, 1),
(22, '异常行为查询',   'behavior:query',     3, 5, 2),
(23, '人员资料查询',   'person:query',       3, 5, 3),
(24, '日志查询',       'log:query',          3, 8, 2);

-- ------------------------------------------------------------
-- 预置角色（type_id=1 超级管理员已在上方插入）
-- ------------------------------------------------------------
INSERT INTO `sys_user_type` (`type_id`, `type_name`, `type_desc`) VALUES
(2, '园区安全负责人', '安保/EHS主管，负责异常行为与轨迹监测，园区全量数据'),
(3, '安保/巡检人员', '一线安保、巡检员，按辖区查看监测与处置告警'),
(4, '心理辅导员(EAP)', '驻场咨询师、社工，查看行为记录与人员资料'),
(5, '部门主管', '班组长、部门经理，仅查看本部门数据'),
(6, '员工本人', '被监测员工，仅查看本人授权与报表'),
(7, '合规审计员', '审计/法务/HRBP，只读全量数据与审计日志');

-- ------------------------------------------------------------
-- 角色默认权限（超级管理员按鉴权规则不配置，登录时直接放行全部）
-- ------------------------------------------------------------
INSERT INTO `sys_type_permission` (`type_id`, `perm_id`) VALUES
-- 园区安全负责人：全业务菜单（无权限管理）+ 全部业务按钮 + 全部数据权限
(2,1),(2,2),(2,3),(2,4),(2,5),(2,6),(2,8),
(2,11),(2,12),(2,13),(2,14),(2,15),(2,16),(2,17),
(2,21),(2,22),(2,23),(2,24),
-- 安保/巡检人员：看板+实时轨迹+历史轨迹+设备+告警
(3,1),(3,2),(3,3),(3,4),(3,6),
(3,11),(3,12),(3,13),
(3,21),(3,22),
-- 心理辅导员(EAP)：看板+数据管理
(4,1),(4,5),
(4,22),(4,23),
-- 部门主管：看板+数据管理（本部门数据）
(5,1),(5,5),
(5,22),
-- 员工本人：仅看板+本人轨迹查询
(6,1),
(6,21),
-- 合规审计员：看板+数据管理+操作日志（只读+导出）
(7,1),(7,5),(7,8),
(7,14),(7,17),
(7,21),(7,22),(7,23),(7,24);

-- ------------------------------------------------------------
-- 超级管理员账号（Mock 阶段密码明文存储，生产必须加密）
-- ------------------------------------------------------------
INSERT INTO `sys_account` (`account_id`, `login_name`, `password`, `real_name`, `dept`, `phone`, `type_id`, `status`)
VALUES (1, 'admin', 'admin123', '系统管理员', 'IT运维部', '13800000001', 1, 1);

-- ============================================================
-- 完成
-- 后续请执行 mock_data.sql 灌入业务演示数据
-- ============================================================
