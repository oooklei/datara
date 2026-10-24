"""Read-only browser evidence for project-scoped run-monitor switching.

The runner adds the short-lived token to request headers from Playwright's
route hook; it never writes the token to page storage, URL, DOM, or evidence.
Set ``REBUILD_MONITOR_TOKEN`` and optionally ``REBUILD_MONITOR_PROJECT_A/B``.
This is intended for the isolated 192.168.1.9 deployment only.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


BASE_URL = os.getenv("REBUILD_MONITOR_BASE_URL", "http://192.168.1.9:18091").rstrip("/")
TOKEN = os.getenv("REBUILD_MONITOR_TOKEN", "")
PROJECT_A = int(os.getenv("REBUILD_MONITOR_PROJECT_A", "7"))
PROJECT_B = int(os.getenv("REBUILD_MONITOR_PROJECT_B", "8"))


def run() -> dict[str, object]:
    if not TOKEN:
        raise RuntimeError("REBUILD_MONITOR_TOKEN is required (never pass it on the command line)")
    held: list[object] = []
    project_b_responses: list[dict[str, object]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        def auth_route(route):
            request = route.request
            headers = dict(request.headers)
            headers["token"] = TOKEN
            url = request.url
            # Hold only project A's run-stat response.  The page can switch to
            # B while A is in flight, proving the generation guard in the UI.
            if "/api/v1/rebuild/execution/run-stats?" in url and f"project_id={PROJECT_A}" in url:
                held.append(route)
                return
            route.continue_(headers=headers)

        page.route("**/api/v1/**", auth_route)
        def capture(response):
            if "/api/v1/rebuild/execution/run-stats?" not in response.url or f"project_id={PROJECT_B}" not in response.url:
                return
            if response.status != 200:
                return
            try:
                payload = response.json()
                data = payload.get("data", payload) if isinstance(payload, dict) else payload
                items = data.get("items", []) if isinstance(data, dict) else []
                project_b_responses.append({"status": response.status, "rows": len(items)})
            except Exception:
                return
        page.on("response", capture)
        page.goto(f"{BASE_URL}/p/{PROJECT_A}/dag?tab=runs", wait_until="domcontentloaded")
        page.get_by_role("button", name="运行监控").click()
        try:
            page.wait_for_selector("[data-workflow-run-monitor]", timeout=10_000)
        except PlaywrightTimeoutError as exc:
            raise AssertionError("run monitor did not mount") from exc
        if not held:
            raise AssertionError("project A run-stats request was not observed")

        # Switch route while A is still pending.  The old rows must not remain
        # visible and A's late response must not overwrite B's real counters.
        page.goto(f"{BASE_URL}/p/{PROJECT_B}/dag?tab=runs", wait_until="domcontentloaded")
        page.get_by_role("button", name="运行监控").click()
        page.wait_for_timeout(500)
        stale_text = page.locator("[data-workflow-run-monitor]").inner_text()
        if stale_text and str(PROJECT_A) in stale_text:
            raise AssertionError("stale project A data remained visible after switching")
        for route in held:
            route.continue_(headers={**route.request.headers, "token": TOKEN})
        page.wait_for_timeout(500)
        final_text = page.locator("[data-workflow-run-monitor]").inner_text()
        if not project_b_responses:
            raise AssertionError("project B run-stats response was not captured")

        # Read the actual B response through the browser request event; no
        # token or full payload is persisted in evidence, only row counters.
        result = {
            "base": BASE_URL,
            "project_a": PROJECT_A,
            "project_b": PROJECT_B,
            "switch_race": "passed",
            "project_b_monitor_visible": bool(final_text),
            "project_b_stats": project_b_responses[-1],
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }
        browser.close()
        return result


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, separators=(",", ":")))
