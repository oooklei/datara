#!/usr/bin/env python3
"""Minimal deployed UI proof for the persistent ecommerce demo project."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18091")
    parser.add_argument("--project-id", type=int, default=33)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--executable-path", type=Path)
    parser.add_argument("--screenshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    key = args.key_file.read_text(encoding="utf-8").strip()
    token = requests.post(
        f"{base}/api/v1/rebuild/validation-token",
        headers={"X-Backend-Validation-Key": key, "X-Backend-Validation-Scope": "high-priority-e2e"},
        json={}, timeout=30,
    ).json()["data"]["token"]
    expected = ["电商订单离线加工样例", "电商订单同步入仓样例", "电商实时订单流观摩样例"]
    console_errors: list[str] = []
    workflow_responses: list[dict[str, object]] = []
    target = f"{base}/#/"
    result: dict[str, object]
    try:
        page = None
        with sync_playwright() as playwright:
            launch: dict[str, object] = {"headless": True, "args": ["--no-sandbox"]}
            if args.executable_path:
                launch["executable_path"] = str(args.executable_path)
            browser = playwright.chromium.launch(**launch)
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
            page.on("response", lambda response: workflow_responses.append({
                "url": response.url, "status": response.status, "body": response.text()[:2000],
            }) if "/rebuild/workflows" in response.url and response.request.method == "GET" else None)
            page.add_init_script(f"globalThis.__DATARA_TEST_TOKEN__ = {json.dumps(token)};")
            page.goto(target, wait_until="networkidle", timeout=30_000)
            page.locator(f'[data-project-id="{args.project_id}"]').click()
            page.locator('[data-nav="dag"]').wait_for(timeout=15_000)
            page.locator('[data-nav="dag"]').click()
            body = page.locator("body")
            workflow_tab = page.locator(".wb-palette:visible .pal-tab").nth(1)
            workflow_tab.click()
            for name in expected:
                page.locator(f'.wb-palette:visible .pt-name[title="{name}"]').first.wait_for(state="attached", timeout=15_000)
            folded_headers = page.locator(".wb-palette:visible .pal-cat.fold > .pal-cat-head")
            while folded_headers.count() > 0:
                folded_headers.first.click()
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(args.screenshot), full_page=True)
            visible = [name for name in expected if page.locator(f'.wb-palette:visible .pt-name[title="{name}"]:visible').count()]
            browser.close()
        result = {
            "url": target,
            "visible_workflows": visible,
            "workflow_responses": workflow_responses,
            "console_error_count": len(console_errors),
            "console_errors": console_errors,
            "verdict": "PASS" if visible == expected and not console_errors else "FAIL",
        }
    except Exception as error:
        result = {"url": target, "error": str(error), "console_errors": console_errors, "verdict": "FAIL"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"VERDICT: {result['verdict']} visible={len(result.get('visible_workflows', []))} console_errors={len(console_errors)}")
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
