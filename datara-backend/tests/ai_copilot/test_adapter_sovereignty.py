from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError


def _clear_llm_environment(monkeypatch):
    for key in ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY"):
        monkeypatch.delenv(key, raising=False)


def _enabled_test_settings():
    from ai_copilot.config import AIConfig

    return AIConfig(
        LLM_PROVIDER="siliconflow",
        LLM_BASE_URL="https://api.siliconflow.cn/v1",
        LLM_MODEL="deepseek-ai/DeepSeek-V4.1-Flash",
        LLM_API_KEY="unit-test-secret",
    )


def test_llm_config_reads_canonical_env_names_and_masks_the_key(monkeypatch):
    from ai_copilot.config import AIConfig

    _clear_llm_environment(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "siliconflow")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.siliconflow.cn/v1")
    monkeypatch.setenv("LLM_MODEL", "deepseek-ai/DeepSeek-V4.1-Flash")
    monkeypatch.setenv("LLM_API_KEY", "test-secret-never-log")
    monkeypatch.setenv("DATARA_AI_LLM_API_KEY", "wrong-alias-must-not-win")
    config = AIConfig.from_env(env_file=None)

    assert config.provider == "siliconflow"
    assert config.base_url == "https://api.siliconflow.cn/v1"
    assert config.model == "deepseek-ai/DeepSeek-V4.1-Flash"
    assert isinstance(config.api_key, SecretStr)
    assert config.api_key.get_secret_value() == "test-secret-never-log"
    assert "test-secret-never-log" not in repr(config)
    assert "wrong-alias-must-not-win" not in repr(config)
    assert "test-secret-never-log" not in repr(config.model_dump())


def test_llm_config_allows_disabled_mode_but_rejects_partial_and_unknown(monkeypatch):
    from ai_copilot.config import AIConfig

    _clear_llm_environment(monkeypatch)
    disabled = AIConfig.from_env(env_file=None)
    assert disabled.enabled is False

    monkeypatch.setenv("LLM_PROVIDER", "unknown-provider")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("LLM_MODEL", "model")
    monkeypatch.setenv("LLM_API_KEY", "test-secret")
    with pytest.raises(ValidationError):
        AIConfig.from_env(env_file=None)

    monkeypatch.setenv("LLM_PROVIDER", "siliconflow")
    monkeypatch.delenv("LLM_API_KEY")
    with pytest.raises(ValidationError):
        AIConfig.from_env(env_file=None)


def test_generate_sql_returns_text_without_any_execution_channel():
    from ai_copilot.adapter import AdapterContext, CopilotAdapter

    generated = []
    executed = []
    events = []

    class FakeVanna:
        def generate_sql(self, question, *, allow_llm_to_see_data, user_id, project_id):
            generated.append((question, allow_llm_to_see_data, user_id, project_id))
            return "SELECT 1"

        def run_sql(self, sql):
            executed.append(sql)
            return []

    adapter = CopilotAdapter(
        vanna_factory=lambda _context, _settings: FakeVanna(),
        audit_hook=events.append,
        settings=_enabled_test_settings(),
    )
    context = AdapterContext(user_id=7, project_id=11)

    assert adapter.generate_sql("show rows", context=context) == "SELECT 1"
    assert generated == [("show rows", False, 7, 11)]
    assert executed == []
    assert not hasattr(adapter, "run_sql")
    assert [(event.action, event.outcome) for event in events] == [
        ("generate_sql", "started"),
        ("generate_sql", "succeeded"),
    ]


@pytest.mark.parametrize(
    "context",
    [None, {"user_id": 7}, {"project_id": 11}, {"user_id": 0, "project_id": 11}],
)
def test_context_requires_positive_user_and_project_ids(context):
    from ai_copilot.adapter import AdapterContext, SovereigntyContextMissing

    with pytest.raises(SovereigntyContextMissing):
        AdapterContext.from_value(context)


def test_context_is_immutable_and_memory_operations_are_audited_and_scoped():
    from ai_copilot.adapter import AdapterContext, CopilotAdapter

    events = []
    vanna_calls = []

    class FakeVanna:
        def add_ddl(self, ddl, *, user_id, project_id):
            vanna_calls.append(("ddl", user_id, project_id, ddl))

        def add_documentation(self, documentation, *, user_id, project_id):
            vanna_calls.append(("documentation", user_id, project_id, documentation))

        def add_question_sql(self, question, sql, *, user_id, project_id):
            vanna_calls.append(("sql", user_id, project_id, question, sql))

    context = AdapterContext(user_id=7, project_id=11)
    adapter = CopilotAdapter(
        vanna_factory=lambda _context, _settings: FakeVanna(),
        audit_hook=events.append,
        settings=_enabled_test_settings(),
    )
    with pytest.raises((AttributeError, TypeError)):
        context.project_id = 12

    adapter.add_ddl("CREATE TABLE t (id INT)", context=context)
    adapter.add_documentation("table t contains records", context=context)
    adapter.add_sql("show rows", "SELECT id FROM t", context=context)

    assert [event.action for event in events] == [
        "add_ddl", "add_ddl", "add_documentation", "add_documentation", "add_question_sql", "add_question_sql"
    ]
    assert [event.outcome for event in events] == ["started", "succeeded"] * 3
    assert all(event.user_id == 7 and event.project_id == 11 for event in events)
    assert all(not hasattr(event, "content") for event in events)
    assert all(call[1:3] == (7, 11) for call in vanna_calls)
    assert adapter.chroma_path == Path(__file__).resolve().parents[2] / "data" / "ai_copilot" / "chromadb"
    assert adapter.chroma_path.is_relative_to(adapter.data_root)


def test_started_audit_failure_prevents_memory_mutation():
    from ai_copilot.adapter import AdapterContext, CopilotAdapter

    vanna_calls = []

    class FakeVanna:
        def add_ddl(self, ddl, **_kwargs):
            vanna_calls.append(ddl)

    def audit_hook(event):
        if event.outcome == "started":
            raise RuntimeError("audit store unavailable")

    adapter = CopilotAdapter(
        vanna_factory=lambda _context, _settings: FakeVanna(),
        audit_hook=audit_hook,
        settings=_enabled_test_settings(),
    )

    with pytest.raises(RuntimeError, match="audit store unavailable"):
        adapter.add_ddl("CREATE TABLE t (id INT)", AdapterContext(user_id=7, project_id=11))

    assert vanna_calls == []


def test_chroma_memory_is_partitioned_by_project_and_user():
    from ai_copilot.adapter import CHROMA_DB_PATH, AdapterContext, CopilotAdapter

    path_a = CopilotAdapter._scoped_chroma_path(AdapterContext(user_id=7, project_id=11))
    path_b = CopilotAdapter._scoped_chroma_path(AdapterContext(user_id=8, project_id=11))
    path_c = CopilotAdapter._scoped_chroma_path(AdapterContext(user_id=7, project_id=12))

    assert path_a != path_b
    assert path_a != path_c
    assert path_a.is_relative_to(CHROMA_DB_PATH.resolve())
    assert path_b.is_relative_to(CHROMA_DB_PATH.resolve())
    assert path_c.is_relative_to(CHROMA_DB_PATH.resolve())
