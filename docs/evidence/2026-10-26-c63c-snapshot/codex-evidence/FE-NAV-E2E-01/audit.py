from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


BASE = "http://192.168.1.9:18091/"
OUT = Path("/evidence/FE-NAV-E2E-01")
KEY_PATHS = {"/", "/dag", "/dep/monitor", "/resources", "/ds/list", "/ide"}


def compact(values: list[str], limit: int = 12) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))[:limit]


def main() -> int:
    token = sys.stdin.readline().strip()
    if not token:
        raise RuntimeError("short-lived token was not supplied on stdin")
    OUT.mkdir(parents=True, exist_ok=True)
    responses: list[dict[str, object]] = []
    console_errors: list[str] = []
    page_errors: list[str] = []
    routes: list[dict[str, object]] = []
    modal_checks: list[dict[str, object]] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 960})
        context.add_init_script(
            "globalThis.__DATARA_TEST_TOKEN__ = " + json.dumps(token) + "; "
            "localStorage.removeItem('datara_token'); sessionStorage.removeItem('datara_token');"
        )
        page = context.new_page()
        page.on(
            "response",
            lambda response: responses.append(
                {"status": response.status, "method": response.request.method, "url": response.url}
            )
            if response.status >= 400
            else None,
        )
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: page_errors.append(str(error)))

        page.goto(BASE, wait_until="domcontentloaded", timeout=30_000)
        page.locator(".app-shell").wait_for(state="visible", timeout=15_000)
        for toggle in page.locator("button.group-toggle").all():
            if toggle.get_attribute("aria-expanded") == "false":
                toggle.click()
        menu = page.locator("a.menu-link").evaluate_all(
            "links => links.map(link => ({label:(link.textContent||'').trim(), path:new URL(link.href).pathname}))"
        )
        unique_menu = list({item["path"]: item for item in menu}.values())

        project_routes: list[dict[str, object]] = []
        project_cards = page.locator("[data-project-id]")
        if project_cards.count() > 0:
            project_cards.first.click()
            page.wait_for_url(lambda url: urlparse(url).path.startswith("/p/"), timeout=10_000)
            project_links = page.locator("a.project-nav-link").evaluate_all(
                "links => links.map(link => ({label:(link.textContent||'').trim(), path:new URL(link.href).pathname}))"
            )
            project_routes.append({"path": urlparse(page.url).path, "kind": "workbench"})
            for project_item in project_links:
                target = str(project_item["path"])
                before_http = len(responses)
                page.locator(f'a.project-nav-link[href="{target}"]').click()
                page.wait_for_url(lambda url, expected=target: urlparse(url).path == expected, timeout=10_000)
                project_routes.append(
                    {
                        "path": target,
                        "label": project_item["label"],
                        "empty": not bool(page.locator("main.app-content").inner_text().strip()),
                        "http_error_count": len(responses) - before_http,
                    }
                )
            page.screenshot(path=str(OUT / "project-segment.png"), full_page=True)
            page.locator("a[data-project-exit]").click()
            page.wait_for_url(lambda url: urlparse(url).path == "/", timeout=10_000)

        for item in unique_menu:
            path = str(item["path"])
            before_http = len(responses)
            before_console = len(console_errors)
            before_page = len(page_errors)
            try:
                if urlparse(page.url).path != path:
                    page.locator(f'a.menu-link[href="{path}"]').first.click()
                    page.wait_for_url(lambda url, expected=path: urlparse(url).path == expected, timeout=10_000)
                try:
                    page.wait_for_load_state("networkidle", timeout=5_000)
                except PlaywrightTimeoutError:
                    pass
                page.locator("main.app-content").wait_for(state="visible", timeout=8_000)
                time.sleep(0.35)
                buttons = compact(page.locator("button:visible").all_inner_texts())
                links = compact(page.locator("main a:visible").all_inner_texts())
                inputs = page.locator("main input:visible, main textarea:visible, main select:visible").count()
                canvases = page.locator("canvas, .vue-flow, [class*='canvas'], [class*='graph']").count()
                empty = not bool(page.locator("main.app-content").inner_text().strip())
                route_row = {
                    "label": item["label"],
                    "path": path,
                    "landed": urlparse(page.url).path,
                    "title": page.title(),
                    "buttons": buttons,
                    "links": links,
                    "input_count": inputs,
                    "canvas_count": canvases,
                    "empty": empty,
                    "http_error_count": len(responses) - before_http,
                    "console_error_count": len(console_errors) - before_console,
                    "page_error_count": len(page_errors) - before_page,
                }
                routes.append(route_row)
                if path in KEY_PATHS:
                    name = "home" if path == "/" else path.strip("/").replace("/", "-")
                    page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)

                if path in {"/resources", "/ds/list"}:
                    candidates = page.locator("button[data-view-versions]") if path == "/resources" else page.locator("button[data-create]")
                    if candidates.count() > 0:
                        candidates.first.click()
                        try:
                            dialog = page.get_by_role("dialog") if path == "/resources" else page.locator(".mask form")
                            dialog.wait_for(state="visible", timeout=5_000)
                            modal_checks.append(
                                {"path": path, "opened": True, "text": dialog.inner_text()[:240]}
                            )
                            close = dialog.get_by_role("button", name="关闭") if path == "/resources" else dialog.locator("button[data-cancel]")
                            if close.count() > 0:
                                close.first.click()
                            else:
                                page.keyboard.press("Escape")
                        except PlaywrightTimeoutError:
                            modal_checks.append({"path": path, "opened": False})
                    else:
                        modal_checks.append({"path": path, "opened": False, "reason": "no eligible row action"})
            except Exception as exc:
                routes.append({"label": item["label"], "path": path, "landed": urlparse(page.url).path, "error": str(exc)})

        storage = page.evaluate(
            "() => ({local:[...Array(localStorage.length)].map((_,i)=>localStorage.key(i)), "
            "session:[...Array(sessionStorage.length)].map((_,i)=>sessionStorage.key(i)), href:location.href})"
        )
        browser.close()

    logout = urllib.request.Request(
        urljoin(BASE, "api/v1/rebuild/logout"),
        data=b"{}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(logout, timeout=15) as response:
        logout_status = response.status

    report = {
        "ticket": "FE-NAV-E2E-01",
        "base": BASE,
        "menu_count": len(unique_menu),
        "project_routes": project_routes,
        "routes": routes,
        "modal_checks": modal_checks,
        "http_errors": responses,
        "console_errors": compact(console_errors, 30),
        "page_errors": compact(page_errors, 30),
        "security": {
            "token_in_url": token in str(storage["href"]),
            "token_in_local_storage": token in json.dumps(storage["local"]),
            "token_in_session_storage": token in json.dumps(storage["session"]),
            "storage_keys": storage,
        },
        "logout_status": logout_status,
    }
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "menu_count": len(unique_menu),
        "visited": len(routes),
        "route_errors": sum(1 for row in routes if "error" in row or row.get("empty") or row.get("landed") != row.get("path")),
        "http_errors": len(responses),
        "console_errors": len(console_errors),
        "page_errors": len(page_errors),
        "modal_checks": modal_checks,
        "security_ok": not any(
            report["security"][key]
            for key in ("token_in_url", "token_in_local_storage", "token_in_session_storage")
        ),
        "logout_status": logout_status,
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
