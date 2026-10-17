"""SQLAlchemy persistence for variable definitions and execution snapshots."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from rebuild.variables.models import TaskInstanceVariableRuntimeRecord, VariableDefinitionRecord
from rebuild.variables.service import ResolvedVariable, VariableDomainError, validate_definition


def _now_shanghai() -> datetime:
    return datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)


class VariableRepository:
    """Persist definitions and snapshots; no authentication happens here."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # -- definitions -------------------------------------------------------

    def owner_key(self, scope: str, project_id: int | None) -> str:
        if scope == "global":
            return "global"
        if scope in ("project", "tmp") and project_id is not None:
            return f"{scope}:{project_id}"
        raise VariableDomainError(4001, f"scope {scope!r} cannot be persisted for this project")

    def list_owner(self, owner_key: str) -> list[ResolvedVariable]:
        rows = self._session.scalars(
            select(VariableDefinitionRecord)
            .where(VariableDefinitionRecord.owner_key == owner_key)
            .order_by(VariableDefinitionRecord.name)
        )
        return [self._as_resolved(row) for row in rows]

    def upsert(
        self,
        *,
        scope: str,
        project_id: int | None,
        name: str,
        value: str,
        value_type: str,
        sensitive: bool,
        description: str,
    ) -> VariableDefinitionRecord:
        validate_definition(scope, name, value_type, value)
        owner = self.owner_key(scope, project_id)
        row = self._session.scalar(
            select(VariableDefinitionRecord).where(
                VariableDefinitionRecord.owner_key == owner,
                VariableDefinitionRecord.name == name,
            )
        )
        if row is None:
            row = VariableDefinitionRecord(
                scope=scope,
                project_id=project_id,
                owner_key=owner,
                name=name,
                value_type=value_type,
                value_json=value,
                sensitive=sensitive,
                description=description,
            )
            self._session.add(row)
        else:
            row.value_type = value_type
            row.value_json = value
            row.sensitive = sensitive
            row.description = description
            row.updated_at = _now_shanghai()
        self._session.flush()
        return row

    def list_for_project(self, project_id: int) -> list[ResolvedVariable]:
        """Visible stored variables for a bare project context (project + tmp)."""
        items: list[ResolvedVariable] = []
        items.extend(self.list_owner(f"project:{project_id}"))
        items.extend(self.list_owner(f"tmp:{project_id}"))
        return items

    def list_all_with_scope(self, project_id: int) -> list[ResolvedVariable]:
        """Stored variables visible from a bare project context, including global."""
        items: list[ResolvedVariable] = []
        items.extend(self.list_owner(f"project:{project_id}"))
        items.extend(self.list_owner(f"tmp:{project_id}"))
        items.extend(self.list_owner("global"))
        return items

    @staticmethod
    def _as_resolved(row: VariableDefinitionRecord) -> ResolvedVariable:
        return ResolvedVariable(
            name=row.name,
            scope=row.scope,
            value=row.value_json,
            value_type=row.value_type,
            sensitive=row.sensitive,
            description=row.description,
        )

    # -- run snapshots -----------------------------------------------------

    def write_snapshot_rows(self, rows: list[dict[str, object]]) -> int:
        """Append snapshot rows for one execution attempt; returns row count.

        project_id (P0-7 security patch) is optional in the payload; rows
        without it are legacy-shaped and unreadable from every project.
        """
        for payload in rows:
            for field in ("expression", "scope", "name", "resolved_value", "value_type", "source"):
                if not isinstance(payload.get(field), str) or not payload[field]:
                    raise VariableDomainError(4001, f"snapshot row missing field {field!r}")
            project_id = payload.get("project_id")
            if project_id is not None and (isinstance(project_id, bool) or not isinstance(project_id, int) or project_id < 1):
                raise VariableDomainError(4001, "snapshot row project_id must be an integer >= 1")
            self._session.add(
                TaskInstanceVariableRuntimeRecord(
                    instance_id=int(payload["instance_id"]),  # type: ignore[arg-type]
                    project_id=project_id,  # type: ignore[arg-type]
                    attempt_no=int(payload.get("attempt_no") or 1),  # type: ignore[arg-type]
                    expression=str(payload["expression"]),
                    scope=str(payload["scope"]),
                    name=str(payload["name"]),
                    resolved_value=str(payload["resolved_value"]),
                    value_type=str(payload["value_type"]),
                    source=str(payload["source"]),
                    resolved_at=_now_shanghai(),
                )
            )
        self._session.flush()
        return len(rows)

    def read_snapshot(self, instance_id: int, attempt_no: int | None, project_id: int) -> list[dict[str, object]]:
        """Snapshot rows for an instance (latest attempt when attempt_no omitted).

        P0-7 security patch: rows are filtered by the requesting project —
        cross-project instance ids yield an empty list, and legacy NULL rows
        are unreadable from any project (fail-closed).
        """
        query = select(TaskInstanceVariableRuntimeRecord).where(
            TaskInstanceVariableRuntimeRecord.instance_id == instance_id,
            TaskInstanceVariableRuntimeRecord.project_id == project_id,
        )
        if attempt_no is not None:
            query = query.where(TaskInstanceVariableRuntimeRecord.attempt_no == attempt_no)
        rows = self._session.scalars(query.order_by(TaskInstanceVariableRuntimeRecord.id))
        entries = [
            {
                "expression": row.expression,
                "scope": row.scope,
                "name": row.name,
                "resolved_value": row.resolved_value,
                "value_type": row.value_type,
                "source": row.source,
                "resolved_at": row.resolved_at.isoformat(),
                "attempt_no": row.attempt_no,
            }
            for row in rows
        ]
        if attempt_no is None and entries:
            latest = max(entry["attempt_no"] for entry in entries)  # type: ignore[type-var]
            entries = [entry for entry in entries if entry["attempt_no"] == latest]
        return entries
