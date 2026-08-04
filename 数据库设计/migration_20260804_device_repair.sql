-- ============================================================
-- 迁移脚本：设备维修工单模块（2026-08-04）
-- 适用场景：在【已有数据的现有库】上直接执行，无需重建数据库
-- 特性：幂等，可重复执行；不 DROP 任何表，不影响现有数据
-- 内容：
--   1. 新增表：device_repair_order        设备维修工单表（不存在才创建）
--   2. 新增表：device_repair_dispatch_log 维修工单派发日志表（不存在才创建）
--   3. 新增权限点：device:repair（设备维修）、device:info:view（设备信息查看）
--      （按 perm_key 判重，已存在则跳过，perm_id 自增不硬编码）
--   4. 预置角色权限绑定：园区安全负责人(2)、安保/巡检人员(3) 获得维修权限；
--      合规审计员(7) 获得设备信息查看权限（已绑定则跳过）
-- 前置条件：已执行过 init_database.sql（device / fault_record / sys_permission 等表存在）
-- ============================================================

-- ------------------------------------------------------------
-- 1. 设备维修工单表
--    故障记录为触发源，维修工单为衍生业务，通过 fault_id 一对一关联
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `device_repair_order` (
  -- 核心标识
  `id`                BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT  COMMENT '自增主键',
  `order_no`          VARCHAR(32)      NOT NULL                 COMMENT '工单编号（业务唯一，如 RO202608040001）',
  `fault_id`          BIGINT UNSIGNED  NOT NULL                 COMMENT '关联故障记录ID，外键→fault_record.id，唯一（一故障一工单）',
  `device_id`         BIGINT UNSIGNED  NOT NULL                 COMMENT '关联设备ID，外键→device.id',
  `device_code`       VARCHAR(64)      NOT NULL                 COMMENT '设备编号（冗余字段，方便查询）',
  `device_name`       VARCHAR(128)     DEFAULT NULL             COMMENT '设备名称（冗余快照）',
  -- 工单状态
  `status`            VARCHAR(16)      NOT NULL DEFAULT 'PENDING' COMMENT '工单状态：PENDING待处理/REPAIRING维修中/COMPLETED已完成归档',
  -- 维修信息（归档时必填）
  `damage_cause`      VARCHAR(500)     DEFAULT NULL             COMMENT '损坏原因（完成归档必填）',
  `repair_detail`     VARCHAR(500)     DEFAULT NULL             COMMENT '维修情况（完成归档必填）',
  -- 派发信息
  `assigned_to`       BIGINT UNSIGNED  DEFAULT NULL             COMMENT '维修人员ID，关联sys_account.account_id；无可派人员时为NULL',
  `assigned_name`     VARCHAR(64)      DEFAULT NULL             COMMENT '维修人员姓名',
  `dispatch_strategy` VARCHAR(32)      DEFAULT NULL             COMMENT '派发策略：LEAST_LOAD=平均负载派发',
  `assigned_at`       DATETIME         DEFAULT NULL             COMMENT '派发时间',
  `plan_finish_time`  DATETIME         DEFAULT NULL             COMMENT '计划处理时间（默认派发后24小时）',
  `started_at`        DATETIME         DEFAULT NULL             COMMENT '接单/开始维修时间',
  `completed_at`      DATETIME         DEFAULT NULL             COMMENT '完成归档时间',
  -- 审计字段
  `operator_id`       BIGINT UNSIGNED  DEFAULT NULL             COMMENT '最后操作人ID，关联sys_account.account_id',
  `operator_name`     VARCHAR(64)      DEFAULT NULL             COMMENT '最后操作人姓名',
  `is_deleted`        TINYINT          NOT NULL DEFAULT 0       COMMENT '逻辑删除：0未删除 1已删除',
  `create_time`       DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time`       DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_repair_order_no` (`order_no`),
  UNIQUE KEY `uk_repair_fault` (`fault_id`),
  KEY `idx_repair_device` (`device_id`),
  KEY `idx_repair_status` (`status`),
  KEY `idx_repair_assigned_to` (`assigned_to`),
  CONSTRAINT `fk_repair_fault` FOREIGN KEY (`fault_id`) REFERENCES `fault_record` (`id`)
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `fk_repair_device` FOREIGN KEY (`device_id`) REFERENCES `device` (`id`)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='设备维修工单表';

-- ------------------------------------------------------------
-- 2. 维修工单派发日志表
--    记录每次自动派发的候选池、负载快照与中选人，分配规则可追溯
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `device_repair_dispatch_log` (
  `id`               BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT  COMMENT '自增主键',
  `order_id`         BIGINT UNSIGNED  NOT NULL                 COMMENT '关联维修工单ID，外键→device_repair_order.id',
  `fault_id`         BIGINT UNSIGNED  NOT NULL                 COMMENT '关联故障记录ID（冗余）',
  `device_id`        BIGINT UNSIGNED  NOT NULL                 COMMENT '关联设备ID（冗余）',
  `strategy`         VARCHAR(32)      NOT NULL DEFAULT 'LEAST_LOAD' COMMENT '派发策略：LEAST_LOAD=平均负载（未完成工单最少优先）',
  `candidate_count`  INT              NOT NULL DEFAULT 0       COMMENT '候选维修人员数量（拥有device:repair权限且启用）',
  `load_snapshot`    JSON             DEFAULT NULL             COMMENT '候选人负载快照，格式 {"账号ID": 未完成工单数}',
  `winner_id`        BIGINT UNSIGNED  DEFAULT NULL             COMMENT '中选维修人员ID，关联sys_account.account_id',
  `winner_name`      VARCHAR(64)      DEFAULT NULL             COMMENT '中选维修人员姓名',
  `result`           VARCHAR(16)      NOT NULL DEFAULT 'SUCCESS' COMMENT '派发结果：SUCCESS成功/NO_CANDIDATE无候选人员',
  `remark`           VARCHAR(500)     DEFAULT NULL             COMMENT '备注（如无可派人员原因）',
  `create_time`      DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '派发时间',
  PRIMARY KEY (`id`),
  KEY `idx_dispatch_order` (`order_id`),
  KEY `idx_dispatch_fault` (`fault_id`),
  KEY `idx_dispatch_device` (`device_id`),
  CONSTRAINT `fk_dispatch_order` FOREIGN KEY (`order_id`) REFERENCES `device_repair_order` (`id`)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='维修工单派发日志表';

-- ------------------------------------------------------------
-- 2.1 老库补列：device_repair_order.plan_finish_time（已存在则跳过，幂等）
-- ------------------------------------------------------------
SET @col_exists := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'device_repair_order' AND COLUMN_NAME = 'plan_finish_time'
);
SET @alter_sql := IF(@col_exists = 0,
  'ALTER TABLE `device_repair_order` ADD COLUMN `plan_finish_time` DATETIME DEFAULT NULL COMMENT ''计划处理时间（默认派发后24小时）'' AFTER `assigned_at`',
  'SELECT 1'
);
PREPARE stmt FROM @alter_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ------------------------------------------------------------
-- 3. 新增权限点（挂在"设备管理"菜单 parent_id=4 下）
--    perm_type：2=按钮操作权限 3=数据查询权限
--    按 perm_key 判重，已存在则跳过；perm_id 由自增分配，不与现有数据冲突
-- ------------------------------------------------------------
INSERT INTO `sys_permission` (`perm_name`, `perm_key`, `perm_type`, `parent_id`, `sort`)
SELECT '设备维修', 'device:repair', 2, 4, 3 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `sys_permission` WHERE `perm_key` = 'device:repair');

INSERT INTO `sys_permission` (`perm_name`, `perm_key`, `perm_type`, `parent_id`, `sort`)
SELECT '设备信息查看', 'device:info:view', 3, 4, 4 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `sys_permission` WHERE `perm_key` = 'device:info:view');

-- ------------------------------------------------------------
-- 4. 预置角色权限绑定
--    园区安全负责人(2)、安保/巡检人员(3)：设备维修 + 设备信息查看（成为默认维修候选人员池）
--    合规审计员(7)：设备信息查看（只读追溯）
--    超级管理员(1) 按鉴权规则不配置，登录时直接放行全部
--    按 (type_id, perm_key) 判重，已绑定则跳过
-- ------------------------------------------------------------
INSERT INTO `sys_type_permission` (`type_id`, `perm_id`)
SELECT m.type_id, p.perm_id
FROM (
  SELECT 2 AS type_id, 'device:repair'    AS perm_key
  UNION ALL SELECT 2, 'device:info:view'
  UNION ALL SELECT 3, 'device:repair'
  UNION ALL SELECT 3, 'device:info:view'
  UNION ALL SELECT 7, 'device:info:view'
) m
JOIN `sys_permission` p ON p.perm_key = m.perm_key
WHERE NOT EXISTS (
  SELECT 1 FROM `sys_type_permission` tp
  WHERE tp.type_id = m.type_id AND tp.perm_id = p.perm_id
);
