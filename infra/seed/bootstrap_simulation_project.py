"""仿真项目引导：把旧版（datara_meta）平台对象迁入新栈项目域。

用途
----
1. 找到或创建"电商数据全域治理项目"（与临时测试项目隔离）。
2. 旧版 `t_data_source` 中 kind=mysql 的数据源 → `POST /projects/{id}/datasources`
   （新栈数据源为项目域模型；file/kafka 类型不属数据源注册面，跳过并报告）。
3. 旧版 `t_ssh_node` → `POST /ssh-nodes`（全局基础设施注册表）。

执行环境：datara-rebuild-api 容器内（自带 pymysql，API 在 127.0.0.1:8001）。

    docker exec -e LEGACY_DB_PWD=<from mysql container MYSQL_ROOT_PASSWORD> \
        datara-rebuild-api python /tmp/bootstrap_simulation_project.py

幂等：按名称去重（已存在即跳过），可安全重跑。
红线：凭据只从环境变量/旧库读取，不落日志、不落静态产物。
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

import pymysql

API_BASE = os.environ.get("REBUILD_API_BASE", "http://127.0.0.1:8001/api/v1/rebuild")
PROJECT_NAME = os.environ.get("SIM_PROJECT_NAME", "电商数据全域治理项目")
PROJECT_DESC = os.environ.get(
    "SIM_PROJECT_DESC",
    "承载旧版 datara_meta 初始化迁移数据（数据源/SSH 节点）的仿真项目，与临时测试项目隔离",
)
LEGACY = {
    "host": os.environ.get("LEGACY_DB_HOST", "mysql-meta"),
    "port": int(os.environ.get("LEGACY_DB_PORT", "3306")),
    "user": os.environ.get("LEGACY_DB_USER", "root"),
    "password": os.environ.get("LEGACY_DB_PWD", ""),
    "database": os.environ.get("LEGACY_DB_NAME", "datara_meta"),
}


def api(method: str, path: str, payload: dict | None = None, token: str = "") -> tuple[int, dict]:
    req = urllib.request.Request(
        API_BASE + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        method=method,
        headers={"Content-Type": "application/json", "token": token},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read() or b"{}")
        except json.JSONDecodeError:
            return exc.code, {}


def lookup_project_id_in_db(name: str) -> int | None:
    """分页兜底：直查 rebuild 库项目 id（只读）。"""
    from sqlalchemy.engine import make_url

    url = make_url(os.environ["REBUILD_DB_URL"])
    conn = pymysql.connect(
        host=url.host, port=url.port or 3306, user=url.username,
        password=url.password, database=url.database, charset="utf8mb4",
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM rebuild_project WHERE name=%s", (name,))
            row = cur.fetchone()
            return row[0] if row else None
    finally:
        conn.close()


def data_items(body: dict) -> list:
    """列表端点形状兼容：data 为裸数组或 {total, list}。"""
    data = body.get("data") if isinstance(body, dict) else None
    if isinstance(data, dict):
        return data.get("list") or data.get("items") or []
    return data if isinstance(data, list) else []


def main() -> int:
    if not LEGACY["password"]:
        print("FATAL: LEGACY_DB_PWD not set", file=sys.stderr)
        return 2

    # 1. 短时 token（key 只从容器环境读取）
    key = os.environ["REBUILD_VALIDATION_KEY"]
    req = urllib.request.Request(
        API_BASE + "/validation-token",
        data=b"{}",
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Backend-Validation-Key": key,
            "X-Backend-Validation-Scope": "high-priority-e2e",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        token = json.loads(resp.read())["data"]["token"]
    print("[1] token acquired")

    # 2. 找到或创建仿真项目（GET 形状 {total, list}；分页漏项时 SQL 兜底）
    _, body = api("GET", "/projects", None, token)
    project_id = next((p["id"] for p in data_items(body) if p.get("name") == PROJECT_NAME), None)
    if project_id is None:
        status, body = api("POST", "/projects", {"name": PROJECT_NAME, "description": PROJECT_DESC}, token)
        if status in (200, 201) and isinstance(body.get("data"), dict) and "id" in body["data"]:
            project_id = body["data"]["id"]
            print(f"[2] project created: id={project_id}")
        else:
            project_id = lookup_project_id_in_db(PROJECT_NAME)
            if project_id is None:
                print("FATAL: project not found and creation failed", file=sys.stderr)
                return 3
            print(f"[2] project resolved via db fallback: id={project_id}")
    else:
        print(f"[2] project exists: id={project_id}")

    # 3. 旧库读取
    conn = pymysql.connect(**LEGACY, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT name, type, host, port, db_name, user, pwd FROM t_data_source "
                "WHERE status='online' AND LOWER(type) IN ('mysql','postgresql')"
            )
            sources = cur.fetchall()
            cur.execute("SELECT name, host, port, ssh_user, cred_enc AS cred, tags, enabled FROM t_ssh_node")
            ssh_nodes = cur.fetchall()
    finally:
        conn.close()
    print(f"[3] legacy rows: mysql/pg sources={len(sources)}, ssh_nodes={len(ssh_nodes)}")

    # 4. 数据源注册（项目域，按名称幂等）
    _, body = api("GET", f"/projects/{project_id}/datasources", None, token)
    existing = {d["name"] for d in data_items(body)}
    created, failed = [], []
    for row in sources:
        if row["name"] in existing:
            print(f"    = datasource skip(existing): {row['name']}")
            continue
        db_name = row["db_name"] or os.environ.get("LEGACY_DEFAULT_DB", "ec_retail")
        if not row["db_name"]:
            print(f"    ~ db_name NULL, fallback to '{db_name}': {row['name']}")
        status, body = api(
            "POST",
            f"/projects/{project_id}/datasources",
            {
                "name": row["name"],
                "kind": row["type"].lower(),
                "host": row["host"],
                "port": int(row["port"] or 3306),
                "database": db_name,
                "username": row["user"],
                "password": row["pwd"] or "",
            },
            token,
        )
        if status == 201:
            created.append(row["name"])
            print(f"    + datasource created: {row['name']} -> {row['host']}:{row['port']}/{row['db_name']}")
        else:
            failed.append((row["name"], status, body.get("msg", "")))
            print(f"    ! datasource FAILED: {row['name']} http={status} msg={body.get('msg', '')}")

    # 5. SSH 节点注册（全局基础设施，按名称幂等）
    _, body = api("GET", "/ssh-nodes", None, token)
    ssh_existing = {n["name"] for n in data_items(body)}
    ssh_created = []
    for row in ssh_nodes:
        if row["name"] in ssh_existing:
            print(f"    = ssh_node skip(existing): {row['name']}")
            continue
        tags = json.loads(row["tags"]) if row["tags"] else []
        status, body = api(
            "POST",
            "/ssh-nodes",
            {
                "name": row["name"],
                "host": row["host"],
                "port": int(row["port"] or 22),
                "sshUser": row["ssh_user"],
                "cred": row["cred"] or "",
                "tags": tags,
                "enabled": bool(row["enabled"]),
            },
            token,
        )
        if status in (200, 201):
            ssh_created.append(row["name"])
            print(f"    + ssh_node created: {row['name']} -> {row['host']}:{row['port']}")
        else:
            print(f"    ! ssh_node FAILED: {row['name']} http={status} msg={body.get('msg', '')}")

    # 6. 终态盘点
    final_ds = len(data_items(api("GET", f"/projects/{project_id}/datasources", None, token)[1]))
    final_ssh = len(data_items(api("GET", "/ssh-nodes", None, token)[1]))
    print(f"[6] FINAL: project={PROJECT_NAME}(id={project_id}) datasources={final_ds} ssh_nodes={final_ssh}")
    print("NOTE: file/kafka 类型旧源不走数据源注册面（新栈分别走资源上传/流任务 mq_topic）")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
