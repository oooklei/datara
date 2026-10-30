import json
import urllib.error
from io import BytesIO

import pytest

from rebuild.dbx import DbxClient, DbxError


def test_schema_calls_use_dbx_tree_granularity_and_internal_token():
    calls = []

    def transport(method, url, body, headers, timeout):
        calls.append((method, url, body, headers, timeout))
        return []

    client = DbxClient(base_url="http://dbx/ide", internal_token="test-token", transport=transport)
    client.list_databases("conn-1")
    client.list_schemas("conn-1", "sales")
    client.list_objects("conn-1", "sales", "public")
    client.list_columns("conn-1", "sales", "public", "orders")

    assert [call[1].split("?", 1)[0] for call in calls] == [
        "http://dbx/ide/api/schema/databases",
        "http://dbx/ide/api/schema/schemas",
        "http://dbx/ide/api/schema/objects",
        "http://dbx/ide/api/schema/columns",
    ]
    assert "database=sales" in calls[1][1]
    assert "schema=public" in calls[2][1]
    assert "table=orders" in calls[3][1]
    assert all(call[3]["X-Datara-Internal-Token"] == "test-token" for call in calls)
    assert all(call[2] is None for call in calls)


def test_execute_only_sends_connection_id_and_no_credentials():
    requests = []

    def transport(method, url, body, headers, timeout):
        requests.append(json.loads(body))
        return {"rows": []}

    client = DbxClient(base_url="http://dbx/ide", internal_token="test-token", transport=transport)
    client.execute_sql(connection_id="conn-1", database="sales", schema="public", sql="select 1", max_rows=50)
    assert requests == [{"connectionId": "conn-1", "database": "sales", "schema": "public", "sql": "select 1", "maxRows": 50}]
    assert "password" not in requests[0]


def test_connection_test_uses_dbx_config_envelope():
    requests = []

    def transport(method, url, body, headers, timeout):
        requests.append((url, json.loads(body)))
        return "Connection successful"

    client = DbxClient(base_url="http://dbx/ide", internal_token="test-token", transport=transport)
    client.test_connection({"id": "conn-1", "db_type": "mysql"})
    assert requests == [("http://dbx/ide/api/connection/test", {"config": {"id": "conn-1", "db_type": "mysql"}})]


def test_missing_internal_token_fails_before_network():
    client = DbxClient(base_url="http://dbx/ide", internal_token="", transport=lambda *_: pytest.fail("network called"))
    with pytest.raises(DbxError) as error:
        client.list_connections()
    assert error.value.status == 503


def test_retries_transient_errors_but_not_auth_errors():
    calls = []

    def transport(method, url, body, headers, timeout):
        calls.append(url)
        if len(calls) == 1:
            raise urllib.error.HTTPError(url, 503, "unavailable", {}, None)
        return []

    client = DbxClient(base_url="http://dbx/ide", internal_token="test-token", transport=transport, sleep=lambda _: None)
    assert client.list_connections() == []
    assert len(calls) == 2

    def unauthorized(method, url, body, headers, timeout):
        raise urllib.error.HTTPError(url, 401, "unauthorized", {}, None)

    client = DbxClient(base_url="http://dbx/ide", internal_token="test-token", transport=unauthorized, sleep=lambda _: None)
    with pytest.raises(DbxError) as error:
        client.list_connections()
    assert error.value.status == 401


def test_post_is_not_replayed_after_upstream_timeout():
    calls = []

    def timed_out(method, url, body, headers, timeout):
        calls.append((method, url))
        raise TimeoutError("upstream result unknown")

    client = DbxClient(base_url="http://dbx/ide", internal_token="test-token", transport=timed_out, retries=3, sleep=lambda _: None)
    with pytest.raises(DbxError):
        client.execute_sql(connection_id="conn-1", database="sales", sql="insert into audit values (1)")
    assert calls == [("POST", "http://dbx/ide/api/query/execute")]


def test_ai_stream_uses_internal_token_and_one_post(monkeypatch):
    calls = []

    def open_url(request, timeout):
        calls.append((request, timeout))
        return BytesIO(b"data: [DONE]\n\n")

    monkeypatch.setattr("urllib.request.urlopen", open_url)
    client = DbxClient(base_url="http://dbx/ide", internal_token="internal-test")
    with client.open_stream("ai/stream", {"sessionId": "s1"}) as response:
        assert response.read() == b"data: [DONE]\n\n"
    assert len(calls) == 1
    request, timeout = calls[0]
    assert request.full_url == "http://dbx/ide/api/ai/stream"
    assert request.get_method() == "POST" and timeout == 300
    assert request.get_header("X-datara-internal-token") == "internal-test"
    assert json.loads(request.data) == {"sessionId": "s1"}
    with pytest.raises(ValueError):
        client.open_stream("connection/save", {})
