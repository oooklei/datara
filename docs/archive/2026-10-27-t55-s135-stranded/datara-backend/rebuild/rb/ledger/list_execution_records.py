"""Project-scoped list service for immutable R5-B execution records."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone

from rebuild.rb.models.rb_models import ObjectRef


class ListExecutionRecordsService:
    def __init__(self, repository) -> None:
        self._repository = repository

    def __call__(
        self,
        *,
        project_id: int,
        datasource_id: int,
        object_ref=None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, object]:
        if not isinstance(project_id, int) or isinstance(project_id, bool) or project_id <= 0:
            raise ValueError("project_id must be a positive integer")
        if not isinstance(datasource_id, int) or isinstance(datasource_id, bool) or datasource_id <= 0:
            raise ValueError("datasource_id must be a positive integer")
        if page < 1 or not 1 <= page_size <= 200:
            raise ValueError("page must be positive and page_size must be between 1 and 200")
        ref = _object_ref(datasource_id, object_ref)
        records = self._repository.list_records(
            project_id=project_id,
            datasource_id=datasource_id,
            object_ref=ref,
            page=page,
            page_size=page_size,
            fetch_limit=page_size + 1,
        )
        has_more = len(records) > page_size
        visible_records = records[:page_size]
        return {
            "items": [
                {
                    "recordId": row.record_id,
                    "datasourceId": row.datasource_id,
                    "objectRef": _serialize_object_ref(row.object_ref),
                    "action": row.action,
                    "scriptHash": row.script_hash,
                    "executedAt": _iso_utc(row.executed_at),
                    "status": row.status,
                    "failureSummary": row.failure_summary,
                    "policySnapshotId": row.policy_snapshot_id,
                    "impactSnapshotId": row.impact_snapshot_id,
                    "compensationRefs": row.compensation_refs,
                    "actorId": row.actor_id,
                }
                for row in visible_records
            ],
            "page": {
                "number": page,
                "pageSize": page_size,
                "nextCursor": str(page + 1) if has_more else None,
                "hasMore": has_more,
            },
        }


def _object_ref(datasource_id: int, value) -> ObjectRef | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("object_ref must be an object")
    database = value.get("database")
    kind = value.get("kind")
    name = value.get("name")
    if not all(isinstance(item, str) and item.strip() for item in (database, kind, name)):
        raise ValueError("object_ref database, kind, and name are required")
    return ObjectRef(
        datasource_id=datasource_id,
        database=database,
        catalog=value.get("catalog"),
        schema=value.get("schema"),
        kind=kind,
        name=name,
        parent=value.get("parent"),
    )


def _serialize_object_ref(value) -> dict[str, object]:
    if isinstance(value, ObjectRef):
        raw = asdict(value)
    elif is_dataclass(value):
        raw = asdict(value)
    elif isinstance(value, dict):
        raw = dict(value)
    else:
        raise ValueError("execution record has an invalid object_ref")
    return {
        "datasourceId": raw.get("datasource_id", raw.get("datasourceId")),
        "database": raw.get("database"),
        "catalog": raw.get("catalog"),
        "schema": raw.get("schema"),
        "kind": raw.get("kind"),
        "name": raw.get("name"),
        "parent": raw.get("parent"),
    }


def _iso_utc(value: datetime) -> str:
    if not isinstance(value, datetime):
        raise ValueError("execution record has an invalid executed_at")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
