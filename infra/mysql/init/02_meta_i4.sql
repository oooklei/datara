-- ============================================================
-- I4 数据源中心 + 可视化 IDE · meta 库增量 DDL（I4 设计文档 §7）
-- 幂等：新表 CREATE TABLE IF NOT EXISTS；
--       加列用 INFORMATION_SCHEMA 判断 + PREPARE 动态执行
--       （MySQL 8 无 ADD COLUMN IF NOT EXISTS，重跑无副作用）
-- 内容：
--   1) t_data_source 加列 params（文件源参数/类型扩展参数）
--   2) t_ide_history IDE 执行历史
--   3) t_tmp_data 临时工作数据（C22 三形态 + ${tmp.*} 引用）
-- 注：测试存储过程 sp_i4_demo 建于 datara-mysql-src（meta 库不可跨库 DDL），
--     属 i4-8 实测步骤（设计文档 §13）。
-- ============================================================

-- ---------- 1. t_data_source 加列 params ----------
SET @col_exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 't_data_source' AND COLUMN_NAME = 'params');
SET @ddl := IF(@col_exists = 0,
  'ALTER TABLE t_data_source ADD COLUMN params JSON NULL COMMENT ''文件源参数/类型扩展参数（{format,path,encoding,delimiter,header,sheet}）'' AFTER group_name',
  'SELECT 1');
PREPARE s FROM @ddl;
EXECUTE s;
DEALLOCATE PREPARE s;

-- ---------- 2. t_ide_history IDE 执行历史 ----------
CREATE TABLE IF NOT EXISTS t_ide_history (
  id            BIGINT        NOT NULL AUTO_INCREMENT,
  user_id       INT           NULL COMMENT '执行用户 id',
  datasource_id BIGINT        NOT NULL COMMENT '数据源 id',
  db_name       VARCHAR(128)  NULL COMMENT '执行库',
  sql_text      VARCHAR(4000) NULL COMMENT 'SQL 全文（超长截断）',
  status        VARCHAR(16)   NOT NULL DEFAULT 'success' COMMENT 'success/failure',
  elapsed_ms    INT           NULL COMMENT '总耗时 ms',
  rows_total    INT           NULL COMMENT '结果集总行数',
  exported      TINYINT       NOT NULL DEFAULT 0 COMMENT '是否已导出 0/1',
  error         VARCHAR(2000) NULL COMMENT '失败原因',
  create_time   DATETIME      NULL,
  update_time   DATETIME      NULL,
  PRIMARY KEY (id),
  KEY idx_ide_hist_ds (datasource_id, create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='IDE 执行历史（I4）';

-- ---------- 3. t_tmp_data 临时工作数据 ----------
CREATE TABLE IF NOT EXISTS t_tmp_data (
  id           BIGINT       NOT NULL AUTO_INCREMENT,
  instance_id  VARCHAR(64)  NOT NULL COMMENT '运行实例编号（对齐 t_task_instance 字符串口径）',
  task_id      BIGINT       NULL COMMENT '任务实例 id',
  node_id      VARCHAR(64)  NULL COMMENT '画布节点 id',
  name         VARCHAR(64)  NOT NULL COMMENT '临时数据名（${tmp.<name>} 引用）',
  kind         VARCHAR(16)  NOT NULL DEFAULT 'table' COMMENT 'table/resultset/file 三形态',
  ref          VARCHAR(255) NULL COMMENT '实体引用：临时表名/共享卷文件路径/结果集标识',
  target_ds_id BIGINT       NULL COMMENT '物化目标数据源 id',
  rows_count   BIGINT       NULL COMMENT '行数统计',
  schema_json  JSON         NULL COMMENT '字段类型推断/空值率',
  preview_json JSON         NULL COMMENT '抽样预览（≤200 行）',
  retention    VARCHAR(16)  NOT NULL DEFAULT 'immediate' COMMENT 'immediate/days/keep 保留策略',
  expire_at    DATETIME     NULL COMMENT '保留到期时间（days 策略）',
  status       VARCHAR(16)  NOT NULL DEFAULT 'active' COMMENT 'active/consumed/expired/cleaned',
  create_time  DATETIME     NULL,
  update_time  DATETIME     NULL,
  PRIMARY KEY (id),
  KEY idx_tmp_inst (instance_id),
  UNIQUE KEY uk_tmp_name (instance_id, name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='临时工作数据（C22 注册，I4）';
