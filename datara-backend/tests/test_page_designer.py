"""页面设计器 API 单测（资源目录/预览；sqlite 内存库，零外部依赖）。"""

import sys
from pathlib import Path
from types import SimpleNamespace

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from api.auth import get_current_user  # noqa: E402
from common.models import DataSource  # noqa: E402


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


# ---------------------------------------------------------------- 数据预览


def test_preview_rejects_non_select(client):
    set_role(client.app, "dev")
    r = client.post("/api/v1/page-designer/preview", json={
        "queries": [{"id": "q1", "datasourceId": 1, "sql": "DELETE FROM t"}]})
    assert r.status_code == 422


def test_preview_caps_rows(monkeypatch, client, db_session):
    db_session.add(DataSource(id=1, name="dw", type="mysql"))
    db_session.commit()
    set_role(client.app, "dev")
    called = {}

    def fake_run(ds, sql, cap):
        called["sql"], called["cap"] = sql, cap
        return {"id": "q1", "columns": ["a"], "rows": [[str(i)] for i in range(cap)],
                "truncated": True, "error": ""}

    monkeypatch.setattr("api.page_designer._run_readonly", fake_run)
    r = client.post("/api/v1/page-designer/preview", json={
        "queries": [{"id": "q1", "datasourceId": 1, "sql": "SELECT a FROM t"}]})
    assert r.status_code == 200
    assert called["cap"] == 100
    assert len(r.json()["data"]["results"]["q1"]["rows"]) == 100


def test_preview_widget_errors_aggregated(monkeypatch, client, db_session):
    """失败组件聚合进 widgetErrors（按 body.queries 顺序），成功项不进；results 既有形状不变。"""
    db_session.add(DataSource(id=1, name="dw", type="mysql"))
    db_session.commit()
    set_role(client.app, "dev")
    monkeypatch.setattr(
        "api.page_designer._run_readonly",
        lambda ds, sql, cap: {"id": "", "columns": ["a"], "rows": [["1"]],
                              "truncated": False, "error": ""})
    r = client.post("/api/v1/page-designer/preview", json={
        "queries": [
            {"id": "ok1", "datasourceId": 1, "sql": "SELECT a FROM t"},
            {"id": "bad1", "datasourceId": 999, "sql": "SELECT a FROM t"},
            {"id": "ok2", "datasourceId": 1, "sql": "SELECT b FROM t"},
        ]})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["widgetErrors"] == [{"id": "bad1", "error": "数据源 999 不存在"}]
    # 向后兼容：error 仍落在各自 result 内
    assert data["results"]["bad1"]["error"] == "数据源 999 不存在"
    assert data["results"]["ok1"]["error"] == ""


def test_preview_all_success_widget_errors_empty(monkeypatch, client, db_session):
    """全部成功时 widgetErrors 为空数组。"""
    db_session.add(DataSource(id=1, name="dw", type="mysql"))
    db_session.commit()
    set_role(client.app, "dev")
    monkeypatch.setattr(
        "api.page_designer._run_readonly",
        lambda ds, sql, cap: {"id": "", "columns": ["a"], "rows": [["1"]],
                              "truncated": False, "error": ""})
    r = client.post("/api/v1/page-designer/preview", json={
        "queries": [{"id": "q1", "datasourceId": 1, "sql": "SELECT a FROM t"}]})
    assert r.status_code == 200
    assert r.json()["data"]["widgetErrors"] == []
