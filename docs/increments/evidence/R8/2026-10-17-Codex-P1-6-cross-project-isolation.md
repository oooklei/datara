# Codex P1-6: cross-project memory isolation evidence

Date: 2026-10-17 (Asia/Shanghai). Scope: persistent Chroma isolation for two valid adapter contexts with the same user and different project IDs.

## Reproducible checks

- Existing test `test_chroma_memory_is_partitioned_by_project_and_user` passes as part of `python -m pytest -q tests/ai_copilot` (12 passed).
- In the isolated lock venv (`datara-p16-ai-venv-20261017`), a no-network Chroma integration check temporarily pointed `ai_copilot.adapter.CHROMA_DB_PATH` at a fresh temp directory, derived paths through `CopilotAdapter._scoped_chroma_path`, then wrote vector `a-secret` to project 11 and queried both project stores.
- Result: `PASS project11_query=[['a-secret']] project12_query=[[]] isolated_dirs=True`. Clients were explicitly closed and the verified run cleaned its temporary store.
- The adapter derives per-user/project Chroma paths under `CHROMA_DB_PATH` and rejects path escape (`datara-backend/ai_copilot/adapter.py`, `_scoped_chroma_path`, `_default_factory`). Lock environment setup and `pip check` evidence is in `2026-10-17-Codex-P1-6-lock-venv-install.md`.

## Scope limits

This verifies actual persistent Chroma storage/query separation using deterministic supplied embeddings and the adapter's project path derivation. It does not exercise API authentication/project authorization, LLM embeddings, or end-to-end calls through a mounted R8-A endpoint. Storage-level cross-project isolation is **PASS**; API authorization integration remains outside this demonstration.
