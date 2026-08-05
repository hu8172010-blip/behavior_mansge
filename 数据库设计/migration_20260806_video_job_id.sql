-- 2026-08-06 为 lab_record 与 fa_behavior_alert 增加 video_job_id 字段
-- 用于前端在线播放弹窗直接校验模型视频资源是否存在

USE `behavior_mansge`;

ALTER TABLE `lab_record`
  ADD COLUMN `video_job_id`   VARCHAR(64) DEFAULT NULL COMMENT '单视频/摄像头A对应模型 job_id' AFTER `video_path_b`,
  ADD COLUMN `video_job_id_b` VARCHAR(64) DEFAULT NULL COMMENT '双视频摄像头B对应模型 job_id' AFTER `video_job_id`;

ALTER TABLE `fa_behavior_alert`
  ADD COLUMN `video_job_id`   VARCHAR(64) DEFAULT NULL COMMENT '单视频/摄像头A对应模型 job_id' AFTER `video_path_b`,
  ADD COLUMN `video_job_id_b` VARCHAR(64) DEFAULT NULL COMMENT '双视频摄像头B对应模型 job_id' AFTER `video_job_id`;
