-- ============================================================
-- I5 血缘关系 · meta 库增量 DDL（I5 设计文档 §5）
-- 幂等：新表 CREATE TABLE IF NOT EXISTS（重跑无副作用）
-- 内容：
--   1) t_lineage_edge   表级血缘边（uk 幂等，重跑/容错重放不重复）
--   2) t_lineage_field  字段级映射 + 转换细节留存（F23）
-- 注：from_table/from_field 无来源时用空串而非 NULL——uk 含 NULL 时
--     MySQL 唯一约束失效（NULL<>NULL），ON DUPLICATE 幂等会失效。
-- ============================================================

-- ---------- 1. t_lineage_edge 表级血缘边 ----------
CREATE TABLE IF NOT EXISTS t_lineage_edge (
  id           BIGINT        NOT NULL AUTO_INCREMENT,
  wf_code      INT           NOT NULL COMMENT '工作流定义 code',
  wf_name      VARCHAR(128)  NULL COMMENT '工作流名称（展示冗余）',
  instance_id  VARCHAR(64)   NOT NULL COMMENT '运行实例编号（追溯主键，对齐 t_task_instance）',
  task_id      BIGINT        NULL COMMENT '任务实例 id',
  node_id      VARCHAR(64)   NOT NULL COMMENT '画布节点 id',
  node_name    VARCHAR(128)  NULL COMMENT '节点名称（展示冗余，前端 task 列）',
  ds_name      VARCHAR(128)  NULL COMMENT '执行数据源名（SQL 节点所在库的 default_db 依据）',
  stmt_no      INT           NOT NULL COMMENT '语句序号（分号拆分序，1 起）',
  stmt         VARCHAR(2000) NULL COMMENT '语句原文（回写文本，超长截断）',
  from_table   VARCHAR(255)  NOT NULL DEFAULT '' COMMENT '输入表 db.table（空串=无来源，如 INSERT..VALUES）',
  to_table     VARCHAR(255)  NOT NULL COMMENT '输出表 db.table',
  tmp_flag     TINYINT       NOT NULL DEFAULT 0 COMMENT '边涉及临时工作数据注册名（来源/目标任一侧 ${tmp.*} 映射）0/1',
  create_time  DATETIME      NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_lineage (wf_code, instance_id, node_id, stmt_no, from_table, to_table),
  KEY idx_ln_from (from_table),
  KEY idx_ln_to (to_table),
  KEY idx_ln_inst (instance_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='表级血缘边（I5 运行时采集）';

-- ---------- 2. t_lineage_field 字段级映射 + 转换细节 ----------
CREATE TABLE IF NOT EXISTS t_lineage_field (
  id           BIGINT         NOT NULL AUTO_INCREMENT,
  edge_id      BIGINT         NOT NULL COMMENT '所属表级血缘边 id（t_lineage_edge.id）',
  to_field     VARCHAR(128)   NOT NULL COMMENT '目标字段',
  from_table   VARCHAR(255)   NOT NULL DEFAULT '' COMMENT '来源表 db.table（空串=常量/无来源）',
  from_field   VARCHAR(128)   NOT NULL DEFAULT '' COMMENT '来源字段',
  transform    VARCHAR(1000)  NULL COMMENT '加工表达式（mysql 方言回写，如 o.amount * 0.9）',
  create_time  DATETIME       NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_field (edge_id, to_field, from_table, from_field),
  KEY idx_lnfield_edge (edge_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='字段级血缘映射与转换细节（I5，F22/F23）';
