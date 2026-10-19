"""Persistence records for the R4-SYNC domain.

Contract source: design 正本 §6.4 同步节点（docs/increments/2026-10-14-datara-platform-rebuild-design.md）。

- One saved object = "workflow version × task" sync (同步节点) definition,
  keyed by (project, workflow, version, task) — the same slot semantics as
  R4-DEPENDENCY; re-saving the slot replaces the draft configuration.
- Source/target references (form fields 1–4: 源数据源/源表/目标数据源/目标表)
  point at registered project datasources + schema/object names.
- 字段映射 snapshot (自动映射 + 用户调整映射, form fields 7–8) is stored
  verbatim as JSON; each mapping entry records exactly the §6.4 mapping
  8 fields (source_column/target_column/source_type/target_type/
  transform_expression/nullable/default_value/mapping_status). The run-time
  consumes the snapshot saved with the workflow version (映射随版本引用).
- 转换配置 JSON holds 表达式转换/过滤条件 (form fields 9–10); 目标属性 JSON
  holds 分区和增量字段/主键和冲突处理/批大小和并发度 (form fields 11–13).
- 字段探查/类型探查 (form fields 5–6) are read-time capabilities served from
  the datasource domain metadata catalog — they are not persisted here.
- created_at/updated_at are DB-generated (design §9 convention).
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from rebuild.common.db import Base


class SyncTaskDefinitionRecord(Base):
    """sync_task_definition — per (project, workflow version, task) sync definition snapshot."""

    __tablename__ = "sync_task_definition"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "workflow_id",
            "workflow_version",
            "task_id",
            name="uq_sync_task_definition_slot",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    workflow_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    workflow_version: Mapped[int] = mapped_column(Integer, nullable=False)
    task_id: Mapped[str] = mapped_column(String(128), nullable=False)
    # 源数据源/源表 (§6.4 form fields 1–2): registered datasource + object reference.
    src_datasource_id: Mapped[int] = mapped_column(Integer, nullable=False)
    src_schema: Mapped[str] = mapped_column(String(255), nullable=False)
    src_object: Mapped[str] = mapped_column(String(255), nullable=False)
    # 目标数据源/目标表 (§6.4 form fields 3–4).
    tgt_datasource_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tgt_schema: Mapped[str] = mapped_column(String(255), nullable=False)
    tgt_object: Mapped[str] = mapped_column(String(255), nullable=False)
    # 字段映射 snapshot (§6.4 form fields 7–8): list of mapping 8-field entries.
    field_mappings_json: Mapped[str] = mapped_column(Text, nullable=False)
    # 转换配置 (§6.4 form fields 9–10): 表达式转换/过滤条件.
    transform_config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 目标属性 (§6.4 form fields 11–13): 分区增量/主键冲突/批大小并发度.
    target_properties_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), server_onupdate=func.current_timestamp()
    )
