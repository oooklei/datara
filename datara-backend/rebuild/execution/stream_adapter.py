"""Execution-to-STREAM protocol adapter for long-running run checkpoints."""

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from rebuild.execution.repository import ExecutionDomainError, ExecutionRepository
from rebuild.stream.repository import StreamDomainError, StreamRepository


def record_stream_checkpoint(
    session: Session,
    *,
    workflow_instance_id: int,
    stream_job_id: int,
    partition_id: str,
    offset_value: int,
    payload: dict[str, Any] | str | None,
    event_time: datetime,
) -> dict[str, Any]:
    """Validate the STREAM instance/job pairing, then use the stream domain API."""
    instance = ExecutionRepository(session)._require_workflow_instance(workflow_instance_id)
    if instance.instance_type != "STREAM":
        raise ExecutionDomainError(4109, "checkpoints are only valid for STREAM instances")
    stream = StreamRepository(session)
    try:
        job = stream.get_job(stream_job_id)
        if job.workflow_id != instance.workflow_id:
            raise ExecutionDomainError(4109, "stream job does not belong to workflow_instance workflow")
        stream.write_checkpoint(
            stream_job_id,
            partition_id,
            offset_value,
            payload,
            event_time,
        )
        result = stream.latest_checkpoint(stream_job_id, partition_id)
    except StreamDomainError as exc:
        raise ExecutionDomainError(4109, exc.msg) from exc
    assert result is not None
    return result
