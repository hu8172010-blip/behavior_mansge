USE `behavior_mansge`;

-- 数据备份与恢复（P0 补全）
-- 表：sys_data_backup 备份记录 / sys_data_restore_log 恢复日志

CREATE TABLE IF NOT EXISTS `sys_data_backup` (
  `backup_id`    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `backup_name`  VARCHAR(128)    NOT NULL COMMENT '备份名称',
  `backup_type`  VARCHAR(16)     NOT NULL DEFAULT 'MANUAL' COMMENT '备份类型 MANUAL/AUTO',
  `strategy_desc` VARCHAR(255)   DEFAULT NULL COMMENT '备份策略说明（自动备份时填写周期）',
  `file_path`    VARCHAR(512)    NOT NULL COMMENT '备份文件相对路径',
  `file_size`    BIGINT          DEFAULT 0 COMMENT '备份文件字节数',
  `status`       VARCHAR(16)     NOT NULL DEFAULT 'SUCCESS' COMMENT 'SUCCESS/FAILED/RESTORED',
  `operator_id`  BIGINT UNSIGNED DEFAULT NULL COMMENT '操作人账号ID',
  `operator_name` VARCHAR(64)    DEFAULT NULL COMMENT '操作人姓名',
  `create_time`  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`backup_id`),
  KEY `idx_type_status` (`backup_type`, `status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='数据备份记录';

CREATE TABLE IF NOT EXISTS `sys_data_restore_log` (
  `restore_id`    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `backup_id`     BIGINT UNSIGNED NOT NULL COMMENT '来源备份ID',
  `backup_name`   VARCHAR(128)    DEFAULT NULL COMMENT '来源备份名称（冗余快照）',
  `restore_status` VARCHAR(16)    NOT NULL DEFAULT 'SUCCESS' COMMENT 'SUCCESS/FAILED',
  `result_msg`    VARCHAR(500)    DEFAULT NULL COMMENT '恢复结果说明',
  `operator_id`   BIGINT UNSIGNED DEFAULT NULL,
  `operator_name` VARCHAR(64)     DEFAULT NULL,
  `restore_time`  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '恢复时间',
  PRIMARY KEY (`restore_id`),
  KEY `idx_backup_id` (`backup_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='数据恢复日志';
