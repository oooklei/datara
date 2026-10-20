from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from rebuild.common.db import Base
from rebuild.stream.legacy_bridge import (
    _factory,
    sync_legacy_checkpoints,
    sync_legacy_failure,
    sync_legacy_metrics,
    sync_legacy_state,
)
from rebuild.stream.models import (
    StreamCheckpointRecord,
    StreamFailureEventRecord,
    StreamJobAttemptRecord,
    StreamJobRecord,
    StreamMetricSnapshotRecord,
    StreamRecoveryEventRecord,
)


@pytest.fixture()
def linked_stream(tmp_path, monkeypatch):
    path = tmp_path / "stream-bridge.db"
    url = f"sqlite:///{path.as_posix()}"
    engine = create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    tables = [
        StreamJobRecord.__table__, StreamJobAttemptRecord.__table__, StreamCheckpointRecord.__table__,
        StreamMetricSnapshotRecord.__table__, StreamFailureEventRecord.__table__,
        StreamRecoveryEventRecord.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add(StreamJobRecord(
            name="legacy", workflow_id=9, legacy_job_id=42, mq_topic="legacy-topic",
            runtime_config='{"mode":"fixed_rate","rows_per_sec":10,"columns":["id"]}', state="CREATED",
        ))
        session.commit()
    monkeypatch.setenv("REBUILD_DB_URL", url)
    _factory.cache_clear()
    yield factory
    engine.dispose()
    _factory.cache_clear()


def test_legacy_bridge_mirrors_status_checkpoints_metrics_and_failures(linked_stream):
    at = datetime(2026, 10, 19, 12, 0)
    assert sync_legacy_state(42, "starting", event_time=at)
    assert sync_legacy_state(42, "running", event_time=at)
    assert sync_legacy_state(42, "reconnecting", event_time=at)
    assert sync_legacy_checkpoints(42, {"source:kafka": {"partitions": {"0": 51, "1": 73}}}, event_time=at) == 2
    assert sync_legacy_metrics(42, {"produce_rate": 9, "input_count": 8}, captured_at=at)
    assert sync_legacy_failure(42, "TimeoutError", {"message": "timeout"}, event_time=at)
    with linked_stream() as session:
        job = session.query(StreamJobRecord).filter_by(legacy_job_id=42).one()
        checkpoints = session.query(StreamCheckpointRecord).filter_by(job_id=job.id).all()
        metric = session.query(StreamMetricSnapshotRecord).filter_by(job_id=job.id).one()
        failure = session.query(StreamFailureEventRecord).filter_by(job_id=job.id).one()
        assert job.state == "RECOVERING"
        assert sorted(row.offset_value for row in checkpoints) == [51, 73]
        assert metric.produce_rate == 9 and metric.input_count == 8
        assert failure.error_type == "TimeoutError" and failure.attempt_no == 1


def test_legacy_bridge_requires_explicit_crosswalk(linked_stream):
    assert sync_legacy_state(999, "running") is False
    assert sync_legacy_checkpoints(999, {"src": {"pos": 4}}) == 0
    assert sync_legacy_metrics(999, {"input_count": 10}) is False
    assert sync_legacy_failure(999, "X", {}) is False
