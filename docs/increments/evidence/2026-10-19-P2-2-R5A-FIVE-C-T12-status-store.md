# P2-2 R5A FIVE-C T12 status store evidence

## Scope and contract

- A5 §4.8–4.9: minimal execution status is retained for 365 days; event sequence remains available while running and expires seven days after terminal time. The status row does not contain SQL, resolved variable values, or result rows.
- The shared worktree already contained the initial `status_store.py`, `test_status_store.py`, and `sql_ide_0004_status_events` migration before this task resumed. This change owns only those two T12 files, the existing T12 `0004` migration block, and this evidence file. Revisions `0001`–`0003` were not edited.

## TDD evidence

- RED command: `rtk pytest tests/sql_ide/test_status_store.py::test_events_expire_seven_days_after_terminal_status_not_event_creation -q --tb=short` (working directory `datara-backend`). Output: `0 passed, 1 failed`; it demonstrated `EXECUTION_EVENT_TTL` was 365 days instead of seven. Raw output: `%LOCALAPPDATA%\rtk\tee\1792361196_pytest.log`.
- GREEN command: `rtk pytest tests/sql_ide/test_status_store.py -q --tb=short` (working directory `datara-backend`). Output: `5 passed`.
- Test also verifies pre-terminal events remain queryable while running, terminal transition stamps the terminal time, terminal state cannot be changed, event history expires at terminal + 7 days, and status remains available independently.

## Adjacent verification

- `rtk pytest tests/sql_ide/test_status_store.py tests/sql_ide/test_history_store.py tests/sql_ide/test_snapshots.py tests/sql_ide/test_snapshots_migration.py tests/sql_ide/test_snapshots_migrations.py -q --tb=short`: `18 passed, 1 failed`. The existing history migration test expects the final `SQL_IDE_ALL_MIGRATIONS` revision to be `0003`; adding this task's `0004` makes that expectation stale. That test is outside T12's allowed file scope and was not changed. Raw output: `%LOCALAPPDATA%\rtk\tee\1792361238_pytest.log`.
- `rtk ruff check rebuild/sql_ide/status_store.py tests/sql_ide/test_status_store.py`: passed.
- `rtk git diff --check -- datara-backend/rebuild/sql_ide/status_store.py datara-backend/tests/sql_ide/test_status_store.py datara-backend/rebuild/sql_ide/migrations.py`: passed.
- Running Ruff over `migrations.py` also reports a pre-existing E501 at line 78, outside the T12 migration block; no unrelated formatting change was made.
