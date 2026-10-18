"""R6 C6 priority contract tests (tests-only RED handoff).

The production priority module is a follow-up implementation task.  This file
pins the behavior expected at that seam: workflow/task numbers sort ascending,
ties retain submission order, and the legacy inversion is migrated once.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from master.priority import migrate_priority_values, sort_priority


@dataclass
class PriorityItem:
    workflow_priority: int
    task_priority: int
    task_group_priority: int
    submitted_at: datetime
    submission_order: int


def test_small_workflow_and_task_values_have_higher_priority():
    submitted = datetime(2026, 1, 1)
    items = [
        PriorityItem(3, 1, 2, submitted, 0),
        PriorityItem(1, 5, 2, submitted, 1),
        PriorityItem(2, 1, 2, submitted, 2),
    ]

    assert sort_priority(items) == [items[1], items[2], items[0]]


def test_equal_priority_is_fifo_by_submission_time_then_order():
    submitted = datetime(2026, 1, 1)
    items = [
        PriorityItem(2, 2, 3, submitted + timedelta(seconds=1), 1),
        PriorityItem(2, 2, 3, submitted, 0),
        PriorityItem(2, 2, 3, submitted + timedelta(seconds=1), 2),
    ]

    assert sort_priority(items) == [items[1], items[0], items[2]]


def test_legacy_priority_migration_is_applied_once_and_leaves_task_group_direction():
    rows = [
        {"kind": "workflow", "priority": 1},
        {"kind": "task", "priority": 5},
        {"kind": "task_group", "priority": 5},
    ]
    applied_migrations = set()

    assert migrate_priority_values(rows, applied_migrations) == 2
    assert [row["priority"] for row in rows] == [5, 1, 5]
    assert migrate_priority_values(rows, applied_migrations) == 0
    assert [row["priority"] for row in rows] == [5, 1, 5]
