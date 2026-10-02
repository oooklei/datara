"""组件治理 M1 三表 + RBAC 单测（实施计划 20260926 Task B1）。

覆盖：
1. 权限位矩阵（治理设计 §14.2）：admin 双权 / dev 仅设计 / analyst·viewer 均无；
   登录 payload perms 与 ROLE_PERMS 同源；
2. 三表元数据结构：t_component / t_component_version / t_component_log 注册到
   Base.metadata，列名/唯一约束/索引对齐 §7.1-§7.3；
3. 建表语句合法性：MySQL 方言 DDL 编译冒烟（CreateTable.compile 零连接，
   init_db 首启 create_all 走同一条 DDL 路径）。

不依赖任何外部服务：仅结构断言与内存编译。
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from api.auth import ROLE_PERMS, user_payload  # noqa: E402
from common.models import (  # noqa: E402
    Base,
    Component,
    ComponentLog,
    ComponentVersion,
)

# ---------------------------------------------------------------- 权限位矩阵


def test_admin_has_both_component_perms():
    perms = ROLE_PERMS["admin"]
    assert "design_component" in perms
    assert "publish_component" in perms


def test_dev_designs_but_cannot_publish():
    """§14.3 决策：dev 可设计但不可发布。"""
    perms = ROLE_PERMS["dev"]
    assert "design_component" in perms
    assert "publish_component" not in perms


def test_analyst_viewer_have_no_component_perms():
    for role in ("analyst", "viewer"):
        perms = ROLE_PERMS[role]
        assert "design_component" not in perms, role
        assert "publish_component" not in perms, role


def test_existing_perms_unchanged():
    """B1 只增不改：既有权限位保持原样（防回归）。"""
    assert ROLE_PERMS["admin"][:4] == ["manage_user", "edit_definition", "run_instance", "view_all"]
    assert ROLE_PERMS["dev"][:3] == ["edit_definition", "run_instance", "view_all"]
    assert ROLE_PERMS["analyst"] == ["run_instance", "view_all"]
    assert ROLE_PERMS["viewer"] == ["view_all"]


def test_login_payload_perms_from_same_source():
    """登录返回的 perms 与 ROLE_PERMS 同一映射（避免双真源）。"""

    class _FakeUser:
        user_name = "u"
        user_role = "dev"

    assert user_payload(_FakeUser())["perms"] == ROLE_PERMS["dev"]


# ---------------------------------------------------------------- 三表结构


def test_three_tables_registered():
    tables = Base.metadata.tables
    for t in ("t_component", "t_component_version", "t_component_log"):
        assert t in tables, t


def test_component_columns_match_spec():
    cols = set(Component.__table__.columns.keys())
    assert cols == {
        "id", "type", "name", "category", "profile", "scope", "execution_model",
        "executor", "executable", "state", "published_version", "draft_rev",
        "description", "tags", "owner_id", "create_time", "update_time",
    }
    # §7.1 关键约束
    assert Component.__table__.columns["type"].unique is True
    assert Component.__table__.columns["execution_model"].nullable is False
    assert Component.__table__.columns["profile"].nullable is False
    assert "spec_json" not in cols, "主表不存 spec_json（§7.1 设计决策）"


def test_component_version_columns_and_constraints():
    t = ComponentVersion.__table__
    cols = set(t.columns.keys())
    assert cols == {
        "id", "component_id", "type", "version", "state", "spec_json",
        "spec_hash", "remark", "published_by", "published_time",
        "create_time", "update_time",
    }
    # 版本冻结的存储层保证：type+version 唯一
    uk = {c.name for c in t.constraints if c.__class__.__name__ == "UniqueConstraint"}
    assert "uk_comp_type_ver" in uk
    uq = next(c for c in t.constraints if getattr(c, "name", None) == "uk_comp_type_ver")
    assert [col.name for col in uq.columns] == ["type", "version"]
    # spec 不可空
    assert t.columns["spec_json"].nullable is False
    assert t.columns["spec_hash"].nullable is False


def test_component_log_columns_and_index():
    t = ComponentLog.__table__
    cols = set(t.columns.keys())
    assert cols == {
        "id", "component_id", "type", "version", "action", "spec_hash",
        "operator", "remark", "operate_time", "create_time", "update_time",
    }
    idx = {i.name for i in t.indexes}
    assert "idx_complog_comp" in idx


def test_component_indexes():
    assert "idx_comp_profile_state" in {i.name for i in Component.__table__.indexes}
    assert "idx_compver_comp" in {i.name for i in ComponentVersion.__table__.indexes}


# ---------------------------------------------------------------- 建表 DDL 冒烟


def test_mysql_ddl_compiles():
    """MySQL 方言零连接编译 CreateTable：init_db 首启 create_all 走同一条 DDL 路径，
    编译通过 ≈ 建表语句合法（列类型/约束/索引名均可渲染）。"""
    from sqlalchemy.schema import CreateTable
    from sqlalchemy.dialects import mysql

    for model in (Component, ComponentVersion, ComponentLog):
        ddl = str(CreateTable(model.__table__).compile(dialect=mysql.dialect()))
        assert "CREATE TABLE" in ddl
        assert model.__tablename__ in ddl


def test_mysql_index_ddl_compiles():
    """索引 DDL 同样可编译（create_all 会一并下发）。"""
    from sqlalchemy.schema import CreateIndex
    from sqlalchemy.dialects import mysql

    for model in (Component, ComponentVersion, ComponentLog):
        for index in model.__table__.indexes:
            str(CreateIndex(index).compile(dialect=mysql.dialect()))
