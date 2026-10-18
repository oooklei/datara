from __future__ import annotations

import pytest

from rebuild.sql_ide.error_catalog import (
    ERROR_CATALOG,
    build_error_envelope,
    http_status_for,
)


@pytest.mark.parametrize(
    ("error_code", "expected_status"),
    [
        ("INVALID_REQUEST", 400),
        ("UNAUTHENTICATED", 401),
        ("PERMISSION_DENIED", 403),
        ("RESOURCE_NOT_FOUND", 404),
        ("POLICY_BLOCKED", 409),
        ("IDEMPOTENCY_CONFLICT", 409),
        ("RESULT_EXPIRED", 410),
        ("CAPABILITY_UNSUPPORTED", 422),
        ("RATE_LIMITED", 429),
        ("DRIVER_ERROR", 502),
        ("EXECUTION_TIMEOUT", 504),
    ],
)
def test_http_status_for_stable_domain_errors(error_code, expected_status):
    assert http_status_for(error_code) == expected_status


def test_error_envelope_uses_compatible_code_and_domain_error_fields():
    envelope = build_error_envelope(
        "POLICY_BLOCKED",
        message="SQL rejected by policy",
        details={"rule": "read_only"},
    )

    assert envelope == {
        "code": 409,
        "msg": "SQL rejected by policy",
        "data": {
            "errorCode": "POLICY_BLOCKED",
            "details": {"rule": "read_only"},
        },
    }


def test_error_envelope_defaults_to_safe_catalog_message_and_empty_details():
    envelope = build_error_envelope("INVALID_REQUEST")

    assert envelope["code"] == 400
    assert envelope["data"]["errorCode"] == "INVALID_REQUEST"
    assert envelope["data"]["details"] == {}
    assert envelope["msg"]


def test_error_catalog_cannot_be_mutated():
    with pytest.raises(TypeError):
        ERROR_CATALOG["INVALID_REQUEST"] = ERROR_CATALOG["POLICY_BLOCKED"]


def test_unknown_error_code_is_rejected_instead_of_guessed():
    with pytest.raises(ValueError, match="unknown SQL IDE error code"):
        http_status_for("UNRECOGNIZED_ERROR")
