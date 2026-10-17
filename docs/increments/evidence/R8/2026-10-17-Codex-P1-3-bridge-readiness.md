# Codex P1-3 R8-A bridge readiness review

Date: 2026-10-17 (Asia/Shanghai)  
Scope: reconcile supervisor decision #147 and Trae handoff #148 with the current Datara Backend before wiring the P1-3 runtime bridge.

## Completed in this increment

- Commit `ab10b2d` corrected the two R8-A §2.1 paths to `/api/v1/rebuild/ai/tools` and `/api/v1/rebuild/ai/tool-calls`, following #147. No alias path or payload/tool-set change was introduced.
- #147 confirms `generate_sql` is an adapter-layer mock/generation capability, not a ninth R8-A registry tool.
- #148 assigns the BE bridge implementation to the Codex `ai_copilot/` domain and says Trae must not cross into it. The older §7 owner snapshot still says P1-3 (Trae); #148 is the newer status, but does not enumerate a Codex start sequence or changed pathspec boundary.

## Source inspection

- `datara-backend/rebuild/api/app.py:create_app` constructs a Rebuild `session_factory`, `DatasourceEngineRegistry`, `current_user`, and `project_permission_error`; existing routers are assembled near the end of the factory. This is the correct hosting boundary.
- `datara-backend/ai_copilot/` currently contains the Vanna adapter/config only; there is no R8-A router, registry, dispatcher, or bridge test.
- No existing Rebuild SQL query-execution service/port was found. `DatasourceEngineRegistry.connect(...)` is a datasource connection facility, not the R5-A governed SQL execution service; calling it directly from the AI bridge would create a second execution path.
- The R8-A audit schema/model is in governance, but its availability is migration-controlled. There is no injected Copilot audit writer in `create_app`.

## Readiness conclusion

The route prefix and `generate_sql` boundary are now unambiguous. Production bridge wiring is not yet ready to claim GREEN: it needs (1) the R8-A tool registry/dispatcher and envelope/audit implementation, (2) an injected project-scoped R5-A SQL execution port for `run_sql`, and (3) a metadata service binding for `search_schema`. Until those are composed, do not mount a route that reports success, do not add `generate_sql` to `GET /tools`, and do not call `DatasourceEngineRegistry` or Vanna's SQL runner to execute SQL.

## Safe next implementation slice

1. Add contract tests for the frozen eight-tool registry, exact endpoint paths, auth-before-handler order, and fail-closed behavior when the dispatcher or audit writer is absent.
2. Add an injected router builder under `datara-backend/ai_copilot/`; keep `generate_sql` internal to the adapter/orchestrator and let `run_sql` accept only the R5-A execution port.
3. Wire the builder through `rebuild/api/app.py:create_app` only when all required ports are supplied; default application construction must not expose an unaudited or ungoverned execution path.
4. Complete `search_schema` and `run_sql` against the existing metadata and SQL IDE services, then run the P1-3 contract tests and record the exact audit/project/run trace evidence.

This document records an implementation boundary review, not P1-3 completion or GREEN evidence.