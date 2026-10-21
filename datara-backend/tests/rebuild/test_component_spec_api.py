import hashlib
import json

from fastapi.testclient import TestClient

from common.models import Component, ComponentVersion
from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository


def _client():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="component-spec-secret")
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
        session.commit()
    login = client.post("/api/v1/rebuild/login", json={"username": "admin", "password": "admin-pass"})
    return client, app, {"Authorization": f"Bearer {login.json()['data']['token']}"}


def _component(*, identifier: int, type_name: str, published_version: int | None = 1, state: str = "published"):
    return Component(
        id=identifier, type=type_name, name=type_name.title(), category="test", profile="dag",
        scope="builtin", execution_model="dag-engine", executable=True,
        state=state, published_version=published_version, draft_rev=0,
    )


def _version(*, identifier: int, component_id: int, type_name: str, version: int = 1,
             state: str = "published", spec_json: str = '{}'):
    return ComponentVersion(
        id=identifier, component_id=component_id, type=type_name, version=version,
        state=state, spec_json=spec_json, spec_hash="hash",
    )


def test_requires_active_ordinary_token_before_reading_database():
    client, _, _ = _client()
    try:
        response = client.get("/api/v1/rebuild/components/spec")
        assert response.status_code == 401
        assert response.json() == {"code": 1001, "msg": "invalid token", "data": None}
        assert "ETag" not in response.headers
    finally:
        client.__exit__(None, None, None)


def test_published_exact_join_stable_bytes_strong_etag_and_304():
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            Component.__table__.create(session.bind, checkfirst=True)
            ComponentVersion.__table__.create(session.bind, checkfirst=True)
            session.add_all([
                _component(identifier=20, type_name="python"),
                _component(identifier=10, type_name="sql"),
                _component(identifier=30, type_name="draft", state="draft"),
                _version(identifier=1, component_id=10, type_name="sql", spec_json=json.dumps({"summary": "SQL"})),
                _version(identifier=2, component_id=20, type_name="python", spec_json=json.dumps({"summary": "Python"})),
                _version(identifier=3, component_id=30, type_name="draft"),
                _version(identifier=4, component_id=10, type_name="sql", version=2),
            ])
            session.commit()

        first = client.get("/api/v1/rebuild/components/spec", headers=headers)
        assert first.status_code == 200
        assert [item["type"] for item in first.json()["items"]] == ["sql", "python"]
        etag = first.headers["etag"]
        assert etag == f'"{hashlib.sha256(first.content).hexdigest()}"'
        assert len(etag) == 66
        second = client.get("/api/v1/rebuild/components/spec", headers={**headers, "If-None-Match": etag})
        assert second.status_code == 304
        assert second.content == b""
        assert second.headers["etag"] == etag
        repeated = client.get("/api/v1/rebuild/components/spec", headers=headers)
        assert repeated.content == first.content
        assert repeated.headers["etag"] == etag
    finally:
        client.__exit__(None, None, None)


def test_invalid_published_json_fails_closed_without_empty_list_fallback():
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            Component.__table__.create(session.bind, checkfirst=True)
            ComponentVersion.__table__.create(session.bind, checkfirst=True)
            session.add(_component(identifier=1, type_name="broken"))
            session.add(_version(identifier=1, component_id=1, type_name="broken", spec_json="{"))
            session.commit()
        response = client.get("/api/v1/rebuild/components/spec", headers=headers)
        assert response.status_code == 500
        assert response.json()["data"] is None
        assert "ETag" not in response.headers
    finally:
        client.__exit__(None, None, None)
