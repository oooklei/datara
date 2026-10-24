"""Browser-level login and menu-route audit for the formal Datara frontend."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--username", required=True)
    password_group = parser.add_mutually_exclusive_group(required=True)
    password_group.add_argument("--password")
    password_group.add_argument("--password-file", type=Path)
    parser.add_argument("--browser", choices=("chromium", "firefox", "webkit"), default="chromium")
    args = parser.parse_args()
    password = args.password
    if args.password_file is not None:
        password = args.password_file.read_text(encoding="utf-8").strip()
    assert password is not None

    base = args.base.rstrip("/") + "/"
    failures: list[dict[str, object]] = []
    console_errors: list[str] = []
    visited: list[dict[str, object]] = []

    with sync_playwright() as playwright:
        browser = getattr(playwright, args.browser).launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 960})
        page.on(
            "response",
            lambda response: failures.append({"status": response.status, "url": response.url})
            if response.status >= 400
            else None,
        )
        page.on(
            "console",
            lambda message: console_errors.append(message.text) if message.type == "error" else None,
        )

        page.goto(urljoin(base, "login"), wait_until="networkidle")
        page.locator('input[autocomplete="username"]').fill(args.username)
        page.locator('input[autocomplete="current-password"]').fill(password)
        page.locator('button[type="submit"]').click()
        page.wait_for_url(lambda url: urlparse(url).path != "/login")
        page.locator(".app-shell").wait_for(state="visible")

        for toggle in page.locator("button.group-toggle").all():
            if toggle.get_attribute("aria-expanded") == "false":
                toggle.click()
        paths = page.locator("a.menu-link").evaluate_all(
            "links => [...new Set(links.map(link => new URL(link.href).pathname))]"
        )
        for path in paths:
            before_failures = len(failures)
            before_console = len(console_errors)
            link = page.locator(f'a.menu-link[href="{path}"]').first
            link.click()
            page.wait_for_url(lambda url, expected=str(path): urlparse(url).path == expected)
            page.wait_for_load_state("networkidle")
            shell_visible = True
            try:
                page.locator("main.app-content").wait_for(state="visible", timeout=5_000)
            except PlaywrightTimeoutError:
                shell_visible = False
            visited.append(
                {
                    "path": path,
                    "landed_path": urlparse(page.url).path,
                    "status": 200,
                    "shell_visible": shell_visible,
                    "http_failures": len(failures) - before_failures,
                    "console_errors": len(console_errors) - before_console,
                    "title": page.title(),
                }
            )
        browser.close()

    result = {
        "login": "ok",
        "route_count": len(visited),
        "visited": visited,
        "http_failures": failures,
        "console_errors": console_errors,
    }
    print(json.dumps(result, ensure_ascii=False))
    return 1 if failures or console_errors or any(
        row["status"] != 200 or not row["shell_visible"] for row in visited
    ) else 0


if __name__ == "__main__":
    raise SystemExit(main())
