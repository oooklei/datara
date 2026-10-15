from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
from tools.verify_r2_12_a import BASE_URL, api, project_id  # noqa: E402
from tools.verify_r2_12_c import managed_browser  # noqa: E402

EVIDENCE = ROOT / "docs" / "increments" / "evidence" / "R2"
FIXTURE_PREFIX = "r2-12-d-profile-"
MYSQL_FIXTURE_PREFIX = "r2-12-d-mysql-profile-"


def displays_view_kind(label: str) -> bool:
    """Recognize the visible object-kind label for PostgreSQL views."""
    return "view" in label.casefold() or "视图" in label


def fixture_from_environment() -> dict[str, object]:
    raw = os.getenv("REBUILD_R2_POSTGRES_FIXTURE_JSON", "")
    if not raw:
        raise RuntimeError("REBUILD_R2_POSTGRES_FIXTURE_JSON is not configured")
    fixture = json.loads(raw)
    required = ("kind", "host", "port", "database", "username", "password")
    if any(fixture.get(key) in (None, "") for key in required):
        raise RuntimeError("PostgreSQL fixture is missing required fields")
    if str(fixture["kind"]).lower() != "postgresql":
        raise RuntimeError("R2-12-D requires a PostgreSQL fixture")
    if not str(fixture["host"]).startswith("datara-r2-12d-pg-fixture"):
        raise RuntimeError("refusing a PostgreSQL fixture outside the named disposable container")
    if str(fixture["username"]).casefold() in {"root", "postgres"}:
        raise RuntimeError("fixture must use a least-privilege reader, not a superuser")
    if str(fixture["database"]).casefold() in {"datara_meta", "datara_dw", "postgres"}:
        raise RuntimeError("refusing a legacy or shared PostgreSQL database")
    return {
        "kind": "postgresql",
        "host": str(fixture["host"]),
        "port": int(fixture["port"]),
        "database": str(fixture["database"]),
        "username": str(fixture["username"]),
        "password": str(fixture["password"]),
    }


def mysql_fixture_from_environment() -> dict[str, object]:
    raw = os.getenv("REBUILD_R2_MYSQL_FIXTURE_JSON", "")
    if not raw:
        raise RuntimeError("REBUILD_R2_MYSQL_FIXTURE_JSON is not configured")
    fixture = json.loads(raw)
    required = ("kind", "host", "port", "database", "username", "password")
    if any(fixture.get(key) in (None, "") for key in required):
        raise RuntimeError("MySQL regression fixture is missing required fields")
    if str(fixture["kind"]).lower() != "mysql":
        raise RuntimeError("R2-12-D requires a MySQL compatibility fixture")
    if not str(fixture["host"]).startswith("datara-r2-12d-mysql-fixture"):
        raise RuntimeError("refusing a MySQL regression fixture outside the named disposable container")
    if str(fixture["username"]).casefold() in {"root", "postgres"}:
        raise RuntimeError("MySQL regression fixture must use a least-privilege reader")
    if str(fixture["database"]).casefold() in {"datara_meta", "datara_dw", "mysql"}:
        raise RuntimeError("refusing a legacy or shared MySQL database")
    return {
        "kind": "mysql",
        "host": str(fixture["host"]),
        "port": int(fixture["port"]),
        "database": str(fixture["database"]),
        "username": str(fixture["username"]),
        "password": str(fixture["password"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="R2-12-D PostgreSQL browser control gate")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--base-url", default=BASE_URL)
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    run_id = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("r2-12-d-%Y%m%d%H%M%S")
    report_path = EVIDENCE / f"{run_id}.json"
    screenshot_path = EVIDENCE / f"{run_id}.png"
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {
        "run_id": run_id,
        "started_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "result": "FAIL",
        "token_redacted": True,
        "fixture_credentials_recorded": False,
        "assertions": [],
        "responses": [],
        "page_errors": [],
        "failed_requests": [],
        "profile_cleanup": False,
    }
    token = ""
    project = other_project = None
    created_profiles: list[tuple[int, int]] = []

    try:
        fixture = fixture_from_environment()
        mysql_fixture = mysql_fixture_from_environment()
        key = os.getenv("REBUILD_VALIDATION_KEY", "")
        if not key:
            raise RuntimeError("REBUILD_VALIDATION_KEY is not configured")
        status, auth = api("POST", "/validation-token", body={}, extra_headers={"X-Backend-Validation-Key": key})
        token = auth.get("data", {}).get("token", "") if status == 200 else ""
        if not token:
            raise RuntimeError(f"validation token request failed: HTTP {status}")

        project = project_id(token, "r2-12-d-validation-fixture")
        other_project = project_id(token, "r2-12-d-isolation-fixture")
        listed_status, listed = api("GET", f"/projects/{project}/datasources", token=token)
        if listed_status != 200:
            raise RuntimeError(f"fixture profile list failed: HTTP {listed_status}")
        for profile in listed.get("data", {}).get("items", []):
            if str(profile.get("name", "")).startswith((FIXTURE_PREFIX, MYSQL_FIXTURE_PREFIX)):
                delete_status, _ = api(
                    "DELETE", f"/projects/{project}/datasources/{int(profile['id'])}", token=token
                )
                if delete_status != 200:
                    raise RuntimeError(f"stale disposable profile cleanup failed: HTTP {delete_status}")

        profile_body = {
            "name": f"{FIXTURE_PREFIX}{run_id[-6:]}",
            **fixture,
        }
        created_status, created = api(
            "POST", f"/projects/{project}/datasources", token=token, body=profile_body
        )
        if created_status != 201:
            raise RuntimeError(f"disposable PostgreSQL profile creation failed: HTTP {created_status}")
        postgres_datasource_id = int(created["data"]["id"])
        created_profiles.append((project, postgres_datasource_id))
        mysql_profile_body = {"name": f"{MYSQL_FIXTURE_PREFIX}{run_id[-6:]}", **mysql_fixture}
        mysql_status, mysql_created = api(
            "POST", f"/projects/{project}/datasources", token=token, body=mysql_profile_body
        )
        if mysql_status != 201:
            raise RuntimeError(f"disposable MySQL regression profile creation failed: HTTP {mysql_status}")
        mysql_datasource_id = int(mysql_created["data"]["id"])
        created_profiles.append((project, mysql_datasource_id))
        assertions = report["assertions"]
        responses = report["responses"]
        page_errors = report["page_errors"]
        failed_requests = report["failed_requests"]
        page = None

        def capture_failure(exc: Exception, _context) -> None:
            page_errors.append(type(exc).__name__)
            if page is not None:
                try:
                    page.screenshot(path=str(screenshot_path), full_page=True)
                except Exception:
                    pass

        try:
            with managed_browser(headless=args.headless, on_error=capture_failure) as (
                _playwright,
                _browser,
                context,
            ):
                context.add_init_script(
                    "sessionStorage.setItem('rebuild.validation.token', " + json.dumps(token) + ");"
                )
                page = context.new_page()
                page.on("pageerror", lambda error: page_errors.append(type(error).__name__))
                page.on(
                    "requestfailed",
                    lambda request: failed_requests.append(
                        {"method": request.method, "path": request.url.split("?", 1)[0]}
                    ),
                )
                page.on(
                    "response",
                    lambda response: responses.append(
                        {
                            "method": response.request.method,
                            "path": response.url.split("/api/v1/rebuild", 1)[-1].split("?", 1)[0],
                            "status": response.status,
                        }
                    )
                    if "/api/v1/rebuild/" in response.url
                    else None,
                )
                url = (
                    f"{base_url}/rebuild-validation-r2-12-b.html?projectId={project}"
                    f"&datasourceId={postgres_datasource_id}"
                )
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.get_by_role("heading", name="项目数据源 · Schema / 对象浏览").wait_for()
                page.locator("#datasource-kind").wait_for()
                page.wait_for_function("document.querySelector('#datasource-kind').value === 'POSTGRESQL'")
                assertions.append({"name": "saved-postgresql-profile-kind-displayed-from-backend", "passed": True})

                with page.expect_response(lambda response: "/schemas" in response.url and response.status == 200):
                    page.get_by_role("button", name="加载 Schema").click()
                schemas = ("analytics", "shared")
                for schema in schemas:
                    page.get_by_role("button", name=f"▸ {schema}").wait_for(timeout=15000)
                    page.get_by_role("button", name=f"▸ {schema}").click()
                    page.locator(f'button[data-schema="{schema}"][data-object="orders"]').wait_for(timeout=15000)
                view_button = page.locator('button[data-schema="analytics"][data-object="v_orders"]')
                view_button.wait_for(timeout=15000)
                if not displays_view_kind(view_button.inner_text()):
                    raise AssertionError("PostgreSQL view was not identified as a view in the object tree")
                view_button.click()
                if page.locator("#object-identity").input_value() != "analytics.v_orders":
                    raise AssertionError("schema-qualified PostgreSQL view identity is missing")
                assertions.append({"name": "postgresql-view-discovery-and-identity", "passed": True})

                page.locator('button[data-schema="analytics"][data-object="orders"]').click()
                page.get_by_role("button", name="查看列定义").click()
                page.locator("#column-rows tr").first.wait_for(timeout=15000)
                if page.locator("#object-identity").input_value() != "analytics.orders":
                    raise AssertionError("schema-qualified PostgreSQL object identity is missing")
                if page.locator("#column-rows tr").count() < 2:
                    raise AssertionError("expected PostgreSQL order_id and order_date columns")
                assertions.append({"name": "postgresql-cross-schema-table-view-and-columns", "passed": True})
                page.goto(
                    f"{base_url}/rebuild-validation-r2-12-b.html?projectId={project}&datasourceId={mysql_datasource_id}",
                    wait_until="domcontentloaded",
                )
                page.get_by_role("heading", name="项目数据源 · Schema / 对象浏览").wait_for()
                page.wait_for_function(
                    "document.querySelector('#datasource-kind').value === 'MYSQL'"
                )
                assertions.append({"name": "saved-mysql-profile-kind-displayed-from-backend", "passed": True})
                with page.expect_response(lambda response: "/schemas" in response.url and response.status == 200):
                    page.get_by_role("button", name="加载 Schema").click()
                page.get_by_role("button", name="▸ analytics").click()
                mysql_orders = page.locator('button[data-schema="analytics"][data-object="orders"]')
                mysql_orders.wait_for(timeout=15000)
                mysql_orders.click()
                page.get_by_role("button", name="查看列定义").click()
                page.locator("#column-rows tr").first.wait_for(timeout=15000)
                if page.locator("#object-identity").input_value() != "analytics.orders":
                    raise AssertionError("schema-qualified MySQL object identity is missing")
                assertions.append({"name": "mysql-compatibility-schema-object-and-columns", "passed": True})
                page.screenshot(path=str(screenshot_path), full_page=True)

                page.goto(
                    f"{base_url}/rebuild-validation-r2-12-b.html?projectId={other_project}&datasourceId={postgres_datasource_id}",
                    wait_until="domcontentloaded",
                )
                page.get_by_role("button", name="加载 Schema").click()
                page.get_by_role("status").filter(has_text="Schema 读取失败").wait_for(timeout=10000)
                if not any(row["status"] == 404 for row in responses):
                    raise AssertionError("cross-project datasource access did not return 404")
                assertions.append({"name": "cross-project-profile-isolation", "passed": True})
        except PlaywrightTimeoutError:
            page_errors.append("PlaywrightTimeoutError")
            if page is not None:
                page.screenshot(path=str(screenshot_path), full_page=True)

        expected_404 = any(
            row["status"] == 404 and "/schemas" in row["path"] for row in responses
        )
        non_404_failures = [row for row in responses if row["status"] >= 400 and row["status"] != 404]
        report["result"] = (
            "PASS"
            if (
                len(assertions) == 6
                and expected_404
                and not non_404_failures
                and not page_errors
                and not failed_requests
            )
            else "PARTIAL"
        )
    except Exception as exc:
        report["page_errors"].append(type(exc).__name__)
        report["result"] = "PARTIAL"
    finally:
        cleanup_results = []
        if token:
            for profile_project, datasource_id in reversed(created_profiles):
                delete_status, _ = api(
                    "DELETE", f"/projects/{profile_project}/datasources/{datasource_id}", token=token
                )
                cleanup_results.append(delete_status == 200)
        report["profile_cleanup"] = bool(cleanup_results) and all(cleanup_results)
        report["finished_at"] = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
        report["screenshot"] = screenshot_path.name if screenshot_path.exists() else None
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"RESULT={report['result']}")
    print(f"EVIDENCE_JSON={report_path}")
    print(f"EVIDENCE_PNG={screenshot_path if screenshot_path.exists() else 'NOT_CAPTURED'}")
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
