from __future__ import annotations

from importlib.util import find_spec

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from rebuild.common.db import Base
from rebuild.sql_ide.result_store import PersistentResultPageStore


def test_export_service_defaults_match_supervisor_limits():
    from rebuild.sql_ide.export_service import MAX_EXPORT_BYTES, MAX_EXPORT_ROWS

    assert MAX_EXPORT_ROWS == 100_000
    assert MAX_EXPORT_BYTES == 50 * 1024 * 1024


def test_result_export_can_address_a_specific_result_set(exports):
    service, _factory = exports
    result_set_id = service.result_store.save_snapshot(
        project_id=7,
        user_id=11,
        history_id="history-1",
        stmt_index=0,
        columns=["id", "name"],
        rows=[[9, "Grace"]],
    )

    job = service.create_result_export(
        project_id=7,
        user_id=11,
        history_id="history-1",
        result_set_id=result_set_id,
        format="json",
    )
    payload, _content_type, _filename = service.download(
        project_id=7,
        user_id=11,
        export_id=job["exportId"],
    )

    assert b"Grace" in payload


def test_export_service_is_available():
    assert find_spec("rebuild.sql_ide.export_service") is not None


@pytest.fixture
def exports():
    if find_spec("rebuild.sql_ide.export_service") is None:
        pytest.skip("export service is not implemented yet")
    from rebuild.sql_ide.export_service import SqlIdeExportAuditRecord, SqlIdeExportJobRecord, SqlIdeExportService

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    snapshots = PersistentResultPageStore(session_factory=factory)
    snapshots.save_snapshot(
        project_id=7,
        user_id=11,
        history_id="history-1",
        stmt_index=0,
        columns=["id", "name"],
        rows=[[1, "Ada"], [2, "Lin"]],
    )
    service = SqlIdeExportService(
        session_factory=factory,
        result_store=snapshots,
        authorize_result=lambda **_kwargs: True,
        authorize_table=lambda **_kwargs: True,
        table_reader=lambda **_kwargs: (["id"], [[3], [4]]),
        max_rows=10,
        max_bytes=4096,
    )
    yield service, factory
    engine.dispose()


def test_result_export_reads_snapshot_and_appends_audit(exports):
    service, factory = exports

    job = service.create_result_export(
        project_id=7,
        user_id=11,
        history_id="history-1",
        stmt_index=0,
        format="csv",
    )
    payload, content_type, filename = service.download(
        project_id=7,
        user_id=11,
        export_id=job["exportId"],
    )

    assert payload.decode("utf-8").splitlines() == ["id,name", "1,Ada", "2,Lin"]
    assert content_type == "text/csv; charset=utf-8"
    assert filename.endswith(".csv")
    with factory() as session:
        audit = session.scalars(select(service.audit_model)).all()
        assert [(row.action, row.outcome) for row in audit] == [("result_export", "completed")]


def test_table_export_requires_explicit_authorization_and_caps_rows(exports):
    service, _factory = exports
    denied = service.__class__(
        session_factory=service.session_factory,
        result_store=service.result_store,
        authorize_result=lambda **_kwargs: True,
        authorize_table=lambda **_kwargs: False,
        table_reader=lambda **_kwargs: pytest.fail("reader must not run before authorization"),
        max_rows=1,
        max_bytes=4096,
    )
    with pytest.raises(PermissionError):
        denied.create_table_export(
            project_id=7,
            user_id=11,
            datasource_id=9,
            object_ref={"datasourceId": 9, "database": "db", "schema": "s", "kind": "table", "name": "t"},
            format="json",
            row_limit=1,
        )

    limited = service.__class__(
        session_factory=service.session_factory,
        result_store=service.result_store,
        authorize_result=lambda **_kwargs: True,
        authorize_table=lambda **_kwargs: True,
        table_reader=lambda **_kwargs: (["id"], [[1], [2]]),
        max_rows=1,
        max_bytes=4096,
    )
    with pytest.raises(ValueError, match="row limit"):
        limited.create_table_export(
            project_id=7,
            user_id=11,
            datasource_id=9,
            object_ref={"datasourceId": 9, "database": "db", "schema": "s", "kind": "table", "name": "t"},
            format="json",
            row_limit=2,
        )


def test_export_payload_byte_limit_is_enforced(exports):
    service, _factory = exports
    limited = service.__class__(
        session_factory=service.session_factory,
        result_store=service.result_store,
        authorize_result=lambda **_kwargs: True,
        authorize_table=lambda **_kwargs: True,
        table_reader=lambda **_kwargs: (["id", "name"], [[1, "x" * 5000]]),
        max_rows=10,
        max_bytes=128,
    )

    with pytest.raises(ValueError, match="byte limit"):
        limited.create_table_export(
            project_id=7,
            user_id=11,
            datasource_id=9,
            object_ref={"datasourceId": 9, "database": "db", "schema": "s", "kind": "table", "name": "t"},
            format="json",
            row_limit=1,
        )
