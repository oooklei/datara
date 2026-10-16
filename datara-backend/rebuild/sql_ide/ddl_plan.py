"""Build non-executable SQL IDE DDL plan previews from caller supplied definitions."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from .ddl_diff import DdlDefinitionDiff, build_definition_diff
from .ddl_policy import DdlFinding, DdlPolicyResult, evaluate_ddl_policy


@dataclass(frozen=True)
class DdlPlanInput:
    dialect: str
    object_kind: str
    schema: str | None
    object_name: str
    current_definition: str | None
    current_definition_digest: str | None
    expected_definition: str


@dataclass(frozen=True)
class DdlPlanPreview:
    status: str
    executable: bool
    dialect: str
    object_kind: str
    schema: str | None
    object_name: str
    policy: DdlPolicyResult
    impact_summary: tuple[str, ...]
    sql_sha256: str
    preimage_definition: str | None
    preimage_sha256: str | None
    rollback_candidate: str | None
    diff: DdlDefinitionDiff
    preview_sql: str


def _digest(value: str | None) -> str | None:
    if value is None:
        return None
    return sha256(value.encode("utf-8")).hexdigest()


def build_ddl_plan_preview(request: DdlPlanInput) -> DdlPlanPreview:
    """Create a deterministic local preview with hashes and rollback candidate.

    The result deliberately remains non-executable regardless of policy outcome.
    A rollback candidate is just the caller supplied preimage; its correctness and
    operational safety still require later dependency checks and human review.
    """
    policy = evaluate_ddl_policy(
        dialect=request.dialect,
        object_kind=request.object_kind,
        current_definition=request.current_definition,
        current_definition_digest=request.current_definition_digest,
        expected_definition=request.expected_definition,
    )
    current_digest = _digest(request.current_definition)
    verified_preimage = (
        request.current_definition is not None
        and bool(request.current_definition.strip())
        and request.current_definition_digest is not None
        and current_digest == request.current_definition_digest.lower()
    )
    direct_target = ".".join(part for part in (request.schema, request.object_name) if part)
    impact_summary = [f"Target object: {request.object_kind} {direct_target}"]
    diff = build_definition_diff(request.current_definition, request.expected_definition)
    if not diff.changed:
        impact_summary.append("Definition is unchanged.")
    else:
        impact_summary.append("Definition changes.")
    impact_summary.append("Dependency impact is unknown and requires a later dependency review.")
    impact_summary.append("Rollback candidate preserves the preimage text; adapt and review it before use.")
    findings = policy.findings
    if not request.object_name.strip():
        findings = findings + (DdlFinding("block", "object_name_missing", "Target object name cannot be empty."),)
        policy = DdlPolicyResult(
            dialect=policy.dialect,
            object_kind=policy.object_kind,
            operation=policy.operation,
            statement_count=policy.statement_count,
            findings=findings,
            blocked=True,
        )
    return DdlPlanPreview(
        status="blocked" if policy.blocked else "preview_only",
        executable=False,
        dialect=policy.dialect,
        object_kind=policy.object_kind,
        schema=request.schema,
        object_name=request.object_name,
        policy=policy,
        impact_summary=tuple(impact_summary),
        sql_sha256=sha256(request.expected_definition.encode("utf-8")).hexdigest(),
        preimage_definition=request.current_definition if verified_preimage else None,
        preimage_sha256=current_digest if verified_preimage else None,
        rollback_candidate=request.current_definition if verified_preimage else None,
        diff=diff,
        preview_sql=request.expected_definition,
    )
