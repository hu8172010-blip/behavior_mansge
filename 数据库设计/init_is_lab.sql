-- 给业务表添加 is_lab 标记字段，用于区分模拟实验室数据

ALTER TABLE `track_pass_chain` ADD COLUMN `is_lab` TINYINT NOT NULL DEFAULT 0;
ALTER TABLE `dm_anonymous_person` ADD COLUMN `is_lab` TINYINT NOT NULL DEFAULT 0;
ALTER TABLE `fa_abnormal_behavior` ADD COLUMN `is_lab` TINYINT NOT NULL DEFAULT 0;
ALTER TABLE `fa_behavior_alert` ADD COLUMN `is_lab` TINYINT NOT NULL DEFAULT 0;
ALTER TABLE `fa_work_order` ADD COLUMN `is_lab` TINYINT NOT NULL DEFAULT 0;
