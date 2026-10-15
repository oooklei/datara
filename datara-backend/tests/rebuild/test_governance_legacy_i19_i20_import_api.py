from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import event

from rebuild.api.app import create_app
from rebuild.governance.legacy_source_reader import I19_SOURCE_COLUMNS, I20_SOURCE_COLUMNS
from rebuild.governance.migrations import MigrationRunner, R3_GOVERNANCE_MIGRATIONS
from rebuild.identity.models import UserRecord
from rebuild.identity.passwords import hash_password


class _Reader:
    def __init__(self, columns):
        self.columns = columns
        self.calls = 0
        self.engine = None

    def read_snapshot(self):
        self.calls += 1
        rows = {table: () for table in self.columns}
        return SimpleNamespace(
            schema="datara_meta",
            rows=rows,
            counts={table: 0 for table in rows},
            captured_at=datetime(2026, 10, 16, tzinfo=timezone.utc),
            digest="a" * 64,
        )


def _client(*, enable_i19=False, enable_i20=False):
    i19_reader = _Reader(I19_SOURCE_COLUMNS)
    i20_reader = _Reader(I20_SOURCE_COLUMNS)
    app = create_app(
        "sqlite+pysqlite:///:memory:",
        token_secret="legacy-import-api-test-secret",
        validation_key="legacy-import-api-validation-key",
        legacy_i19_source_reader_factory=lambda: i19_reader,
        legacy_i20_source_reader_factory=lambda: i20_reader,
        legacy_i19_import_enabled=enable_i19,
        legacy_i20_import_enabled=enable_i20,
    )
    client = TestClient(app)
    client.__enter__()
    MigrationRunner(app.state.session_factory.kw["bind"], R3_GOVERNANCE_MIGRATIONS).apply()
    with app.state.session_factory() as session, session.begin():
        session.add(
            UserRecord(
                id=77,
                username="legacy-import-operator",
                password_hash=hash_password("legacy-import-password"),
                role="admin",
            )
        )
    token = client.post(
        "/api/v1/rebuild/login",
        json={"username": "legacy-import-operator", "password": "legacy-import-password"},
    ).json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}
    project_id = client.post("/api/v1/rebuild/projects", headers=headers, json={"name": "I19/I20 import"}).json()[
        "data"
    ]["id"]
    return client, app, i19_reader, i20_reader, headers, project_id


def test_i19_import_is_disabled_by_default_before_source_or_target_access():
    client, app, i19_reader, _i20_reader, headers, project_id = _client()
    writes = []

    def capture(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().split(maxsplit=1)[0].upper() in {"INSERT", "UPDATE", "DELETE", "REPLACE"}:
            writes.append(statement)

    event.listen(app.state.session_factory.kw["bind"], "before_cursor_execute", capture)
    try:
        response = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/legacy/i19/import",
            headers=headers,
            json={
                "source_digest": "a" * 64,
                "target_digest": "b" * 64,
                "idempotency_key": "i19-test",
                "confirmation": f"IMPORT I19 {project_id} {'a' * 64} {'b' * 64}",
            },
        )
    finally:
        event.remove(app.state.session_factory.kw["bind"], "before_cursor_execute", capture)
        client.__exit__(None, None, None)

    assert response.status_code == 503
    assert response.json()["msg"] == "legacy I19 import is disabled"
    assert i19_reader.calls == 0
    assert writes == []


def test_i20_import_is_disabled_by_default_before_source_or_target_access():
    client, app, _i19_reader, i20_reader, headers, project_id = _client()
    writes = []

    def capture(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().split(maxsplit=1)[0].upper() in {"INSERT", "UPDATE", "DELETE", "REPLACE"}:
            writes.append(statement)

    event.listen(app.state.session_factory.kw["bind"], "before_cursor_execute", capture)
    try:
        response = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/legacy/i20/import",
            headers=headers,
            json={
                "source_digest": "a" * 64,
                "target_digest": "b" * 64,
                "idempotency_key": "i20-test",
                "confirmation": f"IMPORT I20 {project_id} {'a' * 64} {'b' * 64}",
            },
        )
    finally:
        event.remove(app.state.session_factory.kw["bind"], "before_cursor_execute", capture)
        client.__exit__(None, None, None)

    assert response.status_code == 503
    assert response.json()["msg"] == "legacy I20 import is disabled"
    assert i20_reader.calls == 0
    assert writes == []


def test_i20_import_rejects_a_source_digest_that_does_not_match_the_fresh_snapshot():
    client, app, _i19_reader, i20_reader, headers, project_id = _client(enable_i20=True)
    writes = []

    def capture(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().split(maxsplit=1)[0].upper() in {"INSERT", "UPDATE", "DELETE", "REPLACE"}:
            writes.append(statement)

    event.listen(app.state.session_factory.kw["bind"], "before_cursor_execute", capture)
    try:
        response = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/legacy/i20/import",
            headers=headers,
            json={
                "source_digest": "b" * 64,
                "target_digest": "b" * 64,
                "idempotency_key": "i20-stale-source",
                "confirmation": f"IMPORT I20 {project_id} {'b' * 64} {'b' * 64}",
            },
        )
    finally:
        event.remove(app.state.session_factory.kw["bind"], "before_cursor_execute", capture)
        client.__exit__(None, None, None)

    assert response.status_code == 409
    assert response.json()["msg"] == "I20 source digest changed; request a fresh mapping preview"
    assert i20_reader.calls == 1
    assert writes == []


def test_i19_import_rejects_a_source_digest_that_does_not_match_the_fresh_snapshot():
    client, app, i19_reader, _i20_reader, headers, project_id = _client(enable_i19=True)
    writes = []

    def capture(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().split(maxsplit=1)[0].upper() in {"INSERT", "UPDATE", "DELETE", "REPLACE"}:
            writes.append(statement)

    event.listen(app.state.session_factory.kw["bind"], "before_cursor_execute", capture)
    try:
        response = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/legacy/i19/import",
            headers=headers,
            json={
                "source_digest": "b" * 64,
                "target_digest": "b" * 64,
                "idempotency_key": "i19-stale-source",
                "confirmation": f"IMPORT I19 {project_id} {'b' * 64} {'b' * 64}",
            },
        )
    finally:
        event.remove(app.state.session_factory.kw["bind"], "before_cursor_execute", capture)
        client.__exit__(None, None, None)

    assert response.status_code == 409
    assert response.json()["msg"] == "I19 source digest changed; request a fresh mapping preview"
    assert i19_reader.calls == 1
    assert writes == []


def test_i20_import_rejects_a_target_digest_that_does_not_match_the_fresh_preview():
    client, app, _i19_reader, i20_reader, headers, project_id = _client(enable_i20=True)
    writes = []

    def capture(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().split(maxsplit=1)[0].upper() in {"INSERT", "UPDATE", "DELETE", "REPLACE"}:
            writes.append(statement)

    event.listen(app.state.session_factory.kw["bind"], "before_cursor_execute", capture)
    try:
        response = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/legacy/i20/import",
            headers=headers,
            json={
                "source_digest": "a" * 64,
                "target_digest": "b" * 64,
                "idempotency_key": "i20-stale-target",
                "confirmation": f"IMPORT I20 {project_id} {'a' * 64} {'b' * 64}",
            },
        )
    finally:
        event.remove(app.state.session_factory.kw["bind"], "before_cursor_execute", capture)
        client.__exit__(None, None, None)

    assert response.status_code == 409
    assert response.json()["msg"] == "I20 target digest changed; request a fresh mapping preview"
    assert i20_reader.calls == 1
    assert writes == []


def test_i19_import_rejects_a_target_digest_that_does_not_match_the_fresh_preview():
    client, app, i19_reader, _i20_reader, headers, project_id = _client(enable_i19=True)
    writes = []

    def capture(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().split(maxsplit=1)[0].upper() in {"INSERT", "UPDATE", "DELETE", "REPLACE"}:
            writes.append(statement)

    event.listen(app.state.session_factory.kw["bind"], "before_cursor_execute", capture)
    try:
        response = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/legacy/i19/import",
            headers=headers,
            json={
                "source_digest": "a" * 64,
                "target_digest": "b" * 64,
                "idempotency_key": "i19-stale-target",
                "confirmation": f"IMPORT I19 {project_id} {'a' * 64} {'b' * 64}",
            },
        )
    finally:
        event.remove(app.state.session_factory.kw["bind"], "before_cursor_execute", capture)
        client.__exit__(None, None, None)

    assert response.status_code == 409
    assert response.json()["msg"] == "I19 target digest changed; request a fresh mapping preview"
    assert i19_reader.calls == 1
    assert writes == []
