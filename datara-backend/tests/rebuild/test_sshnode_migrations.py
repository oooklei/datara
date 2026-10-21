from sqlalchemy import create_engine, inspect

from rebuild.sshnode.migrations import apply_ssh_node_migrations


def test_ssh_node_migration_is_versioned_and_idempotent():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    first = apply_ssh_node_migrations(engine)
    second = apply_ssh_node_migrations(engine)
    assert first.applied == ("i17_0001_ssh_node_registry",)
    assert second.skipped == first.applied
    assert "rebuild_ssh_node" in inspect(engine).get_table_names()
