from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://192.168.1.9:18091"
OUT = Path("/evidence")
PROJECT_ID = 27


def require(condition: object, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def http(url: str, *, method: str = "GET", headers: dict[str, str] | None = None, data: bytes | None = None):
    request = urllib.request.Request(url, method=method, headers=headers or {}, data=data)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {
        "ticket": "FORMAL-E2E-03",
        "baseUrl": BASE,
        "deployedImage": "ba17df2",
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "checks": {},
        "relevantResponses": [],
        "consoleErrors": [],
        "verdict": "FAIL",
    }
    token = ""
    key = os.environ.get("REBUILD_VALIDATION_KEY", "").strip()
    browser = None
    try:
        require(key, "controlled runtime validation key is unavailable")
        status, raw = http(
            f"{BASE}/api/v1/rebuild/validation-token",
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Backend-Validation-Key": key,
                "X-Backend-Validation-Scope": "high-priority-e2e",
            },
            data=b"{}",
        )
        payload = json.loads(raw)
        token = str(payload.get("data", {}).get("token", ""))
        require(status == 200 and token, f"validation token exchange failed: {status}")
        require(payload["data"].get("expires_in") == 900, "validation token TTL is not 900 seconds")
        report["checks"]["tokenExchange"] = {
            "status": status,
            "expiresIn": payload["data"]["expires_in"],
            "scope": "high-priority-e2e",
            "principal": payload["data"]["user"]["username"],
            "injection": "add_init_script + request-header route; memory only",
        }

        with sync_playwright() as pw:
            browser = pw.firefox.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            context.add_init_script(
                script="Object.defineProperty(globalThis, '__DATARA_TEST_TOKEN__', {"
                f"value: {json.dumps(token)}, writable: true, configurable: true}})"
            )

            def route_handler(route):
                headers = dict(route.request.headers)
                headers["token"] = token
                route.continue_(headers=headers)

            context.route("**/api/v1/**", route_handler)
            page = context.new_page()

            def console_handler(message):
                if message.type == "error":
                    report["consoleErrors"].append(message.text[:300])

            def response_handler(response):
                if re.search(r"run-stats|monitor/nodes|workflows|workflow/definitions", response.url):
                    parsed = urllib.parse.urlsplit(response.url)
                    report["relevantResponses"].append({"path": parsed.path + (f"?{parsed.query}" if parsed.query else ""), "status": response.status})

            import urllib.parse

            page.on("console", console_handler)
            page.on("response", response_handler)

            page.goto(f"{BASE}/login", wait_until="networkidle")
            login_inputs = page.locator("input").evaluate_all(
                """els => els.map(el => ({type: el.getAttribute('type') || 'text',
                name: el.getAttribute('name') || '', placeholder: el.getAttribute('placeholder') || ''}))"""
            )
            credential_inputs = [
                item for item in login_inputs
                if item["type"] == "password" or re.search(r"user|account|账号|password|密码", f"{item['name']} {item['placeholder']}", re.I)
            ]
            require(not credential_inputs, "login page exposes account/password inputs")
            report["checks"]["login"] = {"url": page.url, "inputCount": len(login_inputs), "credentialInputCount": 0}
            page.screenshot(path=str(OUT / "01-login.png"), full_page=True)

            page.goto(f"{BASE}/p/{PROJECT_ID}/dag", wait_until="networkidle")
            page.locator("[data-tc-body]").wait_for(state="visible", timeout=15_000)
            first_task = page.locator(".pal-task:visible").first
            require(first_task.count(), "project 27 has no visible workflow candidate")
            first_task.click()
            page.locator(".pal-load").click()
            page.locator("[data-tc-canvas-workbench]").first.wait_for(state="visible", timeout=15_000)
            page.locator(".vue-flow__node").first.wait_for(state="visible", timeout=15_000)
            initial_nodes = page.locator(".vue-flow__node:visible").count()
            require(initial_nodes > 0, "workflow canvas has no visible nodes")

            editors = {}
            for item in (
                ("sql", re.compile("SQL", re.I), "[data-node-parameter-editor]"),
                ("python", re.compile("Python", re.I), "[data-node-parameter-editor]"),
                ("shell", re.compile("Shell", re.I), "[data-node-parameter-editor]"),
                ("dependency", re.compile("依赖|Dependent", re.I), "[data-dependent-editor]"),
            ):
                name, label, editor = item
                tray = page.locator(".wf-tray button:visible").filter(has_text=label).first
                require(tray.count(), f"{name} component entry is absent")
                before = page.locator(".vue-flow__node").count()
                tray.click()
                page.wait_for_function("n => document.querySelectorAll('.vue-flow__node').length > n", arg=before)
                page.locator(".vue-flow__node").last.click()
                page.locator(editor).wait_for(state="visible", timeout=5_000)
                editors[name] = {"trayLabel": tray.inner_text().strip(), "editorVisible": True}
            report["checks"]["canvas"] = {"projectId": PROJECT_ID, "initialVisibleNodes": initial_nodes, "editors": editors}
            page.screenshot(path=str(OUT / "02-workflow-canvas.png"), full_page=True)

            with page.expect_response(lambda r: "/execution/run-stats" in r.url and f"project_id={PROJECT_ID}" in r.url, timeout=15_000) as response_info:
                page.goto(f"{BASE}/p/{PROJECT_ID}/dag?tab=runs", wait_until="domcontentloaded")
            run_response = response_info.value
            page.locator("[data-workflow-run-monitor]").wait_for(state="visible", timeout=15_000)
            run_errors = page.locator("[data-run-error]").count()
            require(run_response.status != 500, "project 27 run-stats API returned 500")
            require(run_response.ok and run_errors == 0, f"project 27 monitor failed: HTTP {run_response.status}")
            report["checks"]["project27Monitor"] = {"apiStatus": run_response.status, "pageVisible": True, "pageErrorCount": run_errors}
            page.screenshot(path=str(OUT / "03-project27-monitor.png"), full_page=True)

            with page.expect_response(lambda r: "/rebuild/monitor/nodes" in r.url, timeout=15_000) as response_info:
                page.goto(f"{BASE}/dep/monitor", wait_until="domcontentloaded")
            cluster_response = response_info.value
            page.locator(".monitor-page").wait_for(state="visible", timeout=15_000)
            require(cluster_response.status != 500 and cluster_response.ok, f"cluster monitor API failed: {cluster_response.status}")
            report["checks"]["clusterMonitor"] = {"apiStatus": cluster_response.status, "pageVisible": True}

            page.set_viewport_size({"width": 375, "height": 812})
            page.goto(f"{BASE}/p/{PROJECT_ID}/dag?tab=runs", wait_until="networkidle")
            overflow = page.evaluate("""() => ({viewport: innerWidth,
              htmlWidth: document.documentElement.scrollWidth, bodyWidth: document.body.scrollWidth,
              overflow: document.documentElement.scrollWidth > innerWidth || document.body.scrollWidth > innerWidth})""")
            require(not overflow["overflow"], f"375px page-level horizontal overflow: {overflow}")
            logout = page.locator("[data-shell-logout]")
            require(logout.is_visible(), "logout button is not visible at 375px")
            report["checks"]["mobile375"] = overflow
            report["checks"]["logoutButton"] = {"visible": True, "text": logout.inner_text().strip()}
            page.screenshot(path=str(OUT / "04-mobile-375.png"), full_page=True)

            storage = page.evaluate("""() => ({localKeys: Object.keys(localStorage), sessionKeys: Object.keys(sessionStorage),
              dataraTokenLocal: localStorage.getItem('datara_token'), dataraTokenSession: sessionStorage.getItem('datara_token'),
              runtimeInjectionPresent: Object.prototype.hasOwnProperty.call(globalThis, '__DATARA_TEST_TOKEN__')})""")
            require(storage["dataraTokenLocal"] is None and storage["dataraTokenSession"] is None, "token found in browser persistence")
            script_urls = page.locator("script[src]").evaluate_all("els => els.map(el => el.src)")
            static_hit = False
            for script_url in script_urls:
                _, body = http(script_url)
                static_hit = static_hit or token.encode() in body or key.encode() in body
            require(not static_hit, "token/key found in loaded static artifacts")
            require(token not in page.url and key not in page.url, "token/key found in URL")
            report["checks"]["secretHygiene"] = {
                "tokenInLocalStorage": False, "tokenInSessionStorage": False, "tokenInUrl": False,
                "keyInUrl": False, "staticArtifactSecretHit": False,
                "runtimeInjectionConsumed": not storage["runtimeInjectionPresent"],
            }

            with page.expect_url(re.compile(r"/login$"), timeout=15_000):
                logout.click()
            revoked_status, _ = http(f"{BASE}/api/v1/rebuild/projects", headers={"token": token})
            require(revoked_status == 401, f"revoked token returned HTTP {revoked_status}")
            report["checks"]["logout"] = {"redirectedTo": urllib.parse.urlsplit(page.url).path, "revokedTokenStatus": revoked_status}
            page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
            page.screenshot(path=str(OUT / "05-logout.png"), full_page=True)
            report["verdict"] = "PASS"
    except Exception as exc:
        report["error"] = str(exc)
    finally:
        token = ""
        key = ""
        if browser is not None:
            browser.close()
        (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
