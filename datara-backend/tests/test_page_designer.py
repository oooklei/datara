"""页面设计器 API 单测（资源目录/预览；sqlite 内存库，零外部依赖）。"""

import sys
from pathlib import Path
from types import SimpleNamespace

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from api.auth import get_current_user  # noqa: E402


def set_role(app, role: str) -> None:
    """切换注入用户角色（权限矩阵用例；与 conftest.set_role 同实现）。"""
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1, user_name="tester", user_role=role)


# ---------------------------------------------------------------- 资源目录


def test_resources_tree(client):
    set_role(client.app, "dev")
    r = client.get("/api/v1/page-designer/resources")
    assert r.status_code == 200
    data = r.json()["data"]
    assert set(data.keys()) == {"datasources", "workflows", "globalParams", "timeParams", "components"}
    assert isinstance(data["timeParams"], list) and data["timeParams"][0]["path"].startswith("$")
