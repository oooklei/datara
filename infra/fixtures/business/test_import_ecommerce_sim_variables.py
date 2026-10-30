"""No network or persistent data is used by these import/cleanup checks."""

import json

import pytest

import import_ecommerce_sim_variables as importer


class FakeClient:
    def __init__(self):
        self.rows = {}
        self.calls = []

    def request(self, method, path, payload=None):
        self.calls.append((method, path))
        if method == "GET":
            return list(self.rows.values())
        if method == "POST":
            self.rows[payload["name"]] = payload.copy()
            return {"saved": True}
        if method == "DELETE":
            name = path.split("/variables/", 1)[1].split("?", 1)[0]
            self.rows.pop(name)
            return {"deleted": True}
        raise AssertionError(method)


def definitions():
    fixture = json.loads(importer.FIXTURE.read_text(encoding="utf-8"))
    return importer.variable_definitions(fixture)


def test_apply_is_repeatable_and_cleanup_removes_only_namespaced_rows():
    client = FakeClient()
    expected = definitions()
    client.rows["business_currency"] = {"scope": "project", "name": "business_currency", "description": "real configuration"}
    assert len(importer.apply_variables(client, 33, expected)) == 4
    assert all(action.startswith("unchanged") for action in importer.apply_variables(client, 33, expected))
    assert len(importer.cleanup_variables(client, 33, expected)) == 4
    assert client.rows == {"business_currency": {"scope": "project", "name": "business_currency", "description": "real configuration"}}


def test_non_fixture_collision_is_never_overwritten_or_deleted():
    client = FakeClient()
    expected = definitions()
    client.rows[expected[0]["name"]] = {"scope": "project", "name": expected[0]["name"], "description": "real configuration"}
    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        importer.apply_variables(client, 33, expected)
    with pytest.raises(RuntimeError, match="refusing to delete"):
        importer.cleanup_variables(client, 33, expected)
    assert [method for method, _ in client.calls] == ["GET", "GET"]


def test_plan_rejects_another_fixture_namespace():
    with pytest.raises(ValueError, match="namespace"):
        importer.variable_definitions({"namespace": "another", "expected": {}, "currency": "CNY"})


def test_variable_types_follow_current_backend_contract():
    assert {row["name"].removeprefix(importer.PREFIX): row["value_type"] for row in definitions()} == {
        "biz_date": "date", "currency": "string", "paid_orders": "integer", "net_paid_cents": "integer"
    }
