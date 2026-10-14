from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

PAGE = Path(__file__).parents[1] / "public" / "rebuild-validation-r3-s9-i22.html"
RUNNER = Path(__file__).parent / "r3-s9-i22-preview.cjs"
LAUNCHER = Path(__file__).parent / "run-r3-s9-i22-preview.ps1"


class PageControls(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.inputs: list[tuple[str, str]] = []
        self.button_depth = 0
        self.button_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if element_id := values.get("id"):
            self.ids.append(element_id)
        if tag == "input":
            self.inputs.append((values.get("type", "text") or "text", values.get("id", "") or ""))
        if tag == "button":
            self.button_depth += 1
            self.button_text.append("")

    def handle_data(self, data: str) -> None:
        if self.button_depth:
            self.button_text[-1] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "button" and self.button_depth:
            self.button_depth -= 1


def test_i22_preview_page_exposes_project_scope_and_operable_controls():
    html = PAGE.read_text(encoding="utf-8")
    controls = PageControls()
    controls.feed(html)
    assert {"projectSelect", "runPreview", "reloadProjects", "domainRows", "previewRows", "issueList"} <= set(
        controls.ids
    )
    assert 'data-testid="run-preview"' in html
    assert "/api/v1/rebuild/projects" in html
    assert "/legacy/i22/mapping-preview" in html
    assert "已载入" in html
    assert "不会写入任何业务表" in html
    assert len(controls.ids) == len(set(controls.ids))


def test_i22_page_keeps_validation_key_out_of_html_and_has_no_import_or_login_form():
    html = PAGE.read_text(encoding="utf-8").lower()
    controls = PageControls()
    controls.feed(html)
    assert "__datara_test_token__" in html
    assert "x-backend-validation-key" not in html
    assert "rebuild_validation_key" not in html
    assert "localstorage" not in html
    assert "sessionstorage" not in html
    assert not any(name.lower() in {"username", "password", "login"} for _, name in controls.inputs)
    assert not any("导入" in label or "迁移" in label for label in controls.button_text)
    assert "parity" in html
    assert "import_enabled" not in html


def test_i22_runner_uses_protected_key_and_exercises_real_page_controls():
    runner = RUNNER.read_text(encoding="utf-8")
    launcher = LAUNCHER.read_text(encoding="utf-8")
    assert "http://192.168.1.9:18091" in runner
    assert "rebuild-validation-r3-s9-i22.html" in runner
    assert "DATARA_REBUILD_VALIDATION_KEY" in runner
    assert "validation-token" in runner
    assert "addInitScript" in runner and "__DATARA_TEST_TOKEN__" in runner
    assert "getByTestId('run-preview').click()" in runner
    assert "parity_verified" in runner and "import_enabled" in runner
    assert "blocked-row-and-reason-rendered" in runner
    assert "writeFile(reportPath" in runner and "screenshot" in runner
    assert "Remove-Item Env:DATARA_REBUILD_VALIDATION_KEY" in launcher
    assert "localStorage" not in runner and "sessionStorage" not in runner
