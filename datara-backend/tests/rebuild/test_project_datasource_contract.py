import pytest

from rebuild.datasource.contracts import DataSourceDraft, probe_datasource, validate_datasource
from rebuild.identity.contracts import Role
from rebuild.project.contracts import Member, can_manage_project


def test_project_owner_can_manage_members():
    owner = Member(user_id=7, role=Role.DEV, is_owner=True)

    assert can_manage_project(owner) is True


def test_viewer_cannot_manage_project_members():
    viewer = Member(user_id=8, role=Role.VIEWER, is_owner=False)

    assert can_manage_project(viewer) is False


def test_mysql_datasource_requires_host_port_database_and_user():
    with pytest.raises(ValueError, match="host"):
        validate_datasource(
            DataSourceDraft(name="orders", kind="mysql", host="", port=3306, database="ec_retail", username="root")
        )


def test_valid_datasource_exposes_mysql_capabilities():
    result = validate_datasource(
        DataSourceDraft(name="orders", kind="mysql", host="mysql-src", port=3306, database="ec_retail", username="root")
    )

    assert result.capabilities == {"query", "metadata", "cross_schema"}


def test_postgresql_does_not_advertise_runtime_capabilities_before_driver_exists():
    result = validate_datasource(
        DataSourceDraft(name="pg", kind="postgresql", host="pg-test", port=5432, database="warehouse", username="reader")
    )

    assert result.capabilities == set()


def test_mysql_probe_uses_read_only_transaction_and_rolls_back(monkeypatch):
    import rebuild.datasource.contracts as datasource_contracts

    events = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement):
            events.append(("execute", statement))

        def fetchone(self):
            return ("analytics", "8.test")

    class Connection:
        def cursor(self):
            return Cursor()

        def begin(self):
            events.append(("begin",))

        def rollback(self):
            events.append(("rollback",))

        def close(self):
            events.append(("close",))

    observed = {}

    def connect(**kwargs):
        observed.update(kwargs)
        return Connection()

    monkeypatch.setattr(datasource_contracts.pymysql, "connect", connect)
    result = probe_datasource(
        DataSourceDraft(
            name="warehouse",
            kind="mysql",
            host="mysql-test",
            port=3306,
            database="analytics",
            username="readonly",
            password="test-only",
        )
    )

    assert result["connected"] is True
    assert observed["autocommit"] is False
    assert events == [
        ("execute", "SET TRANSACTION READ ONLY"),
        ("begin",),
        ("execute", "SELECT DATABASE(), VERSION()"),
        ("rollback",),
        ("close",),
    ]
