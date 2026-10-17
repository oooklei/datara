"""Tests for R5-A production AuditWriter (Track A Gap 3).

Covers:
- write_execution_start returns audit_id and persists record
- write_execution_end updates record with status/elapsed/error
- DB-backed storage via session_factory
- AuditWriter Protocol conformance
- Error handling (write failure propagates)
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch, call

import pytest

from rebuild.sql_ide.audit import (
    DbBackedAuditWriter,
    build_audit_writer,
    SqlIdeAuditRecord,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


class _MockSessionFactory:
    """Helper that provides a session_factory mock with inspection."""

    def __init__(self, records=None):
        self.session = MagicMock()
        self.added = []
        self.session.add = self.added.append
        if records is not None:
            self.session.scalar.return_value = records
            # also support query().filter().first() chain
            query_mock = MagicMock()
            query_mock.filter.return_value.first.return_value = records
            self.session.query.return_value = query_mock
        else:
            self.session.scalar.return_value = None
            query_mock = MagicMock()
            query_mock.filter.return_value.first.return_value = None
            self.session.query.return_value = query_mock
        self.factory = MagicMock()
        self.factory.return_value.__enter__.return_value = self.session
        self.factory.return_value.__exit__.return_value = False

    def __iter__(self):
        yield self.factory
        yield self.session
        yield self.added


def _mock_session_factory(records=None):
    """Return an iterable of (factory, session, added) for unpacking."""
    return _MockSessionFactory(records)


# ---------------------------------------------------------------------------
# factory
# ---------------------------------------------------------------------------


class TestBuildAuditWriter:
    """Factory creates a properly wired audit writer."""

    def test_build_returns_db_backed_writer(self):
        sf = MagicMock()
        writer = build_audit_writer(session_factory=sf)
        assert isinstance(writer, DbBackedAuditWriter)

    def test_build_passes_session_factory_through(self):
        sf = MagicMock()
        writer = build_audit_writer(session_factory=sf)
        assert writer._session_factory is sf


# ---------------------------------------------------------------------------
# write_execution_start
# ---------------------------------------------------------------------------


class TestWriteExecutionStart:
    """write_execution_start persists an audit record and returns audit_id."""

    def test_returns_audit_id_string(self):
        sf, session, added = _mock_session_factory()
        writer = build_audit_writer(session_factory=sf)
        audit_id = writer.write_execution_start(
            project_id=1,
            user_id=42,
            datasource_id=7,
            sql_digest="abc123",
            task_id="task-001",
        )
        assert isinstance(audit_id, str)
        assert len(audit_id) > 0

    def test_adds_record_to_session(self):
        sf, session, added = _mock_session_factory()
        writer = build_audit_writer(session_factory=sf)
        audit_id = writer.write_execution_start(
            project_id=1,
            user_id=42,
            datasource_id=7,
            sql_digest="abc123",
            task_id="task-001",
        )
        assert len(added) == 1
        record = added[0]
        assert isinstance(record, SqlIdeAuditRecord)
        assert record.project_id == 1
        assert record.user_id == 42
        assert record.datasource_id == 7
        assert record.sql_digest == "abc123"
        assert record.task_id == "task-001"
        assert record.status == "running"
        assert record.audit_id == audit_id

    def test_commits_session(self):
        sf, session, added = _mock_session_factory()
        writer = build_audit_writer(session_factory=sf)
        writer.write_execution_start(
            project_id=1,
            user_id=42,
            datasource_id=7,
            sql_digest="abc123",
            task_id="task-001",
        )
        session.commit.assert_called_once()

    def test_different_calls_produce_different_audit_ids(self):
        sf, session, added = _mock_session_factory()
        writer = build_audit_writer(session_factory=sf)
        id1 = writer.write_execution_start(
            project_id=1, user_id=1, datasource_id=1,
            sql_digest="a", task_id="t1",
        )
        id2 = writer.write_execution_start(
            project_id=1, user_id=1, datasource_id=1,
            sql_digest="b", task_id="t2",
        )
        assert id1 != id2


# ---------------------------------------------------------------------------
# write_execution_end
# ---------------------------------------------------------------------------


class TestWriteExecutionEnd:
    """write_execution_end updates the audit record with final status."""

    def _seed_record(self, audit_id: str):
        """Create a mock existing record for update tests."""
        record = MagicMock()
        record.audit_id = audit_id
        return record

    def test_updates_existing_record(self):
        audit_id = "test-audit-123"
        existing = self._seed_record(audit_id)
        sf, session, added = _mock_session_factory(records=existing)
        writer = build_audit_writer(session_factory=sf)
        writer.write_execution_end(
            audit_id=audit_id,
            status="success",
            stmt_count=3,
            elapsed_ms=1500,
        )
        assert existing.status == "success"
        assert existing.stmt_count == 3
        assert existing.elapsed_ms == 1500
        assert existing.error_code is None

    def test_updates_with_error_code(self):
        audit_id = "test-audit-456"
        existing = self._seed_record(audit_id)
        sf, session, added = _mock_session_factory(records=existing)
        writer = build_audit_writer(session_factory=sf)
        writer.write_execution_end(
            audit_id=audit_id,
            status="failed",
            stmt_count=1,
            elapsed_ms=500,
            error_code="EXECUTION_FAILED",
        )
        assert existing.status == "failed"
        assert existing.error_code == "EXECUTION_FAILED"

    def test_commits_after_update(self):
        audit_id = "test-audit-789"
        existing = self._seed_record(audit_id)
        sf, session, added = _mock_session_factory(records=existing)
        writer = build_audit_writer(session_factory=sf)
        writer.write_execution_end(
            audit_id=audit_id,
            status="success",
            stmt_count=1,
            elapsed_ms=100,
        )
        session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestAuditWriterProtocol:
    """DbBackedAuditWriter satisfies the AuditWriter Protocol."""

    def test_satisfies_protocol(self):
        from rebuild.sql_ide.contracts import AuditWriter
        sf = MagicMock()
        writer = build_audit_writer(session_factory=sf)
        assert isinstance(writer, AuditWriter)


# ---------------------------------------------------------------------------
# error handling
# ---------------------------------------------------------------------------


class TestAuditWriterErrorHandling:
    """AuditWriter propagates write failures."""

    def test_start_write_failure_propagates(self):
        sf = MagicMock()
        session = MagicMock()
        session.add.side_effect = RuntimeError("DB down")
        sf.return_value.__enter__.return_value = session
        sf.return_value.__exit__.return_value = False
        writer = build_audit_writer(session_factory=sf)
        with pytest.raises(RuntimeError, match="DB down"):
            writer.write_execution_start(
                project_id=1, user_id=1, datasource_id=1,
                sql_digest="x", task_id="t",
            )

    def test_end_write_failure_propagates(self):
        sf = MagicMock()
        session = MagicMock()
        session.scalar.return_value = None  # record not found
        query_mock = MagicMock()
        query_mock.filter.return_value.first.return_value = None
        session.query.return_value = query_mock
        sf.return_value.__enter__.return_value = session
        sf.return_value.__exit__.return_value = False
        writer = build_audit_writer(session_factory=sf)
        with pytest.raises(RuntimeError, match="not found"):
            writer.write_execution_end(
                audit_id="nonexistent",
                status="success",
                stmt_count=1,
                elapsed_ms=100,
            )
