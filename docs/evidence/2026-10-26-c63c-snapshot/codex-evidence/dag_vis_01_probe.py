from __future__ import annotations

import json
import os
import time
from urllib.request import Request, urlopen

from playwright.sync_api import sync_playwright


WEB = os.getenv("WEB_BASE", "http://127.0.0.1:18111")
API = WEB


def issue_token() -> str:
    request = Request(
        API + "/api/v1/rebuild/validation-token",
        data=b"{}",
        headers={
            "Content-Type": "application/json",
            "X-Backend-Validation-Key": os.environ["REBUILD_VALIDATION_KEY"],
            "X-Backend-Validation-Scope": "high-priority-e2e",
        },
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        return json.load(response)["data"]["token"]


def api(path: str, token: str, method: str = "GET", body=None):
    payload = None if body is None else json.dumps(body).encode()
    request = Request(
        API + path,
        data=payload,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        method=method,
    )
    with urlopen(request, timeout=10) as response:
        payload = json.load(response)
    return payload.get("data", payload)


def rows(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("list", "items", "rows"):
            if isinstance(value.get(key), list):
                return value[key]
    return []


def box(page, selector: str):
    locator = page.locator(selector).first
    if not locator.count():
        return None
    return locator.evaluate(
        """element => {
          const rect = element.getBoundingClientRect()
          const style = getComputedStyle(element)
          return {x: rect.x, y: rect.y, width: rect.width, height: rect.height,
                  display: style.display, visibility: style.visibility,
                  overflow: style.overflow, transform: style.transform}
        }"""
    )


token = issue_token()
stamp = time.strftime("%Y%m%d%H%M%S")
specs = api("/api/v1/rebuild/components/spec?workflow_type=NORMAL", token)
versions = {item["type"]: item["publishedVersion"] for item in specs["items"]}
project = api("/api/v1/rebuild/projects", token, "POST", {"name": f"dag-vis-01-{stamp}"})
project_id = int(project["id"])
workflow = api("/api/v1/rebuild/workflows", token, "POST", {
    "project_id": project_id,
    "name": f"dag-visible-{stamp}",
    "workflow_type": "NORMAL",
})
definition_id = int(workflow["definition_id"])
for index, kind in enumerate(("sql", "python", "shell")):
    api(f"/api/v1/rebuild/workflows/{definition_id}/nodes", token, "POST", {
        "project_id": project_id,
        "node_code": f"{kind}_task",
        "node_type": kind,
        "component_ref": {"type": kind, "version": versions[kind]},
        "params": {"sourceMode": "inline", "sql" if kind == "sql" else "script": "select 1" if kind == "sql" else "print(1)"},
        "position_x": 80 + index * 240,
        "position_y": 120,
    })
with sync_playwright() as playwright:
    browser = playwright.firefox.launch(headless=True)
    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    context.add_init_script(
        "Object.defineProperty(window, '__DATARA_TEST_TOKEN__', "
        f"{{value: {json.dumps(token)}, writable: false, configurable: false}})"
    )
    page = context.new_page()
    page.goto(WEB + f"/p/{project_id}/dag", wait_until="networkidle")
    select_all = page.locator(".pal-all input").last
    if select_all.count():
        select_all.check()
        page.wait_for_timeout(100)
        button = page.locator("button.pal-load")
        button.click()
        page.locator(".wf-workbench").wait_for(timeout=12_000)
    page.wait_for_timeout(500)
    selectors = [
        ".app-content", ".tc", ".tc-body", ".tc-canvas", ".wf-workbench",
        ".wf-toolbar", ".wf-flow", ".vue-flow", ".vue-flow__viewport",
        ".vue-flow__node",
    ]
    report = {selector: box(page, selector) for selector in selectors}
    report["node_count"] = page.locator(".vue-flow__node").count()
    report["pal_count"] = page.locator(".pal-task").count()
    report["checkbox_count"] = page.locator('.pal-task input[type="checkbox"]').count()
    report["load_button_count"] = page.locator("button.pal-load").count()
    report["body_tail"] = page.locator("body").inner_text()[-500:]
    report["row_html"] = page.locator(".pal-task").first.evaluate("e => e.outerHTML")[:1000] if page.locator(".pal-task").count() else ""
    report["forms"] = {}
    nodes = page.locator(".vue-flow__node")
    for index in range(nodes.count()):
        node = nodes.nth(index)
        label = node.inner_text().lower()
        node.click(force=True)
        page.wait_for_timeout(50)
        report["forms"][label] = page.locator("[data-script-resource-editor]").is_visible()
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    browser.close()
