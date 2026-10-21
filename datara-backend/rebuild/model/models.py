"""I18 数仓建模字典表 ORM（五步迁移第②步：旧 `common/models.py` 照抄，业务逻辑不重构）。

迁移源实锚：`datara-backend/common/models.py:743-778`（`DwLayer` / `BizDomain` / `EngineType`）。
列定义、类型、默认值与注释逐项照抄；仅基座由旧 `common.models.Base` 换成 `rebuild.common.db.Base`，
使新后端自有元数据可独立建表，不依赖旧 Backend 模块。

- `t_dw_layer`   数仓分层字典（ODS/DWD/DWS/ADS/DIM）
- `t_biz_domain` 业务域字典（元数据/质量/权限模块复用）
- `t_engine_type` 建模引擎字典（`ddl` 为方言标识，`xc` 为信创徽标）
- `t_data_source` 数据源（**A6-17 物理化目标**，旧侧属 I1/I4 域、建模域仅关联引用；
  承载取舍与候裁见 `DataSourceRecord` 类注）
- `t_lineage_edge` 运行时血缘边（**A6-21 血缘合并图 runtime 半边**，旧侧属 I5 域、建模域
  仅关联引用；承载取舍与候裁见 `LineageEdgeRecord` 类注）
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from rebuild.common.db import Base

# `last_ddl` 旧侧为 MySQL `MEDIUMTEXT`（实锚 common/models.py:799）；
# `with_variant` 保 MySQL DDL 忠实，同时让 SQLite 测试载体可编译。
MediumText = Text().with_variant(MEDIUMTEXT, "mysql")


def _now() -> datetime:
    """本地时区当前时间（与旧侧 `common/models.now()` 同口径）。"""
    return datetime.now()


class DwLayerRecord(Base):
    """数仓分层字典（ODS/DWD/DWS/ADS/DIM，种子见 `rebuild.model.dicts`）。"""

    __tablename__ = "t_dw_layer"

    code: Mapped[str] = mapped_column(String(16), primary_key=True, comment="分层编码")
    name: Mapped[str] = mapped_column(String(64), comment="分层名称")
    rule: Mapped[str] = mapped_column(String(255), default="", comment="命名规范文案")
    color: Mapped[str] = mapped_column(String(16), default="#64748b", comment="统计卡主题色")
    seq: Mapped[int] = mapped_column(Integer, default=0, comment="展示序")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=_now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class BizDomainRecord(Base):
    """业务域字典（元数据/质量/权限模块后续复用）。"""

    __tablename__ = "t_biz_domain"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, comment="业务域名称")
    remark: Mapped[str] = mapped_column(String(255), default="", comment="说明")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=_now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class EngineTypeRecord(Base):
    """建模引擎字典（ddl 为方言标识，xc=信创徽标）。"""

    __tablename__ = "t_engine_type"

    name: Mapped[str] = mapped_column(String(64), primary_key=True, comment="引擎名（Apache Doris 等）")
    ddl: Mapped[str] = mapped_column(String(32), comment="方言标识 mysql/doris/greatdb")
    xc: Mapped[bool] = mapped_column(Boolean, default=False, comment="信创引擎")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=_now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class DwModelRecord(Base):
    """模型主表（状态机 draft→published→built(→produced)，version 为乐观锁基准）。

    迁移源实锚：`datara-backend/common/models.py:782-808`（列定义/类型/默认值逐项照抄）。
    """

    __tablename__ = "t_dw_model"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, comment="物理表名")
    name: Mapped[str] = mapped_column(String(255), comment="中文名")
    layer: Mapped[str] = mapped_column(String(16), comment="分层 → t_dw_layer.code")
    type: Mapped[str] = mapped_column(String(16), default="明细表", comment="事实表/维度表/宽表/明细表")
    biz_domain: Mapped[str] = mapped_column(String(64), default="", comment="业务域 → t_biz_domain.name")
    engine: Mapped[str] = mapped_column(String(64), default="", comment="引擎 → t_engine_type.name")
    ds_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="目标数据源 → t_data_source.id")
    db_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="目标库")
    security_level: Mapped[str] = mapped_column(String(16), default="内部", comment="密级（I19+ sec 接入）")
    status: Mapped[str] = mapped_column(String(16), default="draft", comment="draft/published/built/produced")
    version: Mapped[int] = mapped_column(Integer, default=1, comment="修订号（乐观锁基准）")
    er_pos: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="ER 画布坐标 {x,y}（ER 批）")
    last_ddl: Mapped[Optional[str]] = mapped_column(MediumText, nullable=True, comment="最近物理化 DDL 快照")
    built_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="最近物理化时间")
    built_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="最近物理化操作人")
    owner: Mapped[str] = mapped_column(String(64), default="", comment="负责人")
    remark: Mapped[str] = mapped_column(String(255), default="", comment="备注")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=_now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class DwModelFieldRecord(Base):
    """模型字段（整表全量替换保存，seq 由后端重排）。

    迁移源实锚：`datara-backend/common/models.py:809-830`（A6-6 详情 / A6-9 字段保存共用）。
    """

    __tablename__ = "t_dw_model_field"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_id: Mapped[int] = mapped_column(Integer, comment="所属模型")
    seq: Mapped[int] = mapped_column(Integer, default=0, comment="字段序（1 起）")
    name: Mapped[str] = mapped_column(String(128), comment="字段名")
    data_type: Mapped[str] = mapped_column(String(64), default="VARCHAR", comment="类型（大写）")
    length: Mapped[str] = mapped_column(String(32), default="", comment="长度/精度 p（字符串保真）")
    precision: Mapped[str] = mapped_column(String(32), default="", comment="小数位 s")
    nullable: Mapped[bool] = mapped_column(Boolean, default=True, comment="可空")
    default_value: Mapped[str] = mapped_column(String(255), default="", comment="默认值")
    comment: Mapped[str] = mapped_column(String(255), default="", comment="字段注释")
    is_pk: Mapped[bool] = mapped_column(Boolean, default=False, comment="主键")
    is_partition: Mapped[bool] = mapped_column(Boolean, default=False, comment="分区键（仅 doris 生效）")
    dict_ref: Mapped[str] = mapped_column(String(128), default="", comment="关联字典/维表 code")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=_now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    __table_args__ = (Index("idx_dwfield_model", "model_id", "seq"),)


class DwModelRelationRecord(Base):
    """模型关系（ER 边 = 血缘声明；fields 存 JSON 文本，去重由代码比较）。

    迁移源实锚：`datara-backend/common/models.py:833-854`（A6-4/A6-5 ER 读写共用）。
    """

    __tablename__ = "t_dw_model_relation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    src_model_id: Mapped[int] = mapped_column(Integer, comment="上游模型 id")
    tgt_model_id: Mapped[int] = mapped_column(Integer, comment="下游模型 id")
    rel_type: Mapped[str] = mapped_column(String(8), default="1:N", comment="1:1/1:N/N:N")
    src_fields: Mapped[str] = mapped_column(String(512), default="[]", comment="上游字段名 JSON 数组文本")
    tgt_fields: Mapped[str] = mapped_column(String(512), default="[]", comment="下游字段名 JSON 数组文本")
    join_desc: Mapped[str] = mapped_column(String(255), default="", comment="关联说明")
    created_by: Mapped[str] = mapped_column(String(64), default="", comment="创建人")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=_now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    # 去重由应用层代码比较完成（旧侧同注）：src_fields/tgt_fields 为 JSON 文本、长度不固定，
    # MySQL utf8mb4 下组合唯一键超 InnoDB 3072 字节单索引上限，故不建 DB 级唯一约束。
    __table_args__ = (
        Index("idx_dwrel_src", "src_model_id"),
        Index("idx_dwrel_tgt", "tgt_model_id"),
    )


class DwModelVersionRecord(Base):
    """模型版本快照（A6-12 列表 / A6-13 创建 / A6-14 diff / A6-15 回滚共用）。

    迁移源实锚：`datara-backend/common/models.py:857-871`（`DwModelVersion`，列/类型/约束逐项照抄）。
    `snapshot_json` 为**主数据 + fields + relations 全量 JSON**（旧侧 `_model_snapshot` 产物），
    读取方为 A6-14 diff 与 A6-15 回滚（均 `json.loads`），故文本形态须与旧侧完全一致。
    """

    __tablename__ = "t_dw_model_version"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    model_id: Mapped[int] = mapped_column(Integer, comment="所属模型")
    version: Mapped[int] = mapped_column(Integer, comment="快照版本号")
    snapshot_json: Mapped[str] = mapped_column(
        MediumText, comment="主数据+fields+relations 全量 JSON"
    )
    change_note: Mapped[str] = mapped_column(String(255), default="", comment="变更说明")
    created_by: Mapped[str] = mapped_column(String(64), default="", comment="操作人")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=_now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    __table_args__ = (UniqueConstraint("model_id", "version", name="uq_dw_model_ver"),)


class DataSourceRecord(Base):
    """数据源（**A6-17 物理化目标**；本表在旧侧属 I1/I4 数据源域，建模域仅作关联引用）。

    迁移源实锚：`datara-backend/common/models.py:245-265`（`DataSource`，列/类型/默认值逐项照抄）。

    **为什么由建模域承载**：A6 对照登记 §二.3「关联表」把 `t_data_source`
    （`DataSource`，实锚 `common/models.py:245-265`）登记为建模域物理化目标，
    且 WBS 增量 17 验收门含「门 2（数据模型）」；旧侧 `physicalize` 的 exec 分支
    必须读该行取连接串（`api/model.py:520-523`）。缺此表则 exec 模式「可声明不可执行」。

    ★候裁 ①：`rebuild/datasource/models.py` 刻意用**另一张表**
    （`rebuild_project_datasource`，项目作用域 + 内联连接列）承载 rebuild 侧数据源，
    与全局 `t_data_source`（`ds_id` 所指）**语义不同、不可替代**。若后续域
    （增量 10 数据源管理后端票）也在共享 `rebuild.common.db.Base` 上定义
    `__tablename__ = "t_data_source"`，将触发
    `InvalidRequestError: Table 't_data_source' is already defined`。
    届时应由监督线裁定「全局数据源表唯一归属域」，本票不擅自合并两域。
    """

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
    create_time: Mapped[datetime] = mapped_column(DateTime, default=_now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class LineageEdgeRecord(Base):
    """运行时血缘边（`t_lineage_edge`，A6-21 血缘合并图的 runtime 半边）。

    迁移源实锚：`datara-backend/common/models.py:460-493`（列/默认值/索引/唯一约束逐项照抄）。
    旧侧该表由 **I5 SQL 血缘 worker** 写入（`common/sqlparser.py` 解析后回写），
    **不是** C22 SYNC 执行器；后者在 rebuild 侧写的是另一张表
    `metrics/models.py:133` 的 `lineage_writeback`（项目作用域，列为
    `source_entity`/`target_entity`，无 `tmp_flag`/`src_type`）—— 二者**语义不同、
    不可替代**（同 `DataSourceRecord` 的取舍形态）。

    A6 对照登记（`2026-10-20-17.1-A6-数仓建模对照登记-Claude.md:80`）将本表登记为
    建模域关联表，并在 `:259` 明确「`t_lineage_edge` 由运行时写入，**迁移时需决定沿用
    还是重建**」。缺此表则 A6-21 的 runtime 半边「可声明不可执行」（域规范禁止）。

    ★候裁 ①：rebuild 侧现有 `lineage_writeback` 是否应升级为/替换本表？
    ②：后续 I5 血缘票若在共享 `rebuild.common.db.Base` 定义同名表，将触发
    `InvalidRequestError: Table 't_lineage_edge' is already defined`，届时由监督线
    裁定「全局血缘边表唯一归属域」，本票不擅自合并两域。
    """

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
        String(255), default="", server_default="", comment="输入表 db.table（空串=无来源，如 INSERT..VALUES）"
    )
    to_table: Mapped[str] = mapped_column(String(255), comment="输出表 db.table")
    # 任一侧 ${tmp.*} 映射为注册名 → 1（门 #10：C22 临时表作来源时同样置 1）
    tmp_flag: Mapped[bool] = mapped_column(Boolean, default=False, comment="边涉及临时注册名 0/1")
    # 血缘来源层：runtime=运行时采集（存量默认）/ design=设计态推导（instance_id=0 标识，uk 不变）
    src_type: Mapped[str] = mapped_column(
        String(16), default="runtime", server_default="runtime", comment="血缘来源 runtime/design"
    )
    create_time: Mapped[datetime] = mapped_column(DateTime, default=_now)

    __table_args__ = (
        UniqueConstraint(
            "wf_code", "instance_id", "node_id", "stmt_no", "from_table", "to_table", name="uk_lineage"
        ),
        Index("idx_ln_from", "from_table"),
        Index("idx_ln_to", "to_table"),
        Index("idx_ln_inst", "instance_id"),
    )


# 建表清单：`Base.metadata.create_all` 按本元组逐域装配（见 `rebuild/api/app.py`）。
MODEL_TABLES = (
    DwLayerRecord.__table__,
    BizDomainRecord.__table__,
    EngineTypeRecord.__table__,
    DwModelRecord.__table__,
    DwModelFieldRecord.__table__,
    DwModelRelationRecord.__table__,
    DwModelVersionRecord.__table__,
    # A6-17 物理化目标（旧侧 I1/I4 域，建模域关联引用；见 `DataSourceRecord` 类注）
    DataSourceRecord.__table__,
    # A6-21 运行时血缘边（旧侧 I5 域，建模域关联引用；见 `LineageEdgeRecord` 类注）
    LineageEdgeRecord.__table__,
)


def dict_counts(session) -> dict[str, int]:
    """三字典表行数（诊断/自测用；空库返回全 0，不抛错）。"""
    return {
        "layers": session.query(func.count()).select_from(DwLayerRecord).scalar() or 0,
        "domains": session.query(func.count()).select_from(BizDomainRecord).scalar() or 0,
        "engines": session.query(func.count()).select_from(EngineTypeRecord).scalar() or 0,
    }
