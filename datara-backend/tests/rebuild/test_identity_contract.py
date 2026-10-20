from rebuild.identity.contracts import Permission, Role, TokenService, authorize
from rebuild.identity.passwords import hash_password, verify_password


def test_token_service_round_trip_preserves_user_context():
    service = TokenService(secret="i1-test-secret", ttl_seconds=60)

    token = service.issue(user_id=7, username="dev", role=Role.DEVELOPER)

    assert service.verify(token) == {"user_id": 7, "username": "dev", "role": "developer"}


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
    assert authorize(Role.DEVELOPER, Permission.RUN_INSTANCE) is True
    assert authorize(Role.DEVELOPER, Permission.MANAGE_USER) is False


def test_password_hash_is_not_reversible_and_verifies():
    encoded = hash_password("unit-test-password")

    assert encoded != "unit-test-password"
    assert verify_password("unit-test-password", encoded) is True
    assert verify_password("wrong", encoded) is False


def test_role_permission_matrix_is_explicit_and_consistent():
    all_perms = set(Permission)
    expected = {
        Role.ADMIN: all_perms,
        Role.DEVELOPER: {
            Permission.EDIT_DEFINITION, Permission.RUN_INSTANCE, Permission.VIEW_ALL, Permission.EXECUTE_SQL,
            Permission.PROJECT_READ, Permission.PROJECT_WRITE,
            Permission.WORKFLOW_READ, Permission.WORKFLOW_WRITE, Permission.WORKFLOW_PUBLISH,
            Permission.WORKFLOW_RUN, Permission.WORKFLOW_DELETE,
            Permission.TASK_READ, Permission.TASK_WRITE, Permission.TASK_RUN,
            Permission.DATASOURCE_READ, Permission.DATASOURCE_USE, Permission.DATASOURCE_MANAGE,
            Permission.SQL_READ, Permission.SQL_WRITE_DDL,
            Permission.SCHEDULE_READ, Permission.SCHEDULE_MANAGE,
            Permission.LINEAGE_READ,
            Permission.QUALITY_READ, Permission.QUALITY_WRITE, Permission.QUALITY_RUN,
            Permission.STANDARD_READ, Permission.STANDARD_WRITE, Permission.STANDARD_APPROVE,
            Permission.SECURITY_READ, Permission.SECURITY_MANAGE,
            Permission.AUDIT_READ,
        },
        Role.OPERATOR: {
            Permission.RUN_INSTANCE, Permission.VIEW_ALL, Permission.EXECUTE_SQL,
            Permission.PROJECT_READ,
            Permission.WORKFLOW_READ, Permission.WORKFLOW_RUN,
            Permission.TASK_READ, Permission.TASK_RUN,
            Permission.DATASOURCE_READ, Permission.DATASOURCE_USE,
            Permission.SQL_READ,
            Permission.SCHEDULE_READ,
            Permission.LINEAGE_READ,
            Permission.QUALITY_READ, Permission.QUALITY_RUN,
            Permission.STANDARD_READ,
            Permission.AUDIT_READ,
        },
        Role.VIEWER: {
            Permission.VIEW_ALL,
            Permission.PROJECT_READ,
            Permission.WORKFLOW_READ,
            Permission.TASK_READ,
            Permission.DATASOURCE_READ,
            Permission.SQL_READ,
            Permission.SCHEDULE_READ,
            Permission.LINEAGE_READ,
            Permission.QUALITY_READ,
            Permission.STANDARD_READ,
        },
    }
    for role, expected_permissions in expected.items():
        for permission in Permission:
            assert authorize(role, permission) is (permission in expected_permissions)
