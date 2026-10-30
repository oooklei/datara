# Codex P1-6: adapter sovereignty test report

Date: 2026-10-17 (Asia/Shanghai). Scope: `datara-backend/tests/ai_copilot/test_adapter_sovereignty.py` against P1-0 implementation-plan step 2.

## Execution evidence

- Command: `python -m pytest -q tests/ai_copilot/test_adapter_sovereignty.py` (run from `datara-backend/`).
- Result: **10 passed in 0.15s**.
- Broader package check: `python -m pytest -q tests/ai_copilot` → **12 passed in 0.15s**.

## Four sovereignty assertions

1. **Key/config boundary — covered:** canonical `LLM_*` env variables are read; unknown alias does not override them; `SecretStr` masks key values; disabled/partial/unknown provider configurations are covered (`test_adapter_sovereignty.py` lines 23–61).
2. **Generation does not execute SQL — covered:** fake Vanna records generation and an execution method; assertions confirm `allow_llm_to_see_data=False`, no execution call, and no adapter `run_sql` method (`lines 64–94`).
3. **Trusted user/project context — covered:** missing, incomplete, and non-positive context is rejected; context is immutable (`lines 97–105, 108–145`).
4. **Memory audit and scope — covered with limits:** memory writes emit start/success events bound to user/project, omit content fields, and fail closed when the start audit hook fails (`lines 108–170`). The test does not cover all `remove_training_data` failure paths or a persistent audit backend.

## Status and limitations

The tested files are currently untracked in the canonical worktree; these results prove this working-tree snapshot only. The test suite gives a passing base for the four design assertions, but is not a production audit-store or live Vanna integration test. Cross-project retrieval isolation is reported separately and remains incomplete.

This is test evidence, not a P1-6 closeout or GREEN declaration.
