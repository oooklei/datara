#!/usr/bin/env python3
"""Capture the deployed stream observation panel with a short-lived token."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from playwright.sync_api import sync_playwright


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18091")
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--workflow-id", type=int, required=True)
    parser.add_argument("--job-id", type=int, required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--executable-path", type=Path)
    parser.add_argument("--screenshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    key = args.key_file.read_text(encoding="utf-8").strip()
    response = requests.post(
        f"{args.base_url.rstrip('/')}/api/v1/rebuild/validation-token",
        headers={
            "X-Backend-Validation-Key": key,
            "X-Backend-Validation-Scope": "high-priority-e2e",
            "Content-Type": "application/json",
        },
        json={},
        timeout=30,
    )
    response.raise_for_status()
    envelope = response.json()
    if envelope.get("code") != 0:
        raise RuntimeError(f"validation-token failed: {envelope.get('msg')}")
    token = envelope["data"]["token"]

    target = (
        f"{args.base_url.rstrip('/')}/#/p/{args.project_id}/dag"
        f"?doc={args.workflow_id}&tab=edit"
    )
    console_errors: list[str] = []
    result: dict[str, Any]
    args.screenshot.parent.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as playwright:
            launch_options: dict[str, Any] = {"headless": True, "args": ["--no-sandbox"]}
            if args.executable_path is not None:
                launch_options["executable_path"] = str(args.executable_path)
            browser = playwright.chromium.launch(**launch_options)
            context = browser.new_context(viewport={"width": 1600, "height": 1000})
            page = context.new_page()
            page.on(
                "console",
                lambda message: console_errors.append(message.text)
                if message.type == "error"
                else None,
            )
            page.add_init_script(
                f"globalThis.__DATARA_TEST_TOKEN__ = {json.dumps(token)};"
            )
            try:
                page.goto(target, wait_until="domcontentloaded", timeout=30_000)
                panel = page.locator("[data-stream-observation]")
                panel.wait_for(state="visible", timeout=30_000)
                panel.locator("[data-stream-job-id]").fill(str(args.job_id))
                panel.locator("header button").click()
                metrics = panel.locator("[data-stream-metrics]")
                metrics.wait_for(state="visible", timeout=30_000)
                panel_text = panel.inner_text()
                required = ["流处理观摩", "实时速率", "当前偏移", "成功", "恢复事件"]
                missing = [label for label in required if label not in panel_text]
                if missing:
                    raise RuntimeError(f"stream panel missing labels: {missing}")
                panel.screenshot(path=str(args.screenshot))
            except Exception as exc:
                page.screenshot(path=str(args.screenshot), full_page=True)
                body_text = page.locator("body").inner_text()[:800]
                raise RuntimeError(f"{exc}; page_url={page.url}; body={body_text!r}") from exc
            result = {
                "ticket": "F-STREAM-REAL-E2E-01",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "url": page.url,
                "project_id": args.project_id,
                "workflow_id": args.workflow_id,
                "job_id": args.job_id,
                "panel_excerpt": panel_text[:1200],
                "console_error_count": len(console_errors),
                "console_errors": console_errors[:5],
                "screenshot": str(args.screenshot),
                "verdict": "PASS",
            }
            browser.close()
    except Exception as exc:
        result = {
            "ticket": "F-STREAM-REAL-E2E-01",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "url": target,
            "project_id": args.project_id,
            "workflow_id": args.workflow_id,
            "job_id": args.job_id,
            "console_errors": console_errors[:5],
            "error": str(exc),
            "verdict": "FAIL",
        }
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"VERDICT: FAIL - {exc}")
        return 1

    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"VERDICT: PASS url={result['url']} console_errors={len(console_errors)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
