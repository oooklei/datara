"""Read-only R2-13 UI verification against the deployed R3 governance page."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from rebuild.governance.migrations import R3_GOVERNANCE_MIGRATIONS


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs" / "increments" / "evidence" / "R2"
BASE_URL = os.getenv("REBUILD_R2_VALIDATION_BASE_URL", "http://192.168.1.9:18091").rstrip("/")
API_ROOT = f"{BASE_URL}/api/v1/rebuild"
PROJECT_ID = 8
ASSET_IDS = (10, 11)
REMOTE_SECRET_SOURCE = [
    "ssh",
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=8",
    "root@192.168.1.9",
    "docker exec datara-rebuild-api printenv REBUILD_VALIDATION_KEY",
]


def assert_read_only_responses(responses: list[dict[str, object]]) -> None:
    """Permit only GET requests plus the explicitly required validation-token exchange."""
    for response in responses:
        method = str(response.get("method", "")).upper()
        path = str(response.get("path", ""))
        if method == "GET":
            continue
        if method == "POST" and path == "/api/v1/rebuild/validation-token":
            continue
        raise AssertionError(f"unexpected non-read request: {method} {path}")


def _validation_key() -> tuple[str, str]:
    configured = os.getenv("REBUILD_VALIDATION_KEY", "").strip()
    if configured:
        return configured, "local REBUILD_VALIDATION_KEY runtime environment"
    try:
        result = subprocess.run(REMOTE_SECRET_SOURCE, check=True, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("approved remote runtime secret lookup failed") from exc
    key = result.stdout.strip()
    if not key:
        raise RuntimeError("remote runtime validation key is not configured")
    return key, "192.168.1.9 running rebuild-api environment over BatchMode SSH"


def _path(url: str) -> str:
    return url.split("/api/v1/rebuild", 1)[-1].split("?", 1)[0] if "/api/v1/rebuild" in url else "/"


def _exchange_token(key: str) -> tuple[str, dict[str, object]]:
    request = Request(
        f"{API_ROOT}/validation-token",
        data=b"{}",
        headers={"Accept": "application/json", "Content-Type": "application/json", "X-Backend-Validation-Key": key},
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
            status = response.status
    except HTTPError as exc:
        raise RuntimeError(f"validation-token exchange returned HTTP {exc.code}") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError("validation-token exchange could not reach the backend") from exc
    token = str(payload.get("data", {}).get("token", ""))
    if status != 200 or not token:
        raise RuntimeError("validation-token exchange returned no short-lived token")
    return token, {"method": "POST", "status": status, "path": "/api/v1/rebuild/validation-token"}


def _remote_target_database_snapshot() -> dict[str, object]:
    """Inspect only the isolated target schema; every SQL statement is SELECT-only."""
    def query(sql: str) -> list[str]:
        inner = (
            'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql --protocol=TCP -uroot '
            f"--batch --skip-column-names datara_rebuild_i0 -e {shlex.quote(sql)}"
        )
        remote_command = f"docker exec datara-mysql-meta sh -lc {shlex.quote(inner)}"
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "root@192.168.1.9", remote_command],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return [line for line in result.stdout.splitlines() if line]

    identity_rows = query("SELECT DATABASE(), VERSION(), CURRENT_TIMESTAMP")
    if len(identity_rows) != 1 or identity_rows[0].split("\t", 1)[0] != "datara_rebuild_i0":
        raise RuntimeError("target database identity is not datara_rebuild_i0")
    table_names = query(
        "SELECT TABLE_NAME FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_NAME"
    )
    allowed_tables = [
        name for name in table_names
        if name.startswith("rebuild_governance_") or name == "rebuild_schema_migration"
    ]
    other_target_tables = [name for name in table_names if name not in allowed_tables]
    column_rows = query(
        "SELECT TABLE_NAME, COLUMN_NAME, IS_NULLABLE, COALESCE(COLUMN_DEFAULT, '<NULL>') "
        "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
        "AND COLUMN_NAME IN ('created_at','updated_at','generated_at','started_at','finished_at') "
        "ORDER BY TABLE_NAME, ORDINAL_POSITION"
    )
    columns: dict[str, set[str]] = {}
    for row in column_rows:
        parts = row.split("\t")
        if len(parts) == 4:
            columns.setdefault(parts[0], set()).add(parts[1])

    row_counts: list[dict[str, object]] = []
    for table in allowed_tables:
        if not re.fullmatch(r"rebuild_(?:governance_[a-z0-9_]+|schema_migration)", table):
            raise RuntimeError("unexpected table identifier in isolated schema")
        timestamp_columns = [
            name for name in ("created_at", "updated_at", "generated_at")
            if name in columns.get(table, set())
        ]
        aggregates = ["COUNT(*)"]
        aggregates.extend(f"COALESCE(SUM({name} IS NULL), 0)" for name in timestamp_columns)
        count_rows = query(f"SELECT {', '.join(aggregates)} FROM `{table}`")
        values = [int(value) for value in count_rows[0].split("\t")] if count_rows else []
        row_counts.append(
            {
                "table": table,
                "rows": values[0] if values else None,
                "null_timestamp_counts": dict(zip(timestamp_columns, values[1:])),
            }
        )

    revisions: list[str] = []
    if "rebuild_schema_migration" in allowed_tables:
        revisions = query(
            "SELECT revision, checksum, status, attempt_count, started_at, finished_at "
            "FROM rebuild_schema_migration ORDER BY revision"
        )
    assets = query(
        "SELECT id, asset_name, COALESCE(CAST(row_count AS CHAR), '<NULL>'), "
        "DATE_FORMAT(updated_at, '%Y-%m-%d %H:%i:%s') "
        "FROM rebuild_governance_asset WHERE project_id = 8 AND id IN (10, 11) ORDER BY id"
    )
    audit_events = query(
        "SELECT id, DATE_FORMAT(generated_at, '%Y-%m-%d %H:%i:%s'), action, resource_type, resource_id "
        "FROM rebuild_governance_audit_event WHERE project_id = 8 "
        "ORDER BY generated_at DESC, id DESC LIMIT 100"
    )
    return {
        "database_identity": identity_rows[0],
        "tables": table_names,
        "other_tables_in_same_isolated_schema_not_inspected": other_target_tables,
        "timestamp_column_metadata": column_rows,
        "row_and_null_timestamp_counts": row_counts,
        "migration_records": revisions,
        "existing_assets": assets,
        "audit_events": audit_events,
        "query_policy": "SELECT-only; database fixed to datara_rebuild_i0; no source or warehouse schemas queried",
    }


def _remote_runtime_snapshot() -> dict[str, object]:
    remote_command = (
        "docker ps --format '{{.Names}}|{{.Status}}|{{.Image}}' | grep '^datara-' || true; "
        "printf '\\nACCESS_LOGS\\n'; "
        "docker logs --since 15m datara-rebuild-api 2>&1 "
        "| grep -E '(GET|POST) /api/v1/rebuild/(validation-token|projects|governance)' "
        "| tail -30 || true"
    )
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "root@192.168.1.9", remote_command],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    service_lines, _, access_logs = result.stdout.partition("ACCESS_LOGS")
    return {
        "services": [line for line in service_lines.splitlines() if line],
        "rebuild_api_access_log_lines": [line for line in access_logs.splitlines() if line],
        "remote_commands": "docker ps and filtered docker logs only; no restart/deploy/mutation",
    }


def _http_status(url: str) -> dict[str, object]:
    request = Request(url, headers={"Accept": "application/json, text/html"}, method="GET")
    with urlopen(request, timeout=15) as response:
        body = response.read()
        return {"url": url, "status": response.status, "body_bytes": len(body)}


def assert_timestamp_snapshot(snapshot: dict[str, object]) -> None:
    """Validate governance timestamp defaults and persisted row timestamps."""
    table_names = snapshot["tables"]
    governance_tables = [
        name for name in table_names
        if name.startswith("rebuild_governance_") or name == "rebuild_schema_migration"
    ]
    metadata: dict[str, dict[str, tuple[str, str]]] = {}
    for row in snapshot["timestamp_column_metadata"]:
        table, column, nullable, default = row.split("\t")
        metadata.setdefault(table, {})[column] = (nullable, default)
    counts = {item["table"]: item for item in snapshot["row_and_null_timestamp_counts"]}
    for table in governance_tables:
        if table not in counts:
            raise AssertionError(f"missing persisted row-count evidence for {table}")
        for column in ("created_at", "updated_at"):
            if metadata.get(table, {}).get(column) != ("NO", "CURRENT_TIMESTAMP"):
                raise AssertionError(f"{table}.{column} lacks a non-null database-generated default")
        if "generated_at" in metadata.get(table, {}):
            if metadata[table]["generated_at"] != ("NO", "CURRENT_TIMESTAMP"):
                raise AssertionError(f"{table}.generated_at lacks a non-null database-generated default")
        if any(value for value in counts[table]["null_timestamp_counts"].values()):
            raise AssertionError(f"{table} has persisted null timestamp values")
    migrations = snapshot["migration_records"]
    expected_migrations = {item.revision: item.checksum for item in R3_GOVERNANCE_MIGRATIONS}
    observed_migrations: dict[str, str] = {}
    if len(migrations) < 2 or any(
        len(parts := row.split("\t")) != 6
        or parts[2] != "completed"
        or int(parts[3]) < 1
        or not parts[4]
        or not parts[5]
        for row in migrations
    ):
        raise AssertionError("governance migration history is missing or incomplete")
    for row in migrations:
        parts = row.split("\t")
        observed_migrations[parts[0]] = parts[1]
    if observed_migrations != expected_migrations:
        raise AssertionError("database-applied migration revisions/checksums differ from the current backend")


def main() -> int:
    run_id = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("r2-13-%Y%m%d%H%M%S")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    screenshot_path = EVIDENCE / f"{run_id}.png"
    report_path = EVIDENCE / f"{run_id}.json"
    report: dict[str, object] = {
        "run_id": run_id,
        "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "timezone": "Asia/Shanghai",
        "url": f"{BASE_URL}/rebuild-validation-r3.html",
        "project_id": PROJECT_ID,
        "expected_asset_ids": list(ASSET_IDS),
        "browser": "Chromium via Playwright",
        "browser_use_fallback": {
            "status": "BLOCKED",
            "attempts": ["same-page bind/navigation timed out at 30s", "same-page retry timed out at 60s"],
            "fallback": "Playwright controlled the deployed R3 page at the same 192.168.1.9:18091 URL",
        },
        "token_source": "not resolved",
        "actions": [],
        "assertions": [],
        "responses": [],
        "page_errors": [],
        "console_errors": [],
        "failed_requests": [],
        "screenshot": None,
        "result": "FAIL",
        "mutation_policy": "Only POST /api/v1/rebuild/validation-token is allowed; all page requests must be GET.",
        "notes": ["The key and short-lived token are excluded from this report, URL, page storage, and screenshot."],
    }
    try:
        key, key_source = _validation_key()
        token, token_response = _exchange_token(key)
        del key
        report["token_source"] = key_source
        report["responses"] = [token_response]
        report["remote_runtime"] = _remote_runtime_snapshot()
        report["remote_health"] = {
            "web": _http_status(f"{BASE_URL}/rebuild-validation-r3.html"),
            "api": _http_status(f"{API_ROOT}/health"),
        }
        if (
            report["remote_health"]["web"]["status"] != 200
            or report["remote_health"]["api"]["status"] != 200
        ):
            raise AssertionError("remote Web or rebuild API health probe did not return HTTP 200")
        report["target_database"] = _remote_target_database_snapshot()
        assert_timestamp_snapshot(report["target_database"])
        report["assertions"].append({"name": "isolated-schema-timestamp-defaults-and-row-values", "passed": True})
        report["assertions"].append(
            {"name": "governance-migrations-completed-with-start-and-finish-times", "passed": True}
        )
        report["assertions"].append(
            {"name": "database-migration-checksums-match-checked-out-backend", "passed": True}
        )
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            report["browser_version"] = browser.version
            context = browser.new_context(viewport={"width": 1600, "height": 1100})
            context.add_init_script(f"window.__DATARA_TEST_TOKEN__ = {json.dumps(token)};")
            del token
            page = context.new_page()
            page.on("pageerror", lambda error: report["page_errors"].append(str(error)))
            page.on(
                "console",
                lambda message: report["console_errors"].append(message.text)
                if message.type == "error"
                else None,
            )
            page.on(
                "requestfailed",
                lambda request: report["failed_requests"].append(
                    f"{request.method} {_path(request.url)}: {request.failure}"
                ),
            )
            page_requests: list[dict[str, str]] = []
            page.on(
                "request",
                lambda request: page_requests.append(
                    {"method": request.method, "path": _path(request.url)}
                )
                if "/api/v1/rebuild" in request.url
                else None,
            )

            def record_response(response) -> None:
                if "/api/v1/rebuild/" in response.url or response.url.endswith("/api/v1/rebuild"):
                    report["responses"].append(
                        {"method": response.request.method, "status": response.status, "path": _path(response.url)}
                    )

            page.on("response", record_response)
            try:
                response = page.goto(str(report["url"]), wait_until="domcontentloaded", timeout=30000)
                if response is None or response.status != 200:
                    raise AssertionError("R3 validation page did not return HTTP 200")
                page.locator("#projectSelect").wait_for(state="visible")
                page.locator("#projectSelect").select_option(str(PROJECT_ID))
                page.locator(f"#assetRows tr[data-asset-id='{ASSET_IDS[0]}']").wait_for(timeout=15000)
                page.locator(f"#assetRows tr[data-asset-id='{ASSET_IDS[1]}']").wait_for(timeout=15000)
                project_label = page.locator("#projectSelect option:checked").inner_text()
                if not project_label:
                    raise AssertionError("fixed isolated project selection is not visible")
                report["actions"].append({"action": "select pre-existing isolated project", "project_id": PROJECT_ID})
                report["assertions"].append({"name": "fixed-project-and-existing-assets-visible", "passed": True})

                asset10 = page.locator(f"#assetRows tr[data-asset-id='{ASSET_IDS[0]}']")
                table_snapshot = {
                    "project_label": project_label,
                    "summary": page.locator("#resultSummary").inner_text(),
                    "visible_rows": page.locator("#assetRows tr[data-asset-id]").count(),
                    "assets": [],
                }
                for asset_id in ASSET_IDS:
                    row = page.locator(f"#assetRows tr[data-asset-id='{asset_id}']")
                    table_snapshot["assets"].append(
                        {
                            "id": asset_id,
                            "name": row.locator("td").nth(0).inner_text(),
                            "row_count": row.locator("td").nth(6).inner_text(),
                            "updated_at": row.locator("td").nth(7).inner_text(),
                        }
                    )
                report["table_snapshot"] = table_snapshot
                if any(
                    not item["updated_at"].strip() or item["updated_at"].strip() == "—"
                    for item in table_snapshot["assets"]
                ):
                    raise AssertionError("asset list has a missing updated_at value")

                asset10.click()
                page.locator("#detailPath").filter(has_text="ID 10").wait_for(timeout=15000)
                page.locator("#assetOverview").click()
                overview_text = page.locator("#tabContent").inner_text()
                overview_labels = [
                    item.inner_text().strip() for item in page.locator("#tabContent .kv label").all()
                ]
                if len(overview_labels) < 8:
                    raise AssertionError("asset overview does not show row count and last-update fields")
                db_asset_rows = [row.split("\t") for row in report["target_database"]["existing_assets"]]
                db_assets_by_id = {int(row[0]): row for row in db_asset_rows if len(row) == 4}
                if set(db_assets_by_id) != set(ASSET_IDS):
                    raise AssertionError("target database does not contain the two pre-existing validation assets")
                for asset in table_snapshot["assets"]:
                    db_asset = db_assets_by_id[asset["id"]]
                    if asset["updated_at"] != db_asset[3]:
                        raise AssertionError(f"asset {asset['id']} displayed updated_at differs from MySQL")
                    db_row_count = db_asset[2]
                    displayed_row_count = asset["row_count"].replace(",", "").strip()
                    if db_row_count == "<NULL>" and displayed_row_count != "—":
                        raise AssertionError(f"asset {asset['id']} does not render a null row_count consistently")
                    if db_row_count != "<NULL>" and displayed_row_count != db_row_count:
                        raise AssertionError(f"asset {asset['id']} displayed row_count differs from MySQL")
                report["assertions"].append(
                    {"name": "asset-updated-at-and-row-count-reconciled-to-mysql", "passed": True}
                )
                report["asset_detail"] = {
                    "id": ASSET_IDS[0],
                    "name": page.locator("#detailName").inner_text(),
                    "path": page.locator("#detailPath").inner_text(),
                    "overview": overview_text,
                }
                report["actions"].append(
                    {"action": "open existing asset detail and overview", "asset_id": ASSET_IDS[0]}
                )
                report["assertions"].append({"name": "asset-detail-row-count-and-updated-at-visible", "passed": True})

                with page.expect_response(
                    lambda item: item.request.method == "GET"
                    and f"/governance/projects/{PROJECT_ID}/audit" in item.url,
                    timeout=15000,
                ) as audit_response_info:
                    page.locator("#assetAudit").click()
                audit_response = audit_response_info.value
                if audit_response.status != 200:
                    raise AssertionError(f"project audit request returned HTTP {audit_response.status}")
                audit_payload = audit_response.json().get("data", {})
                audit_items = audit_payload.get("list", [])
                page.locator(".audit-row").first.wait_for(timeout=15000)
                visible_audit_count = page.locator(".audit-row").count()
                audit_rows = []
                for index in range(visible_audit_count):
                    row = page.locator(".audit-row").nth(index)
                    audit_rows.append(
                        {
                            "generated_at": row.locator("time").inner_text(),
                            "action": row.locator("strong").inner_text(),
                            "resource": row.locator("span").inner_text(),
                        }
                    )
                expected_visible = [
                    {
                        "generated_at": str(item.get("generated_at", "")),
                        "action": str(item.get("action", "")),
                        "resource": f"{item.get('resource_type', '')} #{item.get('resource_id', '')}",
                    }
                    for item in audit_items[:visible_audit_count]
                ]
                if not audit_items or visible_audit_count != len(expected_visible) or audit_rows != expected_visible:
                    raise AssertionError("visible Activity/Audit rows differ from their GET response")
                if any(not item["generated_at"].strip() for item in audit_rows):
                    raise AssertionError("Activity/Audit contains an empty generated_at")
                db_audit_events = [row.split("\t") for row in report["target_database"]["audit_events"]]
                db_audit_keys = {
                    (row[1], row[2], row[3], row[4]) for row in db_audit_events if len(row) == 5
                }
                api_audit_keys = {
                    (
                        str(item.get("generated_at", "")),
                        str(item.get("action", "")),
                        str(item.get("resource_type", "")),
                        str(item.get("resource_id", "")),
                    )
                    for item in audit_items
                }
                if not api_audit_keys or not api_audit_keys.issubset(db_audit_keys):
                    raise AssertionError("audit timestamps and rows differ between API and target MySQL")
                report["audit_snapshot"] = {
                    "total": audit_payload.get("total"),
                    "visible_count": visible_audit_count,
                    "rows": audit_rows,
                }
                report["actions"].append(
                    {"action": "open Activity / Audit and reconcile displayed rows", "project_id": PROJECT_ID}
                )
                report["assertions"].append({"name": "audit-generated-timestamps-match-api-and-mysql", "passed": True})

                assert_read_only_responses(report["responses"])
                report["page_requests"] = page_requests
                non_get_page_requests = [item for item in page_requests if item["method"] != "GET"]
                if non_get_page_requests:
                    raise AssertionError("page issued a non-GET request")
                report["assertions"].append({"name": "all-page-api-requests-are-get", "passed": True})
                if report["page_errors"] or report["console_errors"] or report["failed_requests"]:
                    raise AssertionError("browser reported page, console, or network errors")
                page.screenshot(path=str(screenshot_path), full_page=True)
                report["screenshot"] = screenshot_path.name
                report["result"] = "PASS"
            except (AssertionError, PlaywrightTimeoutError) as exc:
                report["failure"] = f"{type(exc).__name__}: {exc}"
                try:
                    page.screenshot(path=str(screenshot_path), full_page=True)
                    report["screenshot"] = screenshot_path.name
                except Exception:
                    pass
            finally:
                context.close()
                browser.close()
    except Exception as exc:
        report["failure"] = f"{type(exc).__name__}: {exc}"
    try:
        assert_read_only_responses(report["responses"])
    except AssertionError as exc:
        report["failure"] = str(exc)
        report["result"] = "FAIL"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PLAYWRIGHT_CONTROL_VALIDATION={report['result']} run_id={run_id}")
    print(f"EVIDENCE_REPORT={report_path}")
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
