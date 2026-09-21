-- ============================================================
-- I10 可视化 IDE 完整版 · meta 库增量 DDL（I10 设计文档 §3）
-- 幂等：新表 CREATE TABLE IF NOT EXISTS；
--       加列/改列/加索引用 INFORMATION_SCHEMA 判断 + PREPARE 动态执行
--       （MySQL 8 无 ADD COLUMN IF NOT EXISTS，重跑无副作用）
-- 内容：
--   1) t_ide_script IDE 命名脚本新表（G16）
--   2) t_ide_history 加列 affected_total / log_text + sql_text 升 MEDIUMTEXT（G5/G21）
--   3) t_global_param 加列 env + 索引 idx_gp_env（G3，存量归 dev）
-- ============================================================

-- ---------- 1. t_ide_script IDE 命名脚本（G16） ----------
CREATE TABLE IF NOT EXISTS t_ide_script (
  id            BIGINT        NOT NULL AUTO_INCREMENT,
  user_id       INT           NOT NULL COMMENT '所属用户',
  name          VARCHAR(128)  NOT NULL COMMENT '脚本名',
  datasource_id BIGINT        NULL COMMENT '关联数据源（可空）',
  db_name       VARCHAR(128)  NULL COMMENT '关联库',
  content       MEDIUMTEXT    NULL COMMENT 'SQL 全文',
  create_time   DATETIME      NULL,
  update_time   DATETIME      NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_script (user_id, name),
  KEY idx_script_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='IDE 命名脚本（I10）';

-- ---------- 2. t_ide_history 加列（G5/G21） ----------
-- 2.1 affected_total 受影响行数合计
SET @col_exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 't_ide_history' AND COLUMN_NAME = 'affected_total');
SET @ddl := IF(@col_exists = 0,
  'ALTER TABLE t_ide_history ADD COLUMN affected_total INT NULL COMMENT ''受影响行数合计（DML/DDL 逐条累加）'' AFTER rows_total',
  'SELECT 1');
PREPARE s FROM @ddl; EXECUTE s; DEALLOCATE PREPARE s;

-- 2.2 log_text 逐条日志 JSON（语句序号/状态/耗时/错误堆栈/SHOW WARNINGS）
SET @col_exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 't_ide_history' AND COLUMN_NAME = 'log_text');
SET @ddl := IF(@col_exists = 0,
  'ALTER TABLE t_ide_history ADD COLUMN log_text MEDIUMTEXT NULL COMMENT ''逐条执行日志 JSON（I10）'' AFTER error',
  'SELECT 1');
PREPARE s FROM @ddl; EXECUTE s; DEALLOCATE PREPARE s;

-- 2.3 sql_text VARCHAR(4000) → MEDIUMTEXT（全文，I4 期为截断口径）
SET @sql_type := (SELECT DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 't_ide_history' AND COLUMN_NAME = 'sql_text');
SET @ddl := IF(@sql_type <> 'mediumtext',
  'ALTER TABLE t_ide_history MODIFY COLUMN sql_text MEDIUMTEXT NULL COMMENT ''SQL 全文''',
  'SELECT 1');
PREPARE s FROM @ddl; EXECUTE s; DEALLOCATE PREPARE s;

-- ---------- 3. t_global_param 加列 env（G3，存量归 dev） ----------
-- 3.1 env 列
SET @col_exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 't_global_param' AND COLUMN_NAME = 'env');
SET @ddl := IF(@col_exists = 0,
  'ALTER TABLE t_global_param ADD COLUMN env VARCHAR(16) NOT NULL DEFAULT ''dev'' COMMENT ''环境分组 dev/staging/prod（I10）'' AFTER type',
  'SELECT 1');
PREPARE s FROM @ddl; EXECUTE s; DEALLOCATE PREPARE s;

-- 3.2 索引 idx_gp_env (env, name)
SET @idx_exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 't_global_param' AND INDEX_NAME = 'idx_gp_env');
SET @ddl := IF(@idx_exists = 0,
  'ALTER TABLE t_global_param ADD INDEX idx_gp_env (env, name)',
  'SELECT 1');
PREPARE s FROM @ddl; EXECUTE s; DEALLOCATE PREPARE s;
