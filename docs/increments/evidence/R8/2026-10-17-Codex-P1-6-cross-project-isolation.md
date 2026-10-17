# Codex P1-6: cross-project memory isolation evidence

Date: 2026-10-17 (Asia/Shanghai). Scope: compare two authenticated adapter contexts using the same user and different project IDs.

## Reproducible checks

- Existing test: `datara-backend/tests/ai_copilot/test_adapter_sovereignty.py::test_chroma_memory_is_partitioned_by_project_and_user` passes as part of the 12-test package run.
- Additional in-process adapter check used `AdapterContext(user_id=7, project_id=11)` and `AdapterContext(user_id=7, project_id=12)` with a fake Vanna factory. Result: `PASS distinct_clients=True distinct_project_paths=True both_under_root=True`.
- The adapter caches Vanna clients by immutable `(user_id, project_id)` context and derives each Chroma path beneath the managed `CHROMA_DB_PATH`; path-escape is rejected (`datara-backend/ai_copilot/adapter.py`, `_client`, `_scoped_chroma_path`, `_default_factory`).

## Limit of this evidence

This proves context-to-client and context-to-storage-path partitioning without making an LLM/network call. It does **not** perform real Chroma writes and cross-project searches, and the available global Python environment has no installed `chromadb` package. Therefore the P1-0 requirement for a two-project “write in A, cannot retrieve from B” demonstration remains **PARTIAL / NOT VERIFIED**. Do not claim complete vector-retrieval isolation or close P1-6 on this evidence alone.
