# Codex P1-6: cross-project memory isolation evidence

Date: 2026-10-17 (Asia/Shanghai). Scope: persistent Chroma isolation for two valid adapter contexts with the same user and different project IDs.

## Reproducible checks

- Existing test `test_chroma_memory_is_partitioned_by_project_and_user` passes as part of `python -m pytest -q tests/ai_copilot` (12 passed).
- In the isolated lock venv (`datara-p16-ai-venv-20261017`), a no-network Chroma integration check temporarily pointed `ai_copilot.adapter.CHROMA_DB_PATH` at a fresh temp directory, derived paths through `CopilotAdapter._scoped_chroma_path`, then wrote vector `a-secret` to project 11 and queried both project stores.
- Result: `PASS project11_query=[['a-secret']] project12_query=[[]] isolated_dirs=True`. Clients were explicitly closed and the verified run cleaned its temporary store.
- The adapter derives per-user/project Chroma paths under `CHROMA_DB_PATH` and rejects path escape (`datara-backend/ai_copilot/adapter.py`, `_scoped_chroma_path`, `_default_factory`). Lock environment setup and `pip check` evidence is in `2026-10-17-Codex-P1-6-lock-venv-install.md`.

## Scope limits

This verifies actual persistent Chroma storage/query separation using deterministic supplied embeddings and the adapter's project path derivation. It does not exercise API authentication/project authorization, LLM embeddings, or end-to-end calls through a mounted R8-A endpoint. Storage-level cross-project isolation is **PASS**; API authorization integration remains outside this demonstration.

## Audit-hook evidence supplement (2026-10-17)

To address the review note that the first storage-isolation demonstration did not show audit events in the same execution, reran both paths together in the isolated lock venv with real `chromadb.PersistentClient` storage under a fresh temporary root, deterministic supplied embeddings, and a mock local Vanna/LLM boundary:

- Project 11 wrote `project-11-secret` to its persistent collection and retrieved that value through `CopilotAdapter.generate_sql`.
- Project 12 queried its distinct persistent collection and returned `NO_MATCH`; it could not retrieve the Project 11 document.
- The same run captured six `MemoryAuditEvent`s: `add_documentation` started/succeeded for project 11, `generate_sql` started/succeeded for project 11, and `generate_sql` started/succeeded for project 12. Each carried user 7 and the corresponding project ID.
- Result: `PASS project11='project-11-secret' project12='NO_MATCH' audit_events=6 projects=[11, 11, 11, 11, 12, 12]`; temporary Chroma clients were closed and the temporary store was removed.

This closes the demonstration-level hook-evidence omission. It still does not exercise HTTP authentication, R8-A dispatch, or a production audit database; those remain separately scoped to the P1-3 bridge and P1-6' follow-up.
