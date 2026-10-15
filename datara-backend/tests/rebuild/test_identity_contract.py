from rebuild.identity.contracts import Permission, Role, TokenService, authorize
from rebuild.identity.passwords import hash_password, verify_password


def test_token_service_round_trip_preserves_user_context():
    service = TokenService(secret="i1-test-secret", ttl_seconds=60)

    token = service.issue(user_id=7, username="dev", role=Role.DEV)

    assert service.verify(token) == {"user_id": 7, "username": "dev", "role": "dev"}


def test_scoped_token_round_trip_preserves_exact_endpoint_capability():
    service = TokenService(secret="i1-test-secret", ttl_seconds=900)

    token = service.issue(
        user_id=0,
        username="validation-runner",
        role=Role.VIEWER,
        capability="legacy:i23:preview",
    )

    assert service.verify(token) == {
        "user_id": 0,
        "username": "validation-runner",
        "role": "viewer",
        "capability": "legacy:i23:preview",
    }


def test_viewer_cannot_edit_definition():
    assert authorize(Role.VIEWER, Permission.EDIT_DEFINITION) is False


def test_developer_can_run_instance_but_cannot_manage_users():
    assert authorize(Role.DEV, Permission.RUN_INSTANCE) is True
    assert authorize(Role.DEV, Permission.MANAGE_USER) is False


def test_password_hash_is_not_reversible_and_verifies():
    encoded = hash_password("unit-test-password")

    assert encoded != "unit-test-password"
    assert verify_password("unit-test-password", encoded) is True
    assert verify_password("wrong", encoded) is False
