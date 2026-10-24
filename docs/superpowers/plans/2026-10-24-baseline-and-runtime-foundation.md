# Datara Baseline and Runtime Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore a reproducible green main application baseline, integrate the already-developed component-spec/LLM/run-statistics work, and establish the execution statistics contract required by every priority workflow.

**Architecture:** Candidate changes in the primary checkout are treated as untrusted source material and are ported as domain-sized source/test/migration units. The rebuild app remains the only backend entry point; migrations are check-summed and idempotent; execution statistics are stored independently from logs and exposed through project-scoped APIs. Each task reaches a locally verifiable checkpoint before the next task starts.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2, pytest, Vue 3, TypeScript, Vitest, Vite.

---

## File structure for this plan

- `datara-backend/rebuild/component_spec/migrations.py` and `revisions/`: component-spec schema migration ownership.
- `datara-backend/rebuild/llm/`: LLM model, encryption, provider, repository, resolver, API, and migration boundary.
- `datara-backend/rebuild/governance/revisions/v0004_token_digest_hardening.py`: existing-token hardening and backfill.
- `datara-backend/rebuild/execution/models.py`, `repository.py`, `run_stats.py`, `api.py`, `migrations.py`, `revisions/v0002_run_statistics.py`: workflow run statistics storage and API.
- `datara-backend/rebuild/api/app.py`: composition root only; no domain logic.
- Matching `datara-backend/tests/rebuild/test_*.py`: contract, migration, and behavior verification.
- `datara-newweb/src/views/qc/`, `views/system/llm-models/`, `views/open/`, `views/sec/`: already-developed candidate pages reviewed for later route integration.

### Task 1: Establish the current failing baseline

**Files:**
- Inspect: `datara-backend/rebuild/api/app.py`
- Inspect: `datara-backend/tests/rebuild/`
- Inspect: `datara-newweb/src/`

- [ ] **Step 1: Verify the worktree backend import fails for the recorded missing migration**

Run: `python -c "import sys; sys.path.insert(0, 'datara-backend'); import rebuild.api.app"`
Expected: FAIL with `ModuleNotFoundError` for `rebuild.component_spec.migrations`.

- [ ] **Step 2: Verify frontend tests/build cannot yet be claimed in the isolated worktree**

Run: `Test-Path datara-newweb/node_modules/.bin/vitest.cmd`
Expected: `False` before dependency provisioning or `True` if dependencies have since been provisioned; record the observed state.

- [ ] **Step 3: Record the primary-checkout comparison baseline**

Run: `git -C 'D:\需求\数据治理工具\Datara' status --short` and the already-proven verification commands.
Expected: primary checkout remains dirty; candidate baseline remains 719 frontend tests passed and 1291 backend tests passed with three failures unless concurrent user work changed it.

### Task 2: Integrate component-spec migration as an atomic unit

**Files:**
- Create: `datara-backend/rebuild/component_spec/migrations.py`
- Create: `datara-backend/rebuild/component_spec/revisions/__init__.py`
- Create: `datara-backend/rebuild/component_spec/revisions/v0001_component_spec_tables.py`
- Create: `datara-backend/tests/rebuild/test_component_spec_migrations.py`
- Modify only if required: `datara-backend/rebuild/api/app.py`

- [ ] **Step 1: Port the candidate migration test unchanged and run it red**

Run: `python -m pytest datara-backend/tests/rebuild/test_component_spec_migrations.py -q`
Expected: collection/import FAIL until migration files are present.

- [ ] **Step 2: Port the revision and migration runner**

The implementation must expose `apply_component_spec_migrations(engine)`, use a stable revision/checksum, create the component definition/version/publication tables and required indexes, reject partial schemas, and remain idempotent.

- [ ] **Step 3: Run the focused migration and component API suites**

Run: `python -m pytest datara-backend/tests/rebuild/test_component_spec_migrations.py datara-backend/tests/rebuild/test_component_spec_api.py datara-backend/tests/rebuild/test_component_spec_runtime_only.py -q`
Expected: all tests PASS.

- [ ] **Step 4: Commit the atomic unit**

Run: `git add datara-backend/rebuild/component_spec datara-backend/tests/rebuild/test_component_spec_migrations.py datara-backend/rebuild/api/app.py && git commit -m "fix(component-spec): restore migration unit"`
Expected: one commit containing source, migration, tests, and composition changes only.

### Task 3: Integrate the LLM domain as an atomic unit

**Files:**
- Create: `datara-backend/rebuild/llm/__init__.py`
- Create: `datara-backend/rebuild/llm/api.py`
- Create: `datara-backend/rebuild/llm/crypto.py`
- Create: `datara-backend/rebuild/llm/migrations.py`
- Create: `datara-backend/rebuild/llm/models.py`
- Create: `datara-backend/rebuild/llm/provider.py`
- Create: `datara-backend/rebuild/llm/repository.py`
- Create: `datara-backend/rebuild/llm/resolver.py`
- Create: `datara-backend/rebuild/llm/revisions/__init__.py`
- Create: `datara-backend/rebuild/llm/revisions/v0001_llm_model.py`
- Create: `datara-backend/tests/rebuild/test_llm_api_and_resolver.py`
- Create: `datara-backend/tests/rebuild/test_llm_model_and_crypto.py`
- Modify only if required: `datara-backend/rebuild/api/app.py`

- [ ] **Step 1: Port the two candidate LLM test modules and run them red**

Run: `python -m pytest datara-backend/tests/rebuild/test_llm_model_and_crypto.py datara-backend/tests/rebuild/test_llm_api_and_resolver.py -q`
Expected: collection/import FAIL until `rebuild.llm` exists.

- [ ] **Step 2: Port the LLM domain with its frozen six-endpoint contract**

The implementation must provide create/list/update/delete, connection test, and set-default behavior; AES-256-GCM encrypted credential storage; masked response values; one enabled default; default-delete protection; provider request isolation; and project/global permission checks defined by the candidate tests.

- [ ] **Step 3: Verify model, encryption, resolver, API, and app composition**

Run: `python -m pytest datara-backend/tests/rebuild/test_llm_model_and_crypto.py datara-backend/tests/rebuild/test_llm_api_and_resolver.py -q`
Expected: all tests PASS and `python -c "import sys; sys.path.insert(0, 'datara-backend'); import rebuild.api.app"` prints no error.

- [ ] **Step 4: Commit the atomic unit**

Run: `git add datara-backend/rebuild/llm datara-backend/tests/rebuild/test_llm_api_and_resolver.py datara-backend/tests/rebuild/test_llm_model_and_crypto.py datara-backend/rebuild/api/app.py && git commit -m "feat(llm): integrate encrypted model configuration"`
Expected: one LLM-domain commit.

### Task 4: Correct token-digest hardening migration

**Files:**
- Create or modify: `datara-backend/rebuild/governance/revisions/v0004_token_digest_hardening.py`
- Modify: `datara-backend/rebuild/governance/migrations.py`
- Modify: `datara-backend/rebuild/identity/models.py`
- Modify: `datara-backend/rebuild/identity/repository.py`
- Create: `datara-backend/tests/rebuild/test_identity_token_digest_migration.py`
- Modify: `datara-backend/tests/rebuild/test_identity_api.py`

- [ ] **Step 1: Port and run the migration tests**

Run: `python -m pytest datara-backend/tests/rebuild/test_identity_token_digest_migration.py -q`
Expected: two failures in the candidate baseline: strict SQLite boolean identity and missing digest backfill.

- [ ] **Step 2: Refresh schema inspection after ALTER and backfill all legacy tokens**

After adding `token_digest`, the migration must refresh inspection state before dependent work, hash every existing raw token with SHA-256, create the unique digest index, and report any remaining pending rows. The SQLite assertion must use truth-value semantics (`bool(index["unique"]) is True`) because SQLAlchemy reports `1` on SQLite.

- [ ] **Step 3: Verify legacy, fresh, idempotent, and repository paths**

Run: `python -m pytest datara-backend/tests/rebuild/test_identity_token_digest_migration.py datara-backend/tests/rebuild/test_identity_api.py -q`
Expected: all tests PASS; legacy rows have non-null correct SHA-256 digests.

- [ ] **Step 4: Commit the hardening fix**

Run: `git add datara-backend/rebuild/governance datara-backend/rebuild/identity datara-backend/tests/rebuild/test_identity_token_digest_migration.py datara-backend/tests/rebuild/test_identity_api.py && git commit -m "fix(identity): backfill token digests during migration"`
Expected: one focused security/migration commit.

### Task 5: Integrate workflow run statistics

**Files:**
- Modify: `datara-backend/rebuild/execution/models.py`
- Modify: `datara-backend/rebuild/execution/repository.py`
- Create: `datara-backend/rebuild/execution/run_stats.py`
- Modify: `datara-backend/rebuild/execution/api.py`
- Modify: `datara-backend/rebuild/execution/migrations.py`
- Create: `datara-backend/rebuild/execution/revisions/v0002_run_statistics.py`
- Create: `datara-backend/tests/rebuild/test_execution_run_statistics.py`
- Modify: `datara-backend/tests/rebuild/test_execution_models.py`
- Modify: `datara-backend/tests/rebuild/test_execution_api.py`
- Modify: `datara-backend/tests/rebuild/test_execution_migrations.py`

- [ ] **Step 1: Port run-statistics tests and confirm the model-contract failure**

Run: `python -m pytest datara-backend/tests/rebuild/test_execution_models.py datara-backend/tests/rebuild/test_execution_run_statistics.py -q`
Expected: old exact-six-table assertion FAILS after statistics tables are registered.

- [ ] **Step 2: Integrate two statistics tables and service**

`workflow_run_stat` stores project/workflow/version/instance/attempt identity with source, target, success, failure, skipped counts and timestamps. `workflow_run_reconcile_detail` stores optional object-level counts. Upserts are idempotent per final attempt; retry attempts remain distinguishable; stream checkpoint counters are monotonic; negative and boolean counts are rejected.

- [ ] **Step 3: Extend project-scoped list/detail APIs**

Expose authenticated project-scoped list and detail endpoints that return the stable envelope and deny cross-project access. Keep statistics independent from log records.

- [ ] **Step 4: Update the original execution-table assertion without weakening it**

Assert that the six original run tables are a required subset of `EXECUTION_TABLES` and separately assert the exact two statistics table names. Do not delete timestamp or constraint checks for the original models.

- [ ] **Step 5: Run the execution domain suite**

Run: `python -m pytest datara-backend/tests/rebuild/test_execution_models.py datara-backend/tests/rebuild/test_execution_run_statistics.py datara-backend/tests/rebuild/test_execution_api.py datara-backend/tests/rebuild/test_execution_migrations.py datara-backend/tests/rebuild/test_execution_sync_bridge.py -q`
Expected: all tests PASS.

- [ ] **Step 6: Commit the statistics unit**

Run: `git add datara-backend/rebuild/execution datara-backend/tests/rebuild/test_execution_models.py datara-backend/tests/rebuild/test_execution_run_statistics.py datara-backend/tests/rebuild/test_execution_api.py datara-backend/tests/rebuild/test_execution_migrations.py && git commit -m "feat(execution): persist workflow run statistics"`
Expected: one execution statistics commit.

### Task 6: Re-establish full local verification baseline

**Files:**
- Verify: `datara-backend/`
- Verify: `datara-newweb/`

- [ ] **Step 1: Provision frontend dependencies without changing declared versions**

Run: `npm ci`
Expected: dependencies match the existing lockfile; no source or manifest diff.

- [ ] **Step 2: Run full backend verification**

Run: `python -m pytest datara-backend/tests/rebuild -q`
Expected: zero failed and zero collection errors; the existing intentional skip is permitted only if its reason remains valid.

- [ ] **Step 3: Run full frontend verification**

Run: `npm test -- --run` and `npm run build` from `datara-newweb`.
Expected: all tests PASS; `vue-tsc -b` and Vite production build exit 0.

- [ ] **Step 4: Confirm repository hygiene**

Run: `git status --short` and `git diff --check`.
Expected: only deliberate plan/progress documentation changes remain; no generated `dist`, caches, credentials, or primary-checkout files are staged.

### Task 7: Produce the next implementation plan from the green baseline

**Files:**
- Create: `docs/superpowers/plans/2026-10-24-core-workflows-and-samples.md`

- [ ] **Step 1: Re-audit core workflow source after baseline integration**

Inspect the actual component spec, DAG workbench, variable, dependency, sync, stream, execution, and sample files now present. Map each user priority requirement to exact source and test paths.

- [ ] **Step 2: Write the core-workflows plan**

The next plan must cover Palette reduction, SQL/Python/Shell samples, dependency matrix samples, five synchronization samples, stream production/aggregation/fusion observation, variable UI, and run-statistics UI using exact file paths and commands.

- [ ] **Step 3: Begin that plan immediately**

Use `executing-plans`; do not wait for another execution-mode choice because the user explicitly requested continuous iteration.
