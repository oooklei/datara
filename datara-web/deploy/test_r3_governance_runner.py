from pathlib import Path


DEPLOY = Path(__file__).parent
RUNNER = (DEPLOY / "r3-governance-control-smoke.cjs").read_text(encoding="utf-8")
LAUNCHER = (DEPLOY / "run-r3-governance-control-smoke.ps1").read_text(encoding="utf-8")


def test_runner_is_pinned_to_approved_origin_and_governance_page():
    assert "http://192.168.1.9:18091" in RUNNER
    assert "/rebuild-validation-r3.html" in RUNNER
    assert "192.168.1.9:18091" in LAUNCHER
    assert "8090" not in RUNNER + LAUNCHER


def test_runner_bootstraps_token_only_in_memory_and_never_persists_it():
    assert "X-Backend-Validation-Key" in RUNNER
    assert "addInitScript" in RUNNER
    assert "localStorage" not in RUNNER
    assert "sessionStorage" not in RUNNER
    assert "writeFile" in RUNNER
    assert "validationKey," not in RUNNER
    assert "token," not in RUNNER
    assert "REBUILD_VALIDATION_KEY" in LAUNCHER
    assert "Remove-Item Env:DATARA_REBUILD_VALIDATION_KEY" in LAUNCHER


def test_runner_drives_catalog_governance_and_real_negative_conflict_controls():
    for control in (
        "#projectSelect",
        "#addAsset",
        "#assetSchema",
        "#addTag",
        "#addRule",
        "#assetLineage",
        "#addStandard",
        "#addMetric",
        "#assetAudit",
        "#logout",
    ):
        assert control in RUNNER
    assert "duplicate-standard-conflict-shown-as-real-409" in RUNNER
    assert "duplicate-standard-conflict-is-backend-409" in RUNNER
    assert "expectedConflictWindow && /409 \\(Conflict\\)/.test(message.text())" in RUNNER
    assert "quality-history-is-real-empty-state-not-fabricated" in RUNNER
    assert "getByText('asset.create', { exact: true }).first().waitFor" in RUNNER
    assert "rendered_text: auditText" in RUNNER
    assert "getByText('尚无真实运行记录', { exact: false }).waitFor" in RUNNER
    assert "rendered_text: qualityText" in RUNNER
    assert "DATARA_R3_PROJECT_ID" in RUNNER
    assert "project.name.startsWith('R3 governance validation ')" in RUNNER


def test_runner_confirms_legacy_quality_route_is_retired_from_same_browser_origin():
    assert "fetch('/api/v1/qc/rules')" in RUNNER
    assert "legacy-quality-api-retired" in RUNNER
    assert "retiredQcStatus === 404" in RUNNER
    assert "expectedRetiredQc404Window && /404 \\(Not Found\\)/.test(message.text())" in RUNNER
