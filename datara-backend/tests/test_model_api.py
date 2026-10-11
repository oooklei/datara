"""I18 数仓建模 API 单测（P0 批）。

DB：sqlite 内存库（conftest compiles 补丁），零外部依赖。
TestClient 不触发 lifespan → init_db/种子不执行，字典数据用 _seed_dicts 手工补。
"""

import sys
from pathlib import Path
from types import SimpleNamespace

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from api.auth import get_current_user  # noqa: E402
from common.models import BizDomain, DwLayer, EngineType  # noqa: E402
from common.db import seed_dict_tables  # noqa: E402


def set_role(client, role: str) -> None:
    """切换注入用户角色（权限矩阵用例）。"""
    client.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1, user_name="tester", user_role=role
    )


def _seed_dicts(db_session) -> None:
    """字典种子（与 init_db 同一入口，幂等）。"""
    seed_dict_tables(db_session)


def test_seed_dict_tables_idempotent(db_session):
    _seed_dicts(db_session)
    _seed_dicts(db_session)  # 二次调用不重复插入
    assert db_session.query(DwLayer).count() == 5
    assert db_session.query(BizDomain).count() >= 4
    assert db_session.query(EngineType).count() == 3
    dwd = db_session.get(DwLayer, "DWD")
    assert dwd.rule.startswith("dwd_")
    gdb = db_session.get(EngineType, "GreatDB")
    assert gdb.ddl == "greatdb" and gdb.xc is True
