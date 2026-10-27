# MON-STATS-03 evidence

- RED source: `../FE-NAV-E2E-02/report-project27-monitor-500.json` records HTTP 500 for project 27 `GET /api/v1/rebuild/metrics/workflow-result-stats`; `../MON-STATS-02/red-project27-window.xml` isolates ISO-Z strings reaching database datetime comparisons.
- GREEN targeted: `targeted-green-final.xml` — 10 passed for the metrics API and trial output contracts.
- GREEN regression: `backend-regression-final.xml` — 49 passed across metrics, structured run statistics, sync bridge, execution domain, and trial E2E.
- The metrics contract covers UTC normalization, canonical `workflow_run_stat` success/failure/skipped projection, legacy-day fallback, canonical same-day override, and stable date/workflow ordering.
- The trial contract covers authoritative workflow-level structured receipts without task-receipt double counting.
- Ruff (`F821,E999,F401,I001`) and scoped `git diff --check` passed.
- No deployment or remote runtime mutation was performed.
