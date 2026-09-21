-- ============================================================
-- I3 调度执行引擎 · meta 库增量 DDL（I3 设计文档 §4）
-- 幂等：新表 CREATE TABLE IF NOT EXISTS；
--       加列用 INFORMATION_SCHEMA 判断 + PREPARE 动态执行
--       （MySQL 8 无 ADD COLUMN IF NOT EXISTS，重跑无副作用）
-- 内容：
--   1) t_wf_schedule 定时调度表（对齐海豚 t_ds_schedule 裁剪）
--   2) t_workflow_instance 加列 run_mode / schedule_time
--   3) t_task_instance 加列 loop_iter / delay_until
--   4) t_data_source seed 内置源库/数仓 2 条（SQL 执行器 C11 过渡数据源）
--   5) t_runtime_node seed 1.9 宿主机（SSH 执行器 C14 实测节点）
-- ============================================================

-- ---------- 1. t_wf_schedule 定时调度 ----------
CREATE TABLE IF NOT EXISTS t_wf_schedule (
  id                  BIGINT       NOT NULL AUTO_INCREMENT,
  wf_code             BIGINT       NOT NULL COMMENT '工作流 code',
  name                VARCHAR(255) NOT NULL DEFAULT '默认定时' COMMENT '定时名',
  crontab             VARCHAR(64)  NOT NULL COMMENT 'cron 表达式（6 段：秒 分 时 日 月 周，quartz ? 自动按 * 处理）',
  start_time          DATETIME     NULL COMMENT '有效起始时间（有效期外不触发）',
  end_time            DATETIME     NULL COMMENT '有效结束时间',
  state               VARCHAR(16)  NOT NULL DEFAULT 'offline' COMMENT 'online/offline',
  priority            INT          NOT NULL DEFAULT 3 COMMENT '任务优先级 1~5（映射三档任务流）',
  worker_group        VARCHAR(64)  NULL COMMENT 'worker 分组（I7 多分组调度）',
  fail_retry_times    INT          NOT NULL DEFAULT 0 COMMENT '失败重试次数（该实例任务缺省）',
  fail_retry_interval INT          NOT NULL DEFAULT 60 COMMENT '失败重试间隔（秒）',
  create_time         DATETIME     NULL,
  update_time         DATETIME     NULL,
  PRIMARY KEY (id),
  KEY idx_schedule_state (state)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='工作流定时调度（对齐海豚 t_ds_schedule 裁剪）';

-- ---------- 2. t_workflow_instance 加列 ----------
SET @col_exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 't_workflow_instance' AND COLUMN_NAME = 'run_mode');
SET @ddl := IF(@col_exists = 0,
  'ALTER TABLE t_workflow_instance ADD COLUMN run_mode VARCHAR(16) NOT NULL DEFAULT ''manual'' COMMENT ''manual/schedule/complement'' AFTER command_type',
  'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @col_exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 't_workflow_instance' AND COLUMN_NAME = 'schedule_time');
SET @ddl := IF(@col_exists = 0,
  'ALTER TABLE t_workflow_instance ADD COLUMN schedule_time DATETIME NULL COMMENT ''调度/补数计划时间（内置时间变量基准）'' AFTER run_mode',
  'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ---------- 3. t_task_instance 加列 ----------
SET @col_exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 't_task_instance' AND COLUMN_NAME = 'loop_iter');
SET @ddl := IF(@col_exists = 0,
  'ALTER TABLE t_task_instance ADD COLUMN loop_iter INT NOT NULL DEFAULT 0 COMMENT ''循环迭代号（C10 Loop，每轮迭代新建行递增）'' AFTER attempt',
  'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @col_exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 't_task_instance' AND COLUMN_NAME = 'delay_until');
SET @ddl := IF(@col_exists = 0,
  'ALTER TABLE t_task_instance ADD COLUMN delay_until DATETIME NULL COMMENT ''延时到期时间（C8 Delay）'' AFTER loop_iter',
  'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ---------- 4. 内置数据源 seed（幂等；加密裁定取消 09-18，pwd 明文存储） ----------
-- 密码缺省 datara_2026；若 .env 覆盖了 MYSQL_ROOT_PASSWORD，请同步在数据源中心（I4）更新
INSERT INTO t_data_source (name, type, host, port, db_name, user, pwd, env, group_name, tags, status)
SELECT '内置源库-ec_retail', 'mysql', 'datara-mysql-src', 3306, 'ec_retail', 'root', 'datara_2026', 'dev', '内置', JSON_ARRAY('builtin'), 'unknown'
WHERE NOT EXISTS (SELECT 1 FROM (SELECT 1 FROM t_data_source WHERE name = '内置源库-ec_retail') x);

INSERT INTO t_data_source (name, type, host, port, db_name, user, pwd, env, group_name, tags, status)
SELECT '内置数仓-datara_dw', 'mysql', 'datara-mysql-dw', 3306, 'datara_dw', 'root', 'datara_2026', 'dev', '内置', JSON_ARRAY('builtin'), 'unknown'
WHERE NOT EXISTS (SELECT 1 FROM (SELECT 1 FROM t_data_source WHERE name = '内置数仓-datara_dw') x);

-- ---------- 5. 运行时节点 seed：1.9 宿主机（C14 SSH 实测节点；auth 实测前由管理员配置） ----------
-- runtime_dir/tmp_dir 用 /tmp 下路径：1.9 宿主机（TrueNAS）根文件系统只读，/datara 不可创建（09-18 实测）
INSERT INTO t_runtime_node (name, kind, host, port, user, auth, runtime_dir, tmp_dir, os, status)
SELECT '1.9宿主机', '远程', '192.168.1.9', 22, 'root', '', '/tmp/datara_runtime', '/tmp/datara_tmp', 'Linux', 'offline'
WHERE NOT EXISTS (SELECT 1 FROM (SELECT 1 FROM t_runtime_node WHERE name = '1.9宿主机') x);

-- ---------- 6. t_runtime_node.auth 加宽为 TEXT（C14 私钥内容直存，VARCHAR(255) 不足） ----------
SET @auth_type := (SELECT DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 't_runtime_node' AND COLUMN_NAME = 'auth');
SET @ddl := IF(@auth_type <> 'text',
  'ALTER TABLE t_runtime_node MODIFY COLUMN auth TEXT NULL COMMENT ''私钥内容（-----BEGIN 开头）/密码明文''',
  'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
