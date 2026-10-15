"""Control-level R2-12-B verification against the deployed 1.9 runtime."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
from tools.verify_r2_12_a import BASE_URL, api, load_fixture, project_id  # noqa: E402

EVIDENCE = ROOT / "docs" / "increments" / "evidence" / "R2"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()
    key = os.getenv("REBUILD_VALIDATION_KEY", "")
    schema = os.getenv("REBUILD_R2_METADATA_SCHEMA", "")
    object_name = os.getenv("REBUILD_R2_METADATA_OBJECT", "")
    if not key or not schema or not object_name:
        print("REMOTE_CONTROL_GATE=BLOCKED_REQUIRED_VALIDATION_INPUT_MISSING")
        return 2
    try:
        fixture = load_fixture()
    except RuntimeError as exc:
        print(f"REMOTE_CONTROL_GATE=BLOCKED_SAFE_FIXTURE: {exc}")
        return 2

    status, auth = api(
        "POST", "/validation-token", body={}, extra_headers={"X-Backend-Validation-Key": key}
    )
    token = auth.get("data", {}).get("token", "") if status == 200 else ""
    if not token:
        print(f"REMOTE_CONTROL_GATE=BLOCKED_VALIDATION_TOKEN_HTTP_{status}")
        return 2

    run_id = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("r2-12-b-%Y%m%d%H%M%S")
    primary_project = project_id(token, "r2-12-b-validation-fixture")
    other_project = project_id(token, "r2-12-b-isolation-fixture")
    profile_name = f"r2-12-b-profile-{run_id[-6:]}"
    datasource_id = None
    cleanup_ok = False
    responses: list[dict[str, object]] = []
    actions: list[dict[str, object]] = []
    assertions: list[dict[str, object]] = []
    page_errors: list[str] = []
    console_errors: list[str] = []
    failed_requests: list[str] = []
    expected_console_errors: list[str] = []
    screenshot = EVIDENCE / f"{run_id}.png"
    report_path = EVIDENCE / f"{run_id}.json"
    result = "FAIL"
    page = None
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    profile = {
        "name": profile_name,
        "kind": fixture["kind"],
        "host": fixture["host"],
        "port": fixture["port"],
        "database": fixture["database"],
        "username": fixture["username"],
        "password": fixture["password"],
    }
    created_status, created_payload = api(
        "POST", f"/projects/{primary_project}/datasources", token=token, body=profile
    )
    if created_status != 201:
        print(f"REMOTE_CONTROL_GATE=BLOCKED_PROFILE_SETUP_HTTP_{created_status}")
        return 2
    datasource_id = int(created_payload["data"]["id"])
    url = (
        f"{BASE_URL}/rebuild-validation-r2-12-b.html?projectId={primary_project}"
        f"&datasourceId={datasource_id}"
    )

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=args.headless)
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            context.add_init_script(
                "sessionStorage.setItem('rebuild.validation.token', " + json.dumps(token) + ");"
            )
            page = context.new_page()
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.on(
                "console",
                lambda message: console_errors.append(message.text) if message.type == "error" else None,
            )
            page.on(
                "requestfailed",
                lambda request: failed_requests.append(f"{request.method} {request.url.split('?')[0]}"),
            )
            page.on(
                "response",
                lambda response: responses.append(
                    {"status": response.status, "method": response.request.method,
                     "path": response.url.split("/api/v1/rebuild", 1)[-1].split("?", 1)[0]}
                ) if "/api/v1/rebuild/" in response.url else None,
            )

            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.get_by_role("heading", name="项目数据源 · Schema / 对象浏览").wait_for()
            assertions.append({"name": "validation-page-loaded", "passed": True})

            page.get_by_role("button", name="加载 Schema").click()
            page.get_by_role("button", name=f"▸ {schema}").wait_for(timeout=15000)
            actions.append({"action": "load schemas through explorer control", "http_status": 200})
            assertions.append({"name": "schema-visible-in-tree", "passed": True})

            page.get_by_role("button", name=f"▸ {schema}").click()
            object_button = page.locator(f'button[data-object="{object_name}"]')
            object_button.wait_for(timeout=15000)
            actions.append({"action": "expand schema and load tables/views", "http_status": 200})
            assertions.append({"name": "table-or-view-visible-in-tree", "passed": True})

            object_button.click()
            page.get_by_role("button", name="查看列定义").click()
            page.locator("#column-rows tr").first.wait_for(timeout=15000)
            column_rows = page.locator("#column-rows tr")
            if column_rows.count() != 2:
                raise AssertionError(f"expected two fixture columns, got {column_rows.count()}")
            order_id_cells = column_rows.nth(0).locator("td")
            amount_cells = column_rows.nth(1).locator("td")
            observed_columns = [order_id_cells.all_text_contents(), amount_cells.all_text_contents()]
            expected_columns = [
                ["order_id", "bigint", "否", "是", ""],
                ["amount", "decimal(10,2)", "否", "否", "amount in analytics"],
            ]
            if observed_columns != expected_columns:
                raise AssertionError(f"column metadata mismatch: {observed_columns}")
            identity = page.locator("#object-identity").input_value()
            if identity != f"{schema}.{object_name}":
                raise AssertionError(f"schema-qualified object identity mismatch: {identity}")
            actions.append({"action": "select qualified table and load column definition", "http_status": 200})
            assertions.append({"name": "qualified-identity-types-nullability-primary-key-and-comments", "passed": True})

            view_button = page.locator('button[data-schema="analytics"][data-object="orders_view"]')
            view_button.click()
            if page.locator("#object-identity").input_value() != "analytics.orders_view":
                raise AssertionError("view identity was not schema-qualified")
            actions.append({"action": "select view from schema tree", "http_status": 200})
            assertions.append({"name": "view-is-distinguished-from-table", "passed": True})

            page.get_by_role("button", name="▸ shared").click()
            shared_orders = page.locator('button[data-schema="shared"][data-object="orders"]')
            shared_orders.wait_for(timeout=15000)
            shared_orders.click()
            page.get_by_role("button", name="查看列定义").click()
            shared_rows = page.locator("#column-rows tr")
            shared_rows.first.wait_for(timeout=15000)
            shared_observed = [
                shared_rows.nth(0).locator("td").all_text_contents(),
                shared_rows.nth(1).locator("td").all_text_contents(),
            ]
            shared_expected = [
                ["order_id", "varchar(36)", "否", "是", ""],
                ["event_time", "datetime", "是", "否", "event timestamp in shared"],
            ]
            if page.locator("#object-identity").input_value() != "shared.orders":
                raise AssertionError("same-named object lost its shared schema identity")
            if shared_observed != shared_expected:
                raise AssertionError(f"shared.orders metadata mismatch: {shared_observed}")
            actions.append({"action": "select same-named table from second schema", "http_status": 200})
            assertions.append({"name": "same-name-objects-remain-schema-distinct", "passed": True})
            page.screenshot(path=str(screenshot), full_page=True)

            console_count_before_isolation = len(console_errors)
            page.goto(
                f"{BASE_URL}/rebuild-validation-r2-12-b.html?projectId={other_project}"
                f"&datasourceId={datasource_id}", wait_until="domcontentloaded"
            )
            page.get_by_role("button", name="加载 Schema").click()
            page.get_by_role("status").filter(has_text="Schema 读取失败").wait_for(timeout=10000)
            if not any(item["status"] == 404 for item in responses):
                raise AssertionError("cross-project profile lookup did not return HTTP 404")
            expected_console_errors.extend(
                message
                for message in console_errors[console_count_before_isolation:]
                if "status of 404" in message
            )
            actions.append({"action": "attempt cross-project datasource browse", "http_status": 404})
            assertions.append({"name": "cross-project-profile-isolation", "passed": True})

            unexpected_console_errors = [
                message for message in console_errors if message not in expected_console_errors
            ]
            result = "PASS" if not page_errors and not unexpected_console_errors and not failed_requests else "PARTIAL"
            context.close()
            browser.close()
    except Exception as exc:  # preserve a failure artifact for every attempted run
        page_errors.append(f"validation failure: {type(exc).__name__}: {exc}")
        if page is not None:
            try:
                page.screenshot(path=str(screenshot), full_page=True)
            except Exception:
                pass

    delete_status, _ = api("DELETE", f"/projects/{primary_project}/datasources/{datasource_id}", token=token)
    cleanup_ok = delete_status == 200
    if not cleanup_ok and result == "PASS":
        result = "PARTIAL"
    report = {
        "run_id": run_id,
        "timestamp": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "timezone": "Asia/Shanghai",
        "url": url,
        "browser": "Chromium via Playwright",
        "actions": actions,
        "assertions": assertions,
        "responses": responses,
        "page_errors": page_errors,
        "console_errors": console_errors,
        "expected_console_errors": expected_console_errors,
        "failed_requests": failed_requests,
        "cleanup": {"datasource_profile_deleted": cleanup_ok},
        "screenshot": screenshot.name if screenshot.exists() else None,
        "result": result,
        "notes": ["Verification key, bearer token, and datasource credentials are excluded."],
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"REMOTE_CONTROL_GATE={result}")
    print(f"RUN_ID={run_id}")
    print(f"EVIDENCE_JSON={report_path}")
    print(f"EVIDENCE_PNG={screenshot if screenshot.exists() else 'NOT_CAPTURED'}")
    return 0 if result == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
