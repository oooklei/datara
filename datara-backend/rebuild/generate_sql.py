"""generate_sql consumption seam over the P1-2 CopilotAdapter public contract.

Contract: supervisor #147 (generate_sql is adapter-internal, never a ninth
registry tool) + R8-A contract §11/§13.9; Codex P1-2 surface:
``ai_copilot/adapter.py`` (``__all__`` public contract). The rebuild side
consumes ONLY that public surface (``generate_sql`` + ``AdapterContext``); no
Vanna import, no engine, no SQL execution here — the adapter's client itself
refuses execution ("SQL execution is owned by the R8-A authorized bridge").
Trusted identity comes from the authorized Datara service layer (bridge
context), never from untrusted request JSON.
"""

from __future__ import annotations

from typing import Any, Protocol

from ai_copilot.adapter import AdapterContext, VannaAdapterError


class SqlGenerationError(RuntimeError):
    """Sanitized generation failure; third-party/LLM detail never leaks."""


class SqlGenerationPort(Protocol):
    """Orchestrator-facing generation seam (R8-B consumes this, not the adapter)."""

    def generate(self, question: str, *, user_id: int, project_id: int) -> str:
        ...


def build_generate_sql_port(adapter: Any) -> SqlGenerationPort:
    """Compose a rebuild-side generation port over the injected P1-2 adapter."""
    if not callable(getattr(adapter, "generate_sql", None)):
        raise ValueError("generate_sql requires an injected adapter exposing generate_sql()")

    class _AdapterGenerationPort:
        def generate(self, question: str, *, user_id: int, project_id: int) -> str:
            # AdapterContext validates the trusted identity; SovereigntyContextMissing
            # (a trusted-layer programming error) propagates instead of being swallowed.
            try:
                return adapter.generate_sql(
                    question, AdapterContext(user_id=user_id, project_id=project_id)
                )
            except VannaAdapterError as exc:
                # sanitized mapping: adapter/LLM internals never reach rebuild callers
                raise SqlGenerationError("generate_sql failed") from exc

    return _AdapterGenerationPort()
