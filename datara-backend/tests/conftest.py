"""pytest 共享夹具：sqlite 内存库 + 鉴权/DB 依赖覆盖。

背景：写路径端点（组件草稿等）的单测需要真实 ORM 行为，但不依赖外部 MySQL/Redis：
- sqlite 内存库 + Base.metadata.create_all 建全量表；
- MySQL 方言类型（LONGTEXT/MEDIUMTEXT）在 sqlite 上无渲染器，compiles 补丁降为 TEXT；
- BigInteger 主键在 sqlite 渲染为 BIGINT 时非 rowid 别名、自增失效，补丁为 INTEGER；
- get_db / get_current_user 用 dependency_overrides 注入，绕开 MySQL 会话与 Redis 会话。

TestClient 不进入 with 上下文，create_app 的 lifespan（init_db/ZK）不会触发。
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.mysql import LONGTEXT, MEDIUMTEXT
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


@compiles(LONGTEXT, "sqlite")
def _sqlite_longtext(element, compiler, **kw):  # noqa: ANN001
    return "TEXT"


@compiles(MEDIUMTEXT, "sqlite")
def _sqlite_mediumtext(element, compiler, **kw):  # noqa: ANN001
    return "TEXT"


@compiles(BigInteger, "sqlite")
def _sqlite_bigint(element, compiler, **kw):  # noqa: ANN001
    return "INTEGER"


from api.auth import get_current_user  # noqa: E402
from api.main import create_app  # noqa: E402
from common.db import get_db  # noqa: E402
from common.models import Base  # noqa: E402


@pytest.fixture()
def db_session():
    # StaticPool：全部会话复用同一连接（sqlite:// 每连接独立内存库，否则建表不可见）
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def client(db_session):
    """dev 角色（可设计不可发布）的测试客户端；改角色用 set_role helper。"""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    set_role(app, "dev")
    return TestClient(app)


def set_role(app, role: str) -> None:
    """切换当前注入用户角色（权限矩阵用例）。"""
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1, user_name="tester", user_role=role)
