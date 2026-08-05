-- ============================================================
-- 跨摄像头异常行为轨迹分析系统 - 业务演示 Mock 数据
-- 前置：已执行 init_database.sql（含维度枚举/权限树/角色/admin账号）
-- 重灌：本脚本使用显式主键，不可重复执行；重灌前请先重新执行 init_database.sql 重置全库
-- 时间基准：以脚本执行时刻 NOW() 为准，所有业务时间按其分钟偏移生成
-- 注意：密码为 Mock 阶段明文存储，生产环境必须替换为加密串
-- ============================================================

USE `behavior_mansge`;

-- ------------------------------------------------------------
-- 1. 演示账号（account_id=1 admin 已在 init 脚本创建）
-- ------------------------------------------------------------
INSERT INTO `sys_account` (`account_id`, `login_name`, `password`, `real_name`, `dept`, `phone`, `type_id`, `status`, `last_login_time`) VALUES
(2, 'security',   'sec123',   '王安全', '安保部',      '13800000002', 2, 1, NOW() - INTERVAL 30 MINUTE),
(3, 'guard',      'guard123', '李巡检', '安保部',      '13800000003', 3, 1, NOW() - INTERVAL 55 MINUTE),
(4, 'counselor',  'coun123',  '张心理', 'EAP心理中心', '13800000004', 4, 1, NOW() - INTERVAL 1 DAY),
(5, 'supervisor', 'sup123',   '赵主管', '生产一部',    '13800000005', 5, 1, NOW() - INTERVAL 3 HOUR),
(6, 'employee',   'emp123',   '钱员工', '生产二部',    '13800000006', 6, 1, NOW() - INTERVAL 2 DAY),
(7, 'auditor',    'aud123',   '孙审计', '审计法务部',  '13800000007', 7, 1, NOW() - INTERVAL 5 HOUR),
(8, 'zhangxun',   'zhang123', '张巡',   '安保部',      '13800000008', 3, 1, NOW() - INTERVAL 2 HOUR),
(9, 'disabled',   'dis123',   '周停用', '安保部',      '13800000009', 3, 0, NULL);

-- 账号8（张巡）配置独立权限：仅 实时轨迹+告警待办+轨迹查询，验证"单人权限覆盖角色权限"规则
INSERT INTO `sys_account_permission` (`account_id`, `perm_id`) VALUES
(8, 2), (8, 6), (8, 21);

-- ------------------------------------------------------------
-- 2. 设备（摄像头 id 1001-1024，NVR 1101，边缘盒 1102）
--    状态分布：21 在线 / 1 故障(1022) / 1 离线(1023) / 1 停用(1024)
-- ------------------------------------------------------------
INSERT INTO `device` (`id`, `device_code`, `device_name`, `device_type`, `location_text`, `longitude`, `latitude`, `region_code`, `region_name`, `status`, `health_score`, `video_quality`, `last_heartbeat_time`, `channel_count`, `capability`, `ip_address`, `manufacturer`, `model`, `install_time`, `operator_id`, `operator_name`) VALUES
(1001, 'CAM-001', '南门入口摄像头',     'CAMERA', '南门入口岗亭旁',     116.3912000, 39.9061000, 'REG-GATE',     '南门仓储区', 'ONLINE',   98, 'HD',      NOW() - INTERVAL 1 MINUTE,  1, '{"ptz":true,"night_vision":true}',  '192.168.10.11', '海康威视', 'DS-2CD3T46', '2025-03-12 09:00:00', 1, '系统管理员'),
(1002, 'CAM-002', '南门仓储区全景',     'CAMERA', '仓储区中央立杆',     116.3913500, 39.9062500, 'REG-GATE',     '南门仓储区', 'ONLINE',   97, 'HD',      NOW() - INTERVAL 2 MINUTE,  1, '{"ptz":true,"night_vision":true}',  '192.168.10.12', '海康威视', 'DS-2DP0818', '2025-03-12 09:30:00', 1, '系统管理员'),
(1003, 'CAM-003', '仓储区通道摄像头',   'CAMERA', '仓储区东侧通道',     116.3915000, 39.9061800, 'REG-GATE',     '南门仓储区', 'ONLINE',   95, 'HD',      NOW() - INTERVAL 1 MINUTE,  1, '{"ptz":false,"night_vision":true}', '192.168.10.13', '大华',     'DH-IPC-HFW5442', '2025-03-12 10:00:00', 1, '系统管理员'),
(1004, 'CAM-004', '研发楼一层大厅',     'CAMERA', '研发楼一层大厅吊顶', 116.3921000, 39.9068000, 'REG-RD',       '研发楼',     'ONLINE',   99, 'HD',      NOW() - INTERVAL 1 MINUTE,  1, '{"ptz":true,"night_vision":false}', '192.168.10.21', '海康威视', 'DS-2CD2346', '2025-04-02 14:00:00', 1, '系统管理员'),
(1005, 'CAM-005', '研发楼二层走廊',     'CAMERA', '研发楼二层东侧走廊', 116.3922000, 39.9068500, 'REG-RD',       '研发楼',     'ONLINE',   96, 'HD',      NOW() - INTERVAL 3 MINUTE,  1, '{"ptz":false,"night_vision":false}','192.168.10.22', '大华',     'DH-IPC-HFW3441', '2025-04-02 14:30:00', 1, '系统管理员'),
(1006, 'CAM-006', '研发楼电梯厅',       'CAMERA', '研发楼电梯厅',       116.3921500, 39.9069000, 'REG-RD',       '研发楼',     'ONLINE',   97, 'SD',      NOW() - INTERVAL 2 MINUTE,  1, '{"ptz":false,"night_vision":false}','192.168.10.23', '宇视',     'IPC-B212', '2025-04-02 15:00:00', 1, '系统管理员'),
(1007, 'CAM-007', '研发楼后门摄像头',   'CAMERA', '研发楼后门',         116.3923000, 39.9069500, 'REG-RD',       '研发楼',     'ONLINE',   93, 'HD',      NOW() - INTERVAL 2 MINUTE,  1, '{"ptz":false,"night_vision":true}', '192.168.10.24', '海康威视', 'DS-2CD3T25', '2025-04-02 15:30:00', 1, '系统管理员'),
(1008, 'CAM-008', '园区东侧路口',       'CAMERA', '园区东侧十字路口',   116.3930000, 39.9065000, 'REG-ROAD',     '园区道路',   'ONLINE',   98, 'HD',      NOW() - INTERVAL 1 MINUTE,  1, '{"ptz":true,"night_vision":true}',  '192.168.10.31', '海康威视', 'DS-2CD7A47', '2025-03-20 08:00:00', 1, '系统管理员'),
(1009, 'CAM-009', '园区西侧路口',       'CAMERA', '园区西侧丁字路口',   116.3905000, 39.9064000, 'REG-ROAD',     '园区道路',   'ONLINE',   94, 'HD',      NOW() - INTERVAL 2 MINUTE,  1, '{"ptz":true,"night_vision":true}',  '192.168.10.32', '大华',     'DH-IPC-HFW7842', '2025-03-20 08:30:00', 1, '系统管理员'),
(1010, 'CAM-010', '园区主干道一',       'CAMERA', '主干道中段立杆',     116.3918000, 39.9065500, 'REG-ROAD',     '园区道路',   'ONLINE',   96, 'HD',      NOW() - INTERVAL 1 MINUTE,  1, '{"ptz":false,"night_vision":true}', '192.168.10.33', '海康威视', 'DS-2CD3T46', '2025-03-20 09:00:00', 1, '系统管理员'),
(1011, 'CAM-011', '园区主干道二',       'CAMERA', '主干道北段立杆',     116.3919000, 39.9070000, 'REG-ROAD',     '园区道路',   'ONLINE',   92, 'SD',      NOW() - INTERVAL 4 MINUTE,  1, '{"ptz":false,"night_vision":true}', '192.168.10.34', '宇视',     'IPC-B312', '2025-03-20 09:30:00', 1, '系统管理员'),
(1012, 'CAM-012', '园区北门路口',       'CAMERA', '北门外侧路口',       116.3920000, 39.9074000, 'REG-ROAD',     '园区道路',   'ONLINE',   95, 'HD',      NOW() - INTERVAL 2 MINUTE,  1, '{"ptz":true,"night_vision":true}',  '192.168.10.35', '海康威视', 'DS-2CD7A27', '2025-03-20 10:00:00', 1, '系统管理员'),
(1013, 'CAM-013', '车间A区摄像头',      'CAMERA', '生产车间A区立柱',    116.3926000, 39.9063000, 'REG-WORKSHOP', '生产车间',   'ONLINE',   97, 'HD',      NOW() - INTERVAL 1 MINUTE,  1, '{"ptz":false,"night_vision":false}','192.168.10.41', '海康威视', 'DS-2CD2146', '2025-05-08 10:00:00', 1, '系统管理员'),
(1014, 'CAM-014', '车间B区摄像头',      'CAMERA', '生产车间B区立柱',    116.3927000, 39.9063500, 'REG-WORKSHOP', '生产车间',   'ONLINE',   98, 'HD',      NOW() - INTERVAL 2 MINUTE,  1, '{"ptz":false,"night_vision":false}','192.168.10.42', '大华',     'DH-IPC-HFW5442', '2025-05-08 10:30:00', 1, '系统管理员'),
(1015, 'CAM-015', '车间C区摄像头',      'CAMERA', '生产车间C区立柱',    116.3928000, 39.9064000, 'REG-WORKSHOP', '生产车间',   'ONLINE',   91, 'SD',      NOW() - INTERVAL 3 MINUTE,  1, '{"ptz":false,"night_vision":false}','192.168.10.43', '海康威视', 'DS-2CD2125', '2025-05-08 11:00:00', 1, '系统管理员'),
(1016, 'CAM-016', '车间消防通道摄像头', 'CAMERA', '车间北侧消防通道',   116.3928500, 39.9064800, 'REG-WORKSHOP', '生产车间',   'ONLINE',   96, 'HD',      NOW() - INTERVAL 1 MINUTE,  1, '{"ptz":false,"night_vision":true}', '192.168.10.44', '大华',     'DH-IPC-HFW3441', '2025-05-08 11:30:00', 1, '系统管理员'),
(1017, 'CAM-017', '办公楼大厅摄像头',   'CAMERA', '办公楼一层大厅',     116.3916000, 39.9071000, 'REG-OFFICE',   '办公楼',     'ONLINE',   99, 'HD',      NOW() - INTERVAL 1 MINUTE,  1, '{"ptz":true,"night_vision":false}', '192.168.10.51', '海康威视', 'DS-2CD2346', '2025-04-15 09:00:00', 1, '系统管理员'),
(1018, 'CAM-018', '办公楼三层走廊',     'CAMERA', '办公楼三层走廊',     116.3916500, 39.9071500, 'REG-OFFICE',   '办公楼',     'ONLINE',   95, 'SD',      NOW() - INTERVAL 2 MINUTE,  1, '{"ptz":false,"night_vision":false}','192.168.10.52', '宇视',     'IPC-B212', '2025-04-15 09:30:00', 1, '系统管理员'),
(1019, 'CAM-019', '停车场东区摄像头',   'CAMERA', '停车场东区灯杆',     116.3932000, 39.9069000, 'REG-PARK',     '停车场',     'ONLINE',   94, 'HD',      NOW() - INTERVAL 2 MINUTE,  1, '{"ptz":true,"night_vision":true}',  '192.168.10.61', '海康威视', 'DS-2CD3T46', '2025-06-01 08:00:00', 1, '系统管理员'),
(1020, 'CAM-020', '停车场西区摄像头',   'CAMERA', '停车场西区灯杆',     116.3930000, 39.9069500, 'REG-PARK',     '停车场',     'ONLINE',   90, 'FLUENT',  NOW() - INTERVAL 5 MINUTE,  1, '{"ptz":false,"night_vision":true}', '192.168.10.62', '大华',     'DH-IPC-HFW2441', '2025-06-01 08:30:00', 1, '系统管理员'),
(1021, 'CAM-021', '宿舍一号楼摄像头',   'CAMERA', '宿舍一号楼门厅',     116.3910000, 39.9073000, 'REG-DORM',     '宿舍区',     'ONLINE',   93, 'HD',      NOW() - INTERVAL 2 MINUTE,  1, '{"ptz":false,"night_vision":true}', '192.168.10.71', '海康威视', 'DS-2CD2125', '2025-06-10 09:00:00', 1, '系统管理员'),
(1022, 'CAM-022', '宿舍二号楼摄像头',   'CAMERA', '宿舍二号楼门厅',     116.3911000, 39.9073500, 'REG-DORM',     '宿舍区',     'FAULT',    45, 'UNKNOWN', NOW() - INTERVAL 45 MINUTE, 1, '{"ptz":false,"night_vision":true}', '192.168.10.72', '海康威视', 'DS-2CD2125', '2025-06-10 09:30:00', 1, '系统管理员'),
(1023, 'CAM-023', '周界东段摄像头',     'CAMERA', '园区东侧围墙',       116.3935000, 39.9066000, 'REG-PERI',     '周界',       'OFFLINE',  10, 'UNKNOWN', NOW() - INTERVAL 2 HOUR,   1, '{"ptz":false,"night_vision":true}', '192.168.10.81', '海康威视', 'DS-2CD2T46', '2025-03-25 10:00:00', 1, '系统管理员'),
(1024, 'CAM-024', '周界北段摄像头',     'CAMERA', '园区北侧围墙',       116.3922000, 39.9075000, 'REG-PERI',     '周界',       'DISABLED', 100, 'HD',     NOW() - INTERVAL 1 DAY,    1, '{"ptz":false,"night_vision":true}', '192.168.10.82', '大华',     'DH-IPC-HFW5442', '2025-03-25 10:30:00', 1, '系统管理员'),
(1101, 'NVR-001', '园区中心录像机',     'NVR',    '机房A区机柜',        116.3915500, 39.9067000, 'REG-OFFICE',   '办公楼',     'ONLINE',   99, NULL,      NOW() - INTERVAL 1 MINUTE,  32, NULL, '192.168.10.5',  '海康威视', 'DS-9632NI', '2025-03-01 09:00:00', 1, '系统管理员'),
(1102, 'EDGE-001', '边缘AI分析盒一号',  'EDGE',   '机房A区机柜',        116.3915500, 39.9067000, 'REG-OFFICE',   '办公楼',     'ONLINE',   96, NULL,      NOW() - INTERVAL 1 MINUTE,  16, NULL, '192.168.10.6',  '华为',     'Atlas-500', '2025-03-01 09:30:00', 1, '系统管理员');

-- ------------------------------------------------------------
-- 3. 故障记录（覆盖 PENDING/AUTO_RECOVERED/ASSIGNED/REPAIRED/CLOSED）
-- ------------------------------------------------------------
INSERT INTO `fault_record` (`id`, `device_id`, `device_code`, `fault_type`, `fault_level`, `fault_desc`, `occurrence_time`, `recovery_time`, `auto_recovery_time`, `closed_at`, `disposal_status`, `assigned_to`, `assigned_name`, `auto_recovery`, `repair_result`, `repair_remark`, `closed_by`, `closed_name`, `operator_id`, `operator_name`) VALUES
(9001, 1022, 'CAM-022', 'HEARTBEAT_TIMEOUT', 'HIGH',     '宿舍二号楼摄像头心跳超时45分钟，疑似掉线', NOW() - INTERVAL 40 MINUTE, NULL, NULL, NULL, 'PENDING', NULL, NULL, 0, NULL, NULL, NULL, NULL, 1, '系统管理员'),
(9002, 1022, 'CAM-022', 'VIDEO_ABNORMAL',    'MEDIUM',   '画面出现周期性花屏，夜间红外异常', NOW() - INTERVAL 1 DAY, NULL, NULL, NULL, 'ASSIGNED', 8, '张巡', 0, NULL, NULL, NULL, NULL, 1, '系统管理员'),
(9003, 1023, 'CAM-023', 'NETWORK_FAIL',      'HIGH',     '周界东段光纤链路中断', NOW() - INTERVAL 6 HOUR, NOW() - INTERVAL 3 HOUR, NULL, NULL, 'REPAIRED', 3, '李巡检', 0, 'PASS', '重新熔接光纤并复位设备，复检通过', NULL, NULL, 1, '系统管理员'),
(9004, 1023, 'CAM-023', 'POWER_FAIL',        'CRITICAL', '周界东段POE供电异常', NOW() - INTERVAL 2 DAY, NOW() - INTERVAL 2 DAY + INTERVAL 12 MINUTE, NOW() - INTERVAL 2 DAY + INTERVAL 10 MINUTE, NULL, 'AUTO_RECOVERED', NULL, NULL, 1, NULL, '自动重启发迟后供电恢复', NULL, NULL, 1, '系统管理员'),
(9005, 1015, 'CAM-015', 'CONTROL_FAIL',      'LOW',      '云台控制无响应', NOW() - INTERVAL 3 DAY, NOW() - INTERVAL 3 DAY + INTERVAL 2 HOUR, NULL, NOW() - INTERVAL 3 DAY + INTERVAL 3 HOUR, 'CLOSED', 3, '李巡检', 0, 'PASS', '固件升级后恢复', 1, '系统管理员', 1, '系统管理员'),
(9006, 1024, 'CAM-024', 'MANUAL_REPORT',     'MEDIUM',   '巡检人工上报：镜头防护罩破损，待更换', NOW() - INTERVAL 5 HOUR, NULL, NULL, NULL, 'PENDING', NULL, NULL, 0, NULL, NULL, NULL, NULL, 3, '李巡检');

-- ------------------------------------------------------------
-- 4. 匿名异常人员（3 人已匹配真实账号，2 人重点关注）
-- ------------------------------------------------------------
INSERT INTO `dm_anonymous_person` (`person_id`, `appearance_desc`, `first_seen_at`, `last_seen_at`, `is_focused`, `risk_level_id`, `matched_user_id`, `match_confidence`) VALUES
(2001, '蓝色工装，男性，中等身材，背黑色双肩包', NOW() - INTERVAL 6 HOUR,  NOW() - INTERVAL 5 MINUTE,  0, NULL, 6, 0.9234),
(2002, '深蓝色保安制服，男性，佩戴工牌',         NOW() - INTERVAL 8 HOUR,  NOW() - INTERVAL 7 MINUTE,  0, NULL, 2, 0.8871),
(2003, '灰色夹克，男性，手提公文包',             NOW() - INTERVAL 9 HOUR,  NOW() - INTERVAL 2 MINUTE,  0, NULL, 5, 0.9522),
(2004, '黑色连帽衫，戴口罩，男性，身形偏瘦',     NOW() - INTERVAL 5 HOUR,  NOW() - INTERVAL 3 MINUTE,  1, 1,    NULL, NULL),
(2005, '白色T恤，女性，马尾，携带帆布袋',        NOW() - INTERVAL 8 HOUR,  NOW() - INTERVAL 117 MINUTE, 0, NULL, NULL, NULL),
(2006, '红色外卖制服，男性，骑电动车',           NOW() - INTERVAL 450 MINUTE, NOW() - INTERVAL 90 MINUTE, 0, NULL, NULL, NULL),
(2007, '橙色反光背心，男性，安全帽未系带',       NOW() - INTERVAL 4 HOUR,  NOW() - INTERVAL 2 MINUTE,  1, 2,    NULL, NULL),
(2008, '深绿色工作服，男性，手提工具箱',         NOW() - INTERVAL 432 MINUTE, NOW() - INTERVAL 90 MINUTE, 0, NULL, NULL, NULL),
(2009, '黑色西装，男性，未佩戴任何证件',         NOW() - INTERVAL 402 MINUTE, NOW() - INTERVAL 58 MINUTE, 0, 2,    NULL, NULL),
(2010, '浅蓝色衬衫，男性，戴眼镜',               NOW() - INTERVAL 372 MINUTE, NOW() - INTERVAL 357 MINUTE, 0, NULL, NULL, NULL),
(2011, '碎花连衣裙，女性，老年，行动缓慢',       NOW() - INTERVAL 312 MINUTE, NOW() - INTERVAL 300 MINUTE, 0, 3,    NULL, NULL),
(2012, '黄色骑行服，男性，骑非机动车',           NOW() - INTERVAL 282 MINUTE, NOW() - INTERVAL 267 MINUTE, 0, NULL, NULL, NULL);

-- ------------------------------------------------------------
-- 5. 轨迹链路主表（chain_status：1=行进中 2=已归档）
--    3001-3005 行进中（end_time 为 NULL）；3006-3020 已归档
--    情景覆盖：3006 单摄像头 / 3007 顺向 / 3008 折返
-- ------------------------------------------------------------
INSERT INTO `track_pass_chain` (`id`, `chain_unique_id`, `person_id`, `confidence`, `device_route`, `first_device_id`, `last_device_id`, `chain_start_time`, `chain_end_time`, `total_duration_sec`, `chain_status`) VALUES
(3001, 'CHAIN-20260728-001', 2001, 0.9234, '1001-1010',        1001, 1010, NOW() - INTERVAL 8 MINUTE,   NULL, 0,   1),
(3002, 'CHAIN-20260728-002', 2004, 0.8712, '1008',             1008, 1008, NOW() - INTERVAL 3 MINUTE,   NULL, 0,   1),
(3003, 'CHAIN-20260728-003', 2002, 0.8871, '1004-1005-1006',   1004, 1006, NOW() - INTERVAL 15 MINUTE,  NULL, 0,   1),
(3004, 'CHAIN-20260728-004', 2007, 0.8540, '1013-1014',        1013, 1014, NOW() - INTERVAL 5 MINUTE,   NULL, 0,   1),
(3005, 'CHAIN-20260728-005', 2003, 0.9522, '1001',             1001, 1001, NOW() - INTERVAL 2 MINUTE,   NULL, 0,   1),
(3006, 'CHAIN-20260728-006', 2005, 0.9011, '1001',             1001, 1001, NOW() - INTERVAL 480 MINUTE, NOW() - INTERVAL 478 MINUTE, 120, 2),
(3007, 'CHAIN-20260728-007', 2006, 0.8830, '1001-1002-1003',   1001, 1003, NOW() - INTERVAL 460 MINUTE, NOW() - INTERVAL 447 MINUTE, 780, 2),
(3008, 'CHAIN-20260728-008', 2008, 0.8675, '1001-1003-1002',   1001, 1002, NOW() - INTERVAL 430 MINUTE, NOW() - INTERVAL 417 MINUTE, 780, 2),
(3009, 'CHAIN-20260728-009', 2009, 0.9120, '1001-1010-1004',   1001, 1004, NOW() - INTERVAL 400 MINUTE, NOW() - INTERVAL 384 MINUTE, 960, 2),
(3010, 'CHAIN-20260728-010', 2010, 0.8950, '1004-1006-1007',   1004, 1007, NOW() - INTERVAL 370 MINUTE, NOW() - INTERVAL 357 MINUTE, 780, 2),
(3011, 'CHAIN-20260728-011', 2001, 0.9201, '1008-1010-1013',   1008, 1013, NOW() - INTERVAL 340 MINUTE, NOW() - INTERVAL 327 MINUTE, 780, 2),
(3012, 'CHAIN-20260728-012', 2011, 0.8460, '1017-1018',        1017, 1018, NOW() - INTERVAL 310 MINUTE, NOW() - INTERVAL 300 MINUTE, 600, 2),
(3013, 'CHAIN-20260728-013', 2012, 0.8770, '1019-1020-1009',   1019, 1009, NOW() - INTERVAL 280 MINUTE, NOW() - INTERVAL 267 MINUTE, 780, 2),
(3014, 'CHAIN-20260728-014', 2004, 0.9405, '1023-1008-1010',   1023, 1010, NOW() - INTERVAL 250 MINUTE, NOW() - INTERVAL 237 MINUTE, 780, 2),
(3015, 'CHAIN-20260728-015', 2007, 0.8620, '1014-1016',        1014, 1016, NOW() - INTERVAL 220 MINUTE, NOW() - INTERVAL 208 MINUTE, 720, 2),
(3016, 'CHAIN-20260728-016', 2003, 0.9480, '1001-1017',        1001, 1017, NOW() - INTERVAL 190 MINUTE, NOW() - INTERVAL 180 MINUTE, 600, 2),
(3017, 'CHAIN-20260728-017', 2002, 0.8790, '1004-1005',        1004, 1005, NOW() - INTERVAL 160 MINUTE, NOW() - INTERVAL 150 MINUTE, 600, 2),
(3018, 'CHAIN-20260728-018', 2005, 0.8930, '1010-1011-1012',   1010, 1012, NOW() - INTERVAL 130 MINUTE, NOW() - INTERVAL 117 MINUTE, 780, 2),
(3019, 'CHAIN-20260728-019', 2008, 0.8560, '1002-1003',        1002, 1003, NOW() - INTERVAL 100 MINUTE, NOW() - INTERVAL 90 MINUTE,  600, 2),
(3020, 'CHAIN-20260728-020', 2009, 0.9050, '1013-1014-1015',   1013, 1015, NOW() - INTERVAL 70 MINUTE,  NOW() - INTERVAL 57 MINUTE,  780, 2);

-- ------------------------------------------------------------
-- 6. 途经摄像头明细（sort 与 device_route 分段严格对应）
-- ------------------------------------------------------------
INSERT INTO `track_pass_item` (`chain_id`, `device_id`, `sort`, `appear_time`, `disappear_time`, `stay_duration_sec`) VALUES
-- 行进中链路（末条明细 disappear_time 为 NULL）
(3001, 1001, 1, NOW() - INTERVAL 8 MINUTE,   NOW() - INTERVAL 6 MINUTE,   120),
(3001, 1010, 2, NOW() - INTERVAL 5 MINUTE,   NULL,                        0),
(3002, 1008, 1, NOW() - INTERVAL 3 MINUTE,   NULL,                        0),
(3003, 1004, 1, NOW() - INTERVAL 15 MINUTE,  NOW() - INTERVAL 12 MINUTE,  180),
(3003, 1005, 2, NOW() - INTERVAL 11 MINUTE,  NOW() - INTERVAL 8 MINUTE,   180),
(3003, 1006, 3, NOW() - INTERVAL 7 MINUTE,   NULL,                        0),
(3004, 1013, 1, NOW() - INTERVAL 5 MINUTE,   NOW() - INTERVAL 3 MINUTE,   120),
(3004, 1014, 2, NOW() - INTERVAL 2 MINUTE,   NULL,                        0),
(3005, 1001, 1, NOW() - INTERVAL 2 MINUTE,   NULL,                        0),
-- 3006 情景1：单摄像头出现后离开
(3006, 1001, 1, NOW() - INTERVAL 480 MINUTE, NOW() - INTERVAL 478 MINUTE, 120),
-- 3007 情景2：顺向 1001-1002-1003
(3007, 1001, 1, NOW() - INTERVAL 460 MINUTE, NOW() - INTERVAL 457 MINUTE, 180),
(3007, 1002, 2, NOW() - INTERVAL 455 MINUTE, NOW() - INTERVAL 452 MINUTE, 180),
(3007, 1003, 3, NOW() - INTERVAL 450 MINUTE, NOW() - INTERVAL 447 MINUTE, 180),
-- 3008 情景3：折返 1001-1003-1002
(3008, 1001, 1, NOW() - INTERVAL 430 MINUTE, NOW() - INTERVAL 427 MINUTE, 180),
(3008, 1003, 2, NOW() - INTERVAL 425 MINUTE, NOW() - INTERVAL 422 MINUTE, 180),
(3008, 1002, 3, NOW() - INTERVAL 420 MINUTE, NOW() - INTERVAL 417 MINUTE, 180),
-- 3009-3020 常规多摄像头归档链路
(3009, 1001, 1, NOW() - INTERVAL 400 MINUTE, NOW() - INTERVAL 397 MINUTE, 180),
(3009, 1010, 2, NOW() - INTERVAL 394 MINUTE, NOW() - INTERVAL 390 MINUTE, 240),
(3009, 1004, 3, NOW() - INTERVAL 388 MINUTE, NOW() - INTERVAL 384 MINUTE, 240),
(3010, 1004, 1, NOW() - INTERVAL 370 MINUTE, NOW() - INTERVAL 367 MINUTE, 180),
(3010, 1006, 2, NOW() - INTERVAL 365 MINUTE, NOW() - INTERVAL 362 MINUTE, 180),
(3010, 1007, 3, NOW() - INTERVAL 360 MINUTE, NOW() - INTERVAL 357 MINUTE, 180),
(3011, 1008, 1, NOW() - INTERVAL 340 MINUTE, NOW() - INTERVAL 337 MINUTE, 180),
(3011, 1010, 2, NOW() - INTERVAL 335 MINUTE, NOW() - INTERVAL 332 MINUTE, 180),
(3011, 1013, 3, NOW() - INTERVAL 330 MINUTE, NOW() - INTERVAL 327 MINUTE, 180),
(3012, 1017, 1, NOW() - INTERVAL 310 MINUTE, NOW() - INTERVAL 306 MINUTE, 240),
(3012, 1018, 2, NOW() - INTERVAL 304 MINUTE, NOW() - INTERVAL 300 MINUTE, 240),
(3013, 1019, 1, NOW() - INTERVAL 280 MINUTE, NOW() - INTERVAL 277 MINUTE, 180),
(3013, 1020, 2, NOW() - INTERVAL 275 MINUTE, NOW() - INTERVAL 272 MINUTE, 180),
(3013, 1009, 3, NOW() - INTERVAL 270 MINUTE, NOW() - INTERVAL 267 MINUTE, 180),
(3014, 1023, 1, NOW() - INTERVAL 250 MINUTE, NOW() - INTERVAL 247 MINUTE, 180),
(3014, 1008, 2, NOW() - INTERVAL 245 MINUTE, NOW() - INTERVAL 242 MINUTE, 180),
(3014, 1010, 3, NOW() - INTERVAL 240 MINUTE, NOW() - INTERVAL 237 MINUTE, 180),
(3015, 1014, 1, NOW() - INTERVAL 220 MINUTE, NOW() - INTERVAL 215 MINUTE, 300),
(3015, 1016, 2, NOW() - INTERVAL 213 MINUTE, NOW() - INTERVAL 208 MINUTE, 300),
(3016, 1001, 1, NOW() - INTERVAL 190 MINUTE, NOW() - INTERVAL 186 MINUTE, 240),
(3016, 1017, 2, NOW() - INTERVAL 184 MINUTE, NOW() - INTERVAL 180 MINUTE, 240),
(3017, 1004, 1, NOW() - INTERVAL 160 MINUTE, NOW() - INTERVAL 156 MINUTE, 240),
(3017, 1005, 2, NOW() - INTERVAL 154 MINUTE, NOW() - INTERVAL 150 MINUTE, 240),
(3018, 1010, 1, NOW() - INTERVAL 130 MINUTE, NOW() - INTERVAL 127 MINUTE, 180),
(3018, 1011, 2, NOW() - INTERVAL 125 MINUTE, NOW() - INTERVAL 122 MINUTE, 180),
(3018, 1012, 3, NOW() - INTERVAL 120 MINUTE, NOW() - INTERVAL 117 MINUTE, 180),
(3019, 1002, 1, NOW() - INTERVAL 100 MINUTE, NOW() - INTERVAL 96 MINUTE,  240),
(3019, 1003, 2, NOW() - INTERVAL 94 MINUTE,  NOW() - INTERVAL 90 MINUTE,  240),
(3020, 1013, 1, NOW() - INTERVAL 70 MINUTE,  NOW() - INTERVAL 67 MINUTE,  180),
(3020, 1014, 2, NOW() - INTERVAL 65 MINUTE,  NOW() - INTERVAL 62 MINUTE,  180),
(3020, 1015, 3, NOW() - INTERVAL 60 MINUTE,  NOW() - INTERVAL 57 MINUTE,  180);

-- ------------------------------------------------------------
-- 7. 异常行为类型（10 种，带默认严重程度）
-- ------------------------------------------------------------
INSERT INTO `dm_behavior_type` (`behavior_type_id`, `type_name`, `default_severity_level_id`, `description`, `is_enabled`) VALUES
(1,  '跌倒',           1, '人员意外倒地，需紧急关注',           1),
(2,  '打架斗殴',       1, '两人及以上肢体冲突',                 1),
(3,  '闯入禁行区域',   1, '人员进入周界/仓储等禁行区域',        1),
(4,  '人员聚集',       2, '同一区域人员数量超过阈值',           1),
(5,  '徘徊滞留',       2, '人员在敏感区域长时间徘徊',           1),
(6,  '非机动车逆行',   2, '非机动车在单行路段逆向行驶',         1),
(7,  '消防通道占用',   3, '消防通道被人员或物品占用',           1),
(8,  '烟火检测',       1, '检测到明火或烟雾',                   1),
(9,  '未佩戴护具',     2, '车间人员未按规范佩戴安全帽/护具',    1),
(10, '周界越界',       2, '人员越过园区周界警戒线',             1);

-- ------------------------------------------------------------
-- 8. 异常行为记录（4001-4012 待确认，对应预警 12 条待办）
--    状态分布：12 待确认 / 4 已确认 / 2 已派单 / 2 处理中 / 2 已处理 / 2 已忽略
-- ------------------------------------------------------------
INSERT INTO `fa_abnormal_behavior` (`behavior_id`, `behavior_type_id`, `person_id`, `track_id`, `severity_level_id`, `alert_status_id`, `detected_at`, `camera_id`, `confidence_score`, `description`) VALUES
(4001, 3,  2004, 3014, 1, 1, NOW() - INTERVAL 245 MINUTE, 1023, 0.9512, '黑衣男子翻越东侧围墙进入园区'),
(4002, 5,  2010, 3010, 2, 1, NOW() - INTERVAL 365 MINUTE, 1004, 0.8730, '男子在研发楼大厅徘徊超过5分钟'),
(4003, 6,  2012, 3013, 2, 1, NOW() - INTERVAL 272 MINUTE, 1009, 0.9105, '非机动车在西侧路口逆向行驶'),
(4004, 7,  2007, 3015, 3, 1, NOW() - INTERVAL 210 MINUTE, 1016, 0.8841, '车间北侧消防通道被人员长时间占用'),
(4005, 1,  2011, 3012, 1, 1, NOW() - INTERVAL 305 MINUTE, 1017, 0.9602, '老年女性在办公楼大厅突然倒地'),
(4006, 4,  2009, 3009, 2, 1, NOW() - INTERVAL 398 MINUTE, 1001, 0.8522, '南门入口短时间内聚集人数超阈值'),
(4007, 2,  2009, 3020, 1, 1, NOW() - INTERVAL 60 MINUTE,  1015, 0.9310, '车间C区两人发生肢体冲突'),
(4008, 9,  2007, 3004, 2, 1, NOW() - INTERVAL 4 MINUTE,   1013, 0.9020, '车间A区人员安全帽未系带'),
(4009, 10, 2005, 3018, 2, 1, NOW() - INTERVAL 118 MINUTE, 1012, 0.8775, '人员越过北门警戒线'),
(4010, 8,  2009, 3020, 1, 1, NOW() - INTERVAL 58 MINUTE,  1015, 0.9660, '车间C区检测到疑似烟雾'),
(4011, 3,  2008, 3019, 1, 1, NOW() - INTERVAL 92 MINUTE,  1003, 0.9450, '人员进入仓储区限制通道'),
(4012, 5,  2002, 3017, 2, 1, NOW() - INTERVAL 152 MINUTE, 1005, 0.8380, '人员在研发楼二层走廊长时间滞留'),
(4013, 5,  2002, NULL, 2, 2, NOW() - INTERVAL 600 MINUTE, 1004, 0.8650, '大厅滞留事件，确认为访客等候'),
(4014, 6,  2012, NULL, 2, 2, NOW() - INTERVAL 900 MINUTE, 1009, 0.8980, '路口逆行事件，已电话警告'),
(4015, 3,  2004, NULL, 1, 3, NOW() - INTERVAL 200 MINUTE, 1001, 0.9380, '南门仓储区闯入，确认为真实告警'),
(4016, 7,  2007, NULL, 3, 3, NOW() - INTERVAL 320 MINUTE, 1016, 0.8710, '消防通道堆放货物'),
(4017, 4,  2009, NULL, 2, 4, NOW() - INTERVAL 400 MINUTE, 1019, 0.8600, '停车场聚集纠纷，巡检已到场'),
(4018, 9,  2007, NULL, 2, 4, NOW() - INTERVAL 260 MINUTE, 1014, 0.8930, '车间B区护具佩戴不规范，现场纠正中'),
(4019, 1,  2011, NULL, 1, 5, NOW() - INTERVAL 500 MINUTE, 1017, 0.9550, '保洁人员滑倒，已协助就医'),
(4020, 10, 2004, NULL, 2, 5, NOW() - INTERVAL 700 MINUTE, 1023, 0.9420, '施工人员越界作业，已劝离'),
(4021, 5,  2002, NULL, 2, 6, NOW() - INTERVAL 800 MINUTE, 1005, 0.7620, '误报：保安正常巡楼'),
(4022, 4,  2005, NULL, 2, 6, NOW() - INTERVAL 1000 MINUTE, 1011, 0.7410, '误报：班车集中上下客'),
(4023, 6,  2012, NULL, 2, 2, NOW() - INTERVAL 1100 MINUTE, 1012, 0.8870, '北门逆行，已现场教育'),
(4024, 7,  2007, NULL, 3, 2, NOW() - INTERVAL 1200 MINUTE, 1016, 0.8560, '临时货物占用，已清理');

-- ------------------------------------------------------------
-- 9. 行为预警（与异常行为一对一，状态与行为表保持同步）
-- ------------------------------------------------------------
INSERT INTO `fa_behavior_alert` (`alert_id`, `behavior_id`, `severity_level_id`, `alert_status_id`, `alert_time`, `notify_method`, `confirmed_at`, `confirmed_by`, `is_marked_focus`, `resolved_at`) VALUES
(5001, 4001, 1, 1, NOW() - INTERVAL 244 MINUTE, 'POPUP,SOUND_LIGHT', NULL, NULL, 1, NULL),
(5002, 4002, 2, 1, NOW() - INTERVAL 364 MINUTE, 'POPUP',             NULL, NULL, 0, NULL),
(5003, 4003, 2, 1, NOW() - INTERVAL 271 MINUTE, 'POPUP',             NULL, NULL, 0, NULL),
(5004, 4004, 3, 1, NOW() - INTERVAL 209 MINUTE, 'POPUP',             NULL, NULL, 0, NULL),
(5005, 4005, 1, 1, NOW() - INTERVAL 304 MINUTE, 'POPUP,SOUND_LIGHT,PUSH', NULL, NULL, 0, NULL),
(5006, 4006, 2, 1, NOW() - INTERVAL 397 MINUTE, 'POPUP',             NULL, NULL, 0, NULL),
(5007, 4007, 1, 1, NOW() - INTERVAL 59 MINUTE,  'POPUP,SOUND_LIGHT', NULL, NULL, 0, NULL),
(5008, 4008, 2, 1, NOW() - INTERVAL 3 MINUTE,   'POPUP',             NULL, NULL, 0, NULL),
(5009, 4009, 2, 1, NOW() - INTERVAL 117 MINUTE, 'POPUP,PUSH',        NULL, NULL, 0, NULL),
(5010, 4010, 1, 1, NOW() - INTERVAL 57 MINUTE,  'POPUP,SOUND_LIGHT,PUSH', NULL, NULL, 1, NULL),
(5011, 4011, 1, 1, NOW() - INTERVAL 91 MINUTE,  'POPUP,SOUND_LIGHT', NULL, NULL, 0, NULL),
(5012, 4012, 2, 1, NOW() - INTERVAL 151 MINUTE, 'POPUP',             NULL, NULL, 0, NULL),
(5013, 4013, 2, 2, NOW() - INTERVAL 599 MINUTE, 'POPUP', NOW() - INTERVAL 595 MINUTE, 2, 0, NULL),
(5014, 4014, 2, 2, NOW() - INTERVAL 899 MINUTE, 'POPUP', NOW() - INTERVAL 890 MINUTE, 2, 0, NULL),
(5015, 4015, 1, 3, NOW() - INTERVAL 199 MINUTE, 'POPUP,SOUND_LIGHT', NOW() - INTERVAL 195 MINUTE, 2, 1, NULL),
(5016, 4016, 3, 3, NOW() - INTERVAL 319 MINUTE, 'POPUP', NOW() - INTERVAL 312 MINUTE, 2, 0, NULL),
(5017, 4017, 2, 4, NOW() - INTERVAL 399 MINUTE, 'POPUP', NOW() - INTERVAL 392 MINUTE, 2, 0, NULL),
(5018, 4018, 2, 4, NOW() - INTERVAL 259 MINUTE, 'POPUP', NOW() - INTERVAL 252 MINUTE, 2, 0, NULL),
(5019, 4019, 1, 5, NOW() - INTERVAL 499 MINUTE, 'POPUP,SOUND_LIGHT,PUSH', NOW() - INTERVAL 490 MINUTE, 2, 0, NOW() - INTERVAL 440 MINUTE),
(5020, 4020, 2, 5, NOW() - INTERVAL 699 MINUTE, 'POPUP,PUSH', NOW() - INTERVAL 692 MINUTE, 2, 0, NOW() - INTERVAL 640 MINUTE),
(5021, 4021, 2, 6, NOW() - INTERVAL 799 MINUTE, 'POPUP', NOW() - INTERVAL 790 MINUTE, 2, 0, NOW() - INTERVAL 790 MINUTE),
(5022, 4022, 2, 6, NOW() - INTERVAL 999 MINUTE, 'POPUP', NOW() - INTERVAL 990 MINUTE, 2, 0, NOW() - INTERVAL 990 MINUTE),
(5023, 4023, 2, 2, NOW() - INTERVAL 1099 MINUTE, 'POPUP', NOW() - INTERVAL 1090 MINUTE, 3, 0, NULL),
(5024, 4024, 3, 2, NOW() - INTERVAL 1199 MINUTE, 'POPUP', NOW() - INTERVAL 1190 MINUTE, 3, 0, NULL);

-- ------------------------------------------------------------
-- 10. 处置工单（与预警状态闭环一致：已派单→待处理，处理中→处理中，已处理→已完成/已关闭）
-- ------------------------------------------------------------
INSERT INTO `fa_work_order` (`work_order_id`, `work_order_no`, `alert_id`, `behavior_id`, `work_order_status_id`, `assigned_to`, `handler_role`, `assigned_by`, `assigned_at`, `handled_at`, `handle_result`, `handle_duration_minutes`) VALUES
(6001, 'WO202607280001', 5015, 4015, 1, 3, 'GUARD', 2, NOW() - INTERVAL 190 MINUTE, NULL, NULL, NULL),
(6002, 'WO202607280002', 5016, 4016, 1, 8, 'GUARD', 2, NOW() - INTERVAL 308 MINUTE, NULL, NULL, NULL),
(6003, 'WO202607280003', 5017, 4017, 2, 3, 'GUARD', 2, NOW() - INTERVAL 385 MINUTE, NULL, NULL, NULL),
(6004, 'WO202607280004', 5018, 4018, 2, 8, 'GUARD', 1, NOW() - INTERVAL 245 MINUTE, NULL, NULL, NULL),
(6005, 'WO202607280005', 5019, 4019, 3, 3, 'GUARD', 2, NOW() - INTERVAL 480 MINUTE, NOW() - INTERVAL 440 MINUTE, '现场核实为保洁人员滑倒，已协助就医并清理地面水渍，现场恢复正常', 40),
(6006, 'WO202607280006', 5020, 4020, 4, 3, 'GUARD', 2, NOW() - INTERVAL 680 MINUTE, NOW() - INTERVAL 640 MINUTE, '确认为施工队越界作业，已劝离并补办临时通行手续，工单归档', 40);

-- ------------------------------------------------------------
-- 11. 操作日志（target_type：BEHAVIOR/USER/BACKUP/DEVICE/TRACK）
-- ------------------------------------------------------------
INSERT INTO `fa_operation_log` (`log_id`, `module_code`, `operation_type`, `operator_id`, `operator_role`, `target_id`, `target_type`, `operation_content`, `ip_address`, `operated_at`) VALUES
(7001, 'ABNORMAL_BEHAVIOR', 'QUERY',  1, 'SUPER_ADMIN',   NULL, NULL, '{"keyword":"闯入","time_range":"today"}', '192.168.1.20', NOW() - INTERVAL 20 MINUTE),
(7002, 'ABNORMAL_BEHAVIOR', 'QUERY',  2, 'SECURITY_LEAD', NULL, NULL, '{"status":1,"severity":1}', '192.168.1.36', NOW() - INTERVAL 35 MINUTE),
(7003, 'ABNORMAL_BEHAVIOR', 'UPDATE', 2, 'SECURITY_LEAD', 4015, 'BEHAVIOR', '{"action":"confirm_alert","alert_id":5015}', '192.168.1.36', NOW() - INTERVAL 195 MINUTE),
(7004, 'ABNORMAL_BEHAVIOR', 'UPDATE', 2, 'SECURITY_LEAD', 5015, 'BEHAVIOR', '{"action":"assign","work_order_no":"WO202607280001","assigned_to":3}', '192.168.1.36', NOW() - INTERVAL 190 MINUTE),
(7005, 'ABNORMAL_BEHAVIOR', 'UPDATE', 1, 'SUPER_ADMIN',   5018, 'BEHAVIOR', '{"action":"assign","work_order_no":"WO202607280004","assigned_to":8}', '192.168.1.20', NOW() - INTERVAL 245 MINUTE),
(7006, 'ABNORMAL_BEHAVIOR', 'UPDATE', 2, 'SECURITY_LEAD', 4019, 'BEHAVIOR', '{"action":"confirm_alert","alert_id":5019}', '192.168.1.36', NOW() - INTERVAL 490 MINUTE),
(7007, 'ABNORMAL_BEHAVIOR', 'UPDATE', 3, 'GUARD',         6005, 'BEHAVIOR', '{"action":"resolve","work_order_no":"WO202607280005"}', '192.168.1.42', NOW() - INTERVAL 440 MINUTE),
(7008, 'ABNORMAL_BEHAVIOR', 'UPDATE', 3, 'GUARD',         6006, 'BEHAVIOR', '{"action":"archive","work_order_no":"WO202607280006"}', '192.168.1.42', NOW() - INTERVAL 638 MINUTE),
(7009, 'ABNORMAL_BEHAVIOR', 'UPDATE', 2, 'SECURITY_LEAD', 4021, 'BEHAVIOR', '{"action":"ignore","alert_id":5021,"note":"保安正常巡楼"}', '192.168.1.36', NOW() - INTERVAL 790 MINUTE),
(7010, 'ABNORMAL_BEHAVIOR', 'UPDATE', 2, 'SECURITY_LEAD', 4022, 'BEHAVIOR', '{"action":"ignore","alert_id":5022,"note":"班车上下客"}', '192.168.1.36', NOW() - INTERVAL 990 MINUTE),
(7011, 'ABNORMAL_BEHAVIOR', 'UPDATE', 3, 'GUARD',         4023, 'BEHAVIOR', '{"action":"confirm_alert","alert_id":5023}', '192.168.1.42', NOW() - INTERVAL 1090 MINUTE),
(7012, 'ABNORMAL_BEHAVIOR', 'UPDATE', 3, 'GUARD',         4024, 'BEHAVIOR', '{"action":"confirm_alert","alert_id":5024}', '192.168.1.42', NOW() - INTERVAL 1190 MINUTE),
(7013, 'ABNORMAL_BEHAVIOR', 'EXPORT', 7, 'AUDITOR',       NULL, NULL, '{"time_range":"2026-07-01~2026-07-28","format":"csv"}', '192.168.1.55', NOW() - INTERVAL 90 MINUTE),
(7014, 'ABNORMAL_BEHAVIOR', 'QUERY',  7, 'AUDITOR',       NULL, NULL, '{"severity":1,"time_range":"month"}', '192.168.1.55', NOW() - INTERVAL 100 MINUTE),
(7015, 'ABNORMAL_BEHAVIOR', 'QUERY',  4, 'COUNSELOR',     2011, 'USER', '{"person_id":2011,"view":"behavior_history"}', '192.168.1.60', NOW() - INTERVAL 1 DAY),
(7016, 'TRACK',            'QUERY',  3, 'GUARD',         3014, 'TRACK', '{"chain_unique_id":"CHAIN-20260728-014","action":"replay"}', '192.168.1.42', NOW() - INTERVAL 50 MINUTE),
(7017, 'TRACK',            'QUERY',  2, 'SECURITY_LEAD', NULL, NULL, '{"time_range":"today","status":2}', '192.168.1.36', NOW() - INTERVAL 70 MINUTE),
(7018, 'TRACK',            'QUERY',  8, 'GUARD',         3001, 'TRACK', '{"chain_unique_id":"CHAIN-20260728-001"}', '192.168.1.48', NOW() - INTERVAL 6 MINUTE),
(7019, 'TRACK',            'EXPORT', 7, 'AUDITOR',       NULL, NULL, '{"person_id":2004,"format":"csv"}', '192.168.1.55', NOW() - INTERVAL 130 MINUTE),
(7020, 'TRACK',            'QUERY',  1, 'SUPER_ADMIN',   NULL, NULL, '{"device_id":1001,"time_range":"today"}', '192.168.1.20', NOW() - INTERVAL 200 MINUTE),
(7021, 'DEVICE',           'QUERY',  3, 'GUARD',         1022, 'DEVICE', '{"device_code":"CAM-022"}', '192.168.1.42', NOW() - INTERVAL 38 MINUTE),
(7022, 'DEVICE',           'UPDATE', 1, 'SUPER_ADMIN',   1024, 'DEVICE', '{"action":"disable","device_code":"CAM-024","reason":"防护罩破损停用"}', '192.168.1.20', NOW() - INTERVAL 288 MINUTE),
(7023, 'DEVICE',           'UPDATE', 1, 'SUPER_ADMIN',   9002, 'DEVICE', '{"action":"assign_fault","fault_id":9002,"assigned_to":8}', '192.168.1.20', NOW() - INTERVAL 1320 MINUTE),
(7024, 'DEVICE',           'UPDATE', 1, 'SUPER_ADMIN',   1102, 'DEVICE', '{"action":"register","device_code":"EDGE-001"}', '192.168.1.20', NOW() - INTERVAL 60 DAY),
(7025, 'DEVICE',           'QUERY',  2, 'SECURITY_LEAD', NULL, NULL, '{"status":"FAULT"}', '192.168.1.36', NOW() - INTERVAL 42 MINUTE),
(7026, 'USER_PROFILE',     'QUERY',  4, 'COUNSELOR',     2007, 'USER', '{"person_id":2007,"view":"profile"}', '192.168.1.60', NOW() - INTERVAL 2 DAY),
(7027, 'USER_PROFILE',     'UPDATE', 1, 'SUPER_ADMIN',   2004, 'USER', '{"action":"mark_focused","person_id":2004}', '192.168.1.20', NOW() - INTERVAL 4 HOUR),
(7028, 'USER_PROFILE',     'UPDATE', 1, 'SUPER_ADMIN',   2007, 'USER', '{"action":"mark_focused","person_id":2007}', '192.168.1.20', NOW() - INTERVAL 210 MINUTE),
(7029, 'USER_PROFILE',     'QUERY',  5, 'SUPERVISOR',    NULL, NULL, '{"dept":"生产一部"}', '192.168.1.62', NOW() - INTERVAL 3 HOUR),
(7030, 'SYSTEM',           'UPDATE', 1, 'SUPER_ADMIN',   8,    'USER', '{"action":"create_account","login_name":"zhangxun"}', '192.168.1.20', NOW() - INTERVAL 5 DAY),
(7031, 'SYSTEM',           'UPDATE', 1, 'SUPER_ADMIN',   8,    'USER', '{"action":"custom_permission","account_id":8,"perm_ids":[2,6,21]}', '192.168.1.20', NOW() - INTERVAL 5 DAY + INTERVAL 10 MINUTE),
(7032, 'SYSTEM',           'UPDATE', 1, 'SUPER_ADMIN',   9,    'USER', '{"action":"disable_account","login_name":"disabled"}', '192.168.1.20', NOW() - INTERVAL 2 DAY),
(7033, 'SYSTEM',           'UPDATE', 1, 'SUPER_ADMIN',   3,    'USER', '{"action":"update_role_permission","type_id":3,"perm_count":10}', '192.168.1.20', NOW() - INTERVAL 6 DAY),
(7034, 'SYSTEM',           'QUERY',  7, 'AUDITOR',       NULL, NULL, '{"view":"account_list"}', '192.168.1.55', NOW() - INTERVAL 312 MINUTE),
(7035, 'BACKUP_RESTORE',   'BACKUP', 1, 'SUPER_ADMIN',   NULL, 'BACKUP', '{"backup_type":"FULL","note":"全量备份"}', '192.168.1.20', NOW() - INTERVAL 1 DAY),
(7036, 'BACKUP_RESTORE',   'BACKUP', 1, 'SUPER_ADMIN',   NULL, 'BACKUP', '{"backup_type":"INCREMENTAL"}', '192.168.1.20', NOW() - INTERVAL 12 HOUR),
(7037, 'BACKUP_RESTORE',   'QUERY',  7, 'AUDITOR',       NULL, 'BACKUP', '{"view":"backup_history"}', '192.168.1.55', NOW() - INTERVAL 306 MINUTE),
(7038, 'ABNORMAL_BEHAVIOR', 'QUERY',  3, 'GUARD',         NULL, NULL, '{"status":1}', '192.168.1.42', NOW() - INTERVAL 15 MINUTE),
(7039, 'TRACK',            'QUERY',  6, 'EMPLOYEE',      NULL, NULL, '{"scope":"self_only"}', '192.168.1.70', NOW() - INTERVAL 2 DAY),
(7040, 'ABNORMAL_BEHAVIOR', 'EXPORT', 2, 'SECURITY_LEAD', NULL, NULL, '{"status":5,"time_range":"week","format":"xlsx"}', '192.168.1.36', NOW() - INTERVAL 1 DAY);

-- ------------------------------------------------------------
-- 12. 统一将本脚本预置的演示业务数据标记为模拟数据（is_lab = 1）
--     说明：角标与业务列表默认按 is_lab = 0 过滤（前端【过滤模拟数据】开关默认开启），
--     标记后新环境告警待办角标只统计真实未处理告警，不再显示预置的 12 条测试预警；
--     如需查看演示数据，关闭顶部【过滤模拟数据】开关即可（手动调试开关）。
--     前置要求：业务表已含 is_lab 字段（SQLAlchemy create_all 建表自带，
--     或已执行 backend/scripts/init_is_lab.sql）。
-- ------------------------------------------------------------
UPDATE `dm_anonymous_person` SET `is_lab` = 1 WHERE `person_id` BETWEEN 2001 AND 2012;
UPDATE `track_pass_chain`    SET `is_lab` = 1 WHERE `id` BETWEEN 3001 AND 3020;
UPDATE `fa_abnormal_behavior` SET `is_lab` = 1 WHERE `behavior_id` BETWEEN 4001 AND 4024;
UPDATE `fa_behavior_alert`   SET `is_lab` = 1 WHERE `alert_id` BETWEEN 5001 AND 5024;
UPDATE `fa_work_order`       SET `is_lab` = 1 WHERE `work_order_id` BETWEEN 6001 AND 6006;

-- ============================================================
-- Mock 数据灌入完成
-- 数据规模：账号9 / 设备26 / 故障6 / 人员12 / 轨迹20链51明细
--           行为24 / 预警24(待确认12) / 工单6 / 日志40
-- 注意：以上演示业务数据已统一标记 is_lab = 1，默认被【过滤模拟数据】开关排除
-- ============================================================
