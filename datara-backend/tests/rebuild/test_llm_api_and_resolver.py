from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from rebuild.ai_bridge import (
    AiBridgePorts,
    LlmConfigUnavailable,
    build_default_bridge_ports,
    resolve_bridge_llm,
)
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
        # The update contract owns the default switch; explicitly clearing it
        # must be observable in the persisted row.
        clear_default = _body(key="", default=False)
        assert client.put(f"/api/v1/rebuild/llm-models/{item_id}", headers=headers, json=clear_default).status_code == 200
        with app.state.session_factory() as session:
            assert session.get(LlmModelRecord, item_id).is_default is False
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
        # T1（D-03 白名单单源）：longcat 与 ai_copilot/config.py SUPPORTED_PROVIDERS 对齐后必须可创建。
        longcat = _body(name="longcat-probe", key="longcat-secret-9999", default=False)
        longcat["provider"] = "longcat"
        longcat_created = client.post("/api/v1/rebuild/llm-models", headers=headers, json=longcat)
        assert longcat_created.status_code == 201
        assert longcat_created.json()["data"]["provider"] == "longcat"
        longcat_id = longcat_created.json()["data"]["id"]
        assert client.delete(f"/api/v1/rebuild/llm-models/{longcat_id}", headers=headers).status_code == 200
        item_id = client.post("/api/v1/rebuild/llm-models", headers=headers, json=_body()).json()["data"]["id"]
        failed = client.post(f"/api/v1/rebuild/llm-models/{item_id}/test", headers=headers)
        assert failed.status_code == 502 and "provider-secret" not in failed.text
        failure = failed.json()["data"]
        assert failure["status"] == "error"
        assert failure["message"] == "LLM connectivity test failed"
        assert failure["detail"].startswith(("LLM connectivity failed:", "LLM endpoint DNS resolution failed"))
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


def test_bridge_llm_seam_database_first_then_environment_fail_closed(monkeypatch):
    """T2（D-02 / §5E.4 FV-02 解阻链闭合）：ai_bridge 消费侧读取默认模型凭证。

    链路：LLM 配置页写库 → DefaultLlmResolver（db 优先 env 兜底）→
    resolve_bridge_llm（bridge 消费侧唯一入口）→ AI 调用链可发起真实 LLM 调用。
    任何环节缺失均 fail-closed 抛 LlmConfigUnavailable，不伪造配置。
    """
    for name in ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    client, app, cipher, headers = _client()
    try:
        # create_app 装配：llm_cipher 注入时 app.state.llm_resolver 必在位
        assert app.state.llm_resolver is not None
        # fail-closed：resolver 未接线
        with pytest.raises(LlmConfigUnavailable):
            resolve_bridge_llm(AiBridgePorts(handlers={}, audit_writer=object()))
        # fail-closed：已接线但库与 env 均无配置
        wired = AiBridgePorts(handlers={}, audit_writer=object(), llm_resolver=app.state.llm_resolver)
        with pytest.raises(LlmConfigUnavailable):
            resolve_bridge_llm(wired)
        # db 优先：LLM 配置页创建默认模型 → bridge 消费侧立即可读（FV-02 解除）
        created = client.post("/api/v1/rebuild/llm-models", headers=headers, json=_body())
        assert created.status_code == 201
        config = resolve_bridge_llm(wired)
        assert config == {
            "provider": "siliconflow",
            "base_url": "https://example.invalid/v1",
            "model": "qwen",
            "api_key": "provider-secret-1234",
            "source": "database",
        }
        # 生产装配透传：build_default_bridge_ports(llm_resolver=…) 消费同一读取面
        ports = build_default_bridge_ports(
            execution_port=SimpleNamespace(execute=lambda *args, **kwargs: {}),
            audit_writer=object(),
            session_factory=app.state.session_factory,
            connector_factory=None,
            llm_resolver=app.state.llm_resolver,
        )
        assert ports is not None and resolve_bridge_llm(ports) == config
        # 不经端口直连 resolver 的兜底口径不回归
        assert DefaultLlmResolver(app.state.session_factory, cipher).resolve() == config
    finally:
        client.__exit__(None, None, None)
    # env 兜底：空库 + ai_copilot 四变量（SUPPORTED_PROVIDERS 含 longcat）
    client_env, app_env, _cipher_env, _ = _client()
    try:
        monkeypatch.setenv("LLM_PROVIDER", "longcat")
        monkeypatch.setenv("LLM_BASE_URL", "https://env.invalid/v1")
        monkeypatch.setenv("LLM_MODEL", "env-model")
        monkeypatch.setenv("LLM_API_KEY", "env-key")
        wired_env = AiBridgePorts(handlers={}, audit_writer=object(), llm_resolver=app_env.state.llm_resolver)
        env_config = resolve_bridge_llm(wired_env)
        assert env_config == {
            "provider": "longcat",
            "base_url": "https://env.invalid/v1",
            "model": "env-model",
            "api_key": "env-key",
            "source": "environment",
        }
    finally:
        client_env.__exit__(None, None, None)


def test_provider_failure_preserves_elapsed_time_without_secret(monkeypatch):
    ticks = iter((10.0, 10.125))
    monkeypatch.setattr(llm_provider, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(llm_provider, "_resolved_addresses", lambda *_args: frozenset({"93.184.216.34"}))
    monkeypatch.setattr(
        llm_provider,
        "_post_json",
        lambda **_kwargs: (_ for _ in ()).throw(OSError("provider-secret-1234")),
    )
    with pytest.raises(LlmProviderError) as captured:
        llm_provider.test_chat("https://example.invalid/v1", "qwen", "provider-secret-1234")
    assert captured.value.elapsed_ms == 125
    assert captured.value.detail == "LLM connectivity failed: OSError"
    assert "provider-secret" not in str(captured.value)


@pytest.mark.parametrize(
    "url",
    (
        "http://example.com/v1",
        "https://user:pass@example.com/v1",
        "https://example.com/v1#fragment",
        "https://example.com/v1?query=yes",
        "https://example.com./v1",
    ),
)
def test_provider_rejects_unsafe_endpoint_shapes(url):
    with pytest.raises(ValueError):
        llm_provider.validate_api_base(url)


@pytest.mark.parametrize("address", ("127.0.0.1", "10.0.0.2", "169.254.169.254", "::1"))
def test_provider_rejects_non_public_resolution_by_default(monkeypatch, address):
    monkeypatch.delenv("DATARA_LLM_PRIVATE_HOST_ALLOWLIST", raising=False)
    monkeypatch.setattr(
        llm_provider.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(2, 1, 6, "", (address, 443))],
    )
    with pytest.raises(LlmProviderError, match="non-public"):
        llm_provider._resolved_addresses("internal.example", 443)


def test_provider_allows_exact_private_host_only_when_deployment_allowlists_it(monkeypatch):
    monkeypatch.setenv("DATARA_LLM_PRIVATE_HOST_ALLOWLIST", "llm.internal.example")
    monkeypatch.setattr(
        llm_provider.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(2, 1, 6, "", ("10.0.0.8", 443))],
    )
    assert llm_provider._resolved_addresses("llm.internal.example", 443) == frozenset({"10.0.0.8"})
    with pytest.raises(LlmProviderError, match="non-public"):
        llm_provider._resolved_addresses("other.internal.example", 443)


def test_provider_pins_validated_address_and_does_not_follow_redirects(monkeypatch):
    calls = []
    monkeypatch.setattr(llm_provider, "_resolved_addresses", lambda *_args: frozenset({"93.184.216.34"}))

    def fake_post(**kwargs):
        calls.append(kwargs)
        return {"choices": [{"message": {"content": "OK"}}]}

    monkeypatch.setattr(llm_provider, "_post_json", fake_post)
    result = llm_provider.test_chat("https://example.com/v1", "qwen", "secret")
    assert result["status"] == "success"
    assert calls[0]["address"] == "93.184.216.34"
    assert calls[0]["path"] == "/v1/chat/completions"


def test_provider_chat_completion_sends_non_streaming_tool_contract(monkeypatch):
    calls = []
    monkeypatch.setattr(llm_provider, "_resolved_addresses", lambda *_args: frozenset({"93.184.216.34"}))
    monkeypatch.setattr(llm_provider, "_post_json", lambda **kwargs: calls.append(kwargs) or {
        "model": "qwen", "choices": [{"message": {"role": "assistant", "content": "ok"}}],
    })

    result = llm_provider.chat_completion(
        api_base="https://example.com/v1",
        model_id="qwen",
        api_key="secret",
        messages=[{"role": "user", "content": "检查"}],
        tools=[{"type": "function", "function": {"name": "search_schema"}}],
    )

    body = json.loads(calls[0]["body"])
    assert result["model"] == "qwen"
    assert calls[0]["path"] == "/v1/chat/completions"
    assert body["stream"] is False and body["tool_choice"] == "auto"
    assert body["tools"][0]["function"]["name"] == "search_schema"
