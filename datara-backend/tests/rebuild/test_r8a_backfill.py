"""R6-H03 backfill contract tests; GREEN is gated on the T19/T20 P0 closure.

The service boundary is intentionally small: ``BackfillBatchService`` owns the
durable ComplementBatch state and accepts a storage port. The fake below only
observes serialized records; it does not implement the scheduling semantics.
"""

from datetime import date

import pytest

from master.backfill import BackfillBatchService, BackfillValidationError
from tests.rebuild.r6_fakes import FakeComplementBatchStore


def test_leap_year_boundary_expands_each_inclusive_date():
    batch = BackfillBatchService(FakeComplementBatchStore()).create(
        workflow_code=90811,
        date_from=date(2024, 2, 28),
        date_to=date(2024, 3, 1),
        mode="serial",
    )

    assert batch.dates == [date(2024, 2, 28), date(2024, 2, 29), date(2024, 3, 1)]


def test_parallelism_three_partitions_ten_days_as_three_three_three_one():
    batch = BackfillBatchService(FakeComplementBatchStore()).create(
        workflow_code=90811,
        date_from=date(2026, 1, 1),
        date_to=date(2026, 1, 10),
        mode="parallel",
        parallelism=3,
    )

    assert [len(group) for group in batch.execution_groups] == [3, 3, 3, 1]
    assert batch.max_parallelism == 3


def test_serial_batch_advances_only_after_success():
    service = BackfillBatchService(FakeComplementBatchStore())
    batch = service.create(
        workflow_code=90811,
        date_from=date(2026, 1, 1),
        date_to=date(2026, 1, 3),
        mode="serial",
    )

    first_run = service.start_next(batch.batch_id)
    assert service.complete_run(first_run.run_id, outcome="failure") is None
    assert service.start_next(batch.batch_id) is None


def test_serial_batch_starts_next_date_after_success():
    service = BackfillBatchService(FakeComplementBatchStore())
    batch = service.create(
        workflow_code=90811,
        date_from=date(2026, 1, 1),
        date_to=date(2026, 1, 2),
        mode="serial",
    )

    first_run = service.start_next(batch.batch_id)
    second_run = service.complete_run(first_run.run_id, outcome="success")

    assert second_run.run_date == date(2026, 1, 2)


def test_parallelism_zero_is_rejected_without_partitioning():
    with pytest.raises(BackfillValidationError, match="parallelism must be at least 1"):
        BackfillBatchService(FakeComplementBatchStore()).create(
            workflow_code=90811,
            date_from=date(2026, 1, 1),
            date_to=date(2026, 1, 2),
            mode="parallel",
            parallelism=0,
        )


def test_batch_and_run_date_links_survive_service_restart():
    store = FakeComplementBatchStore()
    first_process = BackfillBatchService(store)
    batch = first_process.create(
        workflow_code=90811,
        date_from=date(2026, 1, 1),
        date_to=date(2026, 1, 3),
        mode="serial",
    )
    first_run = first_process.start_next(batch.batch_id)
    persisted = store.snapshot()

    restarted = BackfillBatchService(FakeComplementBatchStore(persisted))
    restored = restarted.get(batch.batch_id)
    assert restored.completed_dates == set()
    assert restored.pending_dates == [date(2026, 1, 2), date(2026, 1, 3)]
    assert restarted.run_batch(first_run.run_id) == (batch.batch_id, date(2026, 1, 1))

