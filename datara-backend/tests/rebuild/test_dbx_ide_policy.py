import pytest

from rebuild.dbx.ide_policy import (
    DbxIdeForbidden,
    canonical_connect_payload,
    classify_save,
    merge_connection_save_payload,
    referenced_connection_ids,
    require_visible,
    safe_connection_list,
)


def test_nested_request_cannot_use_another_users_connection():
    frame = {"source": {"connectionId": "owned"}, "target": {"connection_id": "foreign"}}
    assert referenced_connection_ids(frame) == {"owned", "foreign"}
    with pytest.raises(DbxIdeForbidden):
        require_visible(frame, {"owned"})


def test_connection_list_filters_owner_and_credentials():
    rows = [
        {"id": "owned", "name": "Sales", "host": "db", "password": "secret", "connection_string": "db://secret", "ssl": {"private_key": "secret"}},
        {"id": "foreign", "name": "HR", "password": "other-secret"},
    ]
    assert safe_connection_list(rows, {"owned"}) == [{"id": "owned", "name": "Sales", "host": "db", "password": ""}]


def test_connect_uses_server_copy_and_rejects_foreign_connection():
    stored = {"owned": {"id": "owned", "host": "real-db", "password": "server-secret"}}
    frame = {"config": {"id": "owned", "host": "attacker-db"}, "clientAttempt": 1}
    assert canonical_connect_payload(frame, stored, {"owned"}) == {"config": stored["owned"], "clientAttempt": 1}
    with pytest.raises(DbxIdeForbidden):
        canonical_connect_payload(frame, stored, set())


def test_save_cannot_edit_or_remove_unshared_connection():
    with pytest.raises(DbxIdeForbidden):
        classify_save({"configs": [{"id": "foreign"}]}, {"owned", "foreign"}, {"owned"})
    with pytest.raises(DbxIdeForbidden):
        classify_save({"removedIds": ["foreign"]}, {"owned", "foreign"}, {"owned"})
    assert classify_save({"configs": [{"id": "new"}]}, {"owned"}, {"owned"}) == {"new"}


def test_redacted_connection_edit_preserves_hidden_settings():
    stored = {"owned": {
        "id": "owned", "name": "Before", "password": "server-secret",
        "connection_string": "db://user:secret@host", "external_config": {"api_key": "secret"},
        "ssl": True, "driver_profile": "native", "query_timeout_secs": 30,
    }}
    visible = safe_connection_list(list(stored.values()), {"owned"})[0]
    assert visible["ssl"] is True and visible["driver_profile"] == "native"
    assert "connection_string" not in visible and "external_config" not in visible
    assert "secret" not in str(visible)
    saved = merge_connection_save_payload({"configs": [{**visible, "name": "After", "password": "", "query_timeout_secs": 45}]}, stored)
    config = saved["configs"][0]
    assert config["name"] == "After" and config["query_timeout_secs"] == 45
    assert config["password"] == "server-secret"
    assert config["connection_string"] == "db://user:secret@host"
    assert config["external_config"] == {"api_key": "secret"}
