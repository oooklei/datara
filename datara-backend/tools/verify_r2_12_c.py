"""Control-level R2-12-C verification for bounded datasource pool lifecycle."""

from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
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


@contextmanager
def managed_browser(*, headless: bool, on_error=None):
    """Close browser resources before the synchronous Playwright driver stops."""
    with ExitStack() as stack:
        playwright = stack.enter_context(sync_playwright())
        browser = playwright.chromium.launch(headless=headless)
        stack.callback(browser.close)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        stack.callback(context.close)
        try:
            yield playwright, browser, context
        except Exception as exc:
            if on_error is not None:
                on_error(exc, context)
            raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()
    key = os.getenv("REBUILD_VALIDATION_KEY", "")
    schemas = [
        item.strip()
        for item in os.getenv("REBUILD_R2_METADATA_SCHEMAS", "analytics,shared").split(",")
        if item.strip()
    ]
    object_name = os.getenv("REBUILD_R2_METADATA_OBJECT", "orders").strip()
    if not key or len(schemas) < 2 or not object_name:
        print("REMOTE_CONTROL_GATE=BLOCKED_REQUIRED_VALIDATION_INPUT_MISSING")
        return 2
    try:
        fixture = load_fixture()
    except RuntimeError as exc:
        print(f"REMOTE_CONTROL_GATE=BLOCKED_SAFE_FIXTURE: {exc}")
        return 2

    status, auth = api("POST", "/validation-token", body={}, extra_headers={"X-Backend-Validation-Key": key})
    token = auth.get("data", {}).get("token", "") if status == 200 else ""
    if not token:
        print(f"REMOTE_CONTROL_GATE=BLOCKED_VALIDATION_TOKEN_HTTP_{status}")
        return 2

    run_id = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("r2-12-c-%Y%m%d%H%M%S")
    primary_project = project_id(token, "r2-12-c-validation-fixture")
    other_project = project_id(token, "r2-12-c-isolation-fixture")
    listed_status, listed_payload = api("GET", f"/projects/{primary_project}/datasources", token=token)
    if listed_status != 200:
        print(f"REMOTE_CONTROL_GATE=BLOCKED_STALE_FIXTURE_LOOKUP_HTTP_{listed_status}")
        return 2
    stale_profiles = [
        item
        for item in listed_payload.get("data", {}).get("items", [])
        if str(item.get("name", "")).startswith("r2-12-c-profile-")
        and str(item.get("name", "")).endswith("-updated")
    ]
    for stale in stale_profiles:
        cleanup_status, _ = api(
            "DELETE", f"/projects/{primary_project}/datasources/{int(stale['id'])}", token=token
        )
        if cleanup_status != 200:
            print(f"REMOTE_CONTROL_GATE=BLOCKED_STALE_FIXTURE_CLEANUP_HTTP_{cleanup_status}")
            return 2
    profile_name = f"r2-12-c-profile-{run_id[-6:]}"
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
    url = f"{BASE_URL}/rebuild-validation-r2-12-b.html?projectId={primary_project}&datasourceId={datasource_id}"
    report_path = EVIDENCE / f"{run_id}.json"
    screenshot = EVIDENCE / f"{run_id}.png"
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    actions: list[dict[str, object]] = []
    responses: list[dict[str, object]] = []
    page_errors: list[str] = []
    console_errors: list[str] = []
    expected_console_errors: list[str] = []
    failed_requests: list[str] = []
    assertions: list[dict[str, object]] = []
    result = "FAIL"
    page = None
    browser = None
    context = None

    def capture_browser_failure(exc: Exception, _context) -> None:
        page_errors.append(f"validation failure: {type(exc).__name__}: {exc}")
        if page is not None:
            try:
                page.screenshot(path=str(screenshot), full_page=True)
            except Exception:
                pass

    try:
        with managed_browser(headless=args.headless, on_error=capture_browser_failure) as (
            playwright,
            browser,
            context,
        ):
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
                    {
                        "status": response.status,
                        "method": response.request.method,
                        "path": response.url.split("/api/v1/rebuild", 1)[-1].split("?", 1)[0],
                    }
                )
                if "/api/v1/rebuild/" in response.url
                else None,
            )
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.get_by_role("heading", name="项目数据源 · Schema / 对象浏览").wait_for()
            assertions.append({"name": "same-db-x-object-browser-loaded", "passed": True})

            async_rounds = 0

            def browse_schemas_concurrently(round_name: str) -> None:
                nonlocal async_rounds
                with page.expect_response(
                    lambda response: "/schemas" in response.url and response.status == 200
                ):
                    page.get_by_role("button", name="加载 Schema").click()
                for schema in schemas:
                    page.get_by_role("button", name=f"▸ {schema}").wait_for(timeout=15000)
                # These clicks dispatch independent UI fetches before waiting for either response.
                for schema in schemas:
                    page.get_by_role("button", name=f"▸ {schema}").click()
                for schema in schemas:
                    page.locator(
                        f'button[data-schema="{schema}"][data-object="{object_name}"]'
                    ).wait_for(timeout=15000)
                async_rounds += 1
                actions.append({"action": f"expand {len(schemas)} schema controls concurrently ({round_name})"})

            actions_before_update = len(responses)
            browse_schemas_concurrently("initial profile")
            if any(
                row["status"] != 200
                for row in responses[actions_before_update:]
                if "/schemas" in str(row["path"]) or "/objects" in str(row["path"])
            ):
                raise AssertionError("schema/object UI request failed before profile update")

            updated_profile = {**profile, "name": f"{profile_name}-updated", "password": ""}
            update_status, _ = api(
                "PUT", f"/projects/{primary_project}/datasources/{datasource_id}", token=token, body=updated_profile
            )
            if update_status != 200:
                raise AssertionError(f"saved-profile update did not complete: HTTP {update_status}")
            actions.append({"action": "update saved datasource profile through authenticated API", "http_status": 200})

            browse_schemas_concurrently("after profile update invalidation")
            page.locator(f'button[data-object="{object_name}"]').first.click()
            page.get_by_role("button", name="查看列定义").click()
            page.locator("#column-rows tr").first.wait_for(timeout=15000)
            valid_identities = {f"{schema}.{object_name}" for schema in schemas}
            if page.locator("#object-identity").input_value() not in valid_identities:
                raise AssertionError("selected object identity lost its schema")
            assertions.append({"name": "profile-update-invalidates-pool-and-browse-recovers", "passed": True})
            if async_rounds != 2:
                raise AssertionError(f"expected 2 concurrent UI browse rounds, got {async_rounds}")
            browse_responses = [
                item for item in responses if "/schemas" in str(item["path"]) or "/objects" in str(item["path"])
            ]
            if any(item["status"] != 200 for item in browse_responses):
                raise AssertionError("one or more concurrent schema/object requests failed")
            assertions.append({"name": "bounded-pool-serves-repeated-concurrent-schema-requests", "passed": True})

            page.screenshot(path=str(screenshot), full_page=True)
            errors_before_isolation = len(console_errors)
            page.goto(
                f"{BASE_URL}/rebuild-validation-r2-12-b.html?projectId={other_project}&datasourceId={datasource_id}",
                wait_until="domcontentloaded",
            )
            page.get_by_role("button", name="加载 Schema").click()
            page.get_by_role("status").filter(has_text="Schema 读取失败").wait_for(timeout=10000)
            if not any(row["status"] == 404 for row in responses):
                raise AssertionError("cross-project datasource access did not return 404")
            expected_console_errors.extend(
                message for message in console_errors[errors_before_isolation:] if "status of 404" in message
            )
            assertions.append({"name": "cross-project-profile-isolation", "passed": True})
            unexpected_errors = [item for item in console_errors if item not in expected_console_errors]
            result = "PASS" if not page_errors and not unexpected_errors and not failed_requests else "PARTIAL"
    except Exception as exc:
        if not page_errors:
            page_errors.append(f"validation failure: {type(exc).__name__}: {exc}")
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
        "notes": ["Validation key, token, datasource password, and DSN are not included in this report."],
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"REMOTE_CONTROL_GATE={result}")
    print(f"RUN_ID={run_id}")
    print(f"EVIDENCE_JSON={report_path}")
    print(f"EVIDENCE_PNG={screenshot if screenshot.exists() else 'NOT_CAPTURED'}")
    return 0 if result == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
