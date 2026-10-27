# MON-STATS-02 evidence

- RED: `red.xml` — 2 regressions failed as intended: mixed legacy/canonical monitor rows and trial receipt double-counting.
- GREEN targeted: `green-targeted.xml` — 2 passed.
- Backend regression: `backend-regression.xml` — 21 passed across metrics API, trial output, run statistics, and sync bridge.
- Adjacent regression: `adjacent-regression.xml` — 27 passed across execution domain and trial E2E.
- Final combined backend regression: `final-backend-regression.xml` — 49 passed.
- Frontend contract: `frontend-vitest.xml` — metrics API Vitest contract passed.
- Project 27 HTTP-500 regression: `red-project27-window.xml` shows ISO-Z strings reaching DB boundaries; `project27-api-regression.xml` has all 6 metrics API tests passing after UTC datetime normalization.
- Static checks: `git diff --check` passed; Ruff fatal checks (`F821,E999`) passed.
- No deployment or runtime environment mutation was performed.
