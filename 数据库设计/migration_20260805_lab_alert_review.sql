-- ============================================================
-- 2026-08-05 模拟实验室异常行为识别完整业务闭环改造
-- 说明：
--   1. 告警待办层独立保存模型原始输出、原始视频地址、摄像头绑定
--   2. 异常行为记录与轨迹增加 "is_archived" 归档开关
--      仅人工复核确认后 is_archived=1 的记录才进入正式业务表
--   3. 记录复核结论：是否误报、人员身份、复核人、复核时间
--
-- 运行方式：mysql -u root -p behavior_mansge < migration_20260805_lab_alert_review.sql
-- 本脚本通过存储过程 + CONTINUE HANDLER 忽略已存在字段/索引/外键错误，
-- 可以直接重复执行。
-- ============================================================

USE `behavior_mansge`;

DROP PROCEDURE IF EXISTS `do_migration_20260805`;

DELIMITER $$

CREATE PROCEDURE `do_migration_20260805`()
BEGIN
  -- 忽略 DDL 重复错误，使本脚本可重复运行
  DECLARE CONTINUE HANDLER FOR SQLEXCEPTION BEGIN END;

  -- ------------------------------------------------------------
  -- 1. 模拟记录表扩展：支持双视频、双摄像头
  -- ------------------------------------------------------------
  ALTER TABLE `lab_record` ADD COLUMN `camera_a_id`     BIGINT UNSIGNED DEFAULT NULL COMMENT '摄像头A（单视频时为唯一摄像头）';
  ALTER TABLE `lab_record` ADD COLUMN `camera_b_id`     BIGINT UNSIGNED DEFAULT NULL COMMENT '摄像头B（双视频场景）';
  ALTER TABLE `lab_record` ADD COLUMN `is_dual_video`   TINYINT         NOT NULL DEFAULT 0 COMMENT '是否双视频任务：0否 1是';
  ALTER TABLE `lab_record` ADD COLUMN `video_path_b`    VARCHAR(512)    DEFAULT NULL COMMENT '视频B原始资源地址';
  ALTER TABLE `lab_record` ADD KEY `idx_camera_a` (`camera_a_id`);
  ALTER TABLE `lab_record` ADD KEY `idx_camera_b` (`camera_b_id`);

  -- ------------------------------------------------------------
  -- 2. 异常行为记录表：增加归档开关与复核结论
  -- ------------------------------------------------------------
  ALTER TABLE `fa_abnormal_behavior` ADD COLUMN `lab_record_id`     BIGINT UNSIGNED DEFAULT NULL COMMENT '关联模拟记录ID';
  ALTER TABLE `fa_abnormal_behavior` ADD COLUMN `camera_b_id`       BIGINT UNSIGNED DEFAULT NULL COMMENT '双视频场景第二摄像头';
  ALTER TABLE `fa_abnormal_behavior` ADD COLUMN `is_archived`       TINYINT         NOT NULL DEFAULT 0 COMMENT '是否已归档（复核后正式生效）：0否 1是';
  ALTER TABLE `fa_abnormal_behavior` ADD COLUMN `false_positive`    TINYINT         DEFAULT NULL COMMENT '是否误报：0否 1是';
  ALTER TABLE `fa_abnormal_behavior` ADD COLUMN `person_identity`   VARCHAR(32)     DEFAULT NULL COMMENT '人员身份：registered=登记人员，stranger=陌生人';
  ALTER TABLE `fa_abnormal_behavior` ADD COLUMN `reviewed_by`       BIGINT UNSIGNED DEFAULT NULL COMMENT '复核人ID';
  ALTER TABLE `fa_abnormal_behavior` ADD COLUMN `reviewed_at`       DATETIME        DEFAULT NULL COMMENT '复核时间';
  ALTER TABLE `fa_abnormal_behavior` ADD COLUMN `reid_result`       TEXT            DEFAULT NULL COMMENT 'ReID跨视频关联结果JSON';
  ALTER TABLE `fa_abnormal_behavior` ADD COLUMN `model_evidence`    TEXT            DEFAULT NULL COMMENT '模型原始输出证据JSON';
  ALTER TABLE `fa_abnormal_behavior` ADD KEY `idx_lab_record_id` (`lab_record_id`);
  ALTER TABLE `fa_abnormal_behavior` ADD KEY `idx_is_archived` (`is_archived`);
  ALTER TABLE `fa_abnormal_behavior` ADD CONSTRAINT `fk_ab_lab_record` FOREIGN KEY (`lab_record_id`) REFERENCES `lab_record` (`record_id`) ON DELETE SET NULL ON UPDATE CASCADE;
  ALTER TABLE `fa_abnormal_behavior` ADD CONSTRAINT `fk_ab_reviewed_by` FOREIGN KEY (`reviewed_by`) REFERENCES `sys_account` (`account_id`) ON DELETE SET NULL ON UPDATE CASCADE;

  -- ------------------------------------------------------------
  -- 3. 行为预警表：保存模型原始输出、原始视频、摄像头绑定
  -- ------------------------------------------------------------
  ALTER TABLE `fa_behavior_alert` ADD COLUMN `lab_record_id`      BIGINT UNSIGNED DEFAULT NULL COMMENT '关联模拟记录ID';
  ALTER TABLE `fa_behavior_alert` ADD COLUMN `camera_a_id`        BIGINT UNSIGNED DEFAULT NULL COMMENT '摄像头A（单视频时为唯一摄像头）';
  ALTER TABLE `fa_behavior_alert` ADD COLUMN `camera_b_id`        BIGINT UNSIGNED DEFAULT NULL COMMENT '摄像头B（双视频场景）';
  ALTER TABLE `fa_behavior_alert` ADD COLUMN `is_dual_video`      TINYINT         NOT NULL DEFAULT 0 COMMENT '是否双视频任务';
  ALTER TABLE `fa_behavior_alert` ADD COLUMN `video_path`         VARCHAR(512)    DEFAULT NULL COMMENT '视频A原始资源地址';
  ALTER TABLE `fa_behavior_alert` ADD COLUMN `video_path_b`       VARCHAR(512)    DEFAULT NULL COMMENT '视频B原始资源地址';
  ALTER TABLE `fa_behavior_alert` ADD COLUMN `model_result_json`  LONGTEXT        DEFAULT NULL COMMENT '模型原始完整返回JSON';
  ALTER TABLE `fa_behavior_alert` ADD COLUMN `false_positive`     TINYINT         DEFAULT NULL COMMENT '是否误报';
  ALTER TABLE `fa_behavior_alert` ADD COLUMN `person_identity`    VARCHAR(32)     DEFAULT NULL COMMENT '人员身份';
  ALTER TABLE `fa_behavior_alert` ADD COLUMN `reviewed_by`        BIGINT UNSIGNED DEFAULT NULL COMMENT '复核人ID';
  ALTER TABLE `fa_behavior_alert` ADD COLUMN `reviewed_at`        DATETIME        DEFAULT NULL COMMENT '复核时间';
  ALTER TABLE `fa_behavior_alert` ADD KEY `idx_alert_lab_record` (`lab_record_id`);
  ALTER TABLE `fa_behavior_alert` ADD CONSTRAINT `fk_alert_lab_record` FOREIGN KEY (`lab_record_id`) REFERENCES `lab_record` (`record_id`) ON DELETE SET NULL ON UPDATE CASCADE;
  ALTER TABLE `fa_behavior_alert` ADD CONSTRAINT `fk_alert_reviewed_by` FOREIGN KEY (`reviewed_by`) REFERENCES `sys_account` (`account_id`) ON DELETE SET NULL ON UPDATE CASCADE;

  -- ------------------------------------------------------------
  -- 4. 轨迹链路表：增加归档开关与模拟记录关联
  -- ------------------------------------------------------------
  ALTER TABLE `track_pass_chain` ADD COLUMN `lab_record_id`   BIGINT UNSIGNED DEFAULT NULL COMMENT '关联模拟记录ID';
  ALTER TABLE `track_pass_chain` ADD COLUMN `is_archived`     TINYINT         NOT NULL DEFAULT 0 COMMENT '是否已归档';
  ALTER TABLE `track_pass_chain` ADD KEY `idx_chain_lab_record` (`lab_record_id`);
  ALTER TABLE `track_pass_chain` ADD KEY `idx_chain_archived` (`is_archived`);
  ALTER TABLE `track_pass_chain` ADD CONSTRAINT `fk_chain_lab_record` FOREIGN KEY (`lab_record_id`) REFERENCES `lab_record` (`record_id`) ON DELETE SET NULL ON UPDATE CASCADE;
END$$

DELIMITER ;

CALL `do_migration_20260805`();
DROP PROCEDURE `do_migration_20260805`;

-- ------------------------------------------------------------
-- 5. 存量数据归档开关初始化
-- ------------------------------------------------------------
UPDATE `fa_abnormal_behavior` SET `is_archived` = 1 WHERE `is_lab` = 0;
UPDATE `track_pass_chain` SET `is_archived` = 1 WHERE `is_lab` = 0;
