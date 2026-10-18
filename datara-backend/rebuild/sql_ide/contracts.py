"""Interface contracts for R5-A SQL IDE backend.

P2-2 non-production (partial unfreeze #257): interface stubs only.
These define the Protocol contracts that production implementations must satisfy.
No production implementation is provided — that awaits A5 freeze and P2-1 closure.

Design input: docs/increments/2026-10-18-P2-2-R5-A-SQL-IDE后端设计草案.md
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable

from rebuild.sql_ide.ddl_policy import DdlPolicyResult


# ============================================================================
# Execution contracts (extends existing run_sql.SqlExecutionPort)
# ============================================================================


@runtime_checkable
class SqlExecutionSession(Protocol):
    """R5-A controlled execution session.

    One session per datasource/session, statements executed serially.
    Production implementation awaits A5 freeze.
    """

    def execute(
        self,
        *,
        project_id: int,
        datasource_id: int,
        sql: str,
        row_limit: int,
        timeout_ms: int,
        dialect: str | None = None,
        catalog: str | None = None,
        schema: str | None = None,
    ) -> Mapping[str, Any]:
        """Execute read-only SQL and return result page snapshot."""
        ...

    def cancel(self, *, task_id: str) -> bool:
        """Request cancellation. Returns True if cancel was accepted."""
        ...

    def status(self, *, task_id: str) -> Mapping[str, Any]:
        """Return current execution status."""
        ...


@runtime_checkable
class ResultPageStore(Protocol):
    """R5-A result page snapshot store.

    Pages are read from the same snapshot, never re-executed.
    Production implementation awaits A5 freeze.
    """

    def fetch_page(
        self,
        *,
        history_id: str,
        stmt_index: int,
        offset: int,
        limit: int,
    ) -> Mapping[str, Any]:
        """Fetch a result page from a persisted snapshot."""
        ...

    def get_snapshot_meta(self, *, history_id: str, stmt_index: int) -> Mapping[str, Any]:
        """Get snapshot metadata (columns, total rows, truncation flag)."""
        ...


@runtime_checkable
class HistoryStore(Protocol):
    """R5-A SQL history store.

    Records execution summaries with audit associations.
    Production implementation awaits A5 freeze.
    """

    def list_history(
        self,
        *,
        project_id: int,
        user_id: int,
        datasource_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Mapping[str, Any]:
        """List SQL history for a project/user/datasource."""
        ...

    def get_history(self, *, history_id: str) -> Mapping[str, Any]:
        """Get a single history entry."""
        ...

    def delete_history(self, *, history_id: str, deleted_by: int) -> bool:
        """Delete a history entry. Returns True if deleted."""
        ...


@runtime_checkable
class ScriptStore(Protocol):
    """R5-A SQL script asset store.

    Project-isolated SQL script files with revision/ETag concurrency control.
    Production implementation awaits A5 freeze.
    """

    def list_scripts(self, *, project_id: int) -> Mapping[str, Any]:
        """List SQL scripts for a project."""
        ...

    def get_script(self, *, script_id: str) -> Mapping[str, Any]:
        """Get a single script."""
        ...

    def save_script(
        self,
        *,
        project_id: int,
        name: str,
        sql_text: str,
        folder_id: str | None = None,
        expected_revision: int | None = None,
    ) -> Mapping[str, Any]:
        """Create or update a script. Uses revision for CAS concurrency."""
        ...

    def delete_script(self, *, script_id: str, deleted_by: int) -> bool:
        """Delete a script. Returns True if deleted."""
        ...


# ============================================================================
# Security / policy contracts
# ============================================================================


@runtime_checkable
class ReadonlyPolicy(Protocol):
    """R5-A read-only policy gate.

    Combined DB account permissions + server-side AST/dialect analysis.
    Unknown/unclassifiable statements fail closed.
    Production implementation awaits A5 freeze.
    """

    def evaluate(
        self,
        *,
        sql: str,
        datasource_id: int,
        dialect: str,
        catalog: str | None = None,
        schema: str | None = None,
    ) -> Mapping[str, Any]:
        """Evaluate read-only policy. Returns {allowed: bool, violations: [...]}."""
        ...


@runtime_checkable
class VariableResolver(Protocol):
    """R5-A variable resolver (shares R2 resolver).

    Resolves ${scope.name} and $[time expressions] to immutable snapshots.
    Production implementation awaits A5 freeze.
    """

    def resolve(
        self,
        *,
        sql: str,
        project_id: int,
        datasource_id: int,
    ) -> Mapping[str, Any]:
        """Resolve variables. Returns {resolved_sql, snapshot_ref, digest}."""
        ...


@runtime_checkable
class AuditWriter(Protocol):
    """R5-A audit writer.

    Writes audit records for SQL execution, history deletion, script operations.
    Production implementation awaits A5 freeze.
    """

    def write_execution_start(
        self,
        *,
        project_id: int,
        user_id: int,
        datasource_id: int,
        sql_digest: str,
        task_id: str,
    ) -> str:
        """Write execution start audit. Returns audit_id."""
        ...

    def write_execution_end(
        self,
        *,
        audit_id: str,
        status: str,
        stmt_count: int,
        elapsed_ms: int,
        error_code: str | None = None,
    ) -> None:
        """Write execution end audit."""
        ...


# ============================================================================
# Driver / capability contracts
# ============================================================================


@runtime_checkable
class DriverProfile(Protocol):
    """R5-A driver profile.

    Capability level must not be inferred from database name alone.
    Production implementation awaits A5 freeze.
    """

    @property
    def dialect(self) -> str:
        """Driver dialect (mysql, postgresql, sqlite)."""
        ...

    @property
    def capabilities(self) -> Mapping[str, str]:
        """Capability matrix: operation -> supported/unsupported/unknown."""
        ...

    def supports_operation(self, operation: str) -> bool:
        """Check if an operation is supported."""
        ...


@runtime_checkable
class DriverRegistry(Protocol):
    """R5-A driver registry.

    Resolves datasource kind/profile to driver profiles.
    Production implementation awaits A5 freeze.
    """

    def resolve(self, *, datasource_id: int) -> DriverProfile:
        """Resolve a datasource to its driver profile."""
        ...

    def list_databases(self, *, datasource_id: int) -> Mapping[str, Any]:
        """List databases for a datasource."""
        ...

    def list_schemas(self, *, datasource_id: int, database: str) -> Mapping[str, Any]:
        """List schemas for a database."""
        ...

    def list_relations(
        self,
        *,
        datasource_id: int,
        database: str,
        schema: str,
        page: int = 1,
        page_size: int = 50,
    ) -> Mapping[str, Any]:
        """List tables/views in a schema."""
        ...


# ============================================================================
# Export contracts
# ============================================================================


@runtime_checkable
class ExportJobStore(Protocol):
    """R5-A export job store.

    Short-lived export handles with expiry and cleanup.
    Production implementation awaits A5 freeze.
    """

    def create_job(
        self,
        *,
        project_id: int,
        user_id: int,
        task_id: str,
        format: str,
        row_count: int,
        byte_count: int,
    ) -> Mapping[str, Any]:
        """Create an export job after enforcing configured row and byte limits."""
        ...

    def get_job(self, *, export_id: str) -> Mapping[str, Any]:
        """Get export job status."""
        ...

    def cleanup_expired(self, *, before: str) -> int:
        """Cleanup expired exports. Returns count cleaned."""
        ...
