import json
from decimal import Decimal
from io import BytesIO
import pytest
from openpyxl import load_workbook
from rebuild.sql_ide.exporter import DEFAULT_MAX_EXPORT_BYTES, DEFAULT_MAX_EXPORT_ROWS, ExportEngine, ExportLimitError


class AuditSink:
    def __init__(self):
        self.events = []

    def append_event(self, **event):
        self.events.append(event)


class JobStore:
    def __init__(self):
        self.jobs = []

    def create_job(self, **job):
        self.jobs.append(job)
        return {"export_id": "exp-1", **job}


def test_defaults_and_configurable_limits():
    assert DEFAULT_MAX_EXPORT_ROWS == 100_000
    assert DEFAULT_MAX_EXPORT_BYTES == 50 * 1024 * 1024
    engine = ExportEngine(audit_sink=AuditSink(), max_rows=3, max_bytes=1024)
    assert engine.max_rows == 3 and engine.max_bytes == 1024


@pytest.mark.parametrize(
    "format,expected_type",
    [
        ("csv", "text/csv; charset=utf-8"),
        ("json", "application/json; charset=utf-8"),
        ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ],
)
def test_exports_supported_formats_with_header_and_row_count(format, expected_type):
    audit = AuditSink()
    result = ExportEngine(audit_sink=audit).create_export(
        project_id=5,
        user_id=8,
        task_id="task-1",
        format=format.upper(),
        columns=["name", "value"],
        rows=[["alpha", Decimal("1.25")]],
    )
    assert result.content_type == expected_type
    assert result.row_count == 1 and result.byte_count == len(result.payload)
    assert audit.events[-1]["outcome"] == "completed"
    assert audit.events[-1]["byte_count"] == len(result.payload)
    if format == "csv":
        assert result.payload.decode("utf-8-sig").splitlines() == ["name,value", "alpha,1.25"]
    elif format == "json":
        assert json.loads(result.payload) == [{"name": "alpha", "value": "1.25"}]
    else:
        sheet = load_workbook(BytesIO(result.payload), read_only=True).active
        assert list(sheet.values) == [("name", "value"), ("alpha", "1.25")]


def test_limit_excess_fails_closed_without_job_creation():
    audit, jobs = AuditSink(), JobStore()
    engine = ExportEngine(audit_sink=audit, job_store=jobs, max_rows=1, max_bytes=1000)
    with pytest.raises(ExportLimitError, match="row"):
        engine.create_export(project_id=1, user_id=2, task_id="t", format="json", columns=["x"], rows=[[1], [2]])
    assert jobs.jobs == [] and audit.events[-1]["outcome"] == "failed"


def test_byte_limit_excess_fails_closed_without_job_creation():
    audit, jobs = AuditSink(), JobStore()
    engine = ExportEngine(audit_sink=audit, job_store=jobs, max_rows=10, max_bytes=8)
    with pytest.raises(ExportLimitError, match="byte"):
        engine.create_export(
            project_id=1, user_id=2, task_id="t", format="json", columns=["x"], rows=[["long payload"]]
        )
    assert jobs.jobs == [] and audit.events[-1]["outcome"] == "failed"


def test_job_store_is_called_only_after_limits_pass():
    jobs = JobStore()
    result = ExportEngine(audit_sink=AuditSink(), job_store=jobs).create_export(
        project_id=1,
        user_id=2,
        task_id="t",
        format="csv",
        columns=["x"],
        rows=[[1]],
    )
    assert result.export_id == "exp-1"
    assert jobs.jobs[0]["row_count"] == 1 and jobs.jobs[0]["byte_count"] == result.byte_count


def test_invalid_format_and_row_shape_fail_closed():
    audit = AuditSink()
    engine = ExportEngine(audit_sink=audit)
    with pytest.raises(ValueError, match="format"):
        engine.create_export(project_id=1, user_id=2, task_id="t", format="xml", columns=["x"], rows=[])
    with pytest.raises(ValueError, match="column"):
        engine.create_export(project_id=1, user_id=2, task_id="t", format="json", columns=["x", "y"], rows=[[1]])
    assert [event["outcome"] for event in audit.events] == ["failed", "failed"]


def test_audit_failure_does_not_return_export():
    class BrokenAudit:
        def append_event(self, **event):
            raise RuntimeError("audit unavailable")

    with pytest.raises(RuntimeError, match="audit unavailable"):
        ExportEngine(audit_sink=BrokenAudit()).create_export(
            project_id=1,
            user_id=2,
            task_id="t",
            format="json",
            columns=["x"],
            rows=[[1]],
        )
