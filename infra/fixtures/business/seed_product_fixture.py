#!/usr/bin/env python3
"""Seed INFRA-DATA-01 platform objects through the public rebuild API only."""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping


API_PREFIX = "/api/v1/rebuild"
PROJECT_NAME = "INFRA-DATA-01 电商闭环验证"
FIXTURE_DIR = Path(__file__).resolve().parent
FILE_SYNC_PATH = "/datara/files/fixtures/orders_file_sync.csv"
DEFAULT_API_BASE = "http://127.0.0.1:18091"
DEFAULT_KEY_FILE = "/lei/datara/runtime-secrets/rebuild-validation.key"
DEFAULT_ADMIN_PASSWORD_FILE = "/lei/datara/secrets/rebuild-admin-password"
DEMO_ACCOUNTS = (
    {"username": "admin", "password": "Admin@123", "role": "admin", "project_role": "admin"},
    {"username": "dev", "password": "Dev@123", "role": "developer", "project_role": "developer"},
    {"username": "analyst", "password": "Analyst@123", "role": "operator", "project_role": "operator"},
    {"username": "viewer", "password": "Viewer@123", "role": "viewer", "project_role": "viewer"},
)
DEMO_MODELS = (
    {
        "code": "ods_ecommerce_orders", "name": "电商订单原始层", "layer": "ODS",
        "engine": "mysql", "type": "明细表", "bizDomain": "交易域",
        "fields": [
            {"name": "order_id", "dataType": "BIGINT", "length": None, "precision": None, "nullable": False, "defaultValue": None, "comment": "订单主键", "isPk": True, "isPartition": False, "dictRef": None},
            {"name": "user_id", "dataType": "BIGINT", "length": None, "precision": None, "nullable": False, "defaultValue": None, "comment": "用户标识", "isPk": False, "isPartition": False, "dictRef": None},
            {"name": "order_amount", "dataType": "DECIMAL", "length": None, "precision": 2, "nullable": False, "defaultValue": "0", "comment": "订单金额", "isPk": False, "isPartition": False, "dictRef": None},
        ],
    },
    {
        "code": "dwd_ecommerce_orders_detail", "name": "电商订单明细", "layer": "DWD",
        "engine": "mysql", "type": "明细表", "bizDomain": "交易域",
        "fields": [
            {"name": "order_id", "dataType": "BIGINT", "length": None, "precision": None, "nullable": False, "defaultValue": None, "comment": "订单主键", "isPk": True, "isPartition": False, "dictRef": None},
            {"name": "user_id", "dataType": "BIGINT", "length": None, "precision": None, "nullable": False, "defaultValue": None, "comment": "用户标识", "isPk": False, "isPartition": False, "dictRef": None},
            {"name": "pay_amount", "dataType": "DECIMAL", "length": None, "precision": 2, "nullable": False, "defaultValue": "0", "comment": "实付金额", "isPk": False, "isPartition": False, "dictRef": None},
        ],
    },
    {
        "code": "dws_ecommerce_order_daily", "name": "电商订单日汇总", "layer": "DWS",
        "engine": "mysql", "type": "汇总表", "bizDomain": "交易域",
        "fields": [
            {"name": "stat_date", "dataType": "DATE", "length": None, "precision": None, "nullable": False, "defaultValue": None, "comment": "统计日期", "isPk": True, "isPartition": True, "dictRef": None},
            {"name": "order_count", "dataType": "BIGINT", "length": None, "precision": None, "nullable": False, "defaultValue": "0", "comment": "订单数", "isPk": False, "isPartition": False, "dictRef": None},
            {"name": "pay_amount", "dataType": "DECIMAL", "length": None, "precision": 2, "nullable": False, "defaultValue": "0", "comment": "实付金额", "isPk": False, "isPartition": False, "dictRef": None},
        ],
    },
)
DEMO_MODEL_RELATIONS = (
    ("ods_ecommerce_orders", "dwd_ecommerce_orders_detail", "order_id", "order_id"),
    ("dwd_ecommerce_orders_detail", "dws_ecommerce_order_daily", "pay_amount", "pay_amount"),
)


class ApiError(RuntimeError):
    pass


class HostGuardError(RuntimeError):
    pass


def host_addresses() -> set[str]:
    """Return local IPv4 addresses without invoking external commands.

    - DNS/hosts 解析（socket.getaddrinfo）：主机名可能只映射到 127.0.1.1（Debian
      /etc/hosts 惯例），实测 192.168.1.9 上仅得 127.0.1.1，不足以通过守卫。
    - UDP connect trick：connect(TEST-NET 地址) 只做本地路由选择、不产生任何网络
      流量，可取默认路由的本机源地址（如 192.168.1.9），补齐真实环境判定。
    """
    addresses: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, family=socket.AF_INET):
            addresses.add(info[4][0])
    except OSError:
        pass
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("192.0.2.1", 9))
            addresses.add(probe.getsockname()[0])
        finally:
            probe.close()
    except OSError:
        pass
    return addresses


def assert_validation_host() -> None:
    addresses = host_addresses()
    if "192.168.1.9" not in addresses:
        visible = ",".join(sorted(addresses)) or "unknown"
        raise HostGuardError(
            f"execution is restricted to validation host 192.168.1.9 (found: {visible})"
        )


class Settings:
    def __init__(self, values: Mapping[str, str]):
        self.api_base = values.get("DATARA_API_BASE", DEFAULT_API_BASE).rstrip("/")
        self.key_file = Path(values.get("DATARA_VALIDATION_KEY_FILE", DEFAULT_KEY_FILE))
        self.admin_password_file = Path(
            values.get("DATARA_ADMIN_PASSWORD_FILE", DEFAULT_ADMIN_PASSWORD_FILE)
        )
        shared_password = values.get("DATARA_FIXTURE_MYSQL_PASSWORD", "")
        self.source = {
            "name": "INFRA-DATA-01 source",
            "kind": "mysql",
            "host": values.get("DATARA_FIXTURE_SRC_HOST", "datara-mysql-src"),
            "port": int(values.get("DATARA_FIXTURE_SRC_PORT", "3306")),
            "database": values.get("DATARA_FIXTURE_SRC_DATABASE", "ec_retail"),
            "username": values.get("DATARA_FIXTURE_SRC_USERNAME", "root"),
            "password": values.get("DATARA_FIXTURE_SRC_PASSWORD", shared_password),
        }
        self.dw = {
            "name": "INFRA-DATA-01 dw",
            "kind": "mysql",
            "host": values.get("DATARA_FIXTURE_DW_HOST", "datara-mysql-dw"),
            "port": int(values.get("DATARA_FIXTURE_DW_PORT", "3306")),
            "database": values.get("DATARA_FIXTURE_DW_DATABASE", "datara_dw"),
            "username": values.get("DATARA_FIXTURE_DW_USERNAME", "root"),
            "password": values.get("DATARA_FIXTURE_DW_PASSWORD", shared_password),
        }

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> "Settings":
        return cls(environ)


class UrllibTransport:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        request_headers = dict(headers or {})
        body: bytes | None = None
        if json_body is not None:
            body = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            headers=request_headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8"))
                message = payload.get("msg") or "request rejected"
            except (UnicodeDecodeError, json.JSONDecodeError):
                message = "request rejected"
            raise ApiError(f"{method} {path} failed ({exc.code}): {message}") from None
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ApiError(f"{method} {path} failed: connection unavailable") from exc
        if not isinstance(payload, dict) or payload.get("code") != 0:
            message = payload.get("msg", "invalid API response") if isinstance(payload, dict) else "invalid API response"
            raise ApiError(f"{method} {path} failed: {message}")
        return payload


def _data(response: dict[str, Any]) -> Any:
    return response["data"]


def ensure_demo_identities(
    settings: Settings,
    transport: Any,
    auth: dict[str, str],
    projects: list[dict[str, Any]],
) -> dict[str, Any]:
    users = _data(transport.request("GET", f"{API_PREFIX}/users", headers=auth))["list"]
    by_name = {row["username"]: row for row in users}
    for account in DEMO_ACCOUNTS:
        existing = by_name.get(account["username"])
        if existing is None:
            existing = _data(
                transport.request(
                    "POST",
                    f"{API_PREFIX}/users",
                    headers=auth,
                    json_body={key: account[key] for key in ("username", "password", "role")},
                )
            )
            by_name[account["username"]] = existing
        else:
            transport.request(
                "PATCH",
                f"{API_PREFIX}/users/{int(existing['id'])}/password",
                headers=auth,
                json_body={"password": account["password"]},
            )

    settings.admin_password_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = settings.admin_password_file.with_suffix(".tmp")
    temporary.write_text("Admin@123\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(settings.admin_password_file)

    project_names = {PROJECT_NAME, "电商数据全域治理项目"}
    memberships = 0
    for project in projects:
        if project["name"] not in project_names:
            continue
        project_id = int(project["id"])
        members = _data(
            transport.request("GET", f"{API_PREFIX}/projects/{project_id}/members", headers=auth)
        )["list"]
        member_ids = {int(row["user_id"]) for row in members}
        for account in DEMO_ACCOUNTS[1:]:
            user_id = int(by_name[account["username"]]["id"])
            if user_id in member_ids:
                continue
            transport.request(
                "POST",
                f"{API_PREFIX}/projects/{project_id}/members",
                headers=auth,
                json_body={"username": account["username"], "role": account["project_role"]},
            )
            memberships += 1
    return {"usernames": [row["username"] for row in DEMO_ACCOUNTS], "memberships_created": memberships}


def ensure_demo_models(transport: Any, auth: dict[str, str]) -> dict[str, int]:
    """Create a deterministic three-layer ecommerce model graph without duplicating reruns."""
    model_path = f"{API_PREFIX}/models"
    rows = _data(transport.request("GET", model_path, headers=auth))["list"]
    by_code = {row["code"]: row for row in rows}
    models_created = 0
    versions_created = 0

    for definition in DEMO_MODELS:
        code = definition["code"]
        row = by_code.get(code)
        if row is None:
            payload = {key: definition[key] for key in ("code", "name", "layer", "engine", "type", "bizDomain")}
            created = _data(transport.request("POST", model_path, headers=auth, json_body=payload))
            row = {**payload, "id": int(created["id"]), "version": 1, "status": "draft", "fields": []}
            rows.append(row)
            by_code[code] = row
            models_created += 1

        detail = _data(transport.request("GET", f"{model_path}/{int(row['id'])}", headers=auth))
        if not detail.get("fields") and detail.get("status", "draft") == "draft":
            saved = _data(transport.request(
                "PUT", f"{model_path}/{int(row['id'])}/fields", headers=auth,
                json_body={"rev": int(detail.get("version", 1)), "fields": definition["fields"]},
            ))
            row["version"] = int(saved["rev"])

        versions_path = f"{model_path}/{int(row['id'])}/versions"
        versions = _data(transport.request("GET", versions_path, headers=auth))
        if not versions:
            transport.request("POST", versions_path, headers=auth, json_body={"changeNote": "电商治理初始化基线"})
            versions_created += 1

    er = _data(transport.request("GET", f"{model_path}/er", headers=auth))
    existing = {(str(edge["source"]), str(edge["target"])) for edge in er.get("edges", [])}
    added = []
    for source_code, target_code, source_field, target_field in DEMO_MODEL_RELATIONS:
        source_id = int(by_code[source_code]["id"])
        target_id = int(by_code[target_code]["id"])
        if (str(source_id), str(target_id)) not in existing:
            added.append({
                "source": str(source_id), "target": str(target_id), "relType": "1:N",
                "srcFields": source_field, "tgtFields": target_field, "joinDesc": "电商治理样例血缘",
            })
    if added:
        positions = {str(int(by_code[item["code"]]["id"])): {"x": 180 + index * 300, "y": 180} for index, item in enumerate(DEMO_MODELS)}
        transport.request(
            "PUT", f"{model_path}/er", headers=auth,
            json_body={"positions": positions, "relations": {"removed": [], "added": added, "updated": []}},
        )

    return {"models_created": models_created, "versions_created": versions_created, "relations_created": len(added)}


def seed(settings: Settings, transport: Any) -> dict[str, Any]:
    assert_validation_host()
    validation_key = settings.key_file.read_text(encoding="utf-8").strip()
    if not validation_key:
        raise ApiError("validation key file is empty")
    token = _data(
        transport.request(
            "POST",
            f"{API_PREFIX}/validation-token",
            headers={
                "X-Backend-Validation-Key": validation_key,
                "X-Backend-Validation-Scope": "high-priority-e2e",
            },
        )
    )["token"]
    auth = {"Authorization": f"Bearer {token}"}

    projects = _data(transport.request("GET", f"{API_PREFIX}/projects", headers=auth))["list"]
    project = next((item for item in projects if item["name"] == PROJECT_NAME), None)
    if project is None:
        project = _data(
            transport.request(
                "POST",
                f"{API_PREFIX}/projects",
                headers=auth,
                json_body={"name": PROJECT_NAME, "description": "INFRA-DATA-01 deterministic product closure fixture"},
            )
        )
        projects.append(project)
    project_id = int(project["id"])
    identity_summary = ensure_demo_identities(settings, transport, auth, projects)
    model_summary = ensure_demo_models(transport, auth)

    datasource_path = f"{API_PREFIX}/projects/{project_id}/datasources"
    datasource_rows = _data(transport.request("GET", datasource_path, headers=auth))["items"]
    datasource_ids: dict[str, int] = {}
    for role, definition in (("source", settings.source), ("dw", settings.dw)):
        existing = next((row for row in datasource_rows if row["name"] == definition["name"]), None)
        if existing is None:
            existing = _data(
                transport.request("POST", datasource_path, headers=auth, json_body=definition)
            )
            datasource_rows.append(existing)
        datasource_ids[role] = int(existing["id"])

    variable_path = f"{API_PREFIX}/variables?project_id={project_id}&scopes=project"
    variables = _data(transport.request("GET", variable_path, headers=auth))
    variable_name = "fixture_key"
    if not any(row["scope"] == "project" and row["name"] == variable_name for row in variables):
        transport.request(
            "POST",
            f"{API_PREFIX}/variables?project_id={project_id}",
            headers=auth,
            json_body={
                "scope": "project",
                "name": variable_name,
                "value_type": "string",
                "value": "INFRA-DATA-01",
                "description": "Deterministic isolated validation fixture key",
            },
        )

    return {
        "project_id": project_id,
        "datasource_ids": datasource_ids,
        "variable_names": [variable_name],
        "file_sync_path": FILE_SYNC_PATH,
        "demo_identities": identity_summary,
        "models": model_summary,
    }


def dry_run_summary() -> dict[str, Any]:
    return {
        "dry_run": True,
        "object_types": ["identity", "project-member", "project", "datasource:source", "datasource:dw", "variable", "model", "model-field", "model-version", "model-relation", "file_sync:csv"],
        "file_sync_path": FILE_SYNC_PATH,
        "endpoints": [
            f"{API_PREFIX}/validation-token",
            f"{API_PREFIX}/projects",
            f"{API_PREFIX}/users",
            f"{API_PREFIX}/users/{{user_id}}/password",
            f"{API_PREFIX}/projects/{{project_id}}/members",
            f"{API_PREFIX}/projects/{{project_id}}/datasources",
            f"{API_PREFIX}/variables?project_id={{project_id}}",
            f"{API_PREFIX}/models",
            f"{API_PREFIX}/models/{{model_id}}/fields",
            f"{API_PREFIX}/models/{{model_id}}/versions",
            f"{API_PREFIX}/models/er",
        ],
    }


def main(argv: list[str] | None = None, *, environ: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print planned object types and endpoints only")
    args = parser.parse_args(argv)
    if args.dry_run:
        print(json.dumps(dry_run_summary(), ensure_ascii=False, sort_keys=True))
        return 0
    try:
        settings = Settings.from_env(os.environ if environ is None else environ)
        summary = seed(settings, UrllibTransport(settings.api_base))
    except (ApiError, HostGuardError, OSError, ValueError, KeyError) as exc:
        print(f"INFRA-DATA-01 seed failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
