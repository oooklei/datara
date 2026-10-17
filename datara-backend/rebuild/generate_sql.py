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


class SqlGenerationError(RuntimeError):
    """Sanitized generation failure; third-party/LLM detail never leaks."""


class SqlGenerationPort(Protocol):
    """Orchestrator-facing generation seam (R8-B consumes this, not the adapter)."""

    def generate(self, question: str, *, user_id: int, project_id: int) -> str:
        ...


def build_generate_sql_port(adapter: Any) -> SqlGenerationPort:
    """Compose a rebuild-side generation port over the injected P1-2 adapter."""
    raise NotImplementedError("P1-3 step-5 GREEN lands in the next commit")
