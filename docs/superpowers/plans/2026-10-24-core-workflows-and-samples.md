# Core Workflows, Samples, and Frontend Integration Plan

> Execution rule: local workstation is limited to source audit, static/type/unit/component verification. Runtime deployment, middleware, browser E2E, and live stream observation use only `192.168.1.9`. Remote E2E is batched at highest-priority business closures and final unified integration, not repeated for each small change.

## Authoritative outcome

Implement the user priorities against the v3 frontend design, v4 acceptance standard, and WBS: a genuinely connected data-development IDE; variables; focused DAG palette; executable SQL/Python/Shell/dependency/sync/stream workflows and samples; run-statistics monitoring; and every retained navigation page/control wired to the rebuilt backend. Old frontend appearance and layout are the visual baseline, while all data and actions use the rebuilt backend.

## Current green foundation

- Component-spec migrations, immutable versioning, runtime-only exclusions, and publish gates are present under `datara-backend/rebuild/component_spec/**`.
- LLM configuration, token-digest hardening, and execution-owned run statistics are integrated.
- Execution statistics now use one authoritative row per workflow instance, final-attempt selection, monotonic stream checkpoints, repairable finalization, and project-scoped list/detail APIs.
- Existing domain surfaces are present for SQL IDE, variables, dependency, sync, stream, workflow, execution, and monitoring; the remaining work is audited behavior closure, samples, frontend wiring, and runtime proof.

## Task 1 — Freeze the reduced executable component catalogue

**Backend:** `datara-backend/rebuild/component_spec/**`, `datara-backend/rebuild/workflow/**`, `datara-backend/rebuild/execution/**`

**Frontend:** `datara-newweb/src/components/Palette.vue`, `WorkflowGraphWorkbench.vue`, `stores/workflowGraph.ts`, component tests.

1. Add failing catalogue tests for the exact visible groups: focused SQL, Python, Shell, dependency; seven synchronization design components (`src_base_orch`, `tgt_base_orch`, `file_sync_orch`, `endpoint_select`, `field_map`, `field_map_union`, `condition_set`); and the approved stream design components.
2. Enforce `sync`/`file_sync` runtime-only exclusion in palette, canvas, W1 validation, save, and publish gates.
3. Enforce immutable `{type,version}` component references, JSON-only eight-section form DSL, pick/behavior/hidden-input/refresh endpoint allowlists, and zero function-valued `showIf/onChange/text` fields.
4. Make palette filtering depend on workflow type (`NORMAL`, `SYNC`, `STREAM`) and remove unsupported/no-source components.
5. Verify component schema, palette, graph-store, save, and publish tests locally.

## Task 2 — Complete variables across management, canvas, and runtime

**Backend:** `datara-backend/rebuild/variables/**`, execution parameter resolution, variable migrations/tests.

**Frontend:** create/complete `datara-newweb/src/views/variables/**`; wire the task-centre “变量管理” button, canvas variable panel, `services/rebuild/variableApi.ts`, and `variableReferenceField.ts`.

1. Cover global/project/environment/workflow/node namespaces and the fixed resolution order: node parameters > workflow variables > environment group > global.
2. Implement CRUD, secret masking, typed values, current-value preview, autocomplete, and the five reference diagnostics.
3. Ensure the canvas saves references rather than resolved secrets and executors cannot write hidden inputs.
4. Add backend service/API tests plus Vue service/view/component tests; no browser E2E yet.

## Task 3 — Complete dependency component nine-capability chain

**Backend:** `datara-backend/rebuild/dependency/**`, workflow/execution adapters and tests.

**Frontend:** dependency form inside the DAG property panel using `dependencyApi.ts`.

1. Implement DS-compatible dependency parameters, two-level AND/OR groups, condition items, task/cycle/date selectors, time windows, evaluation, polling, timeout, and result detail.
2. Bind the form to the eight-section component DSL and persist through workflow save/version/publish.
3. Add executable samples covering success, waiting, timeout, mixed AND/OR, upstream failure, and date/cycle windows.
4. Prove results flow into execution events and run-statistics without deriving counts from logs.

## Task 4 — Execute SQL, Python, and Shell nodes end to end

**Backend:** execution engine/adapters under `datara-backend/rebuild/execution/**`; component specs and runtime-node/SSH integrations.

**Frontend:** DAG node forms/property panels and trial-run/results presentation.

1. SQL: datasource/database/script/variables, statement result/error mapping, cancellation, and row counts.
2. Python: runtime node, interpreter/environment, script/arguments, stdout/stderr, timeout/cancellation, hidden context.
3. Shell: SSH/runtime node, working directory/environment/script, exit code, timeout/cancellation, hidden context.
4. Add one single-node and one mixed DAG sample for each component, plus a chained SQL→Python→Shell sample.
5. Verify executor contracts locally; reserve real interpreter/SSH/database execution for the first high-priority 1.9 workflow closure.

## Task 5 — Complete synchronization design, forms, materialization, and five samples

**Backend:** `datara-backend/rebuild/sync/**`, `execution/sync_executor.py`, engine materialization, workflow validation.

**Frontend:** `syncComponentApi.ts`, endpoint selector, field mapping, condition forms, graph-edge-derived references.

1. Implement `endpoint_select` modes `src_base`, `tgt_base`, `file_sync`; eliminate legacy source/target selectors.
2. Derive named input references from edges as `nodeId:port`; make `field_map_union` resolve `:sourceRef/:targetRef` semantics instead of positional indexes.
3. Materialize `sys_exec_*` runtime nodes by base mode; keep runtime nodes absent from design JSON.
4. Ship five publishable workflow samples: DB→DB full, DB→DB incremental, file→DB, DB→file, and multi-source union/mapping with success/failure statistics.
5. Run local contract/executor suites, then one consolidated real 1.9 sync closure covering forms, publish, execution, and monitoring.

## Task 6 — Complete stream production, aggregation/fusion, and live observation

**Backend:** `datara-backend/rebuild/stream/**`, execution stream adapter, checkpoint/statistics integration.

**Frontend:** stream workflow category, stream forms, and `/rebuild/validation/stream` observation view.

1. Provide real-time producers for ecommerce, IoT, and visit data with controllable EPS and schema validation.
2. Implement source→transform/filter→window aggregation→multi-stream fusion→sink workflows, checkpoint recovery, stop/restart, alerting, and monotonic statistics.
3. Add deterministic local producer/schema/domain tests and saved sample definitions.
4. On 1.9, run a sustained live producer and display input/output rate, watermark/checkpoint, aggregate/fusion results, success/failure counts, and stop/recovery evidence. This is a mandatory high-priority remote E2E.

## Task 7 — Finish SQL IDE and bind every control to the rebuilt backend

**Backend:** `datara-backend/rebuild/sql_ide/**`, `run_sql.py`, `generate_sql.py`, LLM integration.

**Frontend:** `datara-newweb/src/views/ide/**`, `services/rebuild/sqlIdeApi.ts`, `sqlIdeDdlApi.ts`.

1. Audit every editor/tree/tab/toolbar/menu/dialog/shortcut against old frontend behavior and the DBX capability matrix.
2. Complete datasource metadata browsing, SQL completion/lint/format, variables, multi-statement execution, cancel, paging, export, history, session recovery, and structured/source DDL flows.
3. Preserve backend error codes and capability fail-closed behavior; eliminate mock/static success paths.
4. Run all local IDE contract/view tests and production build, then perform one consolidated 1.9 IDE E2E with real datasource and rebuilt APIs.

## Task 8 — Connect task-centre monitoring to execution-owned statistics

**Backend:** `datara-backend/rebuild/execution/run_stats.py`, execution API, `rebuild/monitor/**`.

**Frontend:** monitor view/tab and `services/rebuild/monitorApi.ts`.

1. Present project/workflow/type/status/time filters, pagination, success/failure/skipped/total/source/target values, start/end/generated timestamps, and paged reconciliation details.
2. Surface statistics-finalization failure and the permission-protected repair action.
3. Link workflow instance/task/log/detail views without deriving result counts from logs.
4. Add local API/service/view tests; validate visually and functionally during the consolidated workflow E2E on 1.9.

## Task 9 — Complete retained navigation surfaces and old-frontend visual parity

**Frontend:** router/navigation definitions, all retained `datara-newweb/src/views/**`, shared layouts/components/styles.

1. Generate a route/control inventory from the v3 retained navigation matrix.
2. For every retained page, verify route load, real API data, empty/loading/error/permission states, and every button/menu/link/dialog field/action.
3. Reproduce old frontend hierarchy, spacing, density, colors, table/detail drawer, DAG workspace, tabs, and dialog interaction while retaining accessible keyboard/focus behavior.
4. Add contract/component tests per surface. Use 1.9 browser E2E only for the highest-priority IDE/task-centre/sync/stream/variables/monitor closures and the final full-navigation sweep.

## Task 10 — Unified verification and release evidence

1. Local gates: full backend `tests/rebuild`, frontend Vitest, `vue-tsc -b`, Vite build, Ruff, migration/checksum/postflight tests, and repository hygiene.
2. Deploy a frozen candidate to an isolated directory on `192.168.1.9`, expose only `http://192.168.1.9:18091/`, inject a short-lived token without storing the verification key in URL/static assets/browser persistence.
3. Run consolidated E2E matrices for IDE; variables; SQL/Python/Shell/dependency; five sync samples; live stream production/aggregation/fusion; workflow monitor/repair; retained navigation and controls.
4. Capture database rows, API envelopes, screenshots/traces, workflow outputs, success/failure counts, stream observation intervals, and migration postflight evidence.
5. Fix all failures, rerun affected local gates, then rerun one final unified 1.9 regression. Only that green evidence can support completion.
