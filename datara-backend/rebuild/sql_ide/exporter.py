"""Bounded render engine for CSV, JSON and XLSX SQL result exports.

Persistence is delegated to the ExportJobStore contract; export audit is an
append-only injected protocol so this module never updates or deletes audit rows.
"""

from __future__ import annotations

import base64
import csv
import json
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Iterable, Mapping, Protocol, Sequence, runtime_checkable

from openpyxl import Workbook

from rebuild.sql_ide.contracts import ExportJobStore

DEFAULT_MAX_EXPORT_ROWS = 100_000
DEFAULT_MAX_EXPORT_BYTES = 50 * 1024 * 1024
SUPPORTED_FORMATS = frozenset({"csv", "json", "xlsx"})
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ExportLimitError(ValueError):
    """Raised when a result exceeds its configured export bounds."""


@runtime_checkable
class ExportAuditSink(Protocol):
    """Append-only channel for export lifecycle events."""

    def append_event(
        self,
        *,
        project_id: int,
        user_id: int,
        task_id: str,
        format: str,
        outcome: str,
        row_count: int,
        byte_count: int,
        error_code: str | None = None,
    ) -> None:
        """Append one immutable event; implementations must not mutate prior events."""
        ...


@dataclass(frozen=True)
class ExportArtifact:
    payload: bytes
    content_type: str
    filename: str
    format: str
    row_count: int
    byte_count: int
    export_id: str | None = None


class _LimitedTextBuffer:
    """UTF-8 text writer that rejects a row before growing past the byte cap."""

    def __init__(self, max_bytes: int) -> None:
        self._max_bytes = max_bytes
        self._parts: list[str] = []
        self._byte_count = 0

    def write(self, value: str) -> int:
        encoded_size = len(value.encode("utf-8"))
        if self._byte_count + encoded_size > self._max_bytes:
            raise ExportLimitError(f"export exceeds byte limit ({self._max_bytes})")
        self._parts.append(value)
        self._byte_count += encoded_size
        return len(value)

    def getvalue(self) -> str:
        return "".join(self._parts)


class ExportEngine:
    """Render bounded export payloads and append lifecycle audit events."""

    def __init__(
        self,
        *,
        audit_sink: ExportAuditSink,
        job_store: ExportJobStore | None = None,
        max_rows: int = DEFAULT_MAX_EXPORT_ROWS,
        max_bytes: int = DEFAULT_MAX_EXPORT_BYTES,
    ) -> None:
        if max_rows <= 0 or max_bytes <= 0:
            raise ValueError("export limits must be positive")
        if not callable(getattr(audit_sink, "append_event", None)):
            raise TypeError("audit_sink must implement append_event")
        self.audit_sink = audit_sink
        self.job_store = job_store
        self.max_rows = max_rows
        self.max_bytes = max_bytes

    def create_export(
        self,
        *,
        project_id: int,
        user_id: int,
        task_id: str,
        format: str,
        columns: Sequence[str],
        rows: Iterable[Sequence[Any]],
    ) -> ExportArtifact:
        normalized_format = str(format).lower()
        row_count = 0
        byte_count = 0
        try:
            if project_id < 0 or user_id < 0 or not task_id:
                raise ValueError("export identity is invalid")
            if normalized_format not in SUPPORTED_FORMATS:
                raise ValueError(f"unsupported export format: {format}")
            if not columns or any(not isinstance(name, str) for name in columns):
                raise ValueError("export columns are invalid")

            normalized_rows: list[list[Any]] = []
            for row in rows:
                if row_count >= self.max_rows:
                    raise ExportLimitError(f"export exceeds row limit ({self.max_rows})")
                if not isinstance(row, Sequence) or isinstance(row, (str, bytes)):
                    raise ValueError("each export row must match the column shape")
                if len(row) != len(columns):
                    raise ValueError("export row does not match column count")
                normalized_rows.append([_export_value(value) for value in row])
                row_count += 1

            payload, content_type, extension = self._render(normalized_format, list(columns), normalized_rows)
            byte_count = len(payload)
            if byte_count > self.max_bytes:
                raise ExportLimitError(f"export exceeds byte limit ({self.max_bytes})")

            # First record that a bounded artifact is ready. Job creation follows
            # only after this append succeeds, so an unavailable audit blocks export.
            self._append(
                project_id,
                user_id,
                task_id,
                normalized_format,
                "prepared",
                row_count,
                byte_count,
                None,
            )
            export_id = None
            if self.job_store is not None:
                job = self.job_store.create_job(
                    project_id=project_id,
                    user_id=user_id,
                    task_id=task_id,
                    format=normalized_format,
                    row_count=row_count,
                    byte_count=byte_count,
                )
                export_id = _job_id(job)
            self._append(
                project_id,
                user_id,
                task_id,
                normalized_format,
                "completed",
                row_count,
                byte_count,
                None,
            )
            return ExportArtifact(
                payload=payload,
                content_type=content_type,
                filename=f"sql-export.{extension}",
                format=normalized_format,
                row_count=row_count,
                byte_count=byte_count,
                export_id=export_id,
            )
        except Exception as exc:
            try:
                self._append(
                    project_id,
                    user_id,
                    task_id,
                    normalized_format,
                    "failed",
                    row_count,
                    byte_count,
                    _error_code(exc),
                )
            except Exception:
                # A broken audit channel must never cause an export to be returned.
                pass
            raise

    def _render(self, format: str, columns: list[str], rows: list[list[Any]]) -> tuple[bytes, str, str]:
        if format == "csv":
            writer_buffer = _LimitedTextBuffer(self.max_bytes)
            # UTF-8 BOM supports spreadsheet consumers and remains included in
            # the enforced payload byte count.
            writer_buffer.write("\ufeff")
            writer = csv.writer(writer_buffer, lineterminator="\r\n")
            writer.writerow(columns)
            for row in rows:
                writer.writerow([_cell_text(value) for value in row])
            return writer_buffer.getvalue().encode("utf-8"), "text/csv; charset=utf-8", "csv"

        if format == "json":
            chunks = [b"["]
            size = 1
            for index, row in enumerate(rows):
                record = {column: _json_compatible(value) for column, value in zip(columns, row)}
                chunk = json.dumps(record, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
                if index:
                    chunk = b"," + chunk
                size += len(chunk)
                if size + 1 > self.max_bytes:
                    raise ExportLimitError(f"export exceeds byte limit ({self.max_bytes})")
                chunks.append(chunk)
            chunks.append(b"]")
            return b"".join(chunks), "application/json; charset=utf-8", "json"

        workbook = Workbook(write_only=True)
        sheet = workbook.create_sheet(title="Export")
        sheet.append(list(columns))
        for row in rows:
            sheet.append([_xlsx_compatible(value) for value in row])
        # SpooledTemporaryFile keeps large workbooks off the Python heap.
        with tempfile.SpooledTemporaryFile(max_size=min(self.max_bytes, 1024 * 1024)) as output:
            workbook.save(output)
            size = output.tell()
            if size > self.max_bytes:
                raise ExportLimitError(f"export exceeds byte limit ({self.max_bytes})")
            output.seek(0)
            payload = output.read()
        return payload, XLSX_CONTENT_TYPE, "xlsx"

    def _append(
        self,
        project_id: int,
        user_id: int,
        task_id: str,
        format: str,
        outcome: str,
        row_count: int,
        byte_count: int,
        error_code: str | None,
    ) -> None:
        self.audit_sink.append_event(
            project_id=project_id,
            user_id=user_id,
            task_id=task_id,
            format=format,
            outcome=outcome,
            row_count=row_count,
            byte_count=byte_count,
            error_code=error_code,
        )


def _job_id(job: Mapping[str, Any]) -> str | None:
    value = job.get("export_id", job.get("exportId"))
    return str(value) if value is not None else None


def _error_code(exc: Exception) -> str:
    if isinstance(exc, PermissionError):
        return "FORBIDDEN"
    if isinstance(exc, LookupError):
        return "EXPORT_NOT_AVAILABLE"
    if isinstance(exc, ExportLimitError):
        return "EXPORT_LIMIT_EXCEEDED"
    if isinstance(exc, ValueError):
        return "INVALID_EXPORT"
    return "EXPORT_FAILED"


def _export_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
            raise ValueError("non-finite numbers are not exportable")
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, bytes):
        return {"$binary": base64.b64encode(value).decode("ascii")}
    if isinstance(value, Mapping):
        return {str(key): _export_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_export_value(item) for item in value]
    raise TypeError(f"export value type is not supported: {type(value).__name__}")


def _json_compatible(value: Any) -> Any:
    return _export_value(value)


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _xlsx_compatible(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value
