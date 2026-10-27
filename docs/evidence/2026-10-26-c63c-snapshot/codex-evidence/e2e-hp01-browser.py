"""E2E-HP-01: formal-browser verification for pinned SQL/Python/Shell resources."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright


FILES = {
    "sql_ui_task": ("ui-bound.sql", b"select 20261025 as ui_resource_value"),
    "python_ui_task": ("ui-bound.py", b"print('ui-resource-python')"),
    "shell_ui_task": ("ui-bound.sh", b"printf ui-resource-shell"),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    args = parser.parse_args()
    token = args.token_file.read_text(encoding="utf-8").strip()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    args.artifact_dir.mkdir(parents=True, exist_ok=True)
    request_failures: list[dict[str, object]] = []
    console_errors: list[str] = []
    binding_statuses: list[int] = []
    token_in_url = False
    selected_versions: dict[str, str] = {}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1050})
        context.add_init_script(f"globalThis.__DATARA_TEST_TOKEN__ = {json.dumps(token)}")
        page = context.new_page()

        def on_request(request):
            nonlocal token_in_url
            if token and token in request.url:
                token_in_url = True

        def on_response(response):
            if "/rebuild/resources/bindings" in response.url:
                binding_statuses.append(response.status)
            if response.status >= 400:
                request_failures.append({"status": response.status, "path": urlparse(response.url).path})

        page.on("request", on_request)
        page.on("response", on_response)
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)

        target = f"{args.base.rstrip('/')}/p/{fixture['project_id']}/dag?doc={fixture['workflow_id']}"
        page.goto(target, wait_until="networkidle")
        page.screenshot(path=args.artifact_dir / "landing.png", full_page=True)
        try:
            page.locator("[data-tc-canvas-workbench]").wait_for(state="visible", timeout=20_000)
        except PlaywrightTimeoutError:
            print(json.dumps({
                "status": "FAIL_LANDING",
                "url_path": urlparse(page.url).path,
                "title": page.title(),
                "body": page.locator("body").inner_text()[:500],
                "http_failures": request_failures,
                "console_errors": console_errors,
            }, ensure_ascii=False, separators=(",", ":")))
            return 2
        page.locator(".vue-flow__node").first.wait_for(state="visible", timeout=20_000)

        for task_id, (filename, content) in FILES.items():
            node = page.locator(".vue-flow__node", has_text=task_id).first
            diagnostics = node.evaluate("""el => {
                const r = el.getBoundingClientRect(); const hit = document.elementFromPoint(r.x + r.width/2, r.y + r.height/2);
                const style = getComputedStyle(el);
                return {box:{x:r.x,y:r.y,width:r.width,height:r.height},pointerEvents:style.pointerEvents,
                    visibility:style.visibility,opacity:style.opacity,hitClass:hit?.className ?? '',hitTag:hit?.tagName ?? ''};
            }""")
            print(json.dumps({"phase": "select-node", "task": task_id, **diagnostics}, separators=(",", ":")))
            node.scroll_into_view_if_needed()
            node.dispatch_event("click")
            editor = page.locator("[data-script-resource-editor]")
            try:
                editor.wait_for(state="visible", timeout=5_000)
            except PlaywrightTimeoutError:
                page.screenshot(path=args.artifact_dir / f"select-{task_id}.png", full_page=True)
                print(json.dumps({
                    "status": "FAIL_NODE_SELECT",
                    "task": task_id,
                    "node_class": node.get_attribute("class"),
                    "node_text": node.inner_text(),
                }, ensure_ascii=False, separators=(",", ":")))
                return 3
            editor.locator("[data-source-mode]").select_option("resource")
            editor.locator("[data-resource-upload]").set_input_files(
                {"name": filename, "mimeType": "text/plain", "buffer": content}
            )
            editor.get_by_role("status").wait_for(state="visible", timeout=20_000)
            version = editor.locator("[data-version-select]").input_value()
            if not version.isdigit() or int(version) <= 0:
                raise AssertionError(f"{task_id} did not select an explicit version")
            selected_versions[task_id] = version
            editor.locator("[data-bind-resource]").click()
            editor.get_by_role("status").filter(has_text="已绑定资源").wait_for(state="visible", timeout=20_000)

        page.get_by_role("button", name="保存", exact=True).click()
        page.wait_for_timeout(500)
        page.screenshot(path=args.artifact_dir / "resource-bindings.png", full_page=True)

        page.reload(wait_until="networkidle")
        page.locator("[data-tc-canvas-workbench]").wait_for(state="visible", timeout=20_000)
        persisted = 0
        for task_id, expected_version in selected_versions.items():
            page.locator(".vue-flow__node", has_text=task_id).first.click(force=True)
            editor = page.locator("[data-script-resource-editor]")
            editor.wait_for(state="visible")
            if editor.locator("[data-source-mode]").input_value() != "resource":
                raise AssertionError(f"{task_id} source mode did not persist")
            editor.locator("[data-version-select]").wait_for(state="visible")
            page.wait_for_function(
                "el => el.value !== ''", editor.locator("[data-version-select]").element_handle(), timeout=10_000
            )
            if editor.locator("[data-version-select]").input_value() != expected_version:
                raise AssertionError(f"{task_id} pinned version did not persist")
            persisted += 1

        storage = page.evaluate(
            "() => ({localToken: localStorage.getItem('datara_token'), sessionToken: sessionStorage.getItem('datara_token')})"
        )
        browser.close()

    result = {
        "status": "PASS",
        "project_id": fixture["project_id"],
        "workflow_id": fixture["workflow_id"],
        "nodes_verified": len(selected_versions),
        "persisted_after_reload": persisted,
        "binding_http_statuses": binding_statuses,
        "explicit_versions": selected_versions,
        "http_failures": request_failures,
        "console_errors": console_errors,
        "token_in_url": token_in_url,
        "persistent_token": storage,
    }
    if binding_statuses != [200, 200, 200] or request_failures or console_errors or token_in_url:
        result["status"] = "FAIL"
    if storage != {"localToken": None, "sessionToken": None}:
        result["status"] = "FAIL"
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
