"""Isolated OpenAI-compatible connectivity probe."""

import json
import ipaddress
import http.client
import os
import socket
import ssl
from time import monotonic, sleep
from urllib.parse import urlsplit

PROVIDER_TIMEOUT_SECONDS = 90

class LlmProviderError(RuntimeError):
    def __init__(self, detail: str, elapsed_ms: int) -> None:
        super().__init__(detail)
        self.detail = detail
        self.elapsed_ms = elapsed_ms


def validate_api_base(api_base: str) -> tuple[str, int]:
    """Validate URL structure without resolving it (safe for configuration writes)."""
    try:
        parsed = urlsplit(api_base)
        port = parsed.port or 443
    except ValueError as exc:
        raise ValueError("api_base is not a valid HTTPS URL") from exc
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError("api_base must use HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("api_base must not contain userinfo")
    if parsed.fragment or parsed.query:
        raise ValueError("api_base must not contain query or fragment")
    if parsed.hostname.endswith(".") or any(char.isspace() for char in parsed.netloc):
        raise ValueError("api_base contains a non-standard host")
    return parsed.hostname.lower(), port


def _resolved_addresses(host: str, port: int) -> frozenset[str]:
    try:
        records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise LlmProviderError("LLM endpoint DNS resolution failed", 0) from exc
    addresses = frozenset(record[4][0].split("%", 1)[0] for record in records)
    if not addresses:
        raise LlmProviderError("LLM endpoint DNS resolution returned no addresses", 0)
    allowlist = {
        item.strip().lower()
        for item in os.getenv("DATARA_LLM_PRIVATE_HOST_ALLOWLIST", "").split(",")
        if item.strip()
    }
    if host.lower() not in allowlist and not all(ipaddress.ip_address(address).is_global for address in addresses):
        raise LlmProviderError("LLM endpoint resolved to a non-public address", 0)
    return addresses


def _post_json(
    *, host: str, port: int, address: str, path: str, body: bytes, headers: dict[str, str]
) -> dict[str, object]:
    """POST over a TLS socket pinned to the address that passed SSRF validation."""
    raw_socket = socket.create_connection((address, port), timeout=PROVIDER_TIMEOUT_SECONDS)
    connection = http.client.HTTPConnection(host, port, timeout=PROVIDER_TIMEOUT_SECONDS)
    try:
        connection.sock = ssl.create_default_context().wrap_socket(raw_socket, server_hostname=host)
        connection.request("POST", path, body=body, headers=headers)
        response = connection.getresponse()
        payload = response.read()
        if response.status < 200 or response.status >= 300:
            # http.client never follows redirects, so credentials cannot cross origins.
            raise LlmProviderError(_provider_http_failure(response.status, payload), 0)
        return json.loads(payload.decode())
    finally:
        connection.close()


def _safe_provider_failure(payload: dict[str, object]) -> str:
    """Return a bounded diagnostic without ever reflecting credentials or request data."""
    error = payload.get("error")
    if isinstance(error, dict):
        code = str(error.get("code", "provider_error"))[:80]
        message = str(error.get("message", "request rejected"))[:240]
        return f"LLM provider rejected request: {code}: {message}"
    if "code" in payload or "message" in payload or "msg" in payload:
        code = str(payload.get("code", "provider_error"))[:80]
        message = str(payload.get("message", payload.get("msg", "request rejected")))[:240]
        return f"LLM provider rejected request: {code}: {message}"
    fields = ",".join(sorted(str(key)[:40] for key in payload)[:12])
    return f"LLM provider returned unexpected response fields: {fields or 'none'}"


def _provider_http_failure(status: int, payload: bytes) -> str:
    """Preserve a bounded provider diagnostic while excluding request credentials."""
    prefix = f"LLM connectivity failed: HTTP {status}"
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return prefix
    if not isinstance(decoded, dict):
        return prefix
    return f"{prefix}; {_safe_provider_failure(decoded)}"


def test_chat(api_base: str, model_id: str, api_key: str) -> dict[str, object]:
    try:
        host, port = validate_api_base(api_base)
    except ValueError as exc:
        raise LlmProviderError(str(exc), 0) from exc
    initial_addresses = _resolved_addresses(host, port)
    body = json.dumps(
        {
            "model": model_id,
            "messages": [{"role": "user", "content": "Hi, this is a connectivity test. Reply with 'OK'."}],
            # Reasoning-capable models may spend the first tokens internally; a tiny
            # budget can yield a valid terminal usage frame with no assistant choice.
            "max_tokens": 1000,
            "temperature": 0.7,
            "thinking": {"type": "disabled"},
            "stream": False,
        }
    ).encode()
    parsed = urlsplit(api_base)
    path = parsed.path.rstrip("/") + "/chat/completions"
    started = monotonic()
    try:
        # The socket is connected to an already-validated address rather than resolving
        # the hostname again, which closes the DNS-rebinding window.
        payload = None
        for attempt in range(3):
            try:
                payload = _post_json(
                    host=host,
                    port=port,
                    address=sorted(initial_addresses)[0],
                    path=path,
                    body=body,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                )
                break
            except LlmProviderError as exc:
                transient = any(f"HTTP {status}" in exc.detail for status in (429, 500, 502, 503, 504))
                if not transient or attempt == 2:
                    raise
                sleep(0.5 * (attempt + 1))
        assert payload is not None
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise LlmProviderError(_safe_provider_failure(payload), int((monotonic() - started) * 1000))
        message = choices[0].get("message")
        if not isinstance(message, dict) or "content" not in message:
            raise LlmProviderError(_safe_provider_failure(payload), int((monotonic() - started) * 1000))
        content = str(message["content"])
    except LlmProviderError:
        raise
    except (OSError, TimeoutError, ValueError, KeyError, IndexError, TypeError) as exc:
        elapsed_ms = int((monotonic() - started) * 1000)
        raise LlmProviderError(f"LLM connectivity failed: {type(exc).__name__}", elapsed_ms) from exc
    return {
        "status": "success",
        "message": "LLM connectivity test succeeded",
        "reply": content[:200],
        "elapsed_ms": int((monotonic() - started) * 1000),
    }


def chat_completion(
    *,
    api_base: str,
    model_id: str,
    api_key: str,
    messages: list[dict[str, object]],
    tools: object,
) -> dict[str, object]:
    """Issue one non-streaming OpenAI-compatible assistant turn."""
    try:
        host, port = validate_api_base(api_base)
    except ValueError as exc:
        raise LlmProviderError(str(exc), 0) from exc
    initial_addresses = _resolved_addresses(host, port)
    body = json.dumps({
        "model": model_id,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "max_tokens": 1200,
        "temperature": 0.2,
        "stream": False,
    }, ensure_ascii=False).encode()
    parsed = urlsplit(api_base)
    path = parsed.path.rstrip("/") + "/chat/completions"
    return _post_json(
        host=host,
        port=port,
        address=next(iter(initial_addresses)),
        path=path,
        body=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
