from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


BASE = os.getenv("BASE_URL", "http://127.0.0.1:18091").rstrip("/")
TOKEN_PATH = Path(os.getenv("TOKEN_PATH", "/evidence/e2e-hp02-token.json"))
OUT = Path(os.getenv("EVIDENCE_DIR", "/evidence"))


def api(path: str, token: str):
    req = Request(BASE + path, headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
    with urlopen(req, timeout=10) as response:
        body = json.load(response)
    return body.get("data", body)


def rows(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("list", "items", "rows"):
            if isinstance(value.get(key), list):
                return value[key]
    return []


def visible(page, selector: str, timeout: int = 8_000) -> bool:
    try:
        page.locator(selector).first.wait_for(state="visible", timeout=timeout)
        return True
    except PlaywrightTimeoutError:
        return False


token_envelope = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
token_data = token_envelope.get("data", token_envelope)
token = token_data["token"]
report = {
    "ticket": "E2E-HP-02",
    "base": BASE,
    "token": {"transport": "window-memory-only", "expires_in": token_data.get("expires_in")},
    "checks": {},
    "network_failures": [],
    "console_errors": [],
    "api_errors": [],
}

projects = rows(api("/api/v1/rebuild/projects", token))
workflow_sets = []
for project in projects:
    pid = project.get("id")
    try:
        workflows = rows(api(f"/api/v1/rebuild/workflows?project_id={pid}", token))
    except (HTTPError, OSError, ValueError) as exc:
        report["api_errors"].append({"project_id": pid, "endpoint": "workflows", "error": type(exc).__name__})
        continue
    if workflows:
        workflow_sets.append((project, workflows))

selected_project = (workflow_sets[0][0] if workflow_sets else (projects[0] if projects else None))
selected_workflows = workflow_sets[0][1] if workflow_sets else []
for project, workflows in workflow_sets:
    if any((w.get("workflow_type") or w.get("workflowType")) == "STREAM" for w in workflows):
        selected_project, selected_workflows = project, workflows
        break

pid = selected_project.get("id") if selected_project else None
stream_workflow = next(
    (w for w in selected_workflows if (w.get("workflow_type") or w.get("workflowType")) == "STREAM"),
    None,
)
script_workflow = next(
    (w for w in selected_workflows if (w.get("workflow_type") or w.get("workflowType")) != "STREAM"),
    selected_workflows[0] if selected_workflows else None,
)
report["fixture"] = {
    "project_id": pid,
    "workflow_count": len(selected_workflows),
    "stream_workflow_id": stream_workflow.get("id") if stream_workflow else None,
    "script_workflow_id": script_workflow.get("id") if script_workflow else None,
}

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)

    anonymous = browser.new_context(viewport={"width": 1440, "height": 960})
    login = anonymous.new_page()
    login.goto(BASE + "/login", wait_until="networkidle")
    report["checks"]["login_page"] = {
        "path": login.url.split(BASE, 1)[-1],
        "heading": login.locator("h1").first.inner_text() if login.locator("h1").count() else "",
        "username": login.locator('input[autocomplete="username"]').count() == 1,
        "password": login.locator('input[autocomplete="current-password"]').count() == 1,
        "submit": login.locator('button[type="submit"]').count() == 1,
    }
    login.screenshot(path=str(OUT / "e2e-hp02-login.png"), full_page=True)
    anonymous.close()

    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    context.add_init_script(
        "Object.defineProperty(window, '__DATARA_TEST_TOKEN__', "
        f"{{value: {json.dumps(token)}, writable: false, configurable: false}})"
    )
    page = context.new_page()
    page.on("console", lambda msg: report["console_errors"].append(msg.text) if msg.type == "error" else None)
    page.on(
        "response",
        lambda response: report["network_failures"].append({"status": response.status, "url": response.url.split("?", 1)[0]})
        if response.status >= 400
        else None,
    )

    page.goto(BASE + "/", wait_until="networkidle")
    report["checks"]["authenticated_shell"] = visible(page, ".app-shell") and "/login" not in page.url

    if pid is not None:
        page.goto(f"{BASE}/p/{pid}/dag", wait_until="networkidle")
        dag = {
            "task_center": visible(page, "[data-tc-tabs]"),
            "canvas": False,
            "node_count": 0,
            "resource_form": False,
            "resource_version_select": False,
        }
        target = stream_workflow or script_workflow
        if target and page.locator(".pal-task").count():
            name = str(target.get("name") or "")
            row = page.locator(".pal-task", has_text=name).first
            if row.count():
                row.click()
                load_button = page.locator("button.pal-load")
                if load_button.is_disabled() and row.locator('input[type="checkbox"]').count():
                    row.locator('input[type="checkbox"]').click(force=True)
                if not load_button.is_disabled():
                    load_button.click()
                    visible(page, ".wf-workbench", 12_000)
                else:
                    dag["load_blocker"] = "workflow row did not enter picked state"
        dag["canvas"] = visible(page, ".vue-flow", 5_000)
        dag["node_count"] = page.locator(".vue-flow__node").count()
        for i in range(dag["node_count"]):
            node = page.locator(".vue-flow__node").nth(i)
            try:
                node.click()
                if visible(page, "[data-script-resource-editor]", 800):
                    dag["resource_form"] = True
                    dag["resource_version_select"] = page.locator("[data-version-select]").count() == 1
                    break
            except Exception:
                continue
        report["checks"]["task_center_dag"] = dag
        report["checks"]["stream_observation"] = {
            "workflow_loaded": stream_workflow is not None,
            "panel": page.locator("[data-stream-observation]").count() == 1,
            "produce": page.locator("[data-stream-produce]").count() == 1,
            "fuse": page.locator("[data-stream-fuse-submit]").count() == 1,
            "metrics": page.locator("[data-stream-metrics]").count() == 1,
        }
        page.screenshot(path=str(OUT / "e2e-hp02-dag-stream.png"), full_page=True)

        page.locator('[data-tab="runs"]').click()
        page.wait_for_timeout(500)
        report["checks"]["run_monitor"] = {
            "tab_active": "on" in (page.locator('[data-tab="runs"]').get_attribute("class") or ""),
            "table_or_state": page.locator("[data-run-empty], [data-run-error], table").count() > 0,
            "rows": page.locator("table tbody tr").count(),
        }
        page.screenshot(path=str(OUT / "e2e-hp02-run-monitor.png"), full_page=True)

        page.goto(f"{BASE}/p/{pid}/resources", wait_until="networkidle")
        report["checks"]["resource_management"] = {
            "heading": page.locator("h1", has_text="资源管理").count() == 1,
            "kind": page.locator('select[aria-label="Upload resource type"]').count() == 1,
            "upload": page.locator('input[type="file"]').count() == 1,
            "table": page.locator("table").count() == 1,
            "rows": page.locator("table tbody tr").count(),
        }
        page.screenshot(path=str(OUT / "e2e-hp02-resources.png"), full_page=True)

    storage = page.evaluate(
        """token => ({
          localKeys: Object.keys(localStorage),
          sessionKeys: Object.keys(sessionStorage),
          localContainsToken: Object.values(localStorage).some(value => value === token || String(value).includes(token)),
          sessionContainsToken: Object.values(sessionStorage).some(value => value === token || String(value).includes(token)),
          urlContainsToken: location.href.includes(token),
        })""",
        token,
    )
    report["checks"]["token_hygiene"] = storage
    context.close()
    browser.close()

del token

required = [
    report["checks"].get("authenticated_shell") is True,
    all(report["checks"].get("login_page", {}).get(k) for k in ("username", "password", "submit")),
    report["checks"].get("task_center_dag", {}).get("task_center") is True,
    report["checks"].get("run_monitor", {}).get("table_or_state") is True,
    report["checks"].get("resource_management", {}).get("upload") is True,
    not report["checks"].get("token_hygiene", {}).get("localContainsToken", True),
    not report["checks"].get("token_hygiene", {}).get("sessionContainsToken", True),
    not report["checks"].get("token_hygiene", {}).get("urlContainsToken", True),
]
report["verdict"] = "PASS" if all(required) else "FAIL"
(OUT / "e2e-hp02-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"verdict": report["verdict"], "project_id": pid, "checks": report["checks"]}, ensure_ascii=False, separators=(",", ":")))
