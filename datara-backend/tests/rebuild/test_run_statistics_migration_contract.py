"""Frozen revision and legacy-to-snapshot migration regression coverage."""

from inspect import getsource

from sqlalchemy import create_engine, inspect, text

from rebuild.execution.revisions import (
    v0001_execution_tables,
    v0002_run_statistics,
    v0003_run_snapshot_contract,
)
from rebuild.metrics.revisions import v0002_workflow_result_unique


def test_run_statistics_revision_checksums_are_frozen_literals():
    assert v0001_execution_tables.checksum == "033390ccac1d2f062448e1d0ca861946662620d95dc05c2db6a3568be0371106"
    assert v0002_run_statistics.checksum == "518b0b484dc74e9fe190d8c4c0e7549670a17f7827d493e01c6afb8d1a403145"
    assert v0003_run_snapshot_contract.checksum == "e0971065bfe2808d68eada6909a091d45901326e9c2f269d49ef3638e6febf3b"
    assert v0002_workflow_result_unique.checksum == "869dbe139fb56572abd9d9050a53acb7588b5d414eb4cffcd89b01bc70b83818"


def test_v0001_is_frozen_without_later_receipt_identity_schema():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    v0001_execution_tables.upgrade(engine)
    event_columns = {item["name"] for item in inspect(engine).get_columns("execution_event")}
    assert "receipt_identity" not in event_columns
    assert not inspect(engine).get_unique_constraints("execution_event")


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


def test_v0003_selects_latest_retry_and_prefers_workflow_rollup_with_authoritative_status():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    v0001_execution_tables.upgrade(engine)
    v0002_run_statistics.upgrade(engine)
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO workflow_instance "
            "(id,workflow_id,workflow_version_id,instance_type,status,started_at) VALUES "
            "(7,11,3,'FORMAL','SUCCEEDED','2026-10-24 10:00:00'),"
            "(8,12,4,'FORMAL','FAILED','2026-10-24 11:00:00')"
        ))
        rows = (
            (1, 7, "task-a", 1, "FAILED", 0, 9),
            (2, 7, "task-a", 2, "SUCCEEDED", 5, 0),
            (3, 7, "task-b", 1, "SUCCEEDED", 4, 0),
            (4, 8, "task-a", 1, "SUCCEEDED", 100, 0),
            (5, 8, "workflow", 1, "SUCCEEDED", 3, 1),
            (6, 8, "workflow", 2, "SUCCEEDED", 7, 2),
        )
        for row_id, instance_id, identity, attempt, status, success, failure in rows:
            connection.execute(text(
                "INSERT INTO workflow_run_stat "
                "(id,project_id,workflow_id,workflow_version_id,workflow_instance_id,task_identity,"
                "attempt_no,instance_type,status,success_count,failure_count,skipped_count) "
                "VALUES (:id,9,:workflow_id,:version,:instance,:identity,:attempt,'FORMAL',:status,:success,:failure,0)"
            ), {
                "id": row_id, "workflow_id": 11 if instance_id == 7 else 12,
                "version": 3 if instance_id == 7 else 4, "instance": instance_id,
                "identity": identity, "attempt": attempt, "status": status,
                "success": success, "failure": failure,
            })
            connection.execute(text(
                "INSERT INTO workflow_run_reconcile_detail "
                "(id,run_stat_id,source_object,target_object,success_count,failure_count,skipped_count) "
                "VALUES (:id,:id,'src','dst',:success,:failure,0)"
            ), {"id": row_id, "success": success, "failure": failure})

    v0003_run_snapshot_contract.upgrade(engine)

    with engine.connect() as connection:
        stats = connection.execute(text(
            "SELECT workflow_instance_id,status,success_count,failure_count,total_count "
            "FROM workflow_run_stat ORDER BY workflow_instance_id"
        )).all()
        details = connection.execute(text(
            "SELECT s.workflow_instance_id,d.success_count,d.failure_count "
            "FROM workflow_run_reconcile_detail d JOIN workflow_run_stat s ON s.id=d.run_stat_id "
            "ORDER BY s.workflow_instance_id"
        )).all()
    assert stats == [(7, "SUCCEEDED", 9, 0, 9), (8, "FAILED", 7, 2, 9)]
    assert details == [(7, 9, 0), (8, 7, 2)]


def test_sqlite_and_mysql_upgrade_plans_share_the_same_latest_v2_selector():
    source = getsource(v0003_run_snapshot_contract)
    assert source.count("_latest_v2_predicate(") >= 5
    predicate = v0003_run_snapshot_contract._latest_v2_predicate("row", "legacy_stats")
    assert "row.task_identity='workflow'" in predicate
    assert "MAX(wf.attempt_no)" in predicate
    assert "MAX(latest.attempt_no)" in predicate
    assert "NOT EXISTS" in predicate


def test_workflow_level_receipt_identity_is_database_unique():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    v0001_execution_tables.upgrade(engine)
    v0002_run_statistics.upgrade(engine)
    v0003_run_snapshot_contract.upgrade(engine)
    uniques = {tuple(item["column_names"]) for item in inspect(engine).get_unique_constraints("execution_event")}
    assert ("workflow_instance_id", "receipt_identity", "attempt_no", "event_kind") in uniques


def test_receipt_upgrade_deduplicates_legacy_null_identity_and_keeps_newest_payload():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    v0001_execution_tables.upgrade(engine)
    v0002_run_statistics.upgrade(engine)
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO execution_event "
            "(id,workflow_instance_id,task_instance_id,attempt_no,event_kind,payload_json) VALUES "
            "(1,7,NULL,1,'RESULT_STAT','old'),(2,7,NULL,1,'RESULT_STAT','new')"
        ))
    v0003_run_snapshot_contract.upgrade(engine)
    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT id,receipt_identity,payload_json FROM execution_event"
        )).one() == (2, "__workflow__", "new")


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


def test_mysql_plans_deduplicate_receipts_and_avoid_target_table_1093():
    execution_source = getsource(v0003_run_snapshot_contract)
    metrics_source = getsource(v0002_workflow_result_unique)
    assert "DELETE older FROM {_EVENT} older JOIN {_EVENT} newer" in execution_source
    assert "newer.id>older.id" in execution_source
    assert "CREATE TEMPORARY TABLE r7_0002_workflow_result_rollup" in metrics_source
    assert "JOIN r7_0002_workflow_result_rollup rollup" in metrics_source
    assert "SELECT SUM(source.success_count) FROM {_TABLE}" not in metrics_source


def test_mysql_partial_legacy_column_cleanup_resumes_after_task_identity_was_dropped():
    # Represents an auto-committed partial migration: task_identity is already
    # gone, while the first and third legacy columns still remain.
    partial_columns = {
        "id", "workflow_instance_id", "task_instance_id", "attempt_no",
        "success_count", "failure_count", "skipped_count",
    }
    plan = v0003_run_snapshot_contract._legacy_stat_drop_plan(partial_columns)
    assert plan == (
        "ALTER TABLE workflow_run_stat DROP COLUMN task_instance_id",
        "ALTER TABLE workflow_run_stat DROP COLUMN attempt_no",
    )
    for statement in plan:
        partial_columns.remove(statement.rsplit(" ", 1)[-1])
    assert not {"task_instance_id", "task_identity", "attempt_no"} & partial_columns
    assert v0003_run_snapshot_contract._legacy_stat_drop_plan(partial_columns) == ()


def test_mysql_upgrade_completes_the_pre_r9_aggregate_shape_before_type_normalisation():
    source = getsource(v0003_run_snapshot_contract._upgrade_mysql)
    for missing_target_column in (
        '"workflow_version_id": "BIGINT NULL"',
        '"source_count": "BIGINT NULL"',
        '"target_count": "BIGINT NULL"',
        '"skipped_count": "BIGINT NOT NULL DEFAULT 0"',
    ):
        assert missing_target_column in source
    assert "s.workflow_version_id=COALESCE(s.workflow_version_id,w.workflow_version_id)" in source
    assert "MODIFY workflow_version_id BIGINT NOT NULL" in source
