from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

PAGE = Path(__file__).resolve().parents[1] / "public" / "rebuild-validation-r3-s9-i21.html"
RUNNER = Path(__file__).parent / "r3-s9-i21-preview.cjs"


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


def test_i21_page_has_project_selector_and_six_table_mapping_controls():
    html = PAGE.read_text(encoding="utf-8")
    controls = Controls()
    controls.feed(html)
    assert {"projectSelect", "runPreview", "reloadProjects", "sourceRows", "previewRows", "issueList"} <= set(
        controls.ids
    )
    assert "taskRuleLinkCount" in controls.ids
    assert 'data-testid="run-preview"' in html
    assert "/api/v1/rebuild/projects" in html
    assert "/legacy/i21/mapping-preview" in html
    for table in ("t_qc_rule", "t_qc_task", "t_qc_run", "t_qc_exception", "t_qc_report", "t_qc_alarm_policy"):
        assert table in html
    assert len(controls.ids) == len(set(controls.ids))


def test_i21_page_does_not_ask_for_login_or_offer_mutations_or_expose_payload():
    html = PAGE.read_text(encoding="utf-8").lower()
    controls = Controls()
    controls.feed(html)
    assert "__datara_test_token__" in html
    assert "x-backend-validation-key" not in html
    assert "localstorage" not in html and "sessionstorage" not in html
    assert not any(name.lower() in {"username", "password", "login"} for _, name in controls.inputs)
    assert not any(any(word in label for word in ("导入", "迁移", "写入", "发布")) for label in controls.buttons)
    assert "parity 未验证" in html
    assert "不显示规则参数、sql、统计 json、报告内容或备注" in html


def test_i21_runner_drives_real_page_and_records_safe_control_evidence():
    runner = RUNNER.read_text(encoding="utf-8")
    assert "http://192.168.1.9:18091" in runner
    assert "rebuild-validation-r3-s9-i21.html" in runner
    assert "DATARA_REBUILD_VALIDATION_KEY" in runner
    assert "validation-token" in runner
    assert "addInitScript" in runner and "__DATARA_TEST_TOKEN__" in runner
    assert "getByTestId('run-preview').click()" in runner
    assert "all-six-i21-source-tables-rendered" in runner
    assert "parity_verified" in runner and "import_enabled" in runner
    assert "target-task-rule-links-rendered" in runner
    assert "no-browser-errors" in runner
    assert "writeFile(reportPath" in runner and "screenshot" in runner
    assert "source_payload_recorded: false" in runner
    assert "target_writes_authorized: false" in runner
    assert "localStorage" not in runner and "sessionStorage" not in runner
