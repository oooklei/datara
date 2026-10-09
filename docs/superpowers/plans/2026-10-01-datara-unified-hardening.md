# Datara Unified Hardening Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** Close the highest-risk gaps between Datara's verified features and its default deployable/runtime behavior without changing the completed IDE feature set.

**Architecture:** Preserve the five backend services and the unified DAG. Make Kafka a first-class deployment dependency, convert alert processing into explicit delivery adapters, expose persisted system alerts to the real frontend, and lock these contracts with automated tests and operator documentation.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic Settings, Vue 3/TypeScript, Docker Compose, MySQL, Redis, ZooKeeper, Kafka KRaft, pytest, Vitest.

**Environment Rule:** Edit and run static syntax/architecture checks locally. Sync the scoped change set to `/mnt/lei/datara` on `192.168.1.9` and run dependency installation, Docker Compose validation, integration tests, runtime verification, and UI/API joint testing there. Use the current user's SSH config; never print private-key contents.

---

### Task 1: Record the authoritative design and constraints

**Files:**
- Create: `docs/increments/I11-全盘统一优化设计.md`
- Modify: `docs/increments/决策记录.md`

1. Record the chronological requirement history and source precedence.
2. Mark V3.0 docx as historical reference only.
3. Record the IDE functional freeze.
4. Record the I11 staged scope and acceptance gates.

### Task 2: Make Kafka part of the default deployment

**Files:**
- Modify: `docker-compose.yml`
- Create: `datara-backend/tests/test_compose_contract.py`

1. Add a single-node KRaft Kafka service, persistent volume and health check.
2. Make worker startup wait for Kafka health without forcing unrelated services to depend on it.
3. Preserve the existing `datara-kafka:9092` address used by validated stream jobs.
4. Add a static compose contract test for service, volume, advertised listener and worker dependency.
5. Run `docker compose config` and backend tests.

### Task 3: Replace fake alert success with delivery adapters

**Files:**
- Modify: `datara-backend/common/config.py`
- Create: `datara-backend/alert/channels.py`
- Modify: `datara-backend/alert/main.py`
- Modify: `datara-backend/alert/__init__.py`
- Create: `datara-backend/tests/test_alert_channels.py`

1. Add explicit configuration for webhook and SMTP delivery with bounded timeout.
2. Implement `system`, `webhook`, and `email` adapters; reject unsupported/misconfigured channels.
3. Process records independently and set `sent` only after adapter success; set `fail` with an error log otherwise.
4. Cover success, missing configuration, HTTP failure, SMTP dispatch and unsupported channel with unit tests.

### Task 4: Connect real persisted alerts to the real UI

**Files:**
- Create: `datara-backend/api/alerts.py`
- Modify: `datara-backend/api/main.py`
- Create: `datara-web/src/services/alertApi.ts`
- Modify: `datara-web/src/services/index.ts`
- Modify: `datara-web/src/App.vue`
- Create: `datara-backend/tests/test_alert_api.py`

1. Add a permission-protected latest-alert endpoint with stable response fields.
2. Export a typed frontend alert client.
3. In mock mode keep mock notifications; in real mode load persisted alerts only.
4. Keep read-state local and map all real alerts to the relevant operations page.
5. Add API serialization/permission tests and frontend tests if existing harness supports the app shell.

### Task 5: Align stream UI wording with the implemented engine

**Files:**
- Modify: `datara-web/src/router/routes.ts`
- Modify: `datara-web/src/App.vue`
- Modify: `datara-web/src/views/stream/StreamListView.vue`
- Modify: `datara-web/src/views/stream/StreamDetailView.vue`

1. Treat the real list and control channel as real, not a blanket demo route.
2. Keep mock-only creation/reference cards hidden in real mode.
3. Replace unsupported Flink/Checkpoint/RocksDB/Doris claims with lightweight-engine facts or explicit unavailable states.
4. Do not touch IDE files or APIs.

### Task 6: Establish the component catalog and baseline-workbench contract

**Files:**
- Create: `datara-backend/common/component_catalog.py`
- Create: `datara-backend/api/components.py`
- Modify: `datara-backend/api/main.py`
- Modify: `datara-backend/master/engine.py`
- Modify: `datara-backend/master/dag.py`
- Modify: `datara-backend/master/failover.py`
- Modify: `datara-backend/master/scheduler.py`
- Create: `datara-backend/tests/test_component_catalog.py`
- Modify/Create: frontend DAG-profile contract tests

1. Define C1-C23 as one backend support matrix: logical, worker, stream, variable, or design-time template.
2. Reuse the same worker-type constant in master execution, failover, scheduling, and DAG helpers.
3. Expose a read-only catalog API for the workbench and operations diagnostics.
4. Assert that frontend component codes/types match the catalog and that runnable worker nodes have registered executors.
5. Keep the existing GraphWorkbench as the only baseline editor; do not create another canvas.

### Task 7: Harden the lineage increment

**Files:**
- Modify: `datara-backend/api/lineage.py`
- Modify: `datara-web/src/views/LineageView.vue`
- Create/Modify: lineage API and utility tests

1. Verify SQL and sync collection contracts, temporary-table mapping, idempotency and latest-edge selection.
2. Add bounded query limits and deterministic latest-edge ordering.
3. Ensure field detail uses the latest matching trace row and empty/cyclic graphs remain usable.
4. Keep all real-mode impact output derived from persisted edges; do not add mock indicators/reports.

### Task 8: Make runtime nodes and cluster monitoring a truthful infrastructure view

**Files:**
- Modify: `datara-backend/common/monitor.py`
- Modify: `datara-backend/api/monitor.py`
- Modify: `datara-web/src/views/deploy/DeployRuntimeView.vue`
- Modify: `datara-web/src/views/deploy/DeployMonitorView.vue`
- Create/Modify: monitor API and frontend tests

1. Define online/offline/unknown/stale states and expose metric timestamps.
2. Prevent overlapping polling timers and display degraded/stale states explicitly.
3. Replace the monitor page's static Prometheus/DolphinScheduler/Flink/Doris claims with real master/worker/SSH nodes and reported metrics.
4. Retain the shared topology workbench only when its nodes are built from the same real response.
5. Validate registration, heartbeat expiry, resource metrics, and failure visibility.

### Task 9: Restore delivery documentation and verification

**Files:**
- Create: `README.md`
- Replace: `datara-web/README.md`
- Create: `docs/increments/I11-验证单.md`

1. Document architecture, prerequisites, configuration, start/stop, tests, real/demo boundary and IDE freeze.
2. Record every executed command, result, deviation and remaining risk in the I11 verification sheet.
3. On 192.168.1.9, install frontend dependencies from the lockfile if needed and run tests/build.
4. On 192.168.1.9, run backend tests, lint, compose validation and runtime smoke tests.
5. Inspect `git diff --check` and final status.
