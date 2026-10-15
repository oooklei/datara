from pathlib import Path


PAGE = Path(__file__).resolve().parents[1] / "public" / "rebuild-validation-r3-s9-i23.html"


def test_i23_preview_page_is_isolated_and_uses_only_runtime_injected_scoped_token():
    page = PAGE.read_text(encoding="utf-8")

    assert "window.__DATARA_I23_CAPABILITY__" in page
    assert "/api/v1/rebuild/governance/legacy/i23/identity-preview" in page
    assert "projectSelect" not in page
    assert "X-Backend-Validation-Key" not in page
    assert "localStorage" not in page
    assert "sessionStorage" not in page
    assert "user_pwd" not in page
    assert "password_hash" not in page
    assert "data-testid=\"run-preview\"" in page
    assert "data-testid=\"identity-rows\"" in page


def test_i23_preview_page_has_no_import_or_account_mutation_controls():
    page = PAGE.read_text(encoding="utf-8")
    lower = page.lower()

    assert "type=\"password\"" not in lower
    assert "create-user" not in lower
    assert "update-user" not in lower
    assert "import-button" not in lower
    assert "parity_verified=false" in page
    assert "import_enabled=false" in page
