from datetime import datetime
from types import SimpleNamespace

from rebuild.governance.legacy_i23_mapping import (
    I23IdentityTarget,
    LegacyI23MappingContext,
    map_i23_snapshot,
)


def _row(**overrides):
    values = {
        "id": 1,
        "user_name": "analyst-a",
        "user_role": "operator",
        "state": "enabled",
        "create_time": "2026-10-01T10:00:00",
        "update_time": "2026-10-02T10:00:00",
    }
    values.update(overrides)
    return values


def _snapshot(*rows):
    return SimpleNamespace(schema="datara_meta", rows={"t_user": tuple(rows)})


def _context(**overrides):
    values = {
        "target_users": {
            "1": I23IdentityTarget(user_id=101, username="analyst-a", role="operator", status="enabled")
        }
    }
    values.update(overrides)
    return LegacyI23MappingContext(**values)


def test_i23_mapper_preserves_explicit_user_identity_and_role_without_credentials():
    mapped = map_i23_snapshot(_snapshot(_row()), _context())

    assert mapped.ready_to_import
    assert len(mapped.rows) == 1
    record = mapped.rows[0]
    assert record.target_table == "rebuild_governance_legacy_identity_mapping"
    assert record.values == {
        "user_id": 101,
        "source_username": "analyst-a",
        "source_role": "operator",
        "mapped_role": "operator",
        "mapping_status": "mapped",
        "source_created_at": datetime(2026, 10, 1, 10),
        "source_updated_at": datetime(2026, 10, 2, 10),
    }
    assert "password" not in repr(record.values).lower()
    assert record.source_id == "1"


def test_i23_mapper_empty_snapshot_is_ready():
    mapped = map_i23_snapshot(_snapshot(), _context(target_users={}))

    assert mapped.ready_to_import
    assert mapped.rows == ()
    assert mapped.mapping_issues == ()


def test_i23_mapper_blocks_missing_and_non_equivalent_target_users():
    missing = map_i23_snapshot(_snapshot(_row()), _context(target_users={}))
    mismatched = map_i23_snapshot(
        _snapshot(_row()),
        _context(
            target_users={
                "1": I23IdentityTarget(user_id=101, username="different", role="developer", status="disabled")
            }
        ),
    )

    assert not missing.ready_to_import
    assert "unresolved_target_user" in {issue.code for issue in missing.mapping_issues}
    assert not mismatched.ready_to_import
    assert {issue.code for issue in mismatched.mapping_issues} >= {
        "target_username_mismatch",
        "target_role_mismatch",
        "target_status_mismatch",
    }


def test_i23_mapper_rejects_unknown_roles_states_duplicate_users_and_invalid_ids():
    mapped = map_i23_snapshot(
        _snapshot(
            _row(id=0),
            _row(id=1),
            _row(id=2, user_name="unknown", user_role="root"),
            _row(id=3, user_name="bad-state", state="locked"),
            _row(id=4, user_name="analyst-a"),
        ),
        _context(
            target_users={
                "1": I23IdentityTarget(user_id=101, username="analyst-a", role="operator", status="enabled"),
                "2": I23IdentityTarget(user_id=102, username="unknown", role="operator", status="enabled"),
                "3": I23IdentityTarget(user_id=103, username="bad-state", role="viewer", status="enabled"),
                "4": I23IdentityTarget(user_id=101, username="analyst-a", role="operator", status="enabled"),
            }
        ),
    )

    codes = {issue.code for issue in mapped.mapping_issues}
    assert "invalid_source_identity" in codes
    assert "unsupported_legacy_role" in codes
    assert "unsupported_legacy_state" in codes
    assert "duplicate_target_user_binding" in codes
    assert not mapped.ready_to_import


def test_i23_mapper_requires_complete_source_shape_and_valid_timestamps():
    bad_shape = map_i23_snapshot(SimpleNamespace(schema="datara_meta", rows={"t_user": ({"id": 1},)}), _context())
    bad_time = map_i23_snapshot(
        _snapshot(_row(create_time="2026-10-01")),
        _context(),
    )

    assert "incomplete_source_row" in {issue.code for issue in bad_shape.mapping_issues}
    assert "invalid_source_value" in {issue.code for issue in bad_time.mapping_issues}
    assert not bad_time.ready_to_import
