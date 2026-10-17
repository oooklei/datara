"""R4 dependency API contract tests — frozen FE contract (dependencyApi.ts / A2 v2.1).

Key assertions: honest empty candidate/task lists (narrow scope, disclosed),
token/Bearer auth + {code,msg,data} envelope, DEP_* domain codes with field
diagnostics, numeric 4001 frame errors, deterministic window math (fixed
as_of), §7.5 two-level three-state verdicts over the R7 history tables,
§7.3/§7.9 policy validation (waiting/timeout mutex), save slot replacement,
evaluated_at echo (Z-normalized).
"""

import json
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import select

from rebuild.api.app import create_app
from rebuild.dependency.models import DependencyConfigRecord
from rebuild.identity.contracts import Role
from rebuild.identity.models import ProjectMemberRecord
from rebuild.identity.repository import UserRepository
from rebuild.metrics.models import (
    TaskDataErrorSampleRecord,
    TaskInstanceDataStatRecord,
    WorkflowResultStatRecord,
)
from rebuild.project.models import ProjectRecord

AS_OF = "2026-10-17T12:00:00Z"
DEPENDENCY = "/api/v1/rebuild/dependency"


def _client():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="r4-dependency-test-secret")
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        dev = UserRepository(session).create(username="dev", password="dev-pass", role=Role.DEV)
        viewer = UserRepository(session).create(username="viewer", password="viewer-pass", role=Role.VIEWER)
        owned = ProjectRecord(name="r4-owned", description="", owner_id=dev.id)
        session.add_all((owned,))
        session.commit()
        owned_id = owned.id
        session.add(ProjectMemberRecord(project_id=owned_id, user_id=viewer.id, role="viewer"))
        session.commit()
    tokens = {}
    for username, password in (("dev", "dev-pass"), ("viewer", "viewer-pass")):
        response = client.post("/api/v1/rebuild/login", json={"username": username, "password": password})
        tokens[username] = {"Authorization": f"Bearer {response.json()['data']['token']}"}
    return client, app, owned_id, tokens


def _condition(**overrides):
    condition = {
        "kind": "workflow",
        "upstream_workflow_id": 7,
        "upstream_workflow_version": 1,
        "upstream_task_code": 0,
        "selector": "workflow",
        "cycle": "day",
        "date_value": "last1Days",
        "depend_result": "success",
        "parameter_passing": False,
    }
    condition.update(overrides)
    return condition


def _body(owned_id, groups=None, **overrides):
    payload = {
        "project_id": owned_id,
        "workflow_id": 10,
        "workflow_version": 3,
        "task_id": "clean",
        "groups": groups if groups is not None else [{"join": "AND", "conditions": [_condition()]}],
        "as_of": AS_OF,
    }
    payload.update(overrides)
    return payload


def _seed_workflow_stat(app, workflow_id, success, failure):
    with app.state.session_factory() as session:
        session.add(
            WorkflowResultStatRecord(
                workflow_id=workflow_id,
                run_date=datetime(2026, 10, 16).date(),
                success_count=success,
                failure_count=failure,
                skipped_count=0,
                retry_count=0,
            )
        )
        session.commit()


def _seed_task_history(app, task_code, with_error):
    with app.state.session_factory() as session:
        session.add(
            TaskInstanceDataStatRecord(
                instance_id=900 + task_code,
                task_id=str(task_code),
                rows_in='{"value": 1, "known": true, "estimated": false}',
                rows_out='{"value": 1, "known": true, "estimated": false}',
                error_rows='{"value": 0, "known": true, "estimated": false}',
                elapsed_ms='{"value": 100, "known": true, "estimated": false}',
                created_at=datetime(2026, 10, 16, 10, 0, 0),
            )
        )
        if with_error:
            session.add(
                TaskDataErrorSampleRecord(
                    instance_id=900 + task_code,
                    task_id=str(task_code),
                    error_type="NOT_NULL_VIOLATION",
                    sample_data='{"row": 1}',
                    captured_at=datetime(2026, 10, 16, 10, 5, 0),
                )
            )
        session.commit()


def test_honest_empty_lists_and_auth_envelope():
    client, app, owned_id, tokens = _client()
    try:
        anonymous = client.get(f"{DEPENDENCY}/workflows", params={"project_id": owned_id})
        assert anonymous.status_code == 401 and anonymous.json()["code"] == 1001

        missing = client.get(f"{DEPENDENCY}/workflows", headers=tokens["dev"])
        assert missing.status_code == 400 and missing.json()["code"] == 4001

        workflows = client.get(
            f"{DEPENDENCY}/workflows", headers=tokens["dev"], params={"project_id": owned_id}
        )
        assert workflows.status_code == 200
        body = workflows.json()
        assert body["code"] == 0 and body["msg"] == "success" and body["data"] == []

        tasks = client.get(
            f"{DEPENDENCY}/workflows/7/tasks", headers=tokens["dev"], params={"project_id": owned_id}
        )
        assert tasks.status_code == 200 and tasks.json()["data"] == []
    finally:
        client.__exit__(None, None, None)


def test_preview_window_math_expression_and_timeout():
    client, app, owned_id, tokens = _client()
    try:
        preview = client.post(f"{DEPENDENCY}/preview", headers=tokens["dev"], json=_body(owned_id))
        assert preview.status_code == 200
        data = preview.json()["data"]
        assert data["expression"] == "wf(7) day:last1Days"
        # No history; window already closed at as_of; no timeout configured → stays pending.
        assert data["verdict"] == "pending"
        resolved = data["resolved"][0]
        assert resolved["window_start"] == "2026-10-16T00:00:00Z"
        assert resolved["window_end"] == "2026-10-17T00:00:00Z"
        assert "upstream_task_code" not in resolved  # selector=workflow carries no task code

        timeout = client.post(
            f"{DEPENDENCY}/preview", headers=tokens["dev"], json=_body(owned_id, timeout_seconds=3600)
        )
        # as_of 12:00Z >= window_end 00:00Z + 1h threshold → timeout.
        assert timeout.json()["data"]["verdict"] == "timeout"

        task_selector = client.post(
            f"{DEPENDENCY}/preview",
            headers=tokens["dev"],
            json=_body(
                owned_id,
                groups=[{"join": "AND", "conditions": [_condition(kind="task", selector="task", upstream_task_code=5)]}],
            ),
        )
        task_data = task_selector.json()["data"]
        assert task_data["expression"] == "wf(7) task(5) day:last1Days"
        assert task_data["resolved"][0]["upstream_task_code"] == "5"  # string only for selector=task

        inverted = client.post(
            f"{DEPENDENCY}/preview",
            headers=tokens["dev"],
            json=_body(
                owned_id,
                groups=[{"join": "AND", "conditions": [_condition(depend_result="failed")]}],
            ),
        )
        assert inverted.json()["data"]["expression"] == "! wf(7) day:last1Days"

        range_condition = _condition()
        del range_condition["cycle"]
        del range_condition["date_value"]
        range_condition["date_range"] = {"period_type": "day", "begin_offset": -2, "end_offset": -1}
        date_range = client.post(
            f"{DEPENDENCY}/preview",
            headers=tokens["dev"],
            json=_body(owned_id, groups=[{"join": "AND", "conditions": [range_condition]}]),
        )
        range_resolved = date_range.json()["data"]["resolved"][0]
        assert range_resolved["window_start"] == "2026-10-15T00:00:00Z"
        assert range_resolved["window_end"] == "2026-10-17T00:00:00Z"
    finally:
        client.__exit__(None, None, None)


def test_history_verdicts_over_r7_tables():
    client, app, owned_id, tokens = _client()
    try:
        _seed_workflow_stat(app, 21, success=5, failure=0)
        _seed_workflow_stat(app, 22, success=0, failure=3)
        _seed_task_history(app, 5, with_error=False)
        _seed_task_history(app, 6, with_error=True)

        def preview_verdict(groups):
            response = client.post(f"{DEPENDENCY}/preview", headers=tokens["dev"], json=_body(owned_id, groups=groups))
            assert response.status_code == 200, response.text
            return response.json()["data"]["verdict"]

        def wf(workflow_id, depend_result="success"):
            return [{"join": "AND", "conditions": [_condition(upstream_workflow_id=workflow_id, depend_result=depend_result)]}]

        def task(code):
            return [{"join": "AND", "conditions": [_condition(kind="task", selector="task", upstream_task_code=code)]}]

        assert preview_verdict(wf(21)) == "satisfied"  # success rows in window
        assert preview_verdict(wf(22)) == "failed"  # only failure rows, success expected
        assert preview_verdict(wf(22, depend_result="failed")) == "satisfied"  # inverted polarity
        assert preview_verdict(task(5)) == "satisfied"  # task rows, no error samples
        assert preview_verdict(task(6)) == "failed"  # error samples in window
    finally:
        client.__exit__(None, None, None)


def test_two_level_group_verdicts():
    client, app, owned_id, tokens = _client()
    try:
        _seed_workflow_stat(app, 21, success=5, failure=0)
        _seed_workflow_stat(app, 22, success=0, failure=3)

        def preview_verdict(groups, group_relation="AND"):
            response = client.post(
                f"{DEPENDENCY}/preview",
                headers=tokens["dev"],
                json=_body(owned_id, groups=groups, group_relation=group_relation),
            )
            assert response.status_code == 200, response.text
            return response.json()["data"]

        one_group = preview_verdict(
            [{"join": "OR", "conditions": [_condition(upstream_workflow_id=21), _condition(upstream_workflow_id=22)]}]
        )
        assert one_group["expression"] == "(wf(21) day:last1Days OR wf(22) day:last1Days)"
        assert one_group["verdict"] == "satisfied"  # OR: satisfied outranks failed

        and_group = preview_verdict(
            [{"join": "AND", "conditions": [_condition(upstream_workflow_id=21), _condition(upstream_workflow_id=22)]}]
        )
        assert and_group["verdict"] == "failed"  # AND: failed outranks

        cross_or = preview_verdict(
            [{"join": "AND", "conditions": [_condition(upstream_workflow_id=21)]},
             {"join": "AND", "conditions": [_condition(upstream_workflow_id=22)]}],
            group_relation="OR",
        )
        assert cross_or["expression"] == "wf(21) day:last1Days OR wf(22) day:last1Days"
        assert cross_or["verdict"] == "satisfied"

        cross_and = preview_verdict(
            [{"join": "AND", "conditions": [_condition(upstream_workflow_id=21)]},
             {"join": "AND", "conditions": [_condition(upstream_workflow_id=22)]}],
            group_relation="AND",
        )
        assert cross_and["verdict"] == "failed"
    finally:
        client.__exit__(None, None, None)


def test_validation_failure_families():
    client, app, owned_id, tokens = _client()
    try:
        dual = _condition()
        dual["date_range"] = {"period_type": "day", "begin_offset": -1, "end_offset": -1}
        response = client.post(
            f"{DEPENDENCY}/preview", headers=tokens["dev"],
            json=_body(owned_id, groups=[{"join": "AND", "conditions": [dual]}]),
        )
        assert response.status_code == 400
        body = response.json()
        assert body["code"] == "DEP_INVALID_WINDOW"  # §3.1 dual-input mutex
        assert any(d["field"] == "groups[0].conditions[0].window" for d in body["data"]["diagnostics"])

        mismatch = client.post(
            f"{DEPENDENCY}/preview", headers=tokens["dev"],
            json=_body(owned_id, groups=[{"join": "AND", "conditions": [_condition(selector="task", upstream_task_code=0)]}]),
        )
        assert mismatch.status_code == 400 and mismatch.json()["code"] == "DEP_INVALID_WINDOW"

        not_frozen = client.post(
            f"{DEPENDENCY}/preview", headers=tokens["dev"],
            json=_body(owned_id, groups=[{"join": "AND", "conditions": [_condition(kind="file")]}]),
        )
        assert not_frozen.status_code == 400
        assert any(d["code"] == "NOT_FROZEN" for d in not_frozen.json()["data"]["diagnostics"])

        mutex = client.post(
            f"{DEPENDENCY}/preview", headers=tokens["dev"],
            json=_body(
                owned_id,
                failure_policy="waiting",
                failure_waiting_seconds=300,
                dependent_wait_timeout_enabled=True,
                dependent_wait_timeout_seconds=60,
            ),
        )
        assert mutex.status_code == 400 and mutex.json()["code"] == "DEP_INVALID_TIMEOUT_POLICY"  # §7.9

        waiting_missing = client.post(
            f"{DEPENDENCY}/preview", headers=tokens["dev"], json=_body(owned_id, failure_policy="waiting")
        )
        assert waiting_missing.status_code == 400 and waiting_missing.json()["code"] == "DEP_INVALID_WINDOW"

        frame = _body(owned_id)
        del frame["workflow_version"]
        malformed = client.post(f"{DEPENDENCY}/preview", headers=tokens["dev"], json=frame)
        assert malformed.status_code == 400 and malformed.json()["code"] == 4001

        bad_clock = client.post(
            f"{DEPENDENCY}/preview", headers=tokens["dev"], json=_body(owned_id, as_of="not-a-timestamp")
        )
        assert bad_clock.status_code == 400 and bad_clock.json()["code"] == 4001

        empty_groups = client.post(
            f"{DEPENDENCY}/preview", headers=tokens["dev"], json=_body(owned_id, groups=[])
        )
        assert empty_groups.status_code == 400 and empty_groups.json()["code"] == "DEP_INVALID_WINDOW"
    finally:
        client.__exit__(None, None, None)


def test_save_slot_replacement_policy_and_permission():
    client, app, owned_id, tokens = _client()
    try:
        saved = client.post(
            f"{DEPENDENCY}/saves", headers=tokens["dev"],
            json=_body(owned_id, check_interval_seconds=120, failure_policy="fail"),
        )
        assert saved.status_code == 200
        assert saved.json()["data"] == {"saved": True, "version": 3}

        with app.state.session_factory() as session:
            records = session.scalars(select(DependencyConfigRecord)).all()
        assert len(records) == 1
        assert records[0].check_interval_seconds == 120
        assert records[0].failure_policy == "fail"

        replaced = client.post(
            f"{DEPENDENCY}/saves", headers=tokens["dev"],
            json=_body(owned_id, groups=[{"join": "AND", "conditions": [_condition(upstream_workflow_id=22)]}]),
        )
        assert replaced.status_code == 200 and replaced.json()["data"]["saved"] is True

        with app.state.session_factory() as session:
            records = session.scalars(select(DependencyConfigRecord)).all()
        assert len(records) == 1  # same slot replaced, not appended
        snapshot = json.loads(records[0].groups_json)
        assert snapshot[0]["conditions"][0]["upstream_workflow_id"] == 22

        denial = client.post(f"{DEPENDENCY}/saves", headers=tokens["viewer"], json=_body(owned_id))
        assert denial.status_code == 403 and denial.json()["code"] == 1003
    finally:
        client.__exit__(None, None, None)


def test_evaluate_echoes_normalized_as_of():
    client, app, owned_id, tokens = _client()
    try:
        evaluate = client.post(f"{DEPENDENCY}/evaluate", headers=tokens["dev"], json=_body(owned_id))
        assert evaluate.status_code == 200
        data = evaluate.json()["data"]
        assert data["evaluated_at"] == "2026-10-17T12:00:00Z"
        assert data["verdict"] == "pending"
        assert data["expression"] == "wf(7) day:last1Days"

        naive = client.post(
            f"{DEPENDENCY}/evaluate", headers=tokens["dev"], json=_body(owned_id, as_of="2026-10-17T12:00:00")
        )
        assert naive.json()["data"]["evaluated_at"] == "2026-10-17T12:00:00Z"

        viewer_preview = client.post(f"{DEPENDENCY}/preview", headers=tokens["viewer"], json=_body(owned_id))
        assert viewer_preview.status_code == 200  # VIEW_ALL is enough to read/preview
    finally:
        client.__exit__(None, None, None)
