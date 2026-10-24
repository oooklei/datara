"""Frozen revision and legacy-to-snapshot migration regression coverage."""

from sqlalchemy import create_engine, inspect, text

from rebuild.execution.revisions import (
    v0001_execution_tables,
    v0002_run_statistics,
    v0003_run_snapshot_contract,
)
from rebuild.metrics.revisions import v0002_workflow_result_unique


def test_run_statistics_revision_checksums_are_frozen_literals():
    assert v0002_run_statistics.checksum == "518b0b484dc74e9fe190d8c4c0e7549670a17f7827d493e01c6afb8d1a403145"
    assert v0003_run_snapshot_contract.checksum == "3580390bd7616a3f064e61e7b88a5ebb51df377f5d38f2e9581986bf73b98f39"
    assert v0002_workflow_result_unique.checksum == "869dbe139fb56572abd9d9050a53acb7588b5d414eb4cffcd89b01bc70b83818"


def test_v0002_rows_upgrade_to_one_fk_backed_instance_snapshot_without_data_loss():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    v0001_execution_tables.upgrade(engine)
    v0002_run_statistics.upgrade(engine)
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO workflow_instance "
            "(id,workflow_id,workflow_version_id,instance_type,status,started_at) "
            "VALUES (7,11,3,'FORMAL','SUCCEEDED','2026-10-24 10:00:00')"
        ))
        for values in ((1, "task:a", 4, 1, 1), (2, "task:b", 5, 2, 0)):
            connection.execute(text(
                "INSERT INTO workflow_run_stat "
                "(id,project_id,workflow_id,workflow_version_id,workflow_instance_id,task_identity,"
                "attempt_no,instance_type,status,success_count,failure_count,skipped_count) "
                "VALUES (:id,9,11,3,7,:task,1,'FORMAL','SUCCEEDED',:ok,:failed,:skipped)"
            ), {"id": values[0], "task": values[1], "ok": values[2], "failed": values[3], "skipped": values[4]})
            connection.execute(text(
                "INSERT INTO workflow_run_reconcile_detail "
                "(id,run_stat_id,source_object,target_object,success_count,failure_count,skipped_count) "
                "VALUES (:id,:id,'src','dst',:ok,:failed,:skipped)"
            ), {"id": values[0], "ok": values[2], "failed": values[3], "skipped": values[4]})

    v0003_run_snapshot_contract.upgrade(engine)

    with engine.connect() as connection:
        stat = connection.execute(text(
            "SELECT success_count,failure_count,skipped_count,total_count FROM workflow_run_stat"
        )).mappings().one()
        detail = connection.execute(text(
            "SELECT success_count,failure_count,skipped_count FROM workflow_run_reconcile_detail"
        )).mappings().one()
        assert dict(stat) == {"success_count": 9, "failure_count": 3, "skipped_count": 1, "total_count": 12}
        assert dict(detail) == {"success_count": 9, "failure_count": 3, "skipped_count": 1}
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    assert v0003_run_snapshot_contract.postflight(engine)["verdict"] == "READY"


def test_snapshot_postflight_rejects_wrong_type_nullable_and_missing_constraints():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    v0001_execution_tables.upgrade(engine)
    v0002_run_statistics.upgrade(engine)
    v0003_run_snapshot_contract.upgrade(engine)
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE workflow_run_stat RENAME TO workflow_run_stat_valid"))
        connection.execute(text(
            "CREATE TABLE workflow_run_stat AS SELECT * FROM workflow_run_stat_valid WHERE 0"
        ))
    # CREATE TABLE AS strips types/nullability/PK/FK/unique/check/defaults.
    assert v0003_run_snapshot_contract.postflight(engine)["verdict"] == "BLOCKED"


def test_workflow_level_receipt_identity_is_database_unique():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    v0001_execution_tables.upgrade(engine)
    v0002_run_statistics.upgrade(engine)
    v0003_run_snapshot_contract.upgrade(engine)
    uniques = {tuple(item["column_names"]) for item in inspect(engine).get_unique_constraints("execution_event")}
    assert ("workflow_instance_id", "receipt_identity", "attempt_no", "event_kind") in uniques


def test_metrics_upgrade_merges_duplicates_and_enforces_workflow_day_identity():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE workflow_result_stat (id INTEGER PRIMARY KEY, workflow_id INTEGER NOT NULL, "
            "run_date DATE NOT NULL, success_count INTEGER NOT NULL, failure_count INTEGER NOT NULL, "
            "skipped_count INTEGER NOT NULL, retry_count INTEGER NOT NULL)"
        ))
        connection.execute(text(
            "INSERT INTO workflow_result_stat VALUES "
            "(1,5,'2026-10-24',2,1,0,0),(2,5,'2026-10-24',3,0,1,1)"
        ))
    v0002_workflow_result_unique.upgrade(engine)
    with engine.connect() as connection:
        row = connection.execute(text(
            "SELECT success_count,failure_count,skipped_count,retry_count FROM workflow_result_stat"
        )).one()
        assert row == (5, 1, 1, 1)
    assert v0002_workflow_result_unique.postflight(engine)["verdict"] == "READY"
