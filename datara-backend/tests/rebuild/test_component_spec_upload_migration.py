"""v0002 component catalog upload migration guards."""

import json

import pytest
from sqlalchemy import create_engine, select, text

from rebuild.common.migrations import SchemaMigrationRecord
from rebuild.component_spec.migrations import (
    COMPONENT_SPEC_MIGRATIONS,
    apply_component_spec_migrations,
)
from rebuild.component_spec.revisions import v0001_component_spec_tables
from rebuild.component_spec.revisions import v0002_component_catalog_upload as revision
from sqlalchemy.orm import Session


def _insert_version(connection, component_id: int, type_name: str, spec: dict) -> None:
    connection.execute(
        text(
            "INSERT INTO t_component_version "
            "(component_id, type, version, state, spec_json, spec_hash, create_time, update_time) "
            "VALUES (:cid, :type, 1, 'published', :spec_json, :spec_hash, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ),
        {
            "cid": component_id,
            "type": type_name,
            "spec_json": json.dumps(spec, ensure_ascii=False, separators=(",", ":")),
            "spec_hash": revision._spec_hash(spec),
        },
    )


def _engine_with_legacy_rows():
    """Fresh catalog schema seeded with executable rows that predate the upload declaration."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    v0001_component_spec_tables.upgrade(engine)
    with engine.begin() as connection:
        for index, type_name in enumerate(("sql", "python", "shell"), start=1):
            _insert_version(connection, index, type_name, {"form": {"params": []}})
    return engine


def test_v0002_adds_upload_declaration_and_recomputes_hash() -> None:
    engine = _engine_with_legacy_rows()
    with engine.connect() as connection:
        before = connection.execute(text("SELECT spec_hash FROM t_component_version WHERE type='sql'")).scalar()

    revision.upgrade(engine)

    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT spec_json, spec_hash FROM t_component_version WHERE type='sql'")
        ).mappings().one()
    spec = json.loads(row["spec_json"])
    params = {item["key"]: item for item in spec["form"]["params"]}
    assert params["sourceMode"]["default"] == "inline"
    assert params["resourceRef"]["uiType"] == "resource"
    assert params["resourceRef"]["cap"]["kind"] == "sql"
    assert params["resourceRef"]["cap"]["versioned"] is True
    assert params["resourceRef"]["cap"]["allowLatest"] is False
    assert ".sql" in params["resourceRef"]["cap"]["extensions"]
    assert any(item["id"] == "c-resource-mode" for item in spec["form"]["conditions"])
    assert row["spec_hash"] != before
    assert row["spec_hash"] == revision._spec_hash(spec)


def test_v0002_is_idempotent() -> None:
    engine = _engine_with_legacy_rows()
    revision.upgrade(engine)
    with engine.connect() as connection:
        first = connection.execute(
            text("SELECT spec_json, spec_hash FROM t_component_version WHERE type='python'")
        ).mappings().one()

    revision.upgrade(engine)

    with engine.connect() as connection:
        second = connection.execute(
            text("SELECT spec_json, spec_hash FROM t_component_version WHERE type='python'")
        ).mappings().one()
    assert first["spec_json"] == second["spec_json"]
    assert first["spec_hash"] == second["spec_hash"]


def test_all_executable_components_gain_upload_declaration() -> None:
    engine = _engine_with_legacy_rows()
    apply_component_spec_migrations(engine)

    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT type, spec_json FROM t_component_version ORDER BY type")
        ).mappings().all()
    assert {row["type"] for row in rows} == {"sql", "python", "shell"}
    for row in rows:
        spec = json.loads(row["spec_json"])
        params = {item["key"]: item for item in spec["form"]["params"]}
        assert "sourceMode" in params
        assert "resourceRef" in params
        assert params["resourceRef"]["cap"]["kind"] == row["type"]
        assert any(item["id"] == "c-resource-mode" for item in spec["form"]["conditions"])


def test_v0002_is_registered_and_applied() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    result = apply_component_spec_migrations(engine)

    assert result.applied == ("i4_0001_component_catalog", "i4_0002_component_catalog_upload")
    assert result.skipped == ()
    with Session(engine) as session:
        record = session.scalar(
            select(SchemaMigrationRecord).where(
                SchemaMigrationRecord.revision == "i4_0002_component_catalog_upload"
            )
        )
        assert record is not None
        assert record.checksum == COMPONENT_SPEC_MIGRATIONS[1].checksum
        assert record.status == "completed"


def test_repeated_apply_is_skipped() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    apply_component_spec_migrations(engine)

    result = apply_component_spec_migrations(engine)

    assert result.applied == ()
    assert result.skipped == ("i4_0001_component_catalog", "i4_0002_component_catalog_upload")


def test_validate_schema_accepts_normalized_rows() -> None:
    engine = _engine_with_legacy_rows()
    revision.upgrade(engine)

    revision.validate_schema(engine)


def test_validate_schema_rejects_missing_upload_declaration() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    v0001_component_spec_tables.upgrade(engine)
    with engine.begin() as connection:
        _insert_version(connection, 1, "sql", {"form": {"params": []}})

    with pytest.raises(RuntimeError, match="sourceMode"):
        revision.validate_schema(engine)


def test_validate_schema_rejects_partial_upload_declaration() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    v0001_component_spec_tables.upgrade(engine)
    with engine.begin() as connection:
        _insert_version(
            connection,
            1,
            "shell",
            {"form": {"params": [revision._source_mode_param()]}},
        )

    with pytest.raises(RuntimeError, match="resourceRef"):
        revision.validate_schema(engine)


def test_v0002_revision_and_checksum_are_wellformed() -> None:
    assert revision.revision == "i4_0002_component_catalog_upload"
    assert len(revision.checksum) == 64
    assert all(character in "0123456789abcdef" for character in revision.checksum)
    assert COMPONENT_SPEC_MIGRATIONS[1].revision == revision.revision
    assert COMPONENT_SPEC_MIGRATIONS[1].checksum == revision.checksum
