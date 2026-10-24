"""Isolated OpenAI-compatible connectivity probe."""

import json
import ipaddress
import http.client
import os
import socket
import ssl
from time import monotonic
from urllib.parse import urlsplit


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
    raw_socket = socket.create_connection((address, port), timeout=30)
    connection = http.client.HTTPConnection(host, port, timeout=30)
    try:
        connection.sock = ssl.create_default_context().wrap_socket(raw_socket, server_hostname=host)
        connection.request("POST", path, body=body, headers=headers)
        response = connection.getresponse()
        payload = response.read()
        if response.status < 200 or response.status >= 300:
            # http.client never follows redirects, so credentials cannot cross origins.
            raise LlmProviderError(f"LLM connectivity failed: HTTP {response.status}", 0)
        return json.loads(payload.decode())
    finally:
        connection.close()


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
            "max_tokens": 10,
            "temperature": 0.1,
            "stream": False,
        }
    ).encode()
    parsed = urlsplit(api_base)
    path = parsed.path.rstrip("/") + "/chat/completions"
    started = monotonic()
    try:
        # The socket is connected to an already-validated address rather than resolving
        # the hostname again, which closes the DNS-rebinding window.
        payload = _post_json(
            host=host,
            port=port,
            address=sorted(initial_addresses)[0],
            path=path,
            body=body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        content = str(payload["choices"][0]["message"]["content"])
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
