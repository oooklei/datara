"""Database-first, environment-fallback default LLM resolver."""

import os

from sqlalchemy import select

from rebuild.llm.models import LlmModelRecord


class DefaultLlmResolver:
    def __init__(self, session_factory, cipher) -> None:
        self._sessions = session_factory
        self._cipher = cipher

    def resolve(self) -> dict[str, str] | None:
        with self._sessions() as session:
            row = session.scalar(
                select(LlmModelRecord).where(LlmModelRecord.is_default.is_(True), LlmModelRecord.is_active.is_(True))
            )
            if row is not None:
                return {
                    "provider": row.provider,
                    "base_url": row.api_base,
                    "model": row.model_id,
                    "api_key": self._cipher.decrypt(row.api_key_cipher),
                    "source": "database",
                }
        values = {
            "provider": os.getenv("LLM_PROVIDER", ""),
            "base_url": os.getenv("LLM_BASE_URL", ""),
            "model": os.getenv("LLM_MODEL", ""),
            "api_key": os.getenv("LLM_API_KEY", ""),
        }
        return {**values, "source": "environment"} if all(values.values()) else None
