"""Control-level R2-12-A verification against the deployed 1.9 runtime."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs" / "increments" / "evidence" / "R2"
BASE_URL = os.getenv("REBUILD_R2_VALIDATION_BASE_URL", "http://192.168.1.9:18091").rstrip("/")
API_ROOT = f"{BASE_URL}/api/v1/rebuild"
FIXTURE_PROJECT = "r2-12-a-validation-fixture"
OTHER_PROJECT = "r2-12-a-isolation-fixture"


def api(
    method: str,
    path: str,
    *,
    token: str = "",
    body: dict | None = None,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, dict]:
    headers = {"Accept": "application/json", **(extra_headers or {})}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    payload = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        payload = json.dumps(body).encode("utf-8")
    request = Request(f"{API_ROOT}{path}", data=payload, headers=headers, method=method)
    try:
        with urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
            return response.status, data
    except HTTPError as exc:
        try:
            data = json.loads(exc.read().decode("utf-8"))
        except Exception:
            data = {}
        return exc.code, data
    except URLError as exc:
        raise RuntimeError(f"remote request failed: {exc.reason}") from exc


def project_id(token: str, name: str) -> int:
    status, payload = api("GET", "/projects", token=token)
    if status != 200:
        raise RuntimeError(f"project fixture lookup failed: HTTP {status}")
    for item in payload.get("data", {}).get("list", []):
        if item.get("name") == name:
            return int(item["id"])
    status, payload = api(
        "POST", "/projects", token=token, body={"name": name, "description": "R2-12-A reusable validation fixture"}
    )
    if status != 200:
        raise RuntimeError(f"project fixture preparation failed: HTTP {status}")
    return int(payload["data"]["id"])


def load_fixture() -> dict[str, object]:
    raw = os.getenv("REBUILD_R2_DATASOURCE_FIXTURE_JSON", "")
    if not raw:
        raise RuntimeError("REBUILD_R2_DATASOURCE_FIXTURE_JSON is not configured")
    try:
        fixture = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("R2-12-A datasource fixture JSON is invalid") from exc
    required = ("kind", "host", "port", "database", "username", "password")
    if any(fixture.get(key) in (None, "") for key in required):
        raise RuntimeError("R2-12-A datasource fixture is missing a required field")
    if fixture["username"].casefold() == "root" or fixture["database"].casefold() == "datara_meta":
        raise RuntimeError("refusing to use the legacy root/datara_meta source as an R2-12-A fixture")
    if fixture["kind"].casefold() != "mysql":
        raise RuntimeError("R2-12-A control test currently requires an isolated MySQL fixture")
    return {
        "name": f"r2-12-a-{datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d%H%M%S')}",
        "kind": fixture["kind"],
        "host": fixture["host"],
        "port": int(fixture["port"]),
        "database": fixture["database"],
        "username": fixture["username"],
        "password": fixture["password"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true", help="run Chromium without a visible window")
    args = parser.parse_args()

    try:
        fixture = load_fixture()
    except RuntimeError as exc:
        print(f"REMOTE_CONTROL_GATE=BLOCKED_SAFE_FIXTURE: {exc}")
        return 2
    validation_key = os.getenv("REBUILD_VALIDATION_KEY", "")
    if not validation_key:
        print("REMOTE_CONTROL_GATE=BLOCKED_VALIDATION_KEY_MISSING")
        return 2

    try:
        status, payload = api(
            "POST",
            "/validation-token",
            body={},
            extra_headers={"X-Backend-Validation-Key": validation_key},
        )
    except RuntimeError as exc:
        print(f"REMOTE_CONTROL_GATE=BLOCKED_VALIDATION_TOKEN_NETWORK: {exc}")
        return 2
    if status != 200:
        print(f"REMOTE_CONTROL_GATE=BLOCKED_VALIDATION_TOKEN_HTTP_{status}")
        return 2
    token = payload.get("data", {}).get("token", "")
    if not token:
        print("REMOTE_CONTROL_GATE=BLOCKED_VALIDATION_TOKEN_EMPTY")
        return 2

    primary_project = project_id(token, FIXTURE_PROJECT)
    other_project = project_id(token, OTHER_PROJECT)
    url = f"{BASE_URL}/rebuild-validation-r2-12-a.html?projectId={primary_project}&otherProjectId={other_project}"
    run_id = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("r2-12-a-%Y%m%d%H%M%S")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    screenshot_path = EVIDENCE / f"{run_id}.png"
    report_path = EVIDENCE / f"{run_id}.json"
    actions: list[dict[str, object]] = []
    assertions: list[dict[str, object]] = []
    responses: list[dict[str, object]] = []
    page_errors: list[str] = []
    console_errors: list[str] = []
    failed_requests: list[str] = []
    created_datasource_id: int | None = None
    result = "FAIL"
    browser_version = "unknown"
    ui_cleanup_completed = False

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=args.headless)
        browser_version = browser.version
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        session = json.dumps({"token": token, "fixture": fixture})
        context.add_init_script(
            f"const session = {session};"
            "sessionStorage.setItem('rebuild.validation.token', session.token);"
            "sessionStorage.setItem('rebuild.datasource.fixture', JSON.stringify(session.fixture));"
        )
        page = context.new_page()
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.on(
            "requestfailed",
            lambda request: failed_requests.append(f"{request.method} {request.url.split('?')[0]}: {request.failure}"),
        )

        def record_response(response):
            if "/projects/" in response.url and "/datasources" in response.url:
                responses.append(
                    {
                        "method": response.request.method,
                        "status": response.status,
                        "path": response.url.split("/api/v1/rebuild", 1)[-1].split("?", 1)[0],
                    }
                )

        page.on("response", record_response)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.get_by_role("heading", name="项目数据源", exact=True).wait_for()
            assertions.append({"name": "validation-page-loaded", "passed": True})
            if page.locator("#project-label").inner_text() != f"#{primary_project}":
                raise AssertionError("primary project scope label mismatch")
            actions.append({"action": "open isolated datasource page", "project_id": primary_project})
            for selector in ("#name", "#kind", "#host", "#port", "#database", "#username", "#password"):
                if not page.locator(selector).input_value():
                    raise AssertionError(f"prefilled datasource field missing: {selector}")
            assertions.append({"name": "preseeded-datasource-form", "passed": True})

            page.get_by_role("button", name="保存数据源").click()
            page.get_by_text(str(fixture["name"]), exact=True).wait_for(timeout=15000)
            created = next((item for item in responses if item["method"] == "POST" and item["status"] == 201), None)
            if not created:
                raise AssertionError("datasource create response was not observed")
            row = page.locator("#datasource-rows tr").filter(has_text=str(fixture["name"])).first
            created_datasource_id = int(row.get_attribute("data-id"))
            action_buttons = row.locator("button")
            actions.append({"action": "create datasource through form", "http_status": 201})
            assertions.append({"name": "datasource-visible-in-project-list", "passed": row.count() == 1})

            action_buttons.nth(1).click()
            page.get_by_text("连接成功：", exact=False).wait_for(timeout=15000)
            actions.append({"action": "test saved datasource connection through row control", "http_status": 200})
            assertions.append({"name": "saved-profile-read-only-probe-success", "passed": True})

            row.get_by_role("button", name="编辑").click()
            updated_name = f"{fixture['name']}-updated"
            page.locator("#name").fill(updated_name)
            page.get_by_role("button", name="保存修改").click()
            page.get_by_text(updated_name, exact=True).wait_for(timeout=15000)
            actions.append({"action": "edit datasource and preserve password when blank", "http_status": 200})
            assertions.append({"name": "datasource-update-control", "passed": True})

            page.get_by_role("button", name="验证跨项目不可读取").click()
            page.get_by_text("验证通过：其他项目无法读取此数据源（404）。").wait_for(timeout=10000)
            assertions.append({"name": "cross-project-datasource-isolation", "passed": True})
            page.get_by_role("button", name="验证无 Token 请求被拒绝").click()
            page.get_by_text("验证通过：未携带 Token 的请求被拒绝（401）。").wait_for(timeout=10000)
            assertions.append({"name": "unauthenticated-request-denied", "passed": True})

            page.screenshot(path=str(screenshot_path), full_page=True)
            page.locator("#datasource-rows tr").filter(has_text=updated_name).get_by_role("button", name="删除").click()
            page.get_by_text("当前项目尚无数据源", exact=False).wait_for(timeout=15000)
            ui_cleanup_completed = True
            actions.append({"action": "delete datasource created by this run", "http_status": 200})
            assertions.append({"name": "fixture-datasource-cleaned-up", "passed": True})
            expected_404 = any(
                item["status"] == 404
                and item["path"] == f"/projects/{other_project}/datasources/{created_datasource_id}"
                for item in responses
            )
            expected_401 = any(
                item["status"] == 401 and item["path"] == f"/projects/{primary_project}/datasources"
                for item in responses
            )
            expected_console_errors = [
                message
                for message in console_errors
                if ("404 (Not Found)" in message and expected_404) or ("401 (Unauthorized)" in message and expected_401)
            ]
            unexpected_console_errors = [
                message for message in console_errors if message not in expected_console_errors
            ]
            result = "PASS" if not page_errors and not unexpected_console_errors and not failed_requests else "PARTIAL"
        except Exception as exc:
            page_errors.append(f"validation failure: {type(exc).__name__}: {exc}")
            try:
                page.screenshot(path=str(screenshot_path), full_page=True)
            except Exception:
                pass
        finally:
            if created_datasource_id and not ui_cleanup_completed:
                # A cleanup fallback only touches the record created by this test run.
                api("DELETE", f"/projects/{primary_project}/datasources/{created_datasource_id}", token=token)
            context.close()
            browser.close()

    report = {
        "run_id": run_id,
        "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "timezone": "Asia/Shanghai",
        "url": url,
        "browser": "Chromium",
        "browser_version": browser_version,
        "project_id": primary_project,
        "isolation_project_id": other_project,
        "datasource_id": created_datasource_id,
        "actions": actions,
        "assertions": assertions,
        "responses": responses,
        "page_errors": page_errors,
        "console_errors": console_errors,
        "expected_console_errors": expected_console_errors if "expected_console_errors" in locals() else [],
        "unexpected_console_errors": unexpected_console_errors
        if "unexpected_console_errors" in locals()
        else console_errors,
        "failed_requests": failed_requests,
        "screenshot": screenshot_path.name if screenshot_path.exists() else None,
        "result": result,
        "notes": ["Validation key, token, datasource credentials, and connection URL are intentionally excluded."],
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"PLAYWRIGHT_CONTROL_VALIDATION={result} run_id={run_id} "
        f"project_id={primary_project} datasource_id={created_datasource_id}"
    )
    print(f"EVIDENCE_REPORT={report_path}")
    if result != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
