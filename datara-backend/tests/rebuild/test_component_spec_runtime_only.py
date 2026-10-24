"""门5① TDD：sync(C17)/file_sync(C24) runtimeOnly 标记实测（normalizeSpec 契约）。

权威锚（同步编排端点合一与设计态分离设计.md L69 四排除 + 权威设计 v3 L515）：
- 设计态禁运行态组件：C17 sync / C24 file_sync 标 runtimeOnly，
  spec 输出 visual.paletteVisible=false（D1 闸门 §13-5 normalizeSpec 契约）；
- 消费方：datara-newweb Palette.vue L80 `if (visual.paletteVisible === false) return null`
  （palette 排除）+ WorkflowGraphWorkbench SYNC_PALETTE_TYPES（画布拖入排除）。

判定源（1.9 真库实锚 2026-10-24）：
- C17 sync / C24 file_sync：execution_model='dag-engine'（executor sync/file_sync）；
- 数据同步组 7 项：execution_model='passthrough'（endpoint_select/field_map/
  field_map_union/condition_set）或 'template'（src_base_orch/tgt_base_orch/file_sync_orch），
  均必须保持 palette 可见（不得被误伤过滤）。
"""
import json

from fastapi.testclient import TestClient

from common.models import Component, ComponentVersion
from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository


def _client():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="runtime-only-secret")
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
        session.commit()
    login = client.post("/api/v1/rebuild/login", json={"username": "admin", "password": "admin-pass"})
    return client, app, {"Authorization": f"Bearer {login.json()['data']['token']}"}


def _component(*, identifier: int, type_name: str, execution_model: str):
    return Component(
        id=identifier, type=type_name, name=type_name.title(), category="sync", profile="dag",
        scope="builtin", execution_model=execution_model, executable=True,
        state="published", published_version=1, draft_rev=0,
    )


def _version(*, identifier: int, component_id: int, type_name: str, spec_json: str = '{}'):
    return ComponentVersion(
        id=identifier, component_id=component_id, type=type_name, version=1,
        state="published", spec_json=spec_json, spec_hash="hash",
    )


def _seed(app, rows):
    with app.state.session_factory() as session:
        for component, version in rows:
            session.add_all([component, version])
        session.commit()


def _fetch_items(client, headers):
    response = client.get("/api/v1/rebuild/components/spec", headers=headers)
    assert response.status_code == 200
    return {item["type"]: item for item in response.json()["items"]}


def test_c17_c24_runtime_only_are_absent_from_design_catalogue():
    """C17/C24 are execution materializations and never enter design JSON."""
    client, app, headers = _client()
    try:
        _seed(app, [
            (_component(identifier=16, type_name="sync", execution_model="dag-engine"),
             _version(identifier=16, component_id=16, type_name="sync",
                      spec_json=json.dumps({"summary": "同步执行", "icon": "⇄"}))),
            (_component(identifier=17, type_name="file_sync", execution_model="dag-engine"),
             _version(identifier=17, component_id=17, type_name="file_sync",
                      spec_json=json.dumps({"summary": "文件同步执行", "icon": "⇄"}))),
        ])
        items = _fetch_items(client, headers)
        assert items == {}
    finally:
        client.__exit__(None, None, None)


def test_sync_orch_seven_items_not_filtered_by_runtime_only_rule():
    """数据同步组 7 项（passthrough/template）不得被 runtimeOnly 规则误伤。"""
    client, app, headers = _client()
    try:
        seven = [
            ("endpoint_select", "passthrough"),
            ("field_map", "passthrough"),
            ("field_map_union", "passthrough"),
            ("condition_set", "passthrough"),
            ("src_base_orch", "template"),
            ("tgt_base_orch", "template"),
            ("file_sync_orch", "template"),
        ]
        _seed(app, [
            (_component(identifier=100 + i, type_name=t, execution_model=m),
             _version(identifier=100 + i, component_id=100 + i, type_name=t))
            for i, (t, m) in enumerate(seven)
        ])
        items = _fetch_items(client, headers)
        assert len(items) == 7
        for type_name, _ in seven:
            visual = items[type_name]["visual"]
            assert visual.get("paletteVisible") is not False, (
                f"{type_name} 是数据同步组 palette 成员，不得被 runtimeOnly 规则过滤"
            )
    finally:
        client.__exit__(None, None, None)
