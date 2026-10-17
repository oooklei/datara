"""R8-A generate_sql consumption-seam tests (P1-3 step 5, TDD).

generate_sql is adapter-internal (supervisor #147): never a ninth registry
tool. This seam consumes ONLY Codex's P1-2 public contract surface
(ai_copilot.adapter.CopilotAdapter.generate_sql + AdapterContext) with trusted
identity from the authorized service layer — no Vanna, no engine, no SQL
execution (the adapter's client already refuses run_sql).
"""

import pytest

from ai_copilot.adapter import AdapterContext, SovereigntyContextMissing, VannaAdapterError
from rebuild.generate_sql import SqlGenerationError, build_generate_sql_port


class _FakeAdapter:
    def __init__(self, *, sql="SELECT count(*) FROM users", exc=None):
        self.calls = []
        self.sql = sql
        self.exc = exc

    def generate_sql(self, question, context):
        self.calls.append((question, context))
        if self.exc is not None:
            raise self.exc
        return self.sql


def test_port_delegates_question_with_trusted_adapter_context():
    adapter = _FakeAdapter()
    port = build_generate_sql_port(adapter)
    sql = port.generate("how many users", user_id=3, project_id=7)
    assert sql == "SELECT count(*) FROM users"
    assert adapter.calls == [("how many users", AdapterContext(user_id=3, project_id=7))]


def test_adapter_generation_failure_maps_sanitized_without_engine_detail():
    # supervisor #181 security fix: the wrapped error must carry NO underlying
    # adapter/LLM text and NO chained cause/traceback leak path (O7 sovereignty).
    leak_marker = "vanna-internal: secret-model-endpoint/api-key-context"
    port = build_generate_sql_port(_FakeAdapter(exc=VannaAdapterError(leak_marker)))
    with pytest.raises(SqlGenerationError) as excinfo:
        port.generate("how many users", user_id=3, project_id=7)
    assert leak_marker not in str(excinfo.value)  # sanitized message only
    assert excinfo.value.__cause__ is None  # exception chain stripped (from None)
    assert "VannaAdapterError" not in repr(excinfo.value.__cause__)


def test_llm_disabled_maps_sanitized():
    port = build_generate_sql_port(
        _FakeAdapter(exc=VannaAdapterError("LLM is disabled; configure the canonical LLM_* variables"))
    )
    with pytest.raises(SqlGenerationError):
        port.generate("how many users", user_id=3, project_id=7)


def test_missing_trusted_context_propagates_not_swallowed():
    port = build_generate_sql_port(
        _FakeAdapter(exc=SovereigntyContextMissing("user_id must be a positive integer"))
    )
    with pytest.raises(SovereigntyContextMissing):
        port.generate("how many users", user_id=3, project_id=7)


def test_invalid_identity_rejected_by_adapter_context():
    adapter = _FakeAdapter()
    port = build_generate_sql_port(adapter)
    with pytest.raises(SovereigntyContextMissing):
        port.generate("how many users", user_id=0, project_id=7)
    assert adapter.calls == []  # rejected before the adapter call


def test_port_refuses_adapter_without_generate_sql():
    with pytest.raises(ValueError):
        build_generate_sql_port(object())
