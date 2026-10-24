"""AES-256-GCM credential protection for provider API keys."""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_AAD = b"datara:rebuild:llm-model:api-key:v1"


class LlmCredentialCipher:
    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("LLM encryption key must be exactly 32 bytes")
        self._cipher = AESGCM(key)

    @classmethod
    def from_env(cls, variable: str = "LLM_ENCRYPTION_KEY") -> "LlmCredentialCipher":
        raw = os.getenv(variable, "")
        if not raw:
            raise RuntimeError(f"{variable} must be configured")
        try:
            return cls(_unb64(raw))
        except (ValueError, TypeError) as exc:
            raise RuntimeError(f"{variable} must be URL-safe base64 encoding exactly 32 bytes") from exc

    def encrypt(self, plaintext: str) -> str:
        if not plaintext:
            raise ValueError("LLM API key must not be empty")
        nonce = os.urandom(12)
        return f"v1.{_b64(nonce)}.{_b64(self._cipher.encrypt(nonce, plaintext.encode(), _AAD))}"

    def decrypt(self, serialized: str) -> str:
        try:
            version, nonce, ciphertext = serialized.split(".", 2)
            if version != "v1":
                raise ValueError("unsupported credential version")
            return self._cipher.decrypt(_unb64(nonce), _unb64(ciphertext), _AAD).decode()
        except Exception as exc:
            if isinstance(exc, ValueError) and str(exc) == "unsupported credential version":
                raise
            raise ValueError("invalid or tampered LLM credential") from exc


def mask_api_key(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return "*" * min(8, len(value) - 4) + value[-4:]


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
