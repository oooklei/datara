-- ============================================================
-- Datara 平台 meta 库建表（I1 设计文档 §4，13 张表）
-- 载体：mysql-meta 容器 /docker-entrypoint-initdb.d（首启自动执行）
--       + install.sh 幂等重放 + common.db.init_db() create_all 兜底
-- 幂等：CREATE TABLE IF NOT EXISTS；初始账号不在此写入（install.sh 第 5 步
--       执行 python -m common.init_accounts，bcrypt 幂等写入 t_user）
-- ============================================================
SET NAMES utf8mb4;

-- 1. t_user 用户（对齐海豚 t_ds_user 裁剪）
CREATE TABLE IF NOT EXISTS t_user (
  id          INT          NOT NULL AUTO_INCREMENT,
  user_name   VARCHAR(64)  NOT NULL COMMENT '登录名',
  user_pwd    VARCHAR(128) NOT NULL COMMENT 'bcrypt 散列',
  user_role   VARCHAR(32)  NOT NULL COMMENT 'admin/dev/analyst/viewer',
  state       VARCHAR(16)  NOT NULL DEFAULT 'enabled' COMMENT 'enabled/disabled',
  create_time DATETIME     NULL,
  update_time DATETIME     NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_user_name (user_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户';

-- 2. t_wf_definition 工作流定义（id=前端 GraphDocument doc.id，code=雪花式数字）
CREATE TABLE IF NOT EXISTS t_wf_definition (
  id           VARCHAR(64) NOT NULL COMMENT 'wf_xxx（doc.id）',
  code         BIGINT      NOT NULL COMMENT '雪花式数字编码',
  name         VARCHAR(255) NOT NULL COMMENT '工作流名称',
  version      INT         NOT NULL DEFAULT 1 COMMENT '当前版本号',
  release_state VARCHAR(16) NOT NULL DEFAULT 'offline' COMMENT 'online/offline',
  flag         VARCHAR(8)  NOT NULL DEFAULT 'yes' COMMENT 'yes/no 可用标志',
  project_code VARCHAR(64) NOT NULL DEFAULT 'default' COMMENT '项目编码（对齐海豚留位）',
  tags         JSON        NULL COMMENT '标签（同步标签等）',
  graph_json   LONGTEXT    NULL COMMENT 'GraphDocument 全量 JSON',
  owner_id     INT         NULL COMMENT '属主用户 id',
  create_time  DATETIME    NULL,
  update_time  DATETIME    NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_wf_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='工作流定义';

-- 3. t_wf_definition_log 定义版本快照（每次 save 追加一行）
CREATE TABLE IF NOT EXISTS t_wf_definition_log (
  id           BIGINT      NOT NULL AUTO_INCREMENT,
  wf_code      BIGINT      NOT NULL COMMENT '工作流 code',
  version      INT         NOT NULL COMMENT '快照版本号',
  graph_json   LONGTEXT    NULL COMMENT '该版本 GraphDocument JSON',
  operator     VARCHAR(64) NULL COMMENT '操作人',
  remark       VARCHAR(512) NULL COMMENT '备注',
  operate_time DATETIME    NULL COMMENT '操作时间',
  create_time  DATETIME    NULL,
  update_time  DATETIME    NULL,
  PRIMARY KEY (id),
  KEY idx_wfdlog_code_ver (wf_code, version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='工作流定义版本快照';

-- 4. t_workflow_instance 工作流运行实例（instance_id 贯穿任务/日志/告警）
CREATE TABLE IF NOT EXISTS t_workflow_instance (
  id           BIGINT      NOT NULL AUTO_INCREMENT,
  instance_id  VARCHAR(64) NOT NULL COMMENT '运行实例编号 {ts}-{code}-{rand4}',
  wf_code      BIGINT      NOT NULL DEFAULT 0 COMMENT '工作流 code（冒烟链路为 0）',
  wf_version   INT         NOT NULL DEFAULT 0 COMMENT '定义版本号',
  state        VARCHAR(32) NOT NULL DEFAULT 'submitted' COMMENT 'submitted/running/success/failure/kill/fault_tolerance',
  start_time   DATETIME    NULL,
  end_time     DATETIME    NULL,
  host         VARCHAR(128) NULL COMMENT '执行 host',
  variables    JSON        NULL COMMENT '变量快照（F48 衔接）',
  command_type VARCHAR(64) NULL COMMENT '触发命令类型',
  recovery     INT         NOT NULL DEFAULT 0 COMMENT '容错恢复标志',
  create_time  DATETIME    NULL,
  update_time  DATETIME    NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_instance_id (instance_id),
  KEY idx_wfinst_code (wf_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='工作流运行实例';

-- 5. t_task_instance 任务实例（状态集见 02 文档 §1.1）
CREATE TABLE IF NOT EXISTS t_task_instance (
  id           BIGINT      NOT NULL AUTO_INCREMENT,
  instance_id  VARCHAR(64) NOT NULL COMMENT '所属运行实例编号',
  node_id      VARCHAR(64) NULL COMMENT '画布节点 id',
  node_type    VARCHAR(64) NOT NULL COMMENT '节点类型（I1 冒烟=smoke）',
  name         VARCHAR(255) NULL COMMENT '任务名',
  state        VARCHAR(32) NOT NULL DEFAULT 'submitted' COMMENT 'submitted/running/success/failure/kill/fault_tolerance',
  attempt      INT         NOT NULL DEFAULT 1 COMMENT '重试序号',
  start_time   DATETIME    NULL,
  end_time     DATETIME    NULL,
  host         VARCHAR(128) NULL COMMENT '执行 host',
  log_path     VARCHAR(512) NULL COMMENT '日志文件路径',
  outputs      JSON        NULL COMMENT '节点输出参数/结果表',
  create_time  DATETIME    NULL,
  update_time  DATETIME    NULL,
  PRIMARY KEY (id),
  KEY idx_taskinst_instance (instance_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='任务实例';

-- 6. t_command 命令表（master 轮询消费，对齐海豚 t_ds_command）
CREATE TABLE IF NOT EXISTS t_command (
  id            BIGINT      NOT NULL AUTO_INCREMENT,
  command_type  VARCHAR(64) NOT NULL COMMENT 'START_PROCESS/STOP/START_PROCESS_SMOKE…',
  command_param JSON        NULL COMMENT '命令参数 JSON',
  priority      INT         NOT NULL DEFAULT 0 COMMENT '优先级（大者优先）',
  state         VARCHAR(16) NOT NULL DEFAULT 'wait' COMMENT 'wait/execute/done',
  create_time   DATETIME    NULL,
  update_time   DATETIME    NULL,
  PRIMARY KEY (id),
  KEY idx_command_state (state, priority)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='命令表';

-- 7. t_data_source 数据源（I1 建表，CRUD 归 I4）
CREATE TABLE IF NOT EXISTS t_data_source (
  id          BIGINT       NOT NULL AUTO_INCREMENT,
  name        VARCHAR(255) NOT NULL COMMENT '数据源名称',
  type        VARCHAR(64)  NOT NULL COMMENT 'mysql/greatdb/…',
  host        VARCHAR(255) NULL,
  port        INT          NULL,
  db_name     VARCHAR(128) NULL,
  user        VARCHAR(128) NULL,
  pwd         VARCHAR(255) NULL COMMENT '密码（加密存储，I4 实现）',
  env         VARCHAR(64)  NULL COMMENT '环境（dev/prod…）',
  group_name  VARCHAR(128) NULL COMMENT '分组',
  tags        JSON         NULL,
  owner_id    INT          NULL,
  status      VARCHAR(16)  NULL COMMENT '连通状态',
  create_time DATETIME     NULL,
  update_time DATETIME     NULL,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据源';

-- 8. t_wf_variable 工作流变量（对齐前端 WfVariable）
CREATE TABLE IF NOT EXISTS t_wf_variable (
  id          BIGINT       NOT NULL AUTO_INCREMENT,
  wf_code     BIGINT       NOT NULL COMMENT '工作流 code',
  name        VARCHAR(128) NOT NULL COMMENT '变量名',
  value       TEXT         NULL COMMENT '变量值',
  type        VARCHAR(16)  NOT NULL DEFAULT '文本' COMMENT '日期/文本/数值/加密/下拉',
  encrypted   TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '是否加密存储',
  options     JSON         NULL COMMENT '下拉选项',
  `desc`      VARCHAR(512) NULL COMMENT '说明',
  create_time DATETIME     NULL,
  update_time DATETIME     NULL,
  PRIMARY KEY (id),
  KEY idx_wfvar_code (wf_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='工作流变量';

-- 9. t_global_param 全局参数
CREATE TABLE IF NOT EXISTS t_global_param (
  id          BIGINT       NOT NULL AUTO_INCREMENT,
  name        VARCHAR(128) NOT NULL COMMENT '参数名',
  value       TEXT         NULL,
  type        VARCHAR(16)  NOT NULL DEFAULT '文本' COMMENT '参数类型',
  encrypt     TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '是否加密',
  `desc`      VARCHAR(512) NULL COMMENT '说明',
  create_time DATETIME     NULL,
  update_time DATETIME     NULL,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='全局参数';

-- 10. t_env_group 环境组（对齐海豚 t_ds_environment）
CREATE TABLE IF NOT EXISTS t_env_group (
  id          BIGINT       NOT NULL AUTO_INCREMENT,
  name        VARCHAR(128) NOT NULL COMMENT '环境组名',
  `desc`      VARCHAR(512) NULL COMMENT '说明',
  config      JSON         NULL COMMENT '环境配置 JSON',
  create_time DATETIME     NULL,
  update_time DATETIME     NULL,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='环境组';

-- 11. t_task_log 日志索引（正文存共享卷文件，logger 按索引读取）
CREATE TABLE IF NOT EXISTS t_task_log (
  id               BIGINT       NOT NULL AUTO_INCREMENT,
  instance_id      VARCHAR(64)  NOT NULL COMMENT '运行实例编号',
  task_instance_id BIGINT       NOT NULL COMMENT '任务实例 id',
  log_path         VARCHAR(512) NOT NULL COMMENT '日志文件路径（共享卷内）',
  host             VARCHAR(128) NULL COMMENT '写日志的 host',
  create_time      DATETIME     NULL,
  update_time      DATETIME     NULL,
  PRIMARY KEY (id),
  KEY idx_tasklog_instance (instance_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='任务日志索引';

-- 12. t_alert_record 告警记录（对齐海豚 t_ds_alert 裁剪）
CREATE TABLE IF NOT EXISTS t_alert_record (
  id          BIGINT       NOT NULL AUTO_INCREMENT,
  instance_id VARCHAR(64)  NULL COMMENT '关联运行实例',
  title       VARCHAR(255) NULL,
  content     TEXT         NULL,
  channel     VARCHAR(32)  NULL COMMENT '告警通道',
  state       VARCHAR(16)  NOT NULL DEFAULT 'wait' COMMENT 'wait/sent/fail',
  create_time DATETIME     NULL,
  update_time DATETIME     NULL,
  PRIMARY KEY (id),
  KEY idx_alert_state (state)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='告警记录';

-- 13. t_runtime_node 运行时节点（对齐前端 RuntimeNode，SSH 唯一权威源；I7 F53 启用）
CREATE TABLE IF NOT EXISTS t_runtime_node (
  id             BIGINT       NOT NULL AUTO_INCREMENT,
  name           VARCHAR(128) NOT NULL COMMENT '节点名',
  kind           VARCHAR(16)  NOT NULL DEFAULT '本地' COMMENT '本地/远程',
  host           VARCHAR(255) NULL,
  port           INT          NULL,
  user           VARCHAR(128) NULL,
  auth           VARCHAR(255) NULL COMMENT '密钥名/加密密码/本地进程',
  runtime_dir    VARCHAR(255) NULL COMMENT '脚本/任务分发运行时目录',
  tmp_dir        VARCHAR(255) NULL COMMENT '临时数据目录',
  os             VARCHAR(64)  NULL COMMENT '操作系统',
  status         VARCHAR(16)  NOT NULL DEFAULT 'offline' COMMENT 'online/offline',
  cpu            VARCHAR(32)  NULL,
  mem            VARCHAR(32)  NULL,
  disk           VARCHAR(32)  NULL,
  tasks          INT          NULL COMMENT '运行任务数',
  last_heartbeat DATETIME     NULL COMMENT '最近心跳',
  create_time    DATETIME     NULL,
  update_time    DATETIME     NULL,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='运行时节点';
