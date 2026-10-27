import json
import os
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright


API = os.environ.get("DATARA_API_BASE", "http://127.0.0.1:18098")
WEB = os.environ.get("DATARA_WEB_BASE", "http://127.0.0.1:18101")
ROUTE = os.environ.get("DATARA_ROUTE", "/p/3/dag")
OUT = Path(os.environ.get("DATARA_EVIDENCE_DIR", "/evidence"))


def issue_token() -> str:
    request = urllib.request.Request(
        API + "/api/v1/rebuild/validation-token",
        data=b"{}",
        headers={
            "Content-Type": "application/json",
            "X-Backend-Validation-Key": os.environ["REBUILD_VALIDATION_KEY"],
            "X-Backend-Validation-Scope": "high-priority-e2e",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.load(response)
    return payload["data"]["token"]


token = issue_token()
OUT.mkdir(parents=True, exist_ok=True)
with sync_playwright() as playwright:
    browser = playwright.firefox.launch(headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    page.add_init_script(
        "window.__DATARA_TEST_TOKEN__ = " + json.dumps(token) + ";"
    )
    page.goto(WEB + ROUTE, wait_until="networkidle", timeout=30000)
    checks = page.locator('input[type="checkbox"]')
    if checks.count() > 1:
        checks.nth(1).check()
        page.get_by_role("button", name="载入选中 (1)").click()
        page.wait_for_load_state("networkidle")
    nodes = page.locator(".vue-flow__node")
    node_results = []
    for index in range(nodes.count()):
        node = nodes.nth(index)
        label = node.inner_text()
        node.click()
        editor = page.locator("[data-script-resource-editor]")
        if editor.count():
            node_results.append({
                "node": label,
                "modeOptions": editor.locator("[data-source-mode] option").all_inner_texts(),
                "resourceModeVisible": editor.locator("[data-source-mode]").is_visible(),
            })
    page.screenshot(path=str(OUT / "resource-browser-dag.png"), full_page=True)
    report = {
        "url": page.url,
        "title": page.title(),
        "body": page.locator("body").inner_text()[:6000],
        "buttons": page.locator("button").all_inner_texts(),
        "links": page.locator("a").all_inner_texts(),
        "nodes": node_results,
        "injectedTokenOnly": page.evaluate(
            "() => Boolean(window.__DATARA_TEST_TOKEN__) && !localStorage.getItem('datara_token')"
        ),
    }
    (OUT / "resource-browser-dag.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    browser.close()

print(json.dumps({
    "status": "PASS",
    "url": report["url"],
    "buttonCount": len(report["buttons"]),
    "scriptEditors": len(report["nodes"]),
    "injectedTokenOnly": report["injectedTokenOnly"],
}, ensure_ascii=False))
