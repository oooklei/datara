from datetime import datetime
from types import SimpleNamespace

from rebuild.governance.legacy_mapping import LegacyMappingContext, TargetIdentityReference
from rebuild.governance.legacy_i21_mapping import map_i21_snapshot
from rebuild.governance.legacy_source_reader import I21_SOURCE_COLUMNS


def _row(table, **values):
    columns = I21_SOURCE_COLUMNS[table][1]
    row = {column: None for column in columns}
    row.update(values)
    return row


def _snapshot(**table_rows):
    return SimpleNamespace(
        schema="datara_meta", rows={table: tuple(table_rows.get(table, ())) for table in I21_SOURCE_COLUMNS}
    )


def _context(**kwargs):
    values = {
        "target_project_id": 7,
        "pending_identities": frozenset({("t_qc_rule", "1"), ("t_qc_task", "7"), ("t_qc_run", "9")}),
    }
    values.update(kwargs)
    return LegacyMappingContext(**values)


def _rule(**overrides):
    values = {
        "id": 1,
        "name": "订单非空",
        "dim": "完整性",
        "rule_type": "not_null",
        "ds_id": 10,
        "db_name": "ods",
        "table_name": "orders",
        "column_name": "order_id",
        "params_json": {"minimum": 1, "columns": ["order_id"]},
        "threshold": 0.0,
        "level": "强规则",
        "status": "enabled",
        "owner": "quality",
        "remark": "keep",
        "create_time": "2026-01-01T00:00:00",
        "update_time": "2026-02-01T00:00:00",
    }
    values.update(overrides)
    return _row("t_qc_rule", **values)


def _task(**overrides):
    values = {
        "id": 7,
        "name": "每日质量检查",
        "crontab": "0 0 * * * *",
        "enabled": True,
        "rule_ids": [1],
        "status": "idle",
        "last_run_at": "2026-01-02T00:00:00",
        "last_result": "success",
        "owner": "quality",
        "remark": "keep",
        "create_time": "2026-01-01T00:00:00",
    }
    values.update(overrides)
    return _row("t_qc_task", **values)


def _run(**overrides):
    values = {
        "id": 9,
        "task_id": 7,
        "trigger": "manual",
        "started_at": "2026-01-02T00:00:00",
        "finished_at": "2026-01-02T00:01:00",
        "result": "success",
        "score": 98.5,
        "stats_json": {"checked_rows": 20, "success_rows": 20},
    }
    values.update(overrides)
    return _row("t_qc_run", **values)


def _exception(**overrides):
    values = {
        "id": 11,
        "run_id": 9,
        "rule_id": 1,
        "task_id": 7,
        "target": "ods.orders.order_id",
        "sample_sql": "DELETE FROM ods.orders",
        "hit_count": 3,
        "status": "open",
        "fix_note": "review",
        "handled_by": "operator",
        "handled_at": "2026-01-02T01:00:00",
    }
    values.update(overrides)
    return _row("t_qc_exception", **values)


def _report(**overrides):
    values = {
        "id": 13,
        "title": "日报",
        "scope": "交易",
        "period": "2026-01-02",
        "content_json": {"count": 1, "items": ["orders"]},
        "created_by": "quality",
        "create_time": "2026-01-02T01:00:00",
    }
    values.update(overrides)
    return _row("t_qc_report", **values)


def _alarm(**overrides):
    values = {
        "id": 15,
        "name": "质量分告警",
        "scope": "交易",
        "metric": "score",
        "op": "<",
        "threshold": 90.0,
        "enabled": True,
        "last_fired_at": "2026-01-02T02:00:00",
    }
    values.update(overrides)
    return _row("t_qc_alarm_policy", **values)


def test_i21_mapper_preserves_all_six_table_semantics_and_task_rule_order():
    mapped = map_i21_snapshot(
        _snapshot(
            t_qc_rule=[_rule()],
            t_qc_task=[_task()],
            t_qc_run=[_run()],
            t_qc_exception=[_exception()],
            t_qc_report=[_report()],
            t_qc_alarm_policy=[_alarm()],
        ),
        _context(),
    )

    assert mapped.mapping_issues == ()
    assert mapped.ready_to_import
    assert mapped.rules[0].target_table == "rebuild_governance_quality_rule_definition"
    assert mapped.rules[0].values["project_id"] == 7
    assert mapped.rules[0].values["severity"] == "强规则"
    assert mapped.rules[0].values["target_table"] == "orders"
    assert mapped.rules[0].values["params_json"] == '{"columns":["order_id"],"minimum":1}'
    task = mapped.tasks[0]
    assert task.task.values["cron_expression"] == "0 0 * * * *"
    assert task.task.values["status"] == "idle"
    assert task.rule_links[0].ordinal_position == 1
    assert task.rule_links[0].rule_definition_id == TargetIdentityReference("t_qc_rule", "1")
    assert mapped.runs[0].values["legacy_task_id"] == 7
    assert mapped.runs[0].values["stats_json"] == '{"checked_rows":20,"success_rows":20}'
    assert mapped.exceptions[0].values["run_details_id"] == TargetIdentityReference("t_qc_run", "9")
    assert mapped.exceptions[0].values["rule_definition_id"] == TargetIdentityReference("t_qc_rule", "1")
    assert mapped.exceptions[0].values["sample_sql"] == "DELETE FROM ods.orders"
    assert mapped.reports[0].values["content_json"] == '{"count":1,"items":["orders"]}'
    assert mapped.alarm_policies[0].values["operator"] == "<"


def test_i21_mapper_empty_snapshot_is_valid_and_project_scoped():
    mapped = map_i21_snapshot(_snapshot(), _context())

    assert mapped.ready_to_import
    assert mapped.mapping_issues == ()
    assert mapped.rules == mapped.tasks == mapped.runs == mapped.exceptions == ()
    assert mapped.reports == mapped.alarm_policies == ()


def test_i21_mapper_resolves_all_references_from_existing_explicit_target_ids():
    context = _context(
        target_ids={
            ("t_qc_rule", "1"): 101,
            ("t_qc_task", "7"): 107,
            ("t_qc_run", "9"): 109,
            ("t_qc_report", "13"): 113,
            ("t_qc_alarm_policy", "15"): 115,
        },
        pending_identities=frozenset(),
    )
    mapped = map_i21_snapshot(
        _snapshot(
            t_qc_rule=[_rule()],
            t_qc_task=[_task()],
            t_qc_run=[_run()],
            t_qc_exception=[_exception()],
            t_qc_report=[_report()],
            t_qc_alarm_policy=[_alarm()],
        ),
        context,
    )

    assert mapped.ready_to_import
    assert mapped.tasks[0].rule_links[0].rule_definition_id == 101
    assert mapped.exceptions[0].values["run_details_id"] == 109
    assert mapped.exceptions[0].values["rule_definition_id"] == 101
    assert mapped.reports[0].target_id == 113
    assert mapped.alarm_policies[0].target_id == 115


def test_i21_mapper_normalizes_iso_datetimes_for_datetime_columns_and_rejects_offsets():
    mapped = map_i21_snapshot(
        _snapshot(
            t_qc_rule=[_rule(create_time="2026-01-01T00:00:00")],
            t_qc_run=[_run(started_at="2026-01-02T00:00:00+08:00")],
        ),
        _context(),
    )

    assert mapped.rules[0].values["source_created_at"] == datetime(2026, 1, 1)
    assert mapped.runs[0].values["started_at"] is None
    assert "timezone_aware_source_datetime" in {issue.code for issue in mapped.mapping_issues}


def test_i21_mapper_rejects_date_only_timestamp_and_invalid_explicit_target_id():
    date_only = map_i21_snapshot(
        _snapshot(t_qc_rule=[_rule(create_time="2026-01-01")]),
        _context(),
    )
    bad_target_id = map_i21_snapshot(
        _snapshot(t_qc_report=[_report()]),
        _context(target_ids={("t_qc_report", "13"): 0}),
    )

    assert not date_only.ready_to_import
    assert "invalid_source_value" in {issue.code for issue in date_only.mapping_issues}
    assert not bad_target_id.ready_to_import
    assert "invalid_explicit_target_id" in {issue.code for issue in bad_target_id.mapping_issues}


def test_i21_mapper_handles_extremely_large_integer_as_blocking_numeric_issue():
    mapped = map_i21_snapshot(
        _snapshot(t_qc_rule=[_rule(threshold=10**1000)]),
        _context(),
    )

    assert not mapped.ready_to_import
    assert "invalid_source_value" in {issue.code for issue in mapped.mapping_issues}


def test_i21_mapper_blocks_unresolved_task_rule_run_and_rule_references():
    mapped = map_i21_snapshot(
        _snapshot(
            t_qc_task=[_task(rule_ids=[88])],
            t_qc_exception=[_exception(run_id=89, rule_id=88)],
        ),
        LegacyMappingContext(target_project_id=7),
    )

    assert not mapped.ready_to_import
    assert {issue.code for issue in mapped.mapping_issues} >= {"unresolved_reference"}
    assert not mapped.tasks[0].ready_to_import
    assert not mapped.exceptions[0].ready_to_import


def test_i21_mapper_blocks_dangling_optional_task_references_on_runs_and_exceptions():
    mapped = map_i21_snapshot(
        _snapshot(
            t_qc_rule=[_rule()],
            t_qc_run=[_run(task_id=88)],
            t_qc_exception=[_exception(task_id=99)],
        ),
        LegacyMappingContext(target_project_id=7),
    )

    assert not mapped.ready_to_import
    assert {issue.source_table for issue in mapped.mapping_issues if issue.code == "unresolved_reference"} == {
        "t_qc_run",
        "t_qc_exception",
    }


def test_i21_mapper_rejects_malformed_rule_id_arrays_and_keeps_source_row_blocked():
    mapped = map_i21_snapshot(_snapshot(t_qc_task=[_task(rule_ids="1,2")]), _context())

    assert not mapped.ready_to_import
    assert "invalid_task_rule_ids" in {issue.code for issue in mapped.mapping_issues}
    assert mapped.tasks[0].rule_links == ()


def test_i21_mapper_fails_closed_on_orphan_exception_references():
    mapped = map_i21_snapshot(_snapshot(t_qc_exception=[_exception()]), LegacyMappingContext(target_project_id=7))

    assert not mapped.ready_to_import
    assert {issue.code for issue in mapped.mapping_issues} == {"unresolved_reference"}


def test_i21_mapper_requires_complete_snapshot_and_explicit_project():
    incomplete = SimpleNamespace(schema="datara_meta", rows={"t_qc_rule": ()})
    assert "invalid_i21_snapshot_shape" in {
        issue.code for issue in map_i21_snapshot(incomplete, _context()).mapping_issues
    }
    assert "target_project_required" in {
        issue.code for issue in map_i21_snapshot(_snapshot(), LegacyMappingContext()).mapping_issues
    }


def test_i21_mapper_reports_duplicate_source_ids_and_duplicate_task_rule_ids():
    mapped = map_i21_snapshot(
        _snapshot(t_qc_rule=[_rule(), _rule(name="duplicate")], t_qc_task=[_task(rule_ids=[1, 1])]),
        _context(),
    )

    codes = {issue.code for issue in mapped.mapping_issues}
    assert "duplicate_source_identity" in codes
    assert "duplicate_task_rule_identity" in codes
    assert not mapped.ready_to_import


def test_i21_mapper_preserves_sql_and_rejects_values_that_overflow_target_columns():
    mapped = map_i21_snapshot(
        _snapshot(t_qc_rule=[_rule(name="n" * 129)], t_qc_exception=[_exception(sample_sql="SELECT 'x'")]),
        _context(),
    )

    assert "target_text_too_long" in {issue.code for issue in mapped.mapping_issues}
    assert mapped.exceptions[0].values["sample_sql"] == "SELECT 'x'"
    assert not mapped.ready_to_import


def test_i21_mapper_rejects_non_text_sample_sql_without_executing_it():
    mapped = map_i21_snapshot(_snapshot(t_qc_exception=[_exception(sample_sql=123)]), _context())

    assert not mapped.ready_to_import
    assert mapped.exceptions[0].values["sample_sql"] == ""
    assert "invalid_source_value" in {issue.code for issue in mapped.mapping_issues}
