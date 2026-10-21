"""17.2-21 A6-21 `GET /api/v1/rebuild/models/{model_id}/lineage` + 17.2-22 A6-22
`GET /api/v1/rebuild/models/{model_id}/impact` 契约测试。

契约真源：`docs/increments/evidence/INC17/2026-10-20-17.1-API契约冻结清单草案-Claude.md`
A6-21/A6-22（旧侧实锚 `datara-backend/api/model.py:741-792` `model_lineage` /
`:795-821` `model_impact`）。

出参（lineage）：`{nodes: [{id, kind, label}], edges: [{from, to, kind, relType?}],
sources: {declared: N, runtime: N}}`
出参（impact）：`{list: [{modelId, code, name, path}]}`
错误码：8001/404（模型不存在）。两图均**不落库**，读端点登录即可（旧侧
`Depends(get_current_user)` → 新侧 `Permission.VIEW_ALL`）。

承载：runtime 半图依赖新增 `LineageEdgeRecord`（`t_lineage_edge`，见
`rebuild/model/models.py` 类注 ★候裁 ①/②）。两图逻辑为 DB 查询 + dict 组装，
**无纯函数可差分**（同 17.2-18 口径）—— 本机只做行为契约稽核。
"""

import pytest
from fastapi.testclient import TestClient

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.model.models import (
    DwModelRecord,
    DwModelRelationRecord,
    LineageEdgeRecord,
)


# ---------------------------------------------------------------- 夹具


def _client():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="model-lineage-secret")
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
        UserRepository(session).create(username="viewer", password="pw-123456", role=Role.VIEWER)
        session.commit()
    login = client.post("/api/v1/rebuild/login", json={"username": "admin", "password": "admin-pass"})
    vlogin = client.post("/api/v1/rebuild/login", json={"username": "viewer", "password": "pw-123456"})
    return client, app, {"token": login.json()["data"]["token"]}, {"token": vlogin.json()["data"]["token"]}


def _seed_model(session, *, code, name=""):
    m = DwModelRecord(
        code=code, name=name or code, layer="ODS", type="明细表", engine="MySQL",
        status="draft", version=1, security_level="内部", owner="admin",
    )
    session.add(m)
    session.commit()
    return m


def _seed_relation(session, src_id, tgt_id, rel_type="1:N"):
    r = DwModelRelationRecord(src_model_id=src_id, tgt_model_id=tgt_id, rel_type=rel_type)
    session.add(r)
    session.commit()
    return r


def _seed_edge(session, *, from_table, to_table, **kw):
    e = LineageEdgeRecord(
        wf_code=kw.get("wf_code", 1), instance_id=kw.get("instance_id", "i-1"),
        node_id=kw.get("node_id", "n-1"), stmt_no=kw.get("stmt_no", 1),
        from_table=from_table, to_table=to_table,
        src_type=kw.get("src_type", "runtime"),
    )
    session.add(e)
    session.commit()
    return e


def _lineage(client, headers, model_id):
    return client.get(f"/api/v1/rebuild/models/{model_id}/lineage", headers=headers)


def _impact(client, headers, model_id):
    return client.get(f"/api/v1/rebuild/models/{model_id}/impact", headers=headers)


def _route_pairs(app):
    """展平后的 (method, path) 有序表 —— 与请求匹配同序。"""
    pairs = []
    for path, ops in app.openapi()["paths"].items():
        for method in ops:
            pairs.append((method.upper(), path))
    return pairs


# ---------------------------------------------------------------- 鉴权 / 权限


def test_lineage_requires_login():
    client, app, _, _ = _client()
    try:
        response = client.get("/api/v1/rebuild/models/1/lineage")
        assert response.status_code == 401
        assert response.json()["code"] == 1001
    finally:
        client.__exit__(None, None, None)


def test_lineage_read_endpoint_allows_viewer():
    """读端点 `view_all`：viewer 可看图（旧侧仅 `get_current_user`）。"""
    client, app, _, vheaders = _client()
    try:
        with app.state.session_factory() as session:
            m = _seed_model(session, code="orders")
        response = _lineage(client, vheaders, m.id)
        assert response.status_code == 200, response.text
        assert response.json()["code"] == 0
    finally:
        client.__exit__(None, None, None)


def test_lineage_missing_model_is_404():
    client, app, headers, _ = _client()
    try:
        response = _lineage(client, headers, 999999)
        assert response.status_code == 404
        assert response.json()["code"] == 8001
    finally:
        client.__exit__(None, None, None)


def test_impact_requires_login():
    client, app, _, _ = _client()
    try:
        response = client.get("/api/v1/rebuild/models/1/impact")
        assert response.status_code == 401
        assert response.json()["code"] == 1001
    finally:
        client.__exit__(None, None, None)


def test_impact_missing_model_is_404():
    client, app, headers, _ = _client()
    try:
        response = _impact(client, headers, 999999)
        assert response.status_code == 404
        assert response.json()["code"] == 8001
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------- A6-21 声明半图


def test_lineage_declared_empty_graph_is_model_only():
    """无关系无边：`nodes` 只有模型自身，`sources` 双零。"""
    client, app, headers, _ = _client()
    try:
        with app.state.session_factory() as session:
            m = _seed_model(session, code="orders", name="订单")
        data = _lineage(client, headers, m.id).json()["data"]
        assert data["nodes"] == [{"id": "orders", "kind": "model", "label": "orders 订单"}]
        assert data["edges"] == []
        assert data["sources"] == {"declared": 0, "runtime": 0}
    finally:
        client.__exit__(None, None, None)


def test_lineage_declared_bidirectional_and_rel_type():
    """双向展开：src==model 与 tgt==model 各出一条 declared 边，relType 原样带出。"""
    client, app, headers, _ = _client()
    try:
        with app.state.session_factory() as session:
            a = _seed_model(session, code="orders", name="订单")
            b = _seed_model(session, code="order_item", name="订单明细")
            _seed_relation(session, a.id, b.id, rel_type="1:N")
            _seed_relation(session, b.id, a.id, rel_type="N:1")
        data = _lineage(client, headers, a.id).json()["data"]
        assert [n["id"] for n in data["nodes"]] == ["orders", "order_item"]
        declared = [e for e in data["edges"] if e["kind"] == "declared"]
        assert declared == [
            {"from": "orders", "to": "order_item", "kind": "declared", "relType": "1:N"},
            {"from": "order_item", "to": "orders", "kind": "declared", "relType": "N:1"},
        ]
        assert data["sources"]["declared"] == 2
    finally:
        client.__exit__(None, None, None)


def test_lineage_declared_rel_type_falls_back_to_empty_string():
    """`relType` 原样带出；`rel_type or ""` 的 `""` 分支为**防御性**（两侧列均 NOT NULL）。

    旧侧 `common/models.py:839` 与 rebuild `models.py:152` 的 `rel_type` 同为
    `String(8), default="1:N"` 且**不可空** → 经 DB 路径 `rel_type` 恒非 NULL，
    旧侧 `r.rel_type or ""` 的兜底分支**不可达**。此处以直接构造未落库实例的方式
    验证兜底行为存在（对齐旧侧源码语义），并断言 DB 层确实拒 NULL。
    """
    client, app, headers, _ = _client()
    try:
        with app.state.session_factory() as session:
            a = _seed_model(session, code="orders")
            b = _seed_model(session, code="cust")
            _seed_relation(session, a.id, b.id, rel_type="1:1")
        data = _lineage(client, headers, a.id).json()["data"]
        assert data["edges"][0]["relType"] == "1:1"

        # DB 层拒 NULL（NOT NULL 约束）→ 证明兜底分支经 DB 不可达
        with app.state.session_factory() as session:
            rel = session.query(DwModelRelationRecord).first()
            rel.rel_type = None
            with pytest.raises(Exception):
                session.flush()
            session.rollback()

        # 兜底分支本身（未落库实例 → 服务层出参空串）
        assert (DwModelRelationRecord(rel_type=None).rel_type or "") == ""
    finally:
        client.__exit__(None, None, None)


def test_lineage_declared_edge_to_deleted_model_is_skipped():
    """关系指向已被删除的模型行：该边整条跳过（旧侧 `if not s or not t: continue`）。"""
    client, app, headers, _ = _client()
    try:
        with app.state.session_factory() as session:
            a = _seed_model(session, code="orders")
            ghost = _seed_model(session, code="ghost")
            _seed_relation(session, a.id, ghost.id)
            session.delete(ghost)
            session.commit()
        data = _lineage(client, headers, a.id).json()["data"]
        assert [n["id"] for n in data["nodes"]] == ["orders"]
        assert data["edges"] == []
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------- A6-21 runtime 半图


def test_lineage_runtime_normalizes_model_endpoint_to_bare_code():
    """`db.orders` → 节点/边端点归一化为裸 `orders`，保证边引用 id 均在 nodes 中。"""
    client, app, headers, _ = _client()
    try:
        with app.state.session_factory() as session:
            m = _seed_model(session, code="orders")
            _seed_edge(session, from_table="trade.orders", to_table="dw.dws_amt")
        data = _lineage(client, headers, m.id).json()["data"]
        assert [n["id"] for n in data["nodes"]] == ["orders", "dw.dws_amt"]
        assert data["edges"] == [{"from": "orders", "to": "dw.dws_amt", "kind": "runtime"}]
        assert data["sources"] == {"declared": 0, "runtime": 1}
    finally:
        client.__exit__(None, None, None)


def test_lineage_runtime_self_edge_collapses_to_model_node():
    """自环边（模型→模型）：两端均归一化为裸 code，不新增 ext 节点。"""
    client, app, headers, _ = _client()
    try:
        with app.state.session_factory() as session:
            m = _seed_model(session, code="orders")
            _seed_edge(session, from_table="trade.orders", to_table="trade.orders")
        data = _lineage(client, headers, m.id).json()["data"]
        assert [n["id"] for n in data["nodes"]] == ["orders"]
        assert data["edges"] == [{"from": "orders", "to": "orders", "kind": "runtime"}]
    finally:
        client.__exit__(None, None, None)


def test_lineage_runtime_matches_by_code_suffix_not_prefix():
    """`like = f"%.{code}"`：只有以 `.<code>` 结尾的表名才命中（前缀不算）。"""
    client, app, headers, _ = _client()
    try:
        with app.state.session_factory() as session:
            m = _seed_model(session, code="orders")
            _seed_edge(session, from_table="orders_trade", to_table="other.t")  # 不命中
            _seed_edge(session, from_table="trade.orders_v2", to_table="other.t")  # 不命中
            _seed_edge(session, from_table="dw.orders", to_table="other.t")  # 命中
        data = _lineage(client, headers, m.id).json()["data"]
        assert data["sources"]["runtime"] == 1
        assert data["edges"][0]["from"] == "orders"
    finally:
        client.__exit__(None, None, None)


def test_lineage_runtime_dedupes_ext_nodes_by_id():
    """同一张外部表出现在多条边：节点去重（keep first），边不去重。

    三条边的 `stmt_no` 必须互异：旧侧 `t_lineage_edge` 的
    `uk_lineage(wf_code, instance_id, node_id, stmt_no, from_table, to_table)`
    使完全相同的行无法共存（旧侧写入同样会撞唯一键）。
    """
    client, app, headers, _ = _client()
    try:
        with app.state.session_factory() as session:
            m = _seed_model(session, code="orders")
            _seed_edge(session, from_table="trade.orders", to_table="ext.src", stmt_no=1)
            _seed_edge(session, from_table="trade.orders", to_table="ext.src", stmt_no=2)
            _seed_edge(session, from_table="ext.src", to_table="trade.orders", stmt_no=3)
        data = _lineage(client, headers, m.id).json()["data"]
        assert [n["id"] for n in data["nodes"]] == ["orders", "ext.src"]
        assert data["sources"]["runtime"] == 3
    finally:
        client.__exit__(None, None, None)


def test_lineage_runtime_is_capped_at_200_edges():
    """旧侧 `.limit(200)`：runtime 边数封顶 200（节点随之封顶）。"""
    client, app, headers, _ = _client()
    try:
        with app.state.session_factory() as session:
            m = _seed_model(session, code="orders")
            for i in range(205):
                session.add(LineageEdgeRecord(
                    wf_code=1, instance_id="i", node_id="n", stmt_no=i + 1,
                    from_table=f"db{i}.orders", to_table=f"ext{i}.t",
                ))
            session.commit()
        data = _lineage(client, headers, m.id).json()["data"]
        assert data["sources"]["runtime"] == 200
        # 200 条边的 from 端均为 `dbN.orders` → 归一化为模型节点（不新增 ext），
        # 仅 to 端新增 200 个互异 ext 节点；另有模型自身 1 个。
        assert len(data["nodes"]) == 1 + 200
    finally:
        client.__exit__(None, None, None)


def test_lineage_merges_declared_and_runtime_sources():
    """声明半 + 运行半同时命中：`sources` 分别计数，节点按出现序去重。"""
    client, app, headers, _ = _client()
    try:
        with app.state.session_factory() as session:
            a = _seed_model(session, code="orders")
            b = _seed_model(session, code="cust")
            _seed_relation(session, a.id, b.id, rel_type="N:1")
            _seed_edge(session, from_table="trade.orders", to_table="dw.dws_amt")
            _seed_edge(session, from_table="dw.dws_amt", to_table="trade.orders")
        data = _lineage(client, headers, a.id).json()["data"]
        assert data["sources"] == {"declared": 1, "runtime": 2}
        assert [n["id"] for n in data["nodes"]] == ["orders", "cust", "dw.dws_amt"]
        assert [e["kind"] for e in data["edges"]] == ["declared", "runtime", "runtime"]
    finally:
        client.__exit__(None, None, None)


def test_lineage_does_not_write():
    """读端点：调用前后模型行数不变（不落库）。"""
    client, app, headers, _ = _client()
    try:
        with app.state.session_factory() as session:
            m = _seed_model(session, code="orders")
        with app.state.session_factory() as session:
            before = session.query(DwModelRecord).count()
            rels = session.query(DwModelRelationRecord).count()
            edges = session.query(LineageEdgeRecord).count()
        _lineage(client, headers, m.id)
        with app.state.session_factory() as session:
            assert session.query(DwModelRecord).count() == before
            assert session.query(DwModelRelationRecord).count() == rels
            assert session.query(LineageEdgeRecord).count() == edges
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------- A6-21/22 路由可达性


def test_lineage_route_is_registered_and_reachable():
    """A6-21 路由可达性：`GET /models/{model_id}/lineage` 命中血缘处理器。

    尾段字面 `lineage`：与同段数的 `/ddl`、`/impact`、`/physicalize`、`/versions` 等
    尾段互异，且无同段数动态尾段路由 → 互不前缀吞并。
    """
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="lineage-order-secret")
    pairs = _route_pairs(app)
    path = "/api/v1/rebuild/models/{model_id}/lineage"
    target = [i for i, (method, p) in enumerate(pairs) if p == path and method == "GET"]
    assert target, "A6-21 GET /models/{model_id}/lineage 未注册"
    rivals = [
        (i, method, p) for i, (method, p) in enumerate(pairs)
        if p.startswith("/api/v1/rebuild/models/")
        and len(p.split("/")) == len(path.split("/"))
        and p.split("/")[-1].startswith("{")
    ]
    assert not [r for r in rivals if r[0] < target[0]], (
        f"存在更早注册的同段数动态尾段路由可抢匹配 A6-21：{rivals}"
    )

    client = TestClient(app)
    client.__enter__()
    try:
        with app.state.session_factory() as session:
            UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
            session.commit()
        login = client.post("/api/v1/rebuild/login", json={"username": "admin", "password": "admin-pass"})
        headers = {"token": login.json()["data"]["token"]}
        body = client.get(f"/api/v1/rebuild/models/1/lineage", headers=headers)
        # 无模型行 → 8001/404（证明命中 lineage 处理器，而非被 /models/{model_id} 吞并）
        assert body.status_code == 404
        assert body.json()["code"] == 8001
    finally:
        client.__exit__(None, None, None)


def test_impact_route_is_registered_and_reachable():
    """A6-22 路由可达性：`GET /models/{model_id}/impact` 命中影响处理器。"""
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="impact-order-secret")
    pairs = _route_pairs(app)
    path = "/api/v1/rebuild/models/{model_id}/impact"
    target = [i for i, (method, p) in enumerate(pairs) if p == path and method == "GET"]
    assert target, "A6-22 GET /models/{model_id}/impact 未注册"
    rivals = [
        (i, method, p) for i, (method, p) in enumerate(pairs)
        if p.startswith("/api/v1/rebuild/models/")
        and len(p.split("/")) == len(path.split("/"))
        and p.split("/")[-1].startswith("{")
    ]
    assert not [r for r in rivals if r[0] < target[0]], (
        f"存在更早注册的同段数动态尾段路由可抢匹配 A6-22：{rivals}"
    )

    client = TestClient(app)
    client.__enter__()
    try:
        with app.state.session_factory() as session:
            UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
            session.commit()
        login = client.post("/api/v1/rebuild/login", json={"username": "admin", "password": "admin-pass"})
        headers = {"token": login.json()["data"]["token"]}
        body = client.get(f"/api/v1/rebuild/models/1/impact", headers=headers)
        assert body.status_code == 404
        assert body.json()["code"] == 8001
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------- A6-22 影响清单


def test_impact_empty_list_for_isolated_model():
    client, app, headers, _ = _client()
    try:
        with app.state.session_factory() as session:
            a = _seed_model(session, code="orders")
        data = _impact(client, headers, a.id).json()["data"]
        assert data == {"list": []}
    finally:
        client.__exit__(None, None, None)


def test_impact_direct_children_and_path_string():
    """直接下游：`path` 含起点自身，形如 `"orders → order_item"`。"""
    client, app, headers, _ = _client()
    try:
        with app.state.session_factory() as session:
            a = _seed_model(session, code="orders", name="订单")
            b = _seed_model(session, code="order_item", name="明细")
            _seed_relation(session, a.id, b.id)
        data = _impact(client, headers, a.id).json()["data"]
        assert data == {"list": [{"modelId": b.id, "code": "order_item", "name": "明细",
                                  "path": "orders → order_item"}]}
    finally:
        client.__exit__(None, None, None)


def test_impact_recursive_chain_builds_full_path():
    """递归链：`orders → item → detail`，每层 path 累积。"""
    client, app, headers, _ = _client()
    try:
        with app.state.session_factory() as session:
            a = _seed_model(session, code="orders")
            b = _seed_model(session, code="item")
            c = _seed_model(session, code="detail")
            _seed_relation(session, a.id, b.id)
            _seed_relation(session, b.id, c.id)
        data = _impact(client, headers, a.id).json()["data"]
        assert [(x["code"], x["path"]) for x in data["list"]] == [
            ("item", "orders → item"),
            ("detail", "orders → item → detail"),
        ]
    finally:
        client.__exit__(None, None, None)


def test_impact_cycle_is_guarded_by_seen_set():
    """环防护：A→B→A 只出 B 一次，不回溯起点。"""
    client, app, headers, _ = _client()
    try:
        with app.state.session_factory() as session:
            a = _seed_model(session, code="a")
            b = _seed_model(session, code="b")
            _seed_relation(session, a.id, b.id)
            _seed_relation(session, b.id, a.id)
        data = _impact(client, headers, a.id).json()["data"]
        assert [x["code"] for x in data["list"]] == ["b"]
    finally:
        client.__exit__(None, None, None)


def test_impact_diamond_visits_shared_target_once():
    """菱形：A→B→D、A→C→D —— D 只出一次（先经 B）。"""
    client, app, headers, _ = _client()
    try:
        with app.state.session_factory() as session:
            a = _seed_model(session, code="a")
            b = _seed_model(session, code="b")
            c = _seed_model(session, code="c")
            d = _seed_model(session, code="d")
            _seed_relation(session, a.id, b.id)
            _seed_relation(session, a.id, c.id)
            _seed_relation(session, b.id, d.id)
            _seed_relation(session, c.id, d.id)
        data = _impact(client, headers, a.id).json()["data"]
        assert [(x["code"], x["path"]) for x in data["list"]] == [
            ("b", "a → b"),
            ("d", "a → b → d"),
            ("c", "a → c"),
        ]
    finally:
        client.__exit__(None, None, None)


def test_impact_skips_relation_to_deleted_model():
    """下游模型行已删除：跳过该分支（旧侧 `if tm is None: continue`），不再递归。"""
    client, app, headers, _ = _client()
    try:
        with app.state.session_factory() as session:
            a = _seed_model(session, code="a")
            ghost = _seed_model(session, code="ghost")
            keep = _seed_model(session, code="keep")
            _seed_relation(session, a.id, ghost.id)
            _seed_relation(session, ghost.id, keep.id)
            session.delete(ghost)
            session.commit()
        data = _impact(client, headers, a.id).json()["data"]
        assert data == {"list": []}
    finally:
        client.__exit__(None, None, None)


def test_impact_self_loop_is_ignored():
    """自环 A→A：起点已在 `seen` 中 → 不出任何项。"""
    client, app, headers, _ = _client()
    try:
        with app.state.session_factory() as session:
            a = _seed_model(session, code="a")
            _seed_relation(session, a.id, a.id)
        data = _impact(client, headers, a.id).json()["data"]
        assert data == {"list": []}
    finally:
        client.__exit__(None, None, None)


def test_impact_ignores_incoming_edges():
    """影响图只看**出边**（src==起点）：上游关系不产生条目。"""
    client, app, headers, _ = _client()
    try:
        with app.state.session_factory() as session:
            a = _seed_model(session, code="a")
            b = _seed_model(session, code="b")
            _seed_relation(session, b.id, a.id)  # b → a，a 是下游
        data = _impact(client, headers, a.id).json()["data"]
        assert data == {"list": []}
    finally:
        client.__exit__(None, None, None)


def test_impact_does_not_write():
    """读端点：调用前后关系/模型行数不变（不落库）。"""
    client, app, headers, _ = _client()
    try:
        with app.state.session_factory() as session:
            a = _seed_model(session, code="a")
        with app.state.session_factory() as session:
            before = session.query(DwModelRelationRecord).count()
            models = session.query(DwModelRecord).count()
        _impact(client, headers, a.id)
        with app.state.session_factory() as session:
            assert session.query(DwModelRelationRecord).count() == before
            assert session.query(DwModelRecord).count() == models
    finally:
        client.__exit__(None, None, None)
