"""Stable SQL IDE domain errors, HTTP mappings, and response envelopes."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class ErrorDefinition:
    """Public error metadata used by SQL IDE HTTP adapters."""

    http_status: int
    message: str


ERROR_CATALOG: Mapping[str, ErrorDefinition] = MappingProxyType(
    {
        "INVALID_REQUEST": ErrorDefinition(400, "Invalid request"),
        "OBJECT_AMBIGUOUS": ErrorDefinition(400, "Object reference is ambiguous"),
        "CURSOR_INVALID": ErrorDefinition(400, "Cursor is invalid"),
        "UNAUTHENTICATED": ErrorDefinition(401, "Authentication required"),
        "PERMISSION_DENIED": ErrorDefinition(403, "Operation is not permitted"),
        "RESOURCE_NOT_FOUND": ErrorDefinition(404, "Resource not found"),
        "OBJECT_NOT_VISIBLE": ErrorDefinition(404, "Resource not found"),
        "RESULT_NOT_AVAILABLE": ErrorDefinition(404, "Result is not available"),
        "POLICY_BLOCKED": ErrorDefinition(409, "Request is blocked by policy"),
        "IDEMPOTENCY_CONFLICT": ErrorDefinition(409, "Idempotency key conflicts"),
        "SCRIPT_REVISION_CONFLICT": ErrorDefinition(409, "Script revision conflicts"),
        "SOURCE_VERSION_CONFLICT": ErrorDefinition(409, "Source version conflicts"),
        "RESULT_EXPIRED": ErrorDefinition(410, "Result has expired"),
        "EVENT_CURSOR_EXPIRED": ErrorDefinition(410, "Event cursor has expired"),
        "CAPABILITY_CONDITION_NOT_MET": ErrorDefinition(422, "Capability conditions are not met"),
        "CAPABILITY_UNSUPPORTED": ErrorDefinition(422, "Capability is unsupported"),
        "CAPABILITY_UNKNOWN": ErrorDefinition(422, "Capability is unknown"),
        "RATE_LIMITED": ErrorDefinition(429, "Request limit exceeded"),
        "DATASOURCE_UNAVAILABLE": ErrorDefinition(502, "Datasource is unavailable"),
        "DRIVER_ERROR": ErrorDefinition(502, "Database driver request failed"),
        "STATEMENT_EXECUTION_FAILED": ErrorDefinition(502, "Statement execution failed"),
        "RESULT_SNAPSHOT_FAILED": ErrorDefinition(502, "Result snapshot could not be saved"),
        "EXECUTION_TIMEOUT": ErrorDefinition(504, "Execution timed out"),
    }
)


def http_status_for(error_code: str) -> int:
    """Return the frozen HTTP status for a known domain error code."""
    try:
        return ERROR_CATALOG[error_code].http_status
    except KeyError as exc:
        raise ValueError(f"unknown SQL IDE error code: {error_code}") from exc


def build_error_envelope(
    error_code: str,
    *,
    message: str | None = None,
    details: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build the A5-compatible `{code, msg, data}` error response."""
    try:
        definition = ERROR_CATALOG[error_code]
    except KeyError as exc:
        raise ValueError(f"unknown SQL IDE error code: {error_code}") from exc

    return {
        "code": definition.http_status,
        "msg": message or definition.message,
        "data": {
            "errorCode": error_code,
            "details": dict(details) if details is not None else {},
        },
    }
