from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

PAGE = Path(__file__).resolve().parents[1] / "public" / "rebuild-validation-r3-s9-i20.html"
RUNNER = Path(__file__).parent / "r3-s9-i20-preview.cjs"


class Controls(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.inputs: list[tuple[str, str]] = []
        self.buttons: list[str] = []
        self.in_button = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if element_id := values.get("id"):
            self.ids.append(element_id)
        if tag == "input":
            self.inputs.append((values.get("type", "text") or "text", values.get("id", "") or ""))
        if tag == "button":
            self.in_button = True
            self.buttons.append("")

    def handle_data(self, data: str) -> None:
        if self.in_button:
            self.buttons[-1] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "button":
            self.in_button = False


def test_i20_page_has_project_selector_and_metric_version_preview_controls():
    html = PAGE.read_text(encoding="utf-8")
    controls = Controls()
    controls.feed(html)
    assert {"projectSelect", "runPreview", "reloadProjects", "sourceRows", "previewRows", "issueList"} <= set(
        controls.ids
    )
    assert 'data-testid="run-preview"' in html
    assert "/api/v1/rebuild/projects" in html
    assert "/legacy/i20/mapping-preview" in html
    assert "t_indicator" in html and "t_indicator_version" in html
    assert len(controls.ids) == len(set(controls.ids))


def test_i20_page_is_read_only_and_does_not_render_source_payloads():
    html = PAGE.read_text(encoding="utf-8").lower()
    controls = Controls()
    controls.feed(html)
    assert "__datara_test_token__" in html
    assert "x-backend-validation-key" not in html
    assert "localstorage" not in html and "sessionstorage" not in html
    assert not any(name.lower() in {"username", "password", "login"} for _, name in controls.inputs)
    assert not any(any(word in label for word in ("导入", "迁移", "写入", "发布")) for label in controls.buttons)
    assert "parity 未验证" in html
    assert "不会回显" in html
    for secret in ("private_metric_code", "private business definition", "private formula"):
        assert secret not in html


def test_i20_runner_drives_the_deployed_page_and_records_safe_evidence():
    runner = RUNNER.read_text(encoding="utf-8")
    assert "http://192.168.1.9:18091" in runner
    assert "rebuild-validation-r3-s9-i20.html" in runner
    assert "DATARA_REBUILD_VALIDATION_KEY" in runner
    assert "validation-token" in runner
    assert "addInitScript" in runner and "__DATARA_TEST_TOKEN__" in runner
    assert "getByTestId('run-preview').click()" in runner
    assert "parity_verified" in runner and "import_enabled" in runner
    assert "no-browser-errors" in runner
    assert "writeFile(reportPath" in runner and "screenshot" in runner
    assert "private_metric_code" in runner
    assert "item.payload_columns_absent" in runner
    assert "localStorage" not in runner and "sessionStorage" not in runner
