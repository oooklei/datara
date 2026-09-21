"""ORM 模型：meta 库 22 张表（I1 十三表 + I3 t_wf_schedule + I4 t_ide_history/t_tmp_data
+ I5 t_lineage_edge/t_lineage_field + I7 t_ssh_node + I8 t_stream_job/t_stream_offset
+ I10 t_ide_script）。

- 所有表含 create_time/update_time（datetime，本地时区写入 datetime.now()）
- t_wf_definition.id = 前端 GraphDocument 的 doc.id（形如 'wf_xxx'），code 为雪花式数字
- graph_json 用 LONGTEXT（GraphDocument 全量 JSON）
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import LONGTEXT, MEDIUMTEXT
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now() -> datetime:
    """本地时区当前时间（写库统一入口）。"""
    return datetime.now()


class Base(DeclarativeBase):
    pass


# ---------- 1. t_user 用户 ----------
class User(Base):
    __tablename__ = "t_user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_name: Mapped[str] = mapped_column(String(64), unique=True, comment="登录名")
    user_pwd: Mapped[str] = mapped_column(String(128), comment="bcrypt 散列")
    user_role: Mapped[str] = mapped_column(String(32), comment="admin/dev/analyst/viewer")
    state: Mapped[str] = mapped_column(String(16), default="enabled", comment="enabled/disabled")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


# ---------- 2. t_wf_definition 工作流定义 ----------
class WfDefinition(Base):
    __tablename__ = "t_wf_definition"

    # id = 前端 GraphDocument.doc.id（'wf_xxx'），非自增
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    code: Mapped[int] = mapped_column(BigInteger, unique=True, comment="雪花式数字编码")
    name: Mapped[str] = mapped_column(String(255), comment="工作流名称")
    version: Mapped[int] = mapped_column(Integer, default=1, comment="当前版本号")
    release_state: Mapped[str] = mapped_column(String(16), default="offline", comment="online/offline")
    flag: Mapped[str] = mapped_column(String(8), default="yes", comment="yes/no 可用标志")
    project_code: Mapped[str] = mapped_column(String(64), default="default", comment="项目编码（对齐海豚留位）")
    tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, comment="标签（同步标签等）")
    graph_json: Mapped[Optional[str]] = mapped_column(LONGTEXT, nullable=True, comment="GraphDocument 全量 JSON")
    owner_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="属主用户 id")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


# ---------- 3. t_wf_definition_log 定义版本快照 ----------
class WfDefinitionLog(Base):
    __tablename__ = "t_wf_definition_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    wf_code: Mapped[int] = mapped_column(BigInteger, comment="工作流 code")
    version: Mapped[int] = mapped_column(Integer, comment="快照版本号")
    graph_json: Mapped[Optional[str]] = mapped_column(LONGTEXT, nullable=True, comment="该版本 GraphDocument JSON")
    operator: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="操作人")
    remark: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment="备注")
    operate_time: Mapped[datetime] = mapped_column(DateTime, default=now, comment="操作时间")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    __table_args__ = (Index("idx_wfdlog_code_ver", "wf_code", "version"),)


# ---------- 4. t_workflow_instance 工作流运行实例 ----------
class WorkflowInstance(Base):
    __tablename__ = "t_workflow_instance"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    instance_id: Mapped[str] = mapped_column(String(64), unique=True, comment="运行实例编号 {ts}-{code}-{rand4}")
    wf_code: Mapped[int] = mapped_column(BigInteger, default=0, comment="工作流 code（冒烟链路为 0）")
    wf_version: Mapped[int] = mapped_column(Integer, default=0, comment="定义版本号")
    state: Mapped[str] = mapped_column(
        String(32), default="submitted", comment="submitted/running/success/failure/kill/fault_tolerance"
    )
    start_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    host: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, comment="执行 host")
    variables: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="变量快照（F48 衔接）")
    command_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="触发命令类型")
    run_mode: Mapped[str] = mapped_column(String(16), default="manual", comment="manual/schedule/complement（I3）")
    schedule_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="调度/补数计划时间（内置时间变量基准，I3）"
    )
    recovery: Mapped[int] = mapped_column(Integer, default=0, comment="容错恢复标志")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    __table_args__ = (Index("idx_wfinst_code", "wf_code"),)


# ---------- 5. t_task_instance 任务实例 ----------
class TaskInstance(Base):
    __tablename__ = "t_task_instance"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    instance_id: Mapped[str] = mapped_column(String(64), comment="所属运行实例编号")
    node_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="画布节点 id")
    node_type: Mapped[str] = mapped_column(String(64), comment="节点类型（I1 冒烟=smoke）")
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="任务名")
    state: Mapped[str] = mapped_column(String(32), default="submitted", comment="同 02 文档 §1.1 状态集")
    attempt: Mapped[int] = mapped_column(Integer, default=1, comment="重试序号")
    loop_iter: Mapped[int] = mapped_column(Integer, default=0, comment="循环迭代号（C10 每轮迭代新建行，I3）")
    delay_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="延时到期（C8，I3）")
    start_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    host: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, comment="执行 host")
    log_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment="日志文件路径")
    outputs: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="节点输出参数/结果表")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    __table_args__ = (Index("idx_taskinst_instance", "instance_id"),)


# ---------- 6. t_command 命令表 ----------
class Command(Base):
    __tablename__ = "t_command"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    command_type: Mapped[str] = mapped_column(String(64), comment="START_PROCESS/STOP/START_PROCESS_SMOKE…")
    command_param: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="命令参数 JSON")
    priority: Mapped[int] = mapped_column(Integer, default=0, comment="优先级（大者优先）")
    state: Mapped[str] = mapped_column(String(16), default="wait", comment="wait/execute/done")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    __table_args__ = (Index("idx_command_state", "state", "priority"),)


# ---------- 7. t_data_source 数据源（I1 建表，CRUD 归 I4） ----------
class DataSource(Base):
    __tablename__ = "t_data_source"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), comment="数据源名称")
    type: Mapped[str] = mapped_column(String(64), comment="mysql/greatdb/…")
    host: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    port: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    db_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    user: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    pwd: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="密码（明文，加密裁定取消）")
    env: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="环境（dev/prod…）")
    group_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, comment="分组")
    params: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="文件源参数/类型扩展参数（{format,path,encoding,delimiter,header,sheet}）"
    )
    tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    owner_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, comment="连通状态")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


# ---------- 8. t_wf_variable 工作流变量（对齐前端 WfVariable） ----------
class WfVariable(Base):
    __tablename__ = "t_wf_variable"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    wf_code: Mapped[int] = mapped_column(BigInteger, comment="工作流 code")
    name: Mapped[str] = mapped_column(String(128), comment="变量名")
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="变量值")
    type: Mapped[str] = mapped_column(String(16), default="文本", comment="日期/文本/数值/加密/下拉")
    encrypted: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否加密存储")
    options: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, comment="下拉选项")
    desc: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment="说明")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    __table_args__ = (Index("idx_wfvar_code", "wf_code"),)


# ---------- 9. t_global_param 全局参数 ----------
class GlobalParam(Base):
    __tablename__ = "t_global_param"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), comment="参数名")
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    type: Mapped[str] = mapped_column(String(16), default="文本", comment="参数类型")
    env: Mapped[str] = mapped_column(
        String(16), default="dev", server_default="dev", comment="环境分组 dev/staging/prod（I10）"
    )
    encrypt: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否加密")
    desc: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    __table_args__ = (Index("idx_gp_env", "env", "name"),)


# ---------- 10. t_env_group 环境组 ----------
class EnvGroup(Base):
    __tablename__ = "t_env_group"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), comment="环境组名")
    desc: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="环境配置 JSON")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


# ---------- 11. t_task_log 日志索引（正文存文件，logger 按索引读） ----------
class TaskLog(Base):
    __tablename__ = "t_task_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    instance_id: Mapped[str] = mapped_column(String(64), comment="运行实例编号")
    task_instance_id: Mapped[int] = mapped_column(BigInteger, comment="任务实例 id")
    log_path: Mapped[str] = mapped_column(String(512), comment="日志文件路径（共享卷内）")
    host: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, comment="写日志的 host")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    __table_args__ = (Index("idx_tasklog_instance", "instance_id"),)


# ---------- 12. t_alert_record 告警记录 ----------
class AlertRecord(Base):
    __tablename__ = "t_alert_record"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    instance_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="关联运行实例")
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    channel: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="告警通道")
    state: Mapped[str] = mapped_column(String(16), default="wait", comment="wait/sent/fail")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    __table_args__ = (Index("idx_alert_state", "state"),)


# ---------- 13. t_runtime_node 运行时节点（对齐前端 RuntimeNode，I7 F53 启用） ----------
class RuntimeNode(Base):
    __tablename__ = "t_runtime_node"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), comment="节点名")
    kind: Mapped[str] = mapped_column(String(16), default="本地", comment="本地/远程")
    host: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    port: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    user: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    auth: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="私钥内容（-----BEGIN 开头）/密码明文/密钥名"
    )
    runtime_dir: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="脚本/任务分发运行时目录")
    tmp_dir: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="临时数据目录")
    os: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="操作系统")
    status: Mapped[str] = mapped_column(String(16), default="offline", comment="online/offline")
    cpu: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    mem: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    disk: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    tasks: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="运行任务数")
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="最近心跳")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


# ---------- 14. t_wf_schedule 定时调度（I3 新增，对齐海豚 t_ds_schedule 裁剪） ----------
class WfSchedule(Base):
    __tablename__ = "t_wf_schedule"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    wf_code: Mapped[int] = mapped_column(BigInteger, comment="工作流 code")
    name: Mapped[str] = mapped_column(String(255), default="默认定时", comment="定时名")
    crontab: Mapped[str] = mapped_column(String(64), comment="cron 表达式（6 段：秒 分 时 日 月 周）")
    start_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="有效起始时间")
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="有效结束时间")
    state: Mapped[str] = mapped_column(String(16), default="offline", comment="online/offline")
    priority: Mapped[int] = mapped_column(Integer, default=3, comment="任务优先级 1~5")
    worker_group: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="worker 分组（I7）")
    fail_retry_times: Mapped[int] = mapped_column(Integer, default=0, comment="失败重试次数（实例任务缺省）")
    fail_retry_interval: Mapped[int] = mapped_column(Integer, default=60, comment="失败重试间隔（秒）")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    __table_args__ = (Index("idx_schedule_state", "state"),)


# ---------- 15. t_ide_history IDE 执行历史（I4 新增，I10 加列） ----------
class IdeHistory(Base):
    __tablename__ = "t_ide_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="执行用户 id")
    datasource_id: Mapped[int] = mapped_column(BigInteger, comment="数据源 id")
    db_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, comment="执行库")
    sql_text: Mapped[Optional[str]] = mapped_column(
        MEDIUMTEXT, nullable=True, comment="SQL 全文（I10 升 MEDIUMTEXT）"
    )
    rendered_sql: Mapped[Optional[str]] = mapped_column(
        MEDIUMTEXT, nullable=True,
        comment="渲染后 SQL 全文（重放分页/导出用；存量历史回退 sql_text，09-22 加列）",
    )
    status: Mapped[str] = mapped_column(String(16), default="success", comment="success/failure")
    elapsed_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="总耗时 ms")
    rows_total: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="结果集总行数")
    affected_total: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="受影响行数合计（DML/DDL 逐条累加，I10）"
    )
    exported: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否已导出")
    error: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True, comment="失败原因")
    log_text: Mapped[Optional[str]] = mapped_column(
        MEDIUMTEXT, nullable=True, comment="逐条执行日志 JSON（语句序号/状态/耗时/错误/SHOW WARNINGS，I10）"
    )
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    __table_args__ = (Index("idx_ide_hist_ds", "datasource_id", "create_time"),)


# ---------- 16. t_tmp_data 临时工作数据（I4 新增，C22 三形态 + ${tmp.*} 引用） ----------
class TmpData(Base):
    __tablename__ = "t_tmp_data"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    instance_id: Mapped[str] = mapped_column(String(64), comment="运行实例编号（对齐 t_task_instance 字符串口径）")
    task_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="任务实例 id")
    node_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="画布节点 id")
    name: Mapped[str] = mapped_column(String(64), comment="临时数据名（${tmp.<name>} 引用）")
    kind: Mapped[str] = mapped_column(String(16), default="table", comment="table/resultset/file 三形态")
    ref: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, comment="实体引用：临时表名/文件路径/结果集标识"
    )
    target_ds_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="物化目标数据源 id")
    rows_count: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="行数统计")
    schema_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="字段类型推断/空值率")
    preview_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="抽样预览（≤200 行）")
    retention: Mapped[str] = mapped_column(String(16), default="immediate", comment="immediate/days/keep 保留策略")
    expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="保留到期时间（days 策略）")
    status: Mapped[str] = mapped_column(String(16), default="active", comment="active/consumed/expired/cleaned")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    __table_args__ = (
        Index("idx_tmp_inst", "instance_id"),
        UniqueConstraint("instance_id", "name", name="uk_tmp_name"),
    )


# ---------- 17. t_lineage_edge 表级血缘边（I5 新增，运行时采集） ----------
class LineageEdge(Base):
    __tablename__ = "t_lineage_edge"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    wf_code: Mapped[int] = mapped_column(BigInteger, comment="工作流定义 code")
    wf_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, comment="工作流名称（展示冗余）")
    instance_id: Mapped[str] = mapped_column(String(64), comment="运行实例编号（追溯主键）")
    task_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="任务实例 id")
    node_id: Mapped[str] = mapped_column(String(64), comment="画布节点 id")
    node_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, comment="节点名称（前端 task 列）")
    ds_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, comment="执行数据源名")
    stmt_no: Mapped[int] = mapped_column(Integer, comment="语句序号（分号拆分序，1 起）")
    stmt: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True, comment="语句原文（回写文本，截断）")
    from_table: Mapped[str] = mapped_column(
        String(255), default="", server_default="",
        comment="输入表 db.table（空串=无来源，如 INSERT..VALUES）",
    )
    to_table: Mapped[str] = mapped_column(String(255), comment="输出表 db.table")
    # 任一侧 ${tmp.*} 映射为注册名 → 1（门 #10：C22 临时表作来源时同样置 1）
    tmp_flag: Mapped[bool] = mapped_column(Boolean, default=False, comment="边涉及临时注册名 0/1")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)

    __table_args__ = (
        UniqueConstraint("wf_code", "instance_id", "node_id", "stmt_no", "from_table", "to_table",
                         name="uk_lineage"),
        Index("idx_ln_from", "from_table"),
        Index("idx_ln_to", "to_table"),
        Index("idx_ln_inst", "instance_id"),
    )


# ---------- 18. t_lineage_field 字段级血缘映射（I5 新增，F22/F23） ----------
class LineageField(Base):
    __tablename__ = "t_lineage_field"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    edge_id: Mapped[int] = mapped_column(BigInteger, comment="所属表级血缘边 id")
    to_field: Mapped[str] = mapped_column(String(128), comment="目标字段")
    from_table: Mapped[str] = mapped_column(
        String(255), default="", server_default="", comment="来源表 db.table（空串=常量/无来源）",
    )
    from_field: Mapped[str] = mapped_column(
        String(128), default="", server_default="", comment="来源字段",
    )
    transform: Mapped[Optional[str]] = mapped_column(
        String(1000), nullable=True, comment="加工表达式（mysql 方言回写）",
    )
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)

    __table_args__ = (
        UniqueConstraint("edge_id", "to_field", "from_table", "from_field", name="uk_field"),
        Index("idx_lnfield_edge", "edge_id"),
    )


# ---------- 19. t_ssh_node SSH 运行节点注册表（I7 新增，F53 多主机 HA） ----------
class SshNode(Base):
    __tablename__ = "t_ssh_node"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, comment="节点名（唯一）")
    host: Mapped[str] = mapped_column(String(255), comment="主机地址")
    port: Mapped[int] = mapped_column(Integer, default=22, comment="SSH 端口")
    ssh_user: Mapped[str] = mapped_column(String(128), default="root", comment="SSH 用户")
    cred_enc: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="凭证（明文裁定：密码或 -----BEGIN 私钥内容）"
    )
    tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, comment="执行节点标签（派发路由匹配）")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="启用开关（false 派发剔除）")
    heartbeat_state: Mapped[str] = mapped_column(
        String(16), default="unknown", comment="探活状态 online/offline/unknown"
    )
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="最近探活通过时间")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    __table_args__ = (Index("idx_sshnode_state", "enabled", "heartbeat_state"),)


# ---------- 20. t_stream_job 流任务常驻运行态（I8 新增，F40 独立状态机，不复用批实例） ----------
class StreamJob(Base):
    __tablename__ = "t_stream_job"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    doc_id: Mapped[str] = mapped_column(String(64), comment="画布文档 id（t_wf_definition.id，一画布一流任务）")
    wf_code: Mapped[int] = mapped_column(BigInteger, default=0, comment="工作流 code（展示/联动）")
    wf_name: Mapped[str] = mapped_column(String(255), default="", comment="工作流名称（展示冗余）")
    name: Mapped[str] = mapped_column(String(255), default="", comment="流任务名（默认取画布名）")
    spec_json: Mapped[Optional[str]] = mapped_column(
        LONGTEXT, nullable=True, comment="流子图规格 JSON（源/算子/汇参数+拓扑）")
    status: Mapped[str] = mapped_column(
        String(16), default="starting",
        comment="starting/running/reconnecting/stopped/failed（started 类状态=宿主 worker 常驻线程）",
    )
    host: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, comment="宿主 worker 身份（认领原子性锚点）")
    generation: Mapped[int] = mapped_column(Integer, default=1, comment="启动代号（每次 start 自增，重启/换主对齐）")
    last_error: Mapped[Optional[str]] = mapped_column(
        String(2000), nullable=True, comment="最近错误（failed/重连留痕）")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="最近启动时间")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    __table_args__ = (Index("idx_streamjob_doc", "doc_id"), Index("idx_streamjob_status", "status"),)


# ---------- 21. t_stream_offset 流源位点持久化（I8 新增，at-least-once 续跑） ----------
class StreamOffset(Base):
    __tablename__ = "t_stream_offset"

    job_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, comment="流任务 id（t_stream_job.id）")
    source_key: Mapped[str] = mapped_column(String(128), primary_key=True, comment="源标识（node_id:分型）")
    offset_json: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="位点（partition offset/file:pos/cursor/字节偏移）")
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="位点提交时间")


# ---------- 22. t_ide_script IDE 命名脚本（I10 新增，G16） ----------
class IdeScript(Base):
    __tablename__ = "t_ide_script"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, comment="所属用户")
    name: Mapped[str] = mapped_column(String(128), comment="脚本名（用户内唯一）")
    datasource_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="关联数据源（可空）")
    db_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, comment="关联库")
    content: Mapped[Optional[str]] = mapped_column(MEDIUMTEXT, nullable=True, comment="SQL 全文")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uk_script"),
        Index("idx_script_user", "user_id"),
    )
