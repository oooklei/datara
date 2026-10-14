import pytest

from rebuild.datasource.contracts import DataSourceDraft, validate_datasource
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
            DataSourceDraft(
                name="orders", kind="mysql", host="", port=3306, database="ec_retail", username="root"
            )
        )


def test_valid_datasource_exposes_mysql_capabilities():
    result = validate_datasource(
        DataSourceDraft(name="orders", kind="mysql", host="mysql-src", port=3306, database="ec_retail", username="root")
    )

    assert result.capabilities == {"query", "metadata", "cross_schema"}

