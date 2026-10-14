from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path


PAGE = Path(__file__).parents[1] / "public" / "rebuild-validation-r3.html"


class Controls(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.inputs: list[tuple[str, str]] = []
        self.buttons: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if element_id := values.get("id"):
            self.ids.add(element_id)
        if tag == "input":
            self.inputs.append((values.get("type", "text"), values.get("id", "")))
        if tag == "button":
            self.buttons.append(values.get("id", ""))


def test_governance_page_uses_catalog_and_asset_detail_information_architecture():
    html = PAGE.read_text(encoding="utf-8")
    controls = Controls()
    controls.feed(html)

    assert {"assetSearch", "assetType", "assetDomain", "assetTag", "assetTable"} <= controls.ids
    assert {"assetOverview", "assetSchema", "assetLineage", "assetQuality", "assetGovernance", "assetAudit"} <= controls.ids
    assert 'aria-label="资产目录"' in html and 'id="assetDetail"' in html


def test_governance_page_has_no_human_login_or_embedded_validation_key():
    html = PAGE.read_text(encoding="utf-8").lower()
    controls = Controls()
    controls.feed(html)

    assert not any(element_id in {"username", "password", "login"} for _, element_id in controls.inputs)
    assert "x-backend-validation-key" not in html
    assert "rebuild_validation_key" not in html
    assert "localstorage" not in html
    assert "sessionstorage" not in html
    assert "__datara_test_token__" in html


def test_governance_actions_call_real_r3_routes_not_static_success_data():
    html = PAGE.read_text(encoding="utf-8").lower()

    assert "/api/v1/rebuild/governance/projects/" in html
    for route_part in ("/assets", "/lineage", "/quality-rules", "/quality-runs", "/standards", "/metrics", "/audit"):
        assert route_part in html
    assert "quality_runs" not in html
    assert "static_success" not in html


def test_asset_creation_form_can_open_without_a_selected_asset():
    html = PAGE.read_text(encoding="utf-8")

    assert "external_id:`manual:${state.selected?.id??'unselected'}:to:`" in html


def test_each_new_modal_resets_submit_button_after_previous_submission():
    html = PAGE.read_text(encoding="utf-8")

    assert "function showForm(kind) {\n    const form=$('modalForm'), fields=$('formFields'); fields.innerHTML='';\n    $('submitModal').disabled=false;" in html
