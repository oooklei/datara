"""组件统一规格下发端点单测（实施计划 Task 3，方案 §2.3）。

覆盖：
1. GET /api/v1/components/spec 只列已发布组件，每项含 8 要素骨架键
   （缺失项显式 None 而非缺键，前端可稳定按键取值）；
2. ETag/304：首次响应带 ETag，If-None-Match 命中返回 304；
3. 组件下线后从 spec 清单消失（仅 published 进清单）。

DB：sqlite 内存库（conftest compiles 补丁），零外部依赖。
"""

import sys
from pathlib import Path
from types import SimpleNamespace

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from api.auth import get_current_user  # noqa: E402

# 8 要素骨架键（方案 §2.3：缺失项显式 None）
SKELETON_KEYS = ["identity", "description", "inputs", "outputs", "visual",
                 "behaviors", "dropPolicy", "extensions"]


def set_role(app, role: str) -> None:
    """切换注入用户角色（与 conftest.set_role 同实现，文件内自含）。"""
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1, user_name="tester", user_role=role)


# ---------------------------------------------------------------- 种子 helper

def _make_frozen(client, type_name="spec_demo", spec=None) -> dict:
    """建组件（spec 直接合法）→ 冻结 v1（与 test_component_design._make_frozen 同模式）。"""
    body = {
        "type": type_name, "name": "规格演示", "profile": "dag",
        "execution_model": "dag-engine", "executor": "sql",
        "executable": True,
        "spec": spec if spec is not None else {
            "fields": [{"key": "sql", "label": "SQL", "uiType": "text"}]},
    }
    r = client.post("/api/v1/components", json=body)
    assert r.status_code == 200, r.text
    r = client.post("/api/v1/components/%s/versions" % type_name, json={})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _publish(client, type_name="spec_demo"):
    """发布 v1（publish_component 由 admin 独占，§14）。"""
    set_role(client.app, "admin")
    return client.post("/api/v1/components/%s/publish" % type_name,
                       json={"version": 1, "draft_rev": 0})


def _offline(client, type_name):
    """下线组件（offline 属 publish_component，admin 独占；dev 403）。"""
    set_role(client.app, "admin")
    return client.post("/api/v1/components/%s/offline" % type_name, json={})


# ---------------------------------------------------------------- 用例


def test_spec_lists_published_components(client):
    """已发布组件进清单，8 要素骨架键齐备，缺失项显式 None 而非缺键。"""
    _make_frozen(client)
    assert _publish(client).status_code == 200
    r = client.get("/api/v1/components/spec")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "items" in body
    items = {i["type"]: i for i in body["items"]}
    assert "spec_demo" in items
    item = items["spec_demo"]
    for key in SKELETON_KEYS:
        assert key in item, "骨架键缺失：%s" % key
    # spec 未声明的要素显式 None（behaviors/dropPolicy/extensions）
    assert item["behaviors"] is None
    assert item["dropPolicy"] is None
    assert item["extensions"] is None
    # 已声明要素正确映射
    assert item["identity"]["type"] == "spec_demo"
    assert item["identity"]["displayName"] == "规格演示"
    assert item["inputs"] == [{"key": "sql", "label": "SQL", "uiType": "text"}]


def test_spec_etag_304(client):
    """条件请求：首次 200 带 ETag；If-None-Match 命中 → 304（无 body）。"""
    _make_frozen(client)
    assert _publish(client).status_code == 200
    r1 = client.get("/api/v1/components/spec")
    assert r1.status_code == 200
    etag = r1.headers["etag"]
    r2 = client.get("/api/v1/components/spec", headers={"If-None-Match": etag})
    assert r2.status_code == 304
    assert r2.headers["etag"] == etag


def test_spec_offline_component_excluded(client):
    """下线组件不在 spec 清单中（仅 state=published 进下发范围）。"""
    _make_frozen(client)
    assert _publish(client).status_code == 200
    assert "spec_demo" in [i["type"] for i in
                           client.get("/api/v1/components/spec").json()["items"]]
    assert _offline(client, "spec_demo").status_code == 200
    r = client.get("/api/v1/components/spec")
    assert r.status_code == 200
    assert "spec_demo" not in [i["type"] for i in r.json()["items"]]
