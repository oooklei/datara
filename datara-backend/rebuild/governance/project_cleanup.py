"""Delete one project's governance graph in foreign-key order.

Audit events are retained with a null project pointer so deletion does not
erase the record of what happened. Migration batches are global evidence and
have no project key, so they are outside this graph.
"""

from __future__ import annotations

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from rebuild.common.db import Base
from rebuild.governance.models import AuditEventRecord


# This nullable link still owns a row when a quality run belongs to a project.
_OPTIONAL_OWNER_LINKS = {("rebuild_governance_quality_run_legacy_details", "quality_run_id")}


class ProjectGovernanceConflict(ValueError):
    """A governance row in another project still references this project."""


def delete_project_governance(session: Session, project_id: int) -> int:
    """Remove project-owned rows and their dependants without touching global rows."""
    tables = [
        table for table in Base.metadata.sorted_tables
        if table.name.startswith("rebuild_governance_") and table.name != AuditEventRecord.__tablename__
    ]
    filters = {}
    for table in tables:
        if "project_id" in table.c:
            # A foreign project's row must never be selected through a cross-project FK.
            predicates = [table.c.project_id == project_id]
            for column in table.c:
                for foreign_key in column.foreign_keys:
                    parent = foreign_key.column.table
                    if parent not in filters:
                        continue
                    foreign_owner = or_(table.c.project_id != project_id, table.c.project_id.is_(None))
                    linked_to_target = column.in_(select(foreign_key.column).where(filters[parent]))
                    if session.scalar(select(1).select_from(table).where(foreign_owner, linked_to_target).limit(1)):
                        raise ProjectGovernanceConflict(f"cross-project reference in {table.name}")
        else:
            predicates = []
            for column in table.c:
                for foreign_key in column.foreign_keys:
                    parent = foreign_key.column.table
                    if parent not in filters:
                        continue
                    if column.nullable and (table.name, column.name) not in _OPTIONAL_OWNER_LINKS:
                        continue
                    predicates.append(column.in_(select(foreign_key.column).where(filters[parent])))
        if predicates:
            filters[table] = or_(*predicates)

    # Preserve the audit trail; its project FK must be released before deletion.
    session.execute(update(AuditEventRecord).where(AuditEventRecord.project_id == project_id).values(project_id=None))
    deleted = 0
    for table in reversed(tables):
        predicate = filters.get(table)
        if predicate is not None:
            deleted += session.execute(delete(table).where(predicate)).rowcount or 0
    return deleted
