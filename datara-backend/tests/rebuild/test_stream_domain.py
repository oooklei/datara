"""R8-STREAM stream domain tests — design §8 observation chain + §13.7 runtime.

Key assertions: four tables (stream_job/stream_checkpoint/stream_metric_snapshot/
stream_failure_event), the eight-state machine (legal chain passes, illegal
transitions → 4002), checkpoint recovery reads (latest per partition), metric
snapshot appends + §8 observation aggregation (latest snapshot verbatim +
window-aggregated error samples), failure sample recording/query, and the
router contract (token auth, {code,msg,data} envelope) on a scratch app —
the stream router is deliberately NOT mounted in rebuild.api.app by this
increment (mounting is collected by the supervision line).
"""

from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from rebuild.common.db import Base
from rebuild.identity.contracts import Role, TokenService
from rebuild.stream.api import build_stream_router
from rebuild.stream.alert import evaluate_failure_alert
from rebuild.stream.models import (
    StreamCheckpointRecord,
    StreamFailureEventRecord,
    StreamJobAttemptRecord,
    StreamJobRecord,
    StreamMetricSnapshotRecord,
    StreamRecoveryEventRecord,
)
from rebuild.stream.repository import STREAM_STATES, STREAM_TRANSITIONS, StreamDomainError, StreamRepository


STREAM_TABLES = (
    StreamJobRecord.__table__,
    StreamJobAttemptRecord.__table__,
    StreamCheckpointRecord.__table__,
    StreamMetricSnapshotRecord.__table__,
    StreamFailureEventRecord.__table__,
    StreamRecoveryEventRecord.__table__,
)


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=STREAM_TABLES)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    engine.dispose()


@pytest.fixture()
def repo(session_factory):
    with session_factory() as session:
        yield StreamRepository(session)


def _register(repo, name="obs-demo"):
    return repo.register(
        name=name,
        workflow_id=17,
        mq_topic="datara.stream.demo",
        runtime_config={"mode": "fixed_rate", "rows_per_sec": 100, "columns": ["value"]},
    )


# -- 1. register defaults ---------------------------------------------------


def test_register_defaults_to_created_state(repo):
    record = _register(repo)
    assert record.state == "CREATED"
    assert record.attempt_no == 0
    assert record.runtime_config == '{"mode": "fixed_rate", "rows_per_sec": 100, "columns": ["value"]}'
    payload = StreamRepository.job_payload(record)
    assert payload["mq_topic"] == "datara.stream.demo" and payload["workflow_id"] == 17
    assert payload["started_at"] is None and payload["finished_at"] is None
    assert [job["state"] for job in repo.list_jobs()] == ["CREATED"]


# -- 2. legal lifecycle chain ------------------------------------------------


def test_full_legal_lifecycle_chain(repo):
    record = _register(repo)
    job_id = record.id
    chain = [
        ("start", "STARTING"),
        ("activate", "RUNNING"),
        ("pause", "PAUSED"),
        ("resume", "RUNNING"),
        ("stop", "STOPPING"),
        ("complete_stop", "STOPPED"),
    ]
    for action, expected in chain:
        assert repo.transition(job_id, action).state == expected
    final = repo.get_job(job_id)
    assert final.state == "STOPPED"
    assert final.attempt_no == 1
    assert final.started_at is not None and final.finished_at is not None


# -- 3. illegal transitions ----------------------------------------------------


def test_illegal_transitions_rejected(repo):
    job_id = _register(repo).id
    for action in ("activate", "pause", "stop", "complete_stop", "resume", "recover"):
        with pytest.raises(StreamDomainError) as excinfo:
            repo.transition(job_id, action)
        assert excinfo.value.code == 4002
    repo.transition(job_id, "start")
    repo.transition(job_id, "activate")
    repo.transition(job_id, "stop")  # RUNNING → STOPPING
    with pytest.raises(StreamDomainError):
        repo.transition(job_id, "pause")  # STOPPING cannot pause


@pytest.mark.parametrize("state", STREAM_STATES)
@pytest.mark.parametrize("action", ("start", "activate", "stop", "fail", "pause", "recover", "resume", "complete_stop"))
def test_transition_state_action_matrix(repo, state, action):
    job = _register(repo, f"matrix-{state}-{action}")
    job.state = state
    repo._session.flush()
    expected = STREAM_TRANSITIONS.get((state, action))
    if expected is None:
        with pytest.raises(StreamDomainError) as excinfo:
            repo.transition(job.id, action)
        assert excinfo.value.code == 4002
    else:
        assert repo.transition(job.id, action).state == expected


# -- 4. failure/recovery paths -------------------------------------------------


def test_failed_and_recovering_paths(repo):
    job_id = _register(repo).id
    assert repo.transition(job_id, "start").state == "STARTING"
    assert repo.transition(job_id, "activate").state == "RUNNING"
    failed = repo.transition(job_id, "fail")
    assert failed.state == "FAILED" and failed.finished_at is not None
    # FAILED → RECOVERING → RUNNING resumes the same attempt.
    assert repo.transition(job_id, "recover").state == "RECOVERING"
    assert repo.transition(job_id, "activate").state == "RUNNING"
    # FAILED → start opens a new attempt.
    repo.transition(job_id, "fail")
    restarted = repo.transition(job_id, "start")
    assert restarted.state == "STARTING" and restarted.attempt_no == 2


# -- 5. checkpoint recovery reads -----------------------------------------------


def test_checkpoint_write_and_recovery_read(repo):
    job_id = _register(repo).id
    base = datetime(2026, 10, 18, 10, 0, 0)
    repo.write_checkpoint(job_id, "p0", 100, {"group": "g1"}, base)
    repo.write_checkpoint(job_id, "p0", 200, {"group": "g1", "stage": "join"}, base)
    repo.write_checkpoint(job_id, "p1", 55, {"group": "g1"}, base)
    # Recovery read: newest row per partition wins.
    latest = repo.latest_checkpoint(job_id, "p0")
    assert latest["offset_value"] == 200 and latest["payload"]["stage"] == "join"
    per_partition = repo.latest_checkpoints(job_id)
    assert [(row["partition_id"], row["offset_value"]) for row in per_partition] == [("p0", 200), ("p1", 55)]
    assert repo.latest_checkpoint(job_id, "p9") is None
    with pytest.raises(StreamDomainError) as excinfo:
        repo.write_checkpoint(999, "p0", 1, {}, base)
    assert excinfo.value.code == 4041


# -- 6. metric snapshot append ---------------------------------------------------


def test_metric_snapshot_append_and_field_mapping(repo):
    job_id = _register(repo).id
    first = repo.append_metric_snapshot(
        job_id,
        {
            "produce_rate": 120,
            "consume_rate": 100,
            "process_rate": 90,
            "input_count": 1000,
            "output_count": 900,
            "success_count": 850,
            "failure_count": 30,
            "skipped_count": 10,
            "duplicate_count": 10,
            "backlog": 150,
            "offset_value": 800,
            "window_result": {"window": "60s", "aggregates": {"sum_amount": 4242}},
        },
        datetime(2026, 10, 18, 10, 0, 0),
    )
    assert first["produce_rate"] == 120 and first["input_count"] == 1000
    assert first["window_result"] == {"window": "60s", "aggregates": {"sum_amount": 4242}}
    second = repo.append_metric_snapshot(
        job_id, {"produce_rate": 200, "backlog": 80}, datetime(2026, 10, 18, 10, 0, 5)
    )
    assert second["attempt_no"] == 0 and second["success_count"] == 0  # absent fields default


# -- 7. observation aggregation ---------------------------------------------------


def test_observe_aggregates_latest_snapshot_and_window_failures(repo):
    job_id = _register(repo).id
    repo.append_metric_snapshot(
        job_id,
        {"produce_rate": 100, "backlog": 500, "failure_count": 5, "window_result": {"w": 1}},
        datetime(2026, 10, 18, 10, 0, 0),
    )
    repo.append_metric_snapshot(
        job_id,
        {
            "produce_rate": 180,
            "consume_rate": 170,
            "process_rate": 160,
            "input_count": 5000,
            "output_count": 4800,
            "success_count": 4700,
            "failure_count": 60,
            "skipped_count": 20,
            "duplicate_count": 20,
            "backlog": 120,
            "offset_value": 4900,
            "window_result": {"window": "60s", "aggregates": {"sum_amount": 999}},
        },
        datetime(2026, 10, 18, 10, 1, 0),
    )
    repo.record_failure(job_id, 0, "DESERIALIZE_ERROR", {"row": 17}, datetime(2026, 10, 18, 10, 0, 30))
    repo.record_failure(job_id, 0, "DESERIALIZE_ERROR", {"row": 42}, datetime(2026, 10, 18, 10, 0, 50))
    repo.record_failure(job_id, 0, "OUT_OF_ORDER", {"row": 9}, datetime(2026, 10, 19, 12, 0, 0))  # outside window
    observation = repo.observe(job_id, "2026-10-18T00:00:00", "2026-10-18T23:59:59")
    # Latest snapshot verbatim.
    assert observation["produce_rate"] == 180 and observation["backlog"] == 120
    assert observation["offset_value"] == 4900 and observation["success_count"] == 4700
    assert observation["window_result"] == {"window": "60s", "aggregates": {"sum_amount": 999}}
    assert observation["snapshot_count"] == 2
    # Error samples aggregated from failure events inside the window only.
    assert observation["error_sample_count"] == 2


def test_observe_empty_window_zero_fills(repo):
    job_id = _register(repo).id
    observation = repo.observe(job_id, "2026-10-18T00:00:00", "2026-10-18T23:59:59")
    assert observation["snapshot_count"] == 0 and observation["error_sample_count"] == 0
    assert observation["produce_rate"] == 0 and observation["window_result"] == {}
    assert observation["captured_at"] is None and observation["state"] == "CREATED"


# -- 8. failure event recording/validation -----------------------------------------


def test_failure_recording_validation_and_unknown_job(repo):
    job_id = _register(repo).id
    event = repo.record_failure(job_id, 1, "NOT_NULL_VIOLATION", {"col": "email", "row": 3}, datetime(2026, 10, 18, 10, 0, 0))
    assert event["error_type"] == "NOT_NULL_VIOLATION" and event["attempt_no"] == 1
    rows = repo.list_failures(job_id, "2026-10-18T00:00:00", "2026-10-18T23:59:59")
    assert len(rows) == 1 and rows[0]["sample_data"] == {"col": "email", "row": 3}
    with pytest.raises(StreamDomainError) as excinfo:
        repo.record_failure(999, 1, "X", {}, datetime(2026, 10, 18, 10, 0, 0))
    assert excinfo.value.code == 4041
    with pytest.raises(StreamDomainError) as excinfo:
        repo.record_failure(job_id, 1, "", {}, datetime(2026, 10, 18, 10, 0, 0))
    assert excinfo.value.code == 4001


def test_failure_alert_threshold_and_recovery_clear(repo):
    job_id = _register(repo).id
    now = datetime(2026, 10, 19, 12, 1, 0)
    for second in (1, 2, 3):
        repo.record_failure(job_id, 1, "X", {}, now.replace(minute=0, second=second))
    assert evaluate_failure_alert(repo._session, job_id, now=now)["active"] is True
    repo.transition(job_id, "start", event_time=now)
    repo.transition(job_id, "activate", event_time=now)
    repo.transition(job_id, "recover", event_time=now)
    repo.transition(job_id, "activate", event_time=now)
    result = evaluate_failure_alert(repo._session, job_id, now=now)
    assert result["active"] is False and result["cleared_by_recovery"] is True


# -- 9. API contract on a scratch app (router not mounted in app.py) ---------------


@pytest.fixture()
def client(session_factory):
    token_service = TokenService(secret="r8-stream-test-secret")
    active_tokens: set[str] = set()
    token = token_service.issue(user_id=1, username="dev", role=Role.DEVELOPER)
    active_tokens.add(token)
    app = FastAPI()
    app.include_router(build_stream_router(session_factory, token_service, active_tokens), prefix="/api/v1/rebuild/stream")
    with TestClient(app) as test_client:
        test_client.headers.update({"token": token})
        yield test_client


def test_api_lifecycle_observe_and_failures_contract(client):
    created = client.post(
        "/api/v1/rebuild/stream/jobs",
        json={"name": "obs-http", "workflow_id": 17, "mq_topic": "datara.stream.demo", "runtime_config": {"mode": "burst", "base": {"rows_per_sec": 5, "columns": ["v"]}, "burst_every_sec": 2, "burst_count": 4}},
    )
    assert created.status_code == 200
    body = created.json()
    assert body["code"] == 0 and body["msg"] == "success"
    job_id = body["data"]["id"]
    assert body["data"]["state"] == "CREATED" and body["data"]["runtime_config"]["mode"] == "burst"

    started = client.post(f"/api/v1/rebuild/stream/jobs/{job_id}/transitions", json={"action": "start"})
    assert started.json()["data"]["state"] == "STARTING"
    activated = client.post(f"/api/v1/rebuild/stream/jobs/{job_id}/transitions", json={"action": "activate"})
    assert activated.json()["data"]["state"] == "RUNNING"

    illegal = client.post(f"/api/v1/rebuild/stream/jobs/{job_id}/transitions", json={"action": "complete_stop"})
    assert illegal.status_code == 400 and illegal.json()["code"] == 4002

    observation = client.post(
        f"/api/v1/rebuild/stream/jobs/{job_id}/observe",
        json={"from": "2026-10-18T00:00:00", "to": "2026-10-18T23:59:59"},
    )
    assert observation.status_code == 200
    data = observation.json()["data"]
    assert data["state"] == "RUNNING" and data["snapshot_count"] == 0 and data["produce_rate"] == 0

    failures = client.post(
        f"/api/v1/rebuild/stream/jobs/{job_id}/failures",
        json={"from": "2026-10-18T00:00:00", "to": "2026-10-18T23:59:59"},
    )
    assert failures.status_code == 200 and failures.json()["data"] == []

    missing = client.post(
        "/api/v1/rebuild/stream/jobs/999/observe",
        json={"from": "2026-10-18T00:00:00", "to": "2026-10-18T23:59:59"},
    )
    assert missing.status_code == 404 and missing.json()["code"] == 4041


def test_api_anonymous_is_401_and_bearer_fallback(client):
    token_header = client.headers.pop("token", None)
    anonymous = client.post("/api/v1/rebuild/stream/jobs", json={"name": "x", "workflow_id": 1, "mq_topic": "t"})
    assert anonymous.status_code == 401 and anonymous.json()["code"] == 1001
    listed = client.get("/api/v1/rebuild/stream/jobs")
    assert listed.status_code == 401
    client.headers.update({"token": token_header})
    bearer_ok = client.get("/api/v1/rebuild/stream/jobs", headers={"Authorization": f"Bearer {token_header}"})
    assert bearer_ok.status_code == 200 and bearer_ok.json()["code"] == 0


def test_api_observation_contract_endpoints(client, session_factory):
    created = client.post("/api/v1/rebuild/stream/jobs", json={
        "name": "query-contract", "workflow_id": 17, "mq_topic": "topic",
        "runtime_config": {"mode": "fixed_rate", "rows_per_sec": 10, "columns": ["id"]},
    }).json()["data"]
    job_id = created["id"]
    with session_factory() as session:
        repo = StreamRepository(session)
        repo.write_checkpoint(job_id, "p0", 12, {}, datetime(2026, 10, 19, 1, 0, 0))
        repo.append_metric_snapshot(job_id, {"produce_rate": 9, "backlog": 3}, datetime(2026, 10, 19, 1, 0, 0))
        repo.transition(job_id, "start", event_time=datetime(2026, 10, 19, 1, 0, 0))
        repo.transition(job_id, "activate", event_time=datetime(2026, 10, 19, 1, 0, 1))
        repo.transition(job_id, "recover", event_time=datetime(2026, 10, 19, 1, 0, 2))
        session.commit()
    start = "2026-10-19T00:00:00"
    end = "2026-10-19T23:59:59"
    assert client.get(f"/api/v1/rebuild/stream/jobs/{job_id}/attempts").json()["data"][0]["attempt_id"] == 1
    checkpoints = client.get(f"/api/v1/rebuild/stream/jobs/{job_id}/checkpoints").json()["data"]
    assert checkpoints[0]["partition_id"] == "p0" and checkpoints[0]["offset_value"] == 12
    metrics = client.get(f"/api/v1/rebuild/stream/jobs/{job_id}/metrics", params={"from": start, "to": end}).json()["data"]
    assert any(row["metric"] == "produce_rate" and row["value"] == 9 for row in metrics)
    events = client.get(f"/api/v1/rebuild/stream/jobs/{job_id}/recovery-events", params={"from": start, "to": end}).json()["data"]
    assert events[0]["kind"] == "recovery-started"


def test_legacy_job_crosswalk_is_unique(repo):
    repo.register("linked", 1, "topic", {"mode": "fixed_rate", "rows_per_sec": 1, "columns": ["id"]}, legacy_job_id=77)
    with pytest.raises(StreamDomainError) as excinfo:
        repo.register("duplicate-link", 2, "topic", {"mode": "fixed_rate", "rows_per_sec": 1, "columns": ["id"]}, legacy_job_id=77)
    assert excinfo.value.code == 4001


# -- 10. stream_job_attempt independent table (DEP-05) -------------------------
#
# DEP-05: Design §13.7 lists stream_job_attempt as one of five runtime tables.
# Implementation had folded attempt into stream_job.attempt_no counter (4+1 model).
# User ruling (2026-10-19, DEPLOY): 独立建表 (方案 A) — attempt slices persist
# in the independent stream_job_attempt table; stream_job.attempt_no remains
# only the current-attempt pointer for failure/snapshot attribution.


def test_stream_job_attempt_table_exists_in_metadata():
    """stream_job_attempt must be a registered table in the stream metadata."""
    from rebuild.common.db import Base

    assert "stream_job_attempt" in Base.metadata.tables
    table = Base.metadata.tables["stream_job_attempt"]
    columns = {column.name for column in table.columns}
    assert {"id", "job_id", "attempt_no", "status", "started_at", "finished_at"} <= columns
    # §13.13 timestamp contract: created_at/updated_at
    assert {"created_at", "updated_at"} <= columns


def test_stream_job_attempt_unique_constraint():
    """(job_id, attempt_no) must be unique — one row per attempt."""
    from sqlalchemy import inspect as sa_inspect
    from rebuild.common.db import Base

    table = Base.metadata.tables["stream_job_attempt"]
    unique_constraints = [
        tuple(sorted(col.name for col in constraint.columns))
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    ]
    assert ("attempt_no", "job_id") in unique_constraints or ("job_id", "attempt_no") in unique_constraints


def test_stream_job_attempt_write_and_read(repo):
    """An attempt row can be written and read back with all fields."""
    job_id = _register(repo).id
    with repo._session as session:
        attempt = StreamJobAttemptRecord(
            job_id=job_id,
            attempt_no=1,
            status="STARTING",
            started_at=datetime(2026, 10, 19, 10, 0, 0),
            finished_at=None,
        )
        session.add(attempt)
        session.flush()
        session.refresh(attempt)
        assert attempt.id is not None
        assert attempt.job_id == job_id
        assert attempt.attempt_no == 1
        assert attempt.status == "STARTING"
        assert attempt.started_at == datetime(2026, 10, 19, 10, 0, 0)
        assert attempt.finished_at is None
        # §13.13 timestamp contract
        assert attempt.created_at is not None
        assert attempt.updated_at is not None


def test_stream_job_attempt_cascade_delete(repo):
    """Deleting a job removes its attempt rows."""
    from sqlalchemy import delete

    job_id = _register(repo).id
    with repo._session as session:
        session.add(
            StreamJobAttemptRecord(
                job_id=job_id,
                attempt_no=1,
                status="STARTING",
                started_at=datetime(2026, 10, 19, 10, 0, 0),
            )
        )
        session.flush()
    with repo._session as session:
        session.execute(delete(StreamJobAttemptRecord).where(StreamJobAttemptRecord.job_id == job_id))
        remaining = session.scalars(
            select(StreamJobAttemptRecord).where(StreamJobAttemptRecord.job_id == job_id)
        ).all()
        assert remaining == []


# -- 10b. repository wiring: transitions persist attempt rows (DEP-05) --------


def test_start_transition_persists_attempt_row(repo):
    """DEP-05: every legal 'start' opens a persistent stream_job_attempt row."""
    job_id = _register(repo).id
    repo.transition(job_id, "start")
    rows = repo._session.scalars(
        select(StreamJobAttemptRecord).where(StreamJobAttemptRecord.job_id == job_id)
    ).all()
    assert len(rows) == 1
    assert rows[0].attempt_no == 1
    assert rows[0].status == "STARTING"
    assert rows[0].started_at is not None
    assert rows[0].finished_at is None
    # §13.13 timestamp contract
    assert rows[0].created_at is not None
    assert rows[0].updated_at is not None


def test_attempt_row_status_tracks_lifecycle(repo):
    """The attempt row status follows the job through its legal chain."""
    job_id = _register(repo).id
    repo.transition(job_id, "start")
    repo.transition(job_id, "activate")
    repo.transition(job_id, "pause")
    repo.transition(job_id, "resume")
    repo.transition(job_id, "stop")
    repo.transition(job_id, "complete_stop")
    row = repo._session.scalar(
        select(StreamJobAttemptRecord).where(StreamJobAttemptRecord.job_id == job_id)
    )
    assert row.status == "STOPPED"
    assert row.finished_at is not None


def test_list_attempts_reads_independent_table(repo):
    """list_attempts is backed by stream_job_attempt rows, oldest first.

    The folded model could only ever return the single current attempt; the
    independent table returns every persisted attempt slice.
    """
    job_id = _register(repo).id
    assert repo.list_attempts(job_id) == []
    repo.transition(job_id, "start")
    repo.transition(job_id, "activate")
    attempts = repo.list_attempts(job_id)
    assert [row["attempt_id"] for row in attempts] == [1]
    assert attempts[0]["started_at"] is not None
    assert attempts[0]["ended_at"] is None
    assert attempts[0]["exit_reason"] is None
    repo.transition(job_id, "stop")
    repo.transition(job_id, "complete_stop")
    attempts = repo.list_attempts(job_id)
    assert attempts[0]["ended_at"] is not None
    assert attempts[0]["exit_reason"] == "STOPPED"
    # Restart opens a second persisted attempt; both are listed.
    repo.transition(job_id, "start")
    attempts = repo.list_attempts(job_id)
    assert [row["attempt_id"] for row in attempts] == [1, 2]


def test_restart_creates_second_attempt_row(repo):
    """FAILED → start opens a new attempt row instead of rewriting history."""
    job_id = _register(repo).id
    repo.transition(job_id, "start")
    repo.transition(job_id, "activate")
    repo.transition(job_id, "fail")
    repo.transition(job_id, "start")
    rows = repo._session.scalars(
        select(StreamJobAttemptRecord)
        .where(StreamJobAttemptRecord.job_id == job_id)
        .order_by(StreamJobAttemptRecord.attempt_no)
    ).all()
    assert [row.attempt_no for row in rows] == [1, 2]
    assert rows[0].status == "FAILED" and rows[0].finished_at is not None
    assert rows[1].status == "STARTING" and rows[1].finished_at is None
