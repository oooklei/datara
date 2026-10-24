from sqlalchemy import create_engine, inspect, text

from rebuild.workflow.migrations import apply_workflow_migrations
from rebuild.workflow.revisions import v0001_workflow_type


def _legacy_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE workflow_definition ("
                "id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, name VARCHAR(256) NOT NULL)"
            )
        )
        connection.execute(
            text("INSERT INTO workflow_definition (id,project_id,name) VALUES (1,1,'legacy')")
        )
    return engine


def test_workflow_type_migration_upgrades_legacy_table_and_is_idempotent():
    assert v0001_workflow_type.checksum == "0dd9efb7d3628d0d994273a14de5333debaa256cd30113dc6f68bb769bfd657b"
    engine = _legacy_engine()
    first = apply_workflow_migrations(engine)
    assert first.applied == (v0001_workflow_type.revision,)
    columns = {column["name"]: column for column in inspect(engine).get_columns("workflow_definition")}
    assert columns["workflow_type"]["nullable"] is False
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT workflow_type FROM workflow_definition WHERE id=1")) == "NORMAL"
    second = apply_workflow_migrations(engine)
    assert second.skipped == (v0001_workflow_type.revision,)


def test_workflow_type_migration_maps_etl_and_postflight_rejects_drift():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE workflow_definition ("
                "id INTEGER PRIMARY KEY, workflow_type VARCHAR(16) NOT NULL DEFAULT 'NORMAL')"
            )
        )
        connection.execute(text("INSERT INTO workflow_definition VALUES (1,'ETL')"))
    apply_workflow_migrations(engine)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT workflow_type FROM workflow_definition")) == "NORMAL"
    with engine.begin() as connection:
        connection.execute(text("UPDATE workflow_definition SET workflow_type='BROKEN'"))
    try:
        apply_workflow_migrations(engine)
    except RuntimeError as error:
        assert "unsupported workflow_type" in str(error)
    else:
        raise AssertionError("completed migration must still validate schema/data drift")


def test_workflow_type_migration_classifies_legacy_sync_and_rejects_wrong_default():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE workflow_definition (id INTEGER PRIMARY KEY)"))
        connection.execute(
            text(
                "CREATE TABLE workflow_node (id INTEGER PRIMARY KEY, definition_id INTEGER NOT NULL, "
                "node_type VARCHAR(64) NOT NULL)"
            )
        )
        connection.execute(text("INSERT INTO workflow_definition VALUES (1)"))
        connection.execute(text("INSERT INTO workflow_node VALUES (1,1,'SYNC')"))
    apply_workflow_migrations(engine)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT workflow_type FROM workflow_definition WHERE id=1")) == "SYNC"

    wrong = create_engine("sqlite+pysqlite:///:memory:")
    with wrong.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE workflow_definition (id INTEGER PRIMARY KEY, "
                "workflow_type VARCHAR(16) NOT NULL DEFAULT 'SYNC')"
            )
        )
    try:
        apply_workflow_migrations(wrong)
    except Exception as error:
        assert "failed" in str(error) or "VARCHAR(16)" in str(error)
    else:
        raise AssertionError("wrong workflow_type default must fail closed")
