from types import SimpleNamespace

from rebuild.governance.legacy_migration_service import i18_import_matches_approved_scope


def _approved_plan(**overrides):
    counts = {
        "create": 44,
        "unchanged": 0,
        "skipped": 1,
        "conflict": 0,
        "blocked": 0,
    }
    counts.update(overrides)
    entries = [SimpleNamespace(disposition="create") for _ in range(44)]
    entries.append(
        SimpleNamespace(
            source_table="t_dw_model_version",
            source_id="1",
            disposition="skipped",
            disposition_reason="approved_missing_model_reference",
        )
    )
    return SimpleNamespace(project_id=3, source_count=45, counts=counts, entries=entries)


def test_i18_import_scope_accepts_only_the_user_approved_project_and_plan():
    assert i18_import_matches_approved_scope(3, _approved_plan())


def test_i18_import_scope_rejects_other_projects_and_count_changes():
    assert not i18_import_matches_approved_scope(4, _approved_plan())
    assert not i18_import_matches_approved_scope(3, _approved_plan(create=43, blocked=1))
    assert not i18_import_matches_approved_scope(3, _approved_plan(unchanged=1))


def test_i18_import_scope_requires_the_approved_orphan_skip_identity_and_reason():
    plan = _approved_plan()
    plan.entries[-1].source_id = "2"
    assert not i18_import_matches_approved_scope(3, plan)

    plan = _approved_plan()
    plan.entries[-1].disposition_reason = "different-reason"
    assert not i18_import_matches_approved_scope(3, plan)
