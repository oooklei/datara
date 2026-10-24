from __future__ import annotations

from urllib.error import URLError

import pytest
from fastapi.testclient import TestClient

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.llm import provider as llm_provider
from rebuild.llm.crypto import LlmCredentialCipher
from rebuild.llm.models import LlmModelRecord
from rebuild.llm.provider import LlmProviderError
from rebuild.llm.resolver import DefaultLlmResolver


def _client(role=Role.ADMIN):
    cipher = LlmCredentialCipher(bytes(range(32)))
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="llm-test-secret", llm_cipher=cipher)
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        UserRepository(session).create(username="llm-user", password="password", role=role)
        session.commit()
    token = client.post("/api/v1/rebuild/login", json={"username": "llm-user", "password": "password"}).json()["data"][
        "token"
    ]
    return client, app, cipher, {"Authorization": f"Bearer {token}"}


def _body(name="main", key="provider-secret-1234", default=True):
    return {
        "name": name,
        "display_name": name.title(),
        "provider": "siliconflow",
        "api_base": "https://example.invalid/v1",
        "model_id": "qwen",
        "api_key": key,
        "max_tokens": 1000,
        "temperature": 0.2,
        "is_active": True,
        "is_default": default,
        "sort_order": 0,
    }


def test_admin_crud_mask_blank_key_unique_default_and_delete_guards():
    client, app, cipher, headers = _client()
    try:
        created = client.post("/api/v1/rebuild/llm-models", headers=headers, json=_body())
        assert created.status_code == 201
        item = created.json()["data"]
        assert item["api_key"].endswith("1234") and "provider-secret" not in item["api_key"]
        item_id = item["id"]
        with app.state.session_factory() as session:
            old_cipher = session.get(LlmModelRecord, item_id).api_key_cipher
            assert "provider-secret" not in old_cipher
        update = _body(key="", default=True)
        update["display_name"] = "Updated"
        assert client.put(f"/api/v1/rebuild/llm-models/{item_id}", headers=headers, json=update).status_code == 200
        with app.state.session_factory() as session:
            row = session.get(LlmModelRecord, item_id)
            assert row.api_key_cipher == old_cipher and cipher.decrypt(row.api_key_cipher) == "provider-secret-1234"
        second_id = client.post(
            "/api/v1/rebuild/llm-models", headers=headers, json=_body("second", "other-secret-5678", False)
        ).json()["data"]["id"]
        assert client.put(f"/api/v1/rebuild/llm-models/{second_id}/default", headers=headers).status_code == 200
        listed = client.get("/api/v1/rebuild/llm-models", headers=headers).json()["data"]["items"]
        assert sum(item["is_default"] for item in listed) == 1
        assert client.delete(f"/api/v1/rebuild/llm-models/{second_id}", headers=headers).status_code == 409
        assert client.delete(f"/api/v1/rebuild/llm-models/{item_id}", headers=headers).status_code == 200
    finally:
        client.__exit__(None, None, None)


def test_admin_only_probe_isolated_validation_and_pagination():
    viewer, _, _, viewer_headers = _client(Role.VIEWER)
    try:
        assert viewer.get("/api/v1/rebuild/llm-models", headers=viewer_headers).status_code == 403
    finally:
        viewer.__exit__(None, None, None)
    client, _, _, headers = _client()
    try:
        unsupported = _body()
        unsupported["provider"] = "openai"
        insecure = _body()
        insecure["api_base"] = "http://example.invalid/v1"
        assert client.post("/api/v1/rebuild/llm-models", headers=headers, json=unsupported).status_code == 422
        assert client.post("/api/v1/rebuild/llm-models", headers=headers, json=insecure).status_code == 422
        item_id = client.post("/api/v1/rebuild/llm-models", headers=headers, json=_body()).json()["data"]["id"]
        failed = client.post(f"/api/v1/rebuild/llm-models/{item_id}/test", headers=headers)
        assert failed.status_code == 502 and "provider-secret" not in failed.text
        failure = failed.json()["data"]
        assert failure["status"] == "error"
        assert failure["message"] == "LLM connectivity test failed"
        assert failure["detail"].startswith("LLM connectivity failed:")
        assert isinstance(failure["elapsed_ms"], int) and failure["elapsed_ms"] >= 0
        assert client.get("/api/v1/rebuild/llm-models?limit=201", headers=headers).status_code == 422
    finally:
        client.__exit__(None, None, None)


def test_resolver_prefers_database_then_environment(monkeypatch):
    client, app, cipher, headers = _client()
    try:
        resolver = DefaultLlmResolver(app.state.session_factory, cipher)
        monkeypatch.setenv("LLM_PROVIDER", "volcengine")
        monkeypatch.setenv("LLM_BASE_URL", "https://env.invalid/v1")
        monkeypatch.setenv("LLM_MODEL", "env-model")
        monkeypatch.setenv("LLM_API_KEY", "env-key")
        assert resolver.resolve()["source"] == "environment"
        client.post("/api/v1/rebuild/llm-models", headers=headers, json=_body())
        resolved = resolver.resolve()
        assert resolved["source"] == "database" and resolved["api_key"] == "provider-secret-1234"
    finally:
        client.__exit__(None, None, None)


def test_provider_failure_preserves_elapsed_time_without_secret(monkeypatch):
    ticks = iter((10.0, 10.125))
    monkeypatch.setattr(llm_provider, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(
        llm_provider,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("provider-secret-1234")),
    )
    with pytest.raises(LlmProviderError) as captured:
        llm_provider.test_chat("https://example.invalid/v1", "qwen", "provider-secret-1234")
    assert captured.value.elapsed_ms == 125
    assert captured.value.detail == "LLM connectivity failed: URLError"
    assert "provider-secret" not in str(captured.value)
