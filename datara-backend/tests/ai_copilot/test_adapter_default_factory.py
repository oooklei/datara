"""TDD test for adapter.py:217 missing-self defect (P1-6' first real defect).

Defect: OpenAI_Chat.__init__(client=..., config=...) called without self
-> TypeError on every _TenantVanna construction -> default factory fails.

This test reproduces the defect by calling _default_factory directly.
Pre-fix: FAIL (TypeError: missing 1 required positional argument: 'self')
Post-fix: PASS (returns valid _TenantVanna instance)

Uses monkeypatch to redirect chroma paths to a temp directory, avoiding
pollution of the real data/ai_copilot/chromadb/ directory.
"""

import pytest


def _test_settings():
    from ai_copilot.config import AIConfig

    return AIConfig(
        LLM_PROVIDER="siliconflow",
        LLM_BASE_URL="https://api.siliconflow.cn/v1",
        LLM_MODEL="deepseek-ai/DeepSeek-V4.1-Flash",
        LLM_API_KEY="unit-test-secret",
    )


@pytest.fixture(autouse=True)
def _isolate_chroma_path(tmp_path, monkeypatch):
    """Redirect _scoped_chroma_path to a temp directory."""
    from ai_copilot.adapter import CopilotAdapter

    def _fake_scoped_path(context):
        return tmp_path / f"project-{context.project_id}" / f"user-{context.user_id}"

    monkeypatch.setattr(CopilotAdapter, "_scoped_chroma_path", staticmethod(_fake_scoped_path))
    yield


def test_default_factory_returns_valid_tenant_vanna_instance():
    """Reproduces adapter.py:217 missing-self defect.

    Calls _default_factory directly. Pre-fix: TypeError (missing self).
    Post-fix: returns a valid _TenantVanna instance with expected semantics.
    """
    from ai_copilot.adapter import AdapterContext, CopilotAdapter

    context = AdapterContext(user_id=7, project_id=11)
    settings = _test_settings()

    # This call triggers the defect: OpenAI_Chat.__init__ without self
    vanna = CopilotAdapter._default_factory(context, settings)

    # Post-fix assertions: valid instance with expected semantics
    assert vanna is not None
    # run_sql raises PermissionError (sovereignty)
    with pytest.raises(PermissionError, match="SQL execution is owned by the R8-A authorized bridge"):
        vanna.run_sql("SELECT 1")
    # log is silent (no leakage)
    assert vanna.log("test message", title="Test") is None


def test_default_factory_uses_scoped_chroma_path():
    """Verify _default_factory creates tenant-isolated chroma path."""
    from ai_copilot.adapter import AdapterContext, CopilotAdapter

    context_a = AdapterContext(user_id=7, project_id=11)
    context_b = AdapterContext(user_id=8, project_id=11)
    settings = _test_settings()

    vanna_a = CopilotAdapter._default_factory(context_a, settings)
    vanna_b = CopilotAdapter._default_factory(context_b, settings)

    # Different users -> different scoped chroma clients (verified via internal state)
    assert vanna_a.chroma_client is not vanna_b.chroma_client
