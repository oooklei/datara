"""Priority ordering and one-time legacy direction migration."""

from __future__ import annotations

from typing import Any, MutableSet, Sequence, TypeVar

from sqlalchemy import text
from sqlalchemy.engine import Engine

T = TypeVar("T")
MIGRATION_KEY = "workflow-task-priority-small-is-high-v1"


def sort_priority(items: Sequence[T]) -> list[T]:
    """Sort by workflow/task ascending, task-group descending, then FIFO."""
    return sorted(items, key=lambda item: (
        item.workflow_priority,
        item.task_priority,
        -item.task_group_priority,
        item.submitted_at,
        item.submission_order,
    ))


def migrate_priority_values(
    rows: Sequence[dict[str, Any]],
    applied_migrations: MutableSet[str],
) -> int:
    """Invert legacy 1..5 workflow/task priorities once; leave task groups intact."""
    if MIGRATION_KEY in applied_migrations:
        return 0
    changed = 0
    for row in rows:
        if row.get("kind") not in {"workflow", "task"}:
            continue
        value = row.get("priority")
        if isinstance(value, int) and 1 <= value <= 5:
            row["priority"] = 6 - value
            changed += 1
    applied_migrations.add(MIGRATION_KEY)
    return changed


def migrate_command_priority_direction(engine: Engine) -> int:
    """Ensure a durable marker column, then invert legacy command weights once.

    This follows the repository's additive ``_ensure_column`` migration pattern.
    The update and marker write share one transaction, making concurrent master
    startup safe and preventing a second inversion after restart.
    """
    from common.db import _ensure_column

    _ensure_column(engine, "t_command", "priority_small_high_v1", "TINYINT NOT NULL DEFAULT 0")
    with engine.begin() as connection:
        result = connection.execute(text(
            "UPDATE t_command SET priority = CASE priority "
            "WHEN 1 THEN 5 WHEN 2 THEN 4 WHEN 3 THEN 3 WHEN 4 THEN 2 WHEN 5 THEN 1 "
            "ELSE priority END, priority_small_high_v1 = 1 "
            "WHERE priority_small_high_v1 = 0"
        ))
        return int(result.rowcount or 0)
