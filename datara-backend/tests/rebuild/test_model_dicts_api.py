"""17.2-01 A6-1 `GET /api/v1/rebuild/model-dicts` 契约测试。

契约真源：`docs/increments/evidence/INC17/2026-10-20-17.1-API契约冻结清单草案-Claude.md` A6-1
（旧侧实锚 `datara-backend/api/model.py:98-108`；迁移源字典种子 `common/db.py:59-92`）。
信封 `{code,msg,data}`（R-31）；读端点登录即可（R-33）。
"""

from fastapi.testclient import TestClient

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository


def _client():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="model-dicts-secret")
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
        session.commit()
    login = client.post("/api/v1/rebuild/login", json={"username": "admin", "password": "admin-pass"})
    assert login.status_code == 200, login.text
    return client, app, {"Authorization": f"Bearer {login.json()['data']['token']}"}


def test_model_dicts_requires_login():
    client, app, _ = _client()
    try:
        response = client.get("/api/v1/rebuild/model-dicts")
        assert response.status_code == 401
        body = response.json()
        assert body["code"] == 1001
        assert body["data"] is None
    finally:
        client.__exit__(None, None, None)


def test_model_dicts_returns_three_seeded_dictionaries():
    client, app, headers = _client()
    try:
        response = client.get("/api/v1/rebuild/model-dicts", headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["code"] == 0
        assert body["msg"] == "success"
        data = body["data"]
        assert set(data) == {"layers", "domains", "engines"}

        layers = data["layers"]
        assert [row["code"] for row in layers] == ["ODS", "DWD", "DWS", "ADS", "DIM"]
        assert [row["seq"] for row in layers] == [1, 2, 3, 4, 5]
        assert set(layers[0]) == {"code", "name", "rule", "color", "seq"}
        assert layers[0]["name"] == "原始数据层"

        domains = data["domains"]
        assert [row["name"] for row in domains] == ["交易域", "用户域", "商品域", "流量域"]
        assert set(domains[0]) == {"name", "remark"}

        engines = data["engines"]
        assert [row["name"] for row in engines] == ["Apache Doris", "GreatDB", "MySQL"]
        assert set(engines[0]) == {"name", "ddl", "xc"}
        assert engines[0] == {"name": "Apache Doris", "ddl": "doris", "xc": False}
        # 信创徽标归一为 bool（旧侧 bool(e.xc) 口径）
        assert [row["xc"] for row in engines] == [False, True, False]
    finally:
        client.__exit__(None, None, None)


def test_model_dicts_seed_is_idempotent_across_restarts(tmp_path):
    """文件库二次装配（模拟重启）后种子不得重复写入。

    用文件库而非 `:memory:`：内存库在 `engine.dispose()` 后连接即失，
    属测试载体语义而非产品行为（生产 REBUILD_DB_URL 为持久库）。
    """
    url = f"sqlite+pysqlite:///{tmp_path / 'model-dicts.db'}"

    def boot():
        app = create_app(url, token_secret="model-dicts-secret")
        client = TestClient(app)
        client.__enter__()
        with app.state.session_factory() as session:
            try:
                UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
                session.commit()
            except Exception:
                # 二次装配时 admin 已在库（持久库语义）
                session.rollback()
        login = client.post("/api/v1/rebuild/login", json={"username": "admin", "password": "admin-pass"})
        return client, app, {"Authorization": f"Bearer {login.json()['data']['token']}"}

    client, app, headers = boot()
    try:
        first = client.get("/api/v1/rebuild/model-dicts", headers=headers).json()["data"]
    finally:
        client.__exit__(None, None, None)

    client, app, headers = boot()
    try:
        second = client.get("/api/v1/rebuild/model-dicts", headers=headers).json()["data"]
    finally:
        client.__exit__(None, None, None)

    assert second == first
    assert len(second["layers"]) == 5
    assert len(second["domains"]) == 4
    assert len(second["engines"]) == 3


def test_model_dicts_ignores_unknown_token():
    client, app, _ = _client()
    try:
        response = client.get(
            "/api/v1/rebuild/model-dicts", headers={"Authorization": "Bearer not-a-real-token"}
        )
        assert response.status_code == 401
        assert response.json()["code"] == 1001
    finally:
        client.__exit__(None, None, None)
