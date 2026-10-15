from __future__ import annotations

import json

import pytest

from tools.verify_r2_12_d import displays_view_kind, fixture_from_environment, mysql_fixture_from_environment


def _fixture(**overrides):
    return {
        "kind": "postgresql",
        "host": "datara-r2-12d-pg-fixture",
        "port": 5432,
        "database": "r2_12d_fixture",
        "username": "ds_reader",
        "password": "test-secret",
        **overrides,
    }


def test_runner_accepts_only_named_postgresql_fixture(monkeypatch):
    monkeypatch.setenv("REBUILD_R2_POSTGRES_FIXTURE_JSON", json.dumps(_fixture()))

    fixture = fixture_from_environment()

    assert fixture["kind"] == "postgresql"
    assert fixture["host"] == "datara-r2-12d-pg-fixture"
    assert "password" in fixture


def test_runner_accepts_only_named_mysql_regression_fixture(monkeypatch):
    monkeypatch.setenv(
        "REBUILD_R2_MYSQL_FIXTURE_JSON",
        json.dumps(
            {
                "kind": "mysql",
                "host": "datara-r2-12d-mysql-fixture",
                "port": 3306,
                "database": "r2_12d_fixture",
                "username": "ds_reader",
                "password": "test-secret",
            }
        ),
    )

    fixture = mysql_fixture_from_environment()

    assert fixture["kind"] == "mysql"
    assert fixture["host"] == "datara-r2-12d-mysql-fixture"


@pytest.mark.parametrize("label", ["v_orders view", "视图 · v_orders"])
def test_runner_recognizes_visible_view_kind(label):
    assert displays_view_kind(label)


def test_runner_does_not_mislabel_table_as_view():
    assert not displays_view_kind("orders table")


@pytest.mark.parametrize(
    "overrides",
    [
        {"kind": "mysql"},
        {"host": "datara-postgres"},
        {"username": "postgres"},
        {"database": "datara_meta"},
        {"database": "postgres"},
    ],
)
def test_runner_rejects_non_disposable_or_privileged_fixture(monkeypatch, overrides):
    monkeypatch.setenv("REBUILD_R2_POSTGRES_FIXTURE_JSON", json.dumps(_fixture(**overrides)))

    with pytest.raises(RuntimeError):
        fixture_from_environment()


@pytest.mark.parametrize(
    "overrides",
    [
        {"kind": "postgresql"},
        {"host": "datara-mysql-dw"},
        {"username": "root"},
        {"database": "datara_dw"},
    ],
)
def test_runner_rejects_non_disposable_mysql_regression_fixture(monkeypatch, overrides):
    fixture = {
        "kind": "mysql",
        "host": "datara-r2-12d-mysql-fixture",
        "port": 3306,
        "database": "r2_12d_fixture",
        "username": "ds_reader",
        "password": "test-secret",
        **overrides,
    }
    monkeypatch.setenv("REBUILD_R2_MYSQL_FIXTURE_JSON", json.dumps(fixture))

    with pytest.raises(RuntimeError):
        mysql_fixture_from_environment()
