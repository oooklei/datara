"""Validated LLM settings for the optional Vanna adapter.

Only the four canonical ``LLM_*`` environment names are accepted. Local
development may source them from ``datara-backend/.env``; deployment should
inject them into the process environment. No secret is logged or persisted.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = BACKEND_ROOT / ".env"
SUPPORTED_PROVIDERS = frozenset({"siliconflow", "volcengine", "longcat"})


class AIConfig(BaseSettings):
    """Immutable process-level model settings; empty values disable live LLM use."""

    provider: str | None = Field(default=None, validation_alias="LLM_PROVIDER")
    base_url: str | None = Field(default=None, validation_alias="LLM_BASE_URL")
    model: str | None = Field(default=None, validation_alias="LLM_MODEL")
    api_key: SecretStr | None = Field(default=None, validation_alias="LLM_API_KEY")

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        frozen=True,
        repr=False,
    )

    @field_validator("provider", "base_url", "model", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("api_key", mode="before")
    @classmethod
    def normalize_optional_secret(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @model_validator(mode="after")
    def validate_configuration(self) -> "AIConfig":
        values = (self.provider, self.base_url, self.model, self.api_key)
        if not any(values):
            return self

        missing = [
            name
            for name, value in zip(
                ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY"), values
            )
            if value is None
        ]
        if missing:
            raise ValueError(f"incomplete LLM configuration; missing: {', '.join(missing)}")
        if self.provider not in SUPPORTED_PROVIDERS:
            raise ValueError("unsupported LLM_PROVIDER")

        parsed = urlparse(self.base_url or "")
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("LLM_BASE_URL must be an absolute HTTPS URL")
        if self.api_key is None or not self.api_key.get_secret_value():
            raise ValueError("LLM_API_KEY must be non-empty when LLM is enabled")
        return self

    @property
    def enabled(self) -> bool:
        return self.provider is not None

    @classmethod
    def from_env(cls, *, env_file: str | Path | None = ENV_FILE) -> "AIConfig":
        """Read process variables plus the local backend ``.env`` by default."""

        return cls(_env_file=env_file)


@lru_cache(maxsize=1)
def get_llm_settings() -> AIConfig:
    """Return cached, validated LLM settings without exposing the secret."""

    return AIConfig()


__all__ = ["AIConfig", "ENV_FILE", "SUPPORTED_PROVIDERS", "ValidationError", "get_llm_settings"]
