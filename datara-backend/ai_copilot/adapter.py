"""Datara-owned boundary around Vanna's SQL generation and Chroma memory.

Vanna SDK imports are intentionally lazy and confined to this module. No
Datara-facing method exposes a Vanna class, database connection, or SQL
execution capability. A request context must come from the authorized
Datara service layer, never directly from untrusted request JSON.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Mapping

from .config import AIConfig, BACKEND_ROOT, get_llm_settings

DATA_ROOT = BACKEND_ROOT / "data" / "ai_copilot"
CHROMA_DB_PATH = DATA_ROOT / "chromadb"


class SovereigntyContextMissing(RuntimeError):
    """Raised when a call lacks a trusted user/project identity."""


class VannaAdapterError(RuntimeError):
    """Sanitized error raised for failures inside the third-party adapter."""


@dataclass(frozen=True)
class AdapterContext:
    """Immutable identity supplied by the authenticated Datara service."""

    user_id: int
    project_id: int

    def __post_init__(self) -> None:
        if not isinstance(self.user_id, int) or isinstance(self.user_id, bool) or self.user_id < 1:
            raise SovereigntyContextMissing("user_id must be a positive integer")
        if not isinstance(self.project_id, int) or isinstance(self.project_id, bool) or self.project_id < 1:
            raise SovereigntyContextMissing("project_id must be a positive integer")

    @classmethod
    def from_value(cls, value: object) -> "AdapterContext":
        if isinstance(value, cls):
            return value
        if isinstance(value, Mapping):
            try:
                return cls(user_id=value.get("user_id"), project_id=value.get("project_id"))  # type: ignore[arg-type]
            except (TypeError, ValueError) as exc:
                raise SovereigntyContextMissing("user_id and project_id are required") from exc
        raise SovereigntyContextMissing("user_id and project_id are required")


@dataclass(frozen=True)
class MemoryAuditEvent:
    """Safe audit metadata; deliberately has no SQL/document content field."""

    action: str
    user_id: int
    project_id: int
    object_category: str
    outcome: str


AuditHook = Callable[[MemoryAuditEvent], None]
VannaFactory = Callable[[AdapterContext, AIConfig], Any]


class CopilotAdapter:
    """Expose Vanna functionality through Datara's narrow sovereignty contract."""

    def __init__(
        self,
        *,
        audit_hook: AuditHook,
        vanna_factory: VannaFactory | None = None,
        settings: AIConfig | None = None,
    ) -> None:
        if audit_hook is None:
            raise ValueError("a Datara audit hook is required")
        self._audit_hook = audit_hook
        self._settings = settings
        self._vanna_factory = vanna_factory or self._default_factory
        self._clients: dict[AdapterContext, Any] = {}
        self._clients_lock = RLock()

    @property
    def data_root(self) -> Path:
        return DATA_ROOT.resolve()

    @property
    def chroma_path(self) -> Path:
        return CHROMA_DB_PATH.resolve()

    def generate_sql(self, question: str, context: AdapterContext) -> str:
        """Generate SQL only. Vanna's optional data-introspection execution stays disabled."""

        trusted_context = AdapterContext.from_value(context)
        if not question or not question.strip():
            raise ValueError("question must be non-empty")
        self._emit("generate_sql", trusted_context, "memory_read_and_llm", "started")
        try:
            client = self._client(trusted_context)
            sql = client.generate_sql(
                question,
                allow_llm_to_see_data=False,
                user_id=trusted_context.user_id,
                project_id=trusted_context.project_id,
            )
            if not isinstance(sql, str):
                raise TypeError("Vanna returned a non-text SQL result")
        except Exception:
            self._emit("generate_sql", trusted_context, "memory_read_and_llm", "failed")
            raise VannaAdapterError("SQL generation failed") from None
        self._emit("generate_sql", trusted_context, "memory_read_and_llm", "succeeded")
        return sql

    def add_ddl(self, ddl: str, context: AdapterContext) -> str:
        return self._memory_write("add_ddl", "ddl", (ddl,), context)

    def add_documentation(self, documentation: str, context: AdapterContext) -> str:
        return self._memory_write("add_documentation", "documentation", (documentation,), context)

    def add_sql(self, question: str, sql: str, context: AdapterContext) -> str:
        return self._memory_write("add_question_sql", "sql", (question, sql), context)

    def remove_training_data(self, memory_id: str, context: AdapterContext) -> bool:
        trusted_context = AdapterContext.from_value(context)
        self._emit("remove_training_data", trusted_context, "memory", "started")
        try:
            result = self._client(trusted_context).remove_training_data(id=memory_id)
        except Exception:
            self._emit("remove_training_data", trusted_context, "memory", "failed")
            raise VannaAdapterError("memory deletion failed") from None
        self._emit("remove_training_data", trusted_context, "memory", "succeeded")
        return bool(result)

    def _memory_write(
        self,
        action: str,
        object_category: str,
        args: tuple[str, ...],
        context: AdapterContext,
    ) -> str:
        trusted_context = AdapterContext.from_value(context)
        self._emit(action, trusted_context, object_category, "started")
        try:
            client = self._client(trusted_context)
            if action == "add_question_sql":
                result = client.add_question_sql(
                    question=args[0],
                    sql=args[1],
                    user_id=trusted_context.user_id,
                    project_id=trusted_context.project_id,
                )
            else:
                result = getattr(client, action)(
                    args[0], user_id=trusted_context.user_id, project_id=trusted_context.project_id
                )
        except Exception:
            self._emit(action, trusted_context, object_category, "failed")
            raise VannaAdapterError(f"{object_category} memory write failed") from None
        self._emit(action, trusted_context, object_category, "succeeded")
        return str(result)

    def _emit(self, action: str, context: AdapterContext, category: str, outcome: str) -> None:
        # Audit-hook failure is fail-closed: the corresponding operation must not proceed.
        self._audit_hook(
            MemoryAuditEvent(
                action=action,
                user_id=context.user_id,
                project_id=context.project_id,
                object_category=category,
                outcome=outcome,
            )
        )

    def _client(self, context: AdapterContext) -> Any:
        settings = self._settings or get_llm_settings()
        if not settings.enabled:
            raise VannaAdapterError("LLM is disabled; configure the canonical LLM_* variables")
        with self._clients_lock:
            client = self._clients.get(context)
            if client is None:
                # A client is cached only within its immutable user/project identity.
                client = self._vanna_factory(context, settings)
                self._clients[context] = client
            return client

    @staticmethod
    def _scoped_chroma_path(context: AdapterContext) -> Path:
        trusted_context = AdapterContext.from_value(context)
        root = CHROMA_DB_PATH.resolve()
        scoped_path = root / f"project-{trusted_context.project_id}" / f"user-{trusted_context.user_id}"
        scoped_path = scoped_path.resolve()
        if not scoped_path.is_relative_to(root):
            raise VannaAdapterError("memory path escaped the managed ChromaDB directory")
        return scoped_path

    @staticmethod
    def _default_factory(context: AdapterContext, settings: AIConfig) -> Any:
        """Build a tenant-isolated Vanna instance using only Datara's data root."""

        from openai import OpenAI
        from vanna.legacy.chromadb.chromadb_vector import ChromaDB_VectorStore
        from vanna.legacy.openai.openai_chat import OpenAI_Chat

        # Separate durable vector stores prevent any cross-user/project memory retrieval.
        scoped_path = CopilotAdapter._scoped_chroma_path(context)

        client = OpenAI(api_key=settings.api_key.get_secret_value(), base_url=settings.base_url)

        class _TenantVanna(ChromaDB_VectorStore, OpenAI_Chat):
            def __init__(self) -> None:
                ChromaDB_VectorStore.__init__(self, config={"path": str(scoped_path)})
                OpenAI_Chat.__init__(self, client=client, config={"model": settings.model})

            def log(self, message: str, title: str = "Info") -> None:
                # Upstream logs SQL prompts and generated SQL; Datara forbids that leakage.
                return None

            def run_sql(self, sql: str, *args: Any, **kwargs: Any) -> Any:
                raise PermissionError("SQL execution is owned by the R8-A authorized bridge")

        return _TenantVanna()


__all__ = [
    "AdapterContext",
    "CHROMA_DB_PATH",
    "CopilotAdapter",
    "DATA_ROOT",
    "MemoryAuditEvent",
    "SovereigntyContextMissing",
    "VannaAdapterError",
]
