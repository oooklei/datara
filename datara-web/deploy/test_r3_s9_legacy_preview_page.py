from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path


PAGE = Path(__file__).parents[1] / "public" / "rebuild-validation-r3-s9.html"
RUNNER = Path(__file__).parent / "r3-s9-i18-preview.cjs"
LAUNCHER = Path(__file__).parent / "run-r3-s9-i18-preview.ps1"


class PageControls(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.inputs: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if element_id := values.get("id"):
            self.ids.append(element_id)
        if tag == "input":
            self.inputs.append((values.get("type", "text"), values.get("id", "")))


def test_i18_preview_page_has_prepopulated_project_and_operable_preview_controls():
    html = PAGE.read_text(encoding="utf-8")
    controls = PageControls()
    controls.feed(html)

    assert {"projectSelect", "runDryRun", "reloadProjects", "planRows", "issueList", "importOrder"} <= set(
        controls.ids
    )
    assert 'data-testid="run-dry-run"' in html
    assert "已载入" in html and "result.list[0]?.id" in html
    assert "请先选择目标项目并执行只读预检" in html
    assert "不写入任何目标业务表" in html
    assert len(controls.ids) == len(set(controls.ids))


def test_i18_preview_page_uses_short_lived_injected_token_without_login_or_key_storage():
    html = PAGE.read_text(encoding="utf-8").lower()
    controls = PageControls()

    controls.feed(html)
    assert "__datara_test_token__" in html
    assert "x-backend-validation-key" not in html
    assert "rebuild_validation_key" not in html
    assert "localstorage" not in html
    assert "sessionstorage" not in html
    assert not any(name in {"username", "password", "login"} for _, name in controls.inputs)


def test_i18_preview_page_calls_actual_read_only_dry_run_contract_and_renders_response_fields():
    html = PAGE.read_text(encoding="utf-8")

    assert "/api/v1/rebuild/projects" in html
    assert "/legacy/i18/dry-run" in html
    for contract_field in (
        "source.counts",
        "source.digest",
        "target.identity_count",
        "plan.counts",
        "plan.entries",
        "plan.import_order",
        "plan.issues",
    ):
        assert contract_field in html


def test_i18_runner_uses_protected_runtime_key_and_real_page_controls():
    runner = RUNNER.read_text(encoding="utf-8")
    launcher = LAUNCHER.read_text(encoding="utf-8")

    assert "http://192.168.1.9:18091" in runner and "rebuild-validation-r3-s9.html" in runner
    assert "DATARA_REBUILD_VALIDATION_KEY" in runner and "validation-token" in runner
    assert "addInitScript" in runner and "__DATARA_TEST_TOKEN__" in runner
    assert "getByTestId('run-dry-run').click()" in runner
    assert "writeFile(reportPath" in runner and "screenshot" in runner
    assert "REBUILD_VALIDATION_KEY" in launcher
    assert "Remove-Item Env:DATARA_REBUILD_VALIDATION_KEY" in launcher
    assert "localStorage" not in runner and "sessionStorage" not in runner
