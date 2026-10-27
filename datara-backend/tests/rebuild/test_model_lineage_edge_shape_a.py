"""R-46 / 14-01: ``t_lineage_edge`` Shape A 承载回归门。

Shape A 复用旧侧运行时血缘表的物理契约，并由 rebuild 建模域唯一装配该表。
本测试刻意比较 SQLAlchemy 元数据，防止后续迁移时只保留类名却漂移列、索引或幂等键。
"""

from common.models import LineageEdge
from rebuild.model.models import LineageEdgeRecord, MODEL_TABLES


def _column_contract(model):
    def default_shape(default):
        if default is None:
            return None
        value = default.arg
        return "callable" if callable(value) else str(value)

    return {
        column.name: {
            "type": str(column.type),
            "nullable": column.nullable,
            "primary_key": column.primary_key,
            "autoincrement": column.autoincrement,
            "python_default": default_shape(column.default),
            "server_default": None if column.server_default is None else str(column.server_default.arg),
        }
        for column in model.__table__.columns
    }


def _index_contract(model):
    return {
        index.name: tuple(column.name for column in index.columns)
        for index in model.__table__.indexes
    }


def _unique_contract(model):
    return {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in model.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }


def test_shape_a_preserves_legacy_lineage_edge_schema():
    assert LineageEdgeRecord.__tablename__ == LineageEdge.__tablename__ == "t_lineage_edge"
    assert _column_contract(LineageEdgeRecord) == _column_contract(LineageEdge)
    assert _index_contract(LineageEdgeRecord) == _index_contract(LineageEdge) == {
        "idx_ln_from": ("from_table",),
        "idx_ln_to": ("to_table",),
        "idx_ln_inst": ("instance_id",),
    }
    assert _unique_contract(LineageEdgeRecord) == _unique_contract(LineageEdge) == {
        "uk_lineage": (
            "wf_code",
            "instance_id",
            "node_id",
            "stmt_no",
            "from_table",
            "to_table",
        )
    }


def test_shape_a_registers_exactly_one_rebuild_lineage_edge_table():
    lineage_tables = [table for table in MODEL_TABLES if table.name == "t_lineage_edge"]
    assert lineage_tables == [LineageEdgeRecord.__table__]

