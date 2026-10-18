"""Bounded SQL result and authorized table exports for R5-A."""

from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable, Iterable, Sequence
from uuid import uuid4

from openpyxl import Workbook
from sqlalchemy import DateTime, Integer, JSON, LargeBinary, String, delete, select
from sqlalchemy.orm import Mapped, mapped_column

from rebuild.common.db import Base
from rebuild.sql_ide.result_store import MAX_PAGE_LIMIT, PersistentResultPageStore

EXPORT_TTL = timedelta(hours=1)
# Deployment limits are provisional pending D8 per-profile measurement.
MAX_EXPORT_ROWS = 100_000
MAX_EXPORT_BYTES = 50 * 1024 * 1024
SUPPORTED_FORMATS = {"csv", "json", "xlsx"}


class SqlIdeExportJobRecord(Base):
    """Short-lived export job and payload kept in platform storage."""

    __tablename__ = "sql_ide_export_jobs"

    export_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    resource_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_ref: Mapped[dict] = mapped_column(JSON, nullable=False)
    format: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    filename: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class SqlIdeExportAuditRecord(Base):
    """Append-only audit event for export creation and cleanup actions."""

    __tablename__ = "sql_ide_export_audit"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    export_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class SqlIdeExportService:
    """Creates bounded exports from immutable snapshots or authorized table readers."""

    audit_model = SqlIdeExportAuditRecord

    def __init__(
        self,
        *,
        session_factory: Callable[[], Any],
        result_store: PersistentResultPageStore,
        authorize_result: Callable[..., bool] | None = None,
        authorize_table: Callable[..., bool] | None = None,
        table_reader: Callable[..., tuple[Sequence[str], Iterable[Sequence[Any]]]] | None = None,
        max_rows: int = MAX_EXPORT_ROWS,
        max_bytes: int = MAX_EXPORT_BYTES,
    ) -> None:
        if max_rows <= 0:
            raise ValueError("max_rows must be positive")
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self.session_factory = session_factory
        self.result_store = result_store
        self._authorize_result = authorize_result
        self._authorize_table = authorize_table
        self._table_reader = table_reader
        self._max_rows = max_rows
        self._max_bytes = max_bytes

    def create_result_export(
        self,
        *,
        project_id: int,
        user_id: int,
        history_id: str,
        stmt_index: int | None = None,
        result_set_id: str | None = None,
        format: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        export_id = str(uuid4())
        try:
            if self._authorize_result is None or not self._authorize_result(
                project_id=project_id, user_id=user_id, history_id=history_id,
                stmt_index=stmt_index, result_set_id=result_set_id,
            ):
                raise PermissionError("result export is not authorized")
            columns, rows = self._read_snapshot(
                project_id=project_id, user_id=user_id, history_id=history_id,
                stmt_index=stmt_index, result_set_id=result_set_id,
            )
            content_type, filename, payload = self._render(columns, rows, format)
            return self._save_job(
                export_id=export_id,
                project_id=project_id,
                user_id=user_id,
                resource_kind="result",
                resource_ref={
                    "historyId": history_id,
                    "stmtIndex": stmt_index,
                    "resultSetId": result_set_id,
                },
                format=format,
                content_type=content_type,
                filename=filename,
                payload=payload,
                now=now,
            )
        except Exception as exc:
            self._audit(project_id, user_id, export_id, "result_export", "failed", _error_code(exc), now)
            raise

    def create_table_export(
        self,
        *,
        project_id: int,
        user_id: int,
        datasource_id: int,
        object_ref: dict[str, Any],
        format: str,
        row_limit: int,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        export_id = str(uuid4())
        try:
            if not _valid_table_ref(object_ref, datasource_id):
                raise ValueError("a complete table ObjectRef is required")
            if not 1 <= row_limit <= self._max_rows:
                raise ValueError(f"row limit must be between 1 and {self._max_rows}")
            if self._authorize_table is None or not self._authorize_table(
                project_id=project_id,
                user_id=user_id,
                datasource_id=datasource_id,
                object_ref=object_ref,
            ):
                raise PermissionError("table export is not authorized")
            if self._table_reader is None:
                raise RuntimeError("read-only table export reader is unavailable")
            columns, source_rows = self._table_reader(
                project_id=project_id,
                user_id=user_id,
                datasource_id=datasource_id,
                object_ref=object_ref,
                row_limit=row_limit + 1,
            )
            rows = [[_json_value(value) for value in row] for row in source_rows]
            if len(rows) > row_limit:
                raise ValueError("table export exceeds row limit")
            content_type, filename, payload = self._render(columns, rows, format)
            return self._save_job(
                export_id=export_id,
                project_id=project_id,
                user_id=user_id,
                resource_kind="table",
                resource_ref={"datasourceId": datasource_id, **object_ref},
                format=format,
                content_type=content_type,
                filename=filename,
                payload=payload,
                now=now,
            )
        except Exception as exc:
            self._audit(project_id, user_id, export_id, "table_export", "failed", _error_code(exc), now)
            raise

    def get_job(
        self, *, project_id: int, user_id: int, export_id: str, now: datetime | None = None
    ) -> dict[str, Any]:
        record = self._find_job(project_id, user_id, export_id, now)
        return {
            "exportId": record.export_id,
            "status": record.status,
            "format": record.format,
            "createdAt": _iso_utc(record.created_at),
            "expiresAt": _iso_utc(record.expires_at),
        }

    def download(
        self, *, project_id: int, user_id: int, export_id: str, now: datetime | None = None
    ) -> tuple[bytes, str, str]:
        record = self._find_job(project_id, user_id, export_id, now)
        return bytes(record.payload), record.content_type, record.filename

    def cancel(self, *, project_id: int, user_id: int, export_id: str, now: datetime | None = None) -> bool:
        current = _utc_naive(now or datetime.now(timezone.utc))
        with self.session_factory() as session, session.begin():
            record = session.scalar(
                select(SqlIdeExportJobRecord).where(
                    SqlIdeExportJobRecord.project_id == project_id,
                    SqlIdeExportJobRecord.user_id == user_id,
                    SqlIdeExportJobRecord.export_id == export_id,
                )
            )
            if record is None:
                raise LookupError("export job is not available")
            if record.expires_at <= current:
                raise LookupError("export job expired")
            session.delete(record)
            session.add(self._audit_record(project_id, user_id, export_id, "export_cancel", "completed", None, current))
        return True

    def cleanup_expired(self, *, now: datetime | None = None) -> int:
        current = _utc_naive(now or datetime.now(timezone.utc))
        with self.session_factory() as session, session.begin():
            result = session.execute(
                delete(SqlIdeExportJobRecord).where(SqlIdeExportJobRecord.expires_at <= current)
            )
            return int(result.rowcount or 0)

    def _read_snapshot(
        self, *, project_id: int, user_id: int, history_id: str,
        stmt_index: int | None = None, result_set_id: str | None = None,
    ):
        meta = self.result_store.get_snapshot_meta(
            project_id=project_id, user_id=user_id, history_id=history_id,
            stmt_index=stmt_index, result_set_id=result_set_id,
        )
        rows: list[list[Any]] = []
        offset = 0
        while True:
            page = self.result_store.fetch_page(
                project_id=project_id,
                user_id=user_id,
                history_id=history_id,
                stmt_index=stmt_index,
                result_set_id=result_set_id,
                offset=offset,
                limit=MAX_PAGE_LIMIT,
            )
            rows.extend(page["rows"])
            if len(rows) > self._max_rows:
                raise ValueError("result export exceeds row limit")
            if not page["page"]["hasMore"]:
                break
            offset += len(page["rows"])
        return meta["columns"], rows

    def _render(self, columns: Sequence[str], rows: Sequence[Sequence[Any]], format: str):
        normalized_format = format.lower()
        if normalized_format not in SUPPORTED_FORMATS:
            raise ValueError("unsupported export format")
        estimate = json.dumps([list(columns), rows], ensure_ascii=False, default=str).encode("utf-8")
        if len(estimate) > self._max_bytes:
            raise ValueError("export exceeds byte limit")
        if normalized_format == "csv":
            text = io.StringIO(newline="")
            writer = csv.writer(text, lineterminator="\r\n")
            writer.writerow(columns)
            writer.writerows(rows)
            payload = text.getvalue().encode("utf-8")
            content_type = "text/csv; charset=utf-8"
        elif normalized_format == "json":
            payload = json.dumps(
                {"columns": list(columns), "rows": rows}, ensure_ascii=False, separators=(",", ":"), default=str
            ).encode("utf-8")
            content_type = "application/json; charset=utf-8"
        else:
            workbook = Workbook(write_only=True)
            sheet = workbook.create_sheet("result")
            sheet.append(list(columns))
            for row in rows:
                sheet.append([_xlsx_value(value) for value in row])
            buffer = io.BytesIO()
            workbook.save(buffer)
            payload = buffer.getvalue()
            content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if len(payload) > self._max_bytes:
            raise ValueError("export exceeds byte limit")
        return content_type, f"sql-ide-export.{normalized_format}", payload

    def _save_job(self, *, export_id, project_id, user_id, resource_kind, resource_ref, format, content_type,
                  filename, payload, now):
        current = _utc_naive(now or datetime.now(timezone.utc))
        record = SqlIdeExportJobRecord(
            export_id=export_id,
            project_id=project_id,
            user_id=user_id,
            resource_kind=resource_kind,
            resource_ref=resource_ref,
            format=format.lower(),
            status="completed",
            content_type=content_type,
            filename=filename,
            payload=payload,
            created_at=current,
            expires_at=current + EXPORT_TTL,
        )
        with self.session_factory() as session, session.begin():
            session.add(record)
            session.add(self._audit_record(project_id, user_id, export_id, f"{resource_kind}_export", "completed", None, current))
            session.flush()
            return {"exportId": export_id, "status": "completed", "expiresAt": _iso_utc(record.expires_at)}

    def _find_job(self, project_id, user_id, export_id, now):
        current = _utc_naive(now or datetime.now(timezone.utc))
        with self.session_factory() as session:
            record = session.scalar(
                select(SqlIdeExportJobRecord).where(
                    SqlIdeExportJobRecord.project_id == project_id,
                    SqlIdeExportJobRecord.user_id == user_id,
                    SqlIdeExportJobRecord.export_id == export_id,
                )
            )
            if record is None:
                raise LookupError("export job is not available")
            if record.expires_at <= current:
                raise LookupError("export job expired")
            return record

    def _audit(self, project_id, user_id, export_id, action, outcome, error_code, now):
        current = _utc_naive(now or datetime.now(timezone.utc))
        with self.session_factory() as session, session.begin():
            session.add(self._audit_record(project_id, user_id, export_id, action, outcome, error_code, current))

    @staticmethod
    def _audit_record(project_id, user_id, export_id, action, outcome, error_code, now):
        return SqlIdeExportAuditRecord(
            event_id=str(uuid4()),
            project_id=project_id,
            user_id=user_id,
            export_id=export_id,
            action=action,
            outcome=outcome,
            error_code=error_code,
            created_at=now,
        )


def _valid_table_ref(object_ref: Any, datasource_id: int) -> bool:
    if not isinstance(object_ref, dict):
        return False
    required = ("database", "schema", "kind", "name")
    return (
        object_ref.get("datasourceId") == datasource_id
        and object_ref.get("kind") == "table"
        and all(isinstance(object_ref.get(key), str) and object_ref[key].strip() for key in required)
    )


def _error_code(exc: Exception) -> str:
    if isinstance(exc, PermissionError):
        return "FORBIDDEN"
    if isinstance(exc, LookupError):
        return "RESULT_NOT_AVAILABLE"
    if isinstance(exc, ValueError):
        return "EXPORT_LIMIT_OR_FORMAT"
    return "EXPORT_FAILED"


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _iso_utc(value: datetime) -> str:
    return _utc_naive(value).replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    raise TypeError(f"export value type is not supported: {type(value).__name__}")


def _xlsx_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value
