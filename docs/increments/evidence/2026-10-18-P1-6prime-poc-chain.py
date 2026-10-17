"""P1-6' PoC: real execution chain (supervision line, 2026-10-18).

Chain under verification (all REAL, no mock on the verified path):
  NL question -> vanna generate_sql (siliconflow DeepSeek, datara-backend/.env)
  -> R8-A authorized bridge envelope (token auth / project authorization /
     read-only gate / budget) -> PoC SqlExecutionPort (real SQLite file, read-only
     connection mode) -> result interpretation (real siliconflow call).

Honest labeling (registered, not claimed as production):
  - The execution port is a PoC port behind the R5-A seam, NOT the production
    R5-A executeSql port (registered gap).
  - The audit writer is a PoC durable SQLite writer proving field threading +
    persistence, NOT the production section-4 DB-backed writer (R5-A/P2-2 scope).
  - DB-side layer-2 read-only (read-only account / transaction / least privilege)
    is NOT provisioned here; only SQLite URI mode=ro is used (defense in depth
    demo). Registered as R5-A production-assembly verification item.

Zero business-code modification: this script only imports and composes.
Artifacts land in a work dir OUTSIDE the repository; stdout is the evidence log.

Defect workaround (registered, zero-touch): ai_copilot/adapter.py:217 calls
`OpenAI_Chat.__init__(client=..., config=...)` WITHOUT self -> TypeError on every
_TenantVanna construction -> all memory writes / generate_sql fail. The PoC injects
a corrected vanna_factory (same scoped-chroma + siliconflow + run_sql refusal +
silent-log semantics, only the missing `self` fixed) via the public CopilotAdapter
seam. The defect itself is registered for the implementation line to fix (TDD).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "datara-backend"
WORK_ROOT = REPO_ROOT.parent / "p16-prime-work"
sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from ai_copilot.adapter import AdapterContext, CopilotAdapter  # noqa: E402
from rebuild.ai_bridge import AiBridgePorts  # noqa: E402
from rebuild.api.app import create_app  # noqa: E402
from rebuild.generate_sql import build_generate_sql_port  # noqa: E402
from rebuild.identity.contracts import Role  # noqa: E402
from rebuild.identity.repository import UserRepository  # noqa: E402
from rebuild.project.models import ProjectRecord  # noqa: E402
from rebuild.run_sql import (  # noqa: E402
    SqlDependencyUnavailable,
    SqlExecutionFailed,
    build_run_sql_handler,
    evaluate_readonly_sql,
)

STEP = "[STEP]"
STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
WORK_DIR = WORK_ROOT / f"run-{STAMP}"


def log(msg: str) -> None:
    print(f"{msg}", flush=True)


def section(title: str) -> None:
    log("")
    log("=" * 72)
    log(f"== {title}")
    log("=" * 72)


class SqliteAuditWriter:
    """PoC durable audit writer: every §4 field persisted to a SQLite file."""

    DDL = """
    CREATE TABLE IF NOT EXISTS audit_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        audit_id TEXT NOT NULL,
        tool_call_id TEXT NOT NULL,
        tool TEXT NOT NULL,
        tool_version INTEGER NOT NULL,
        user_id INTEGER,
        roles TEXT,
        project_id INTEGER,
        request_payload TEXT,
        outcome TEXT NOT NULL,
        error_code TEXT,
        started_at TEXT,
        finished_at TEXT,
        latency_ms INTEGER,
        budget TEXT,
        refs TEXT
    );
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.records: list[dict] = []
        conn = sqlite3.connect(path)
        try:
            conn.executescript(self.DDL)
            conn.commit()
        finally:
            conn.close()

    def write(self, record: dict) -> str:
        self.records.append(dict(record))
        conn = sqlite3.connect(self.path)
        try:
            conn.execute(
                "INSERT INTO audit_records (audit_id, tool_call_id, tool, tool_version, user_id,"
                " roles, project_id, request_payload, outcome, error_code, started_at,"
                " finished_at, latency_ms, budget, refs) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    str(record.get("audit_id")),
                    str(record.get("tool_call_id")),
                    str(record.get("tool")),
                    int(record.get("tool_version") or 0),
                    record.get("user_id"),
                    json.dumps(record.get("roles"), ensure_ascii=False),
                    record.get("project_id"),
                    json.dumps(record.get("request_payload"), ensure_ascii=False),
                    str(record.get("outcome")),
                    record.get("error_code"),
                    str(record.get("started_at")),
                    str(record.get("finished_at")),
                    record.get("latency_ms"),
                    json.dumps(record.get("budget"), ensure_ascii=False),
                    json.dumps(record.get("refs"), ensure_ascii=False),
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return str(record.get("audit_id"))

    def persisted_count(self) -> int:
        conn = sqlite3.connect(self.path)
        try:
            return int(conn.execute("SELECT COUNT(*) FROM audit_records").fetchone()[0])
        finally:
            conn.close()


class PocSqlExecutionPort:
    """PoC execution port behind the R5-A seam: real SQLite file execution.

    datasource_id -> sqlite file mapping is fixed PoC wiring; datasource-project
    ownership stays an R5-A production-assembly item. Connection opens in SQLite
    URI read-only mode as defense-in-depth demo only (layer-2 DB read-only
    account/transaction is NOT provisioned — registered).
    """

    def __init__(self, datasource_map: dict[int, Path]) -> None:
        self._map = {int(k): v for k, v in datasource_map.items()}
        self.calls: list[dict] = []

    def execute(self, *, project_id: int, datasource_id: int, sql: str, row_limit: int,
                timeout_ms: int, dialect: str | None = None) -> dict:
        self.calls.append({"project_id": project_id, "datasource_id": datasource_id, "sql": sql})
        db_path = self._map.get(int(datasource_id))
        if db_path is None:
            raise SqlDependencyUnavailable("unknown datasource", details={"datasource_id": datasource_id})
        started = time.perf_counter()
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=timeout_ms / 1000)
        try:
            cur = conn.execute(sql)
            cols = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchmany(row_limit + 1)
        except sqlite3.Error as exc:
            raise SqlExecutionFailed(str(type(exc).__name__), details={"sqlite_error_class": type(exc).__name__}) from exc
        finally:
            conn.close()
        truncated = len(rows) > row_limit
        rows = rows[:row_limit]
        return {
            "execution_id": f"poc-exec-{uuid.uuid4().hex[:12]}",
            "columns": [{"name": name, "type": "TEXT"} for name in cols],
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "sql_statement_digest": hashlib.sha256(sql.encode("utf-8")).hexdigest(),
        }


def build_business_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE orders (
                order_id INTEGER PRIMARY KEY,
                customer TEXT NOT NULL,
                amount REAL NOT NULL,
                created_at TEXT NOT NULL
            );
            INSERT INTO orders (customer, amount, created_at) VALUES
                ('华东电网', 1200.50, '2026-10-01'),
                ('南方电网', 860.00, '2026-10-02'),
                ('国家电网', 4300.75, '2026-10-03'),
                ('华电集团', 210.00, '2026-10-04'),
                ('大唐集团', 990.25, '2026-10-05');
            """
        )
        conn.commit()
    finally:
        conn.close()


def strip_sql_fences(text: str) -> str:
    """PoC-level normalization: strip markdown fences if the LLM emitted them."""
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[: -3]
    return text.strip().rstrip(";").strip()


def corrected_vanna_factory(context: AdapterContext, settings) -> object:
    """Copy of CopilotAdapter._default_factory with the :217 missing-self bug fixed.

    Semantics identical to the adapter default: scoped chroma path, siliconflow
    client, silent log, run_sql refusal. ONLY the unbound `OpenAI_Chat.__init__`
    call is corrected. Registered as the fix the implementation line must apply
    to ai_copilot/adapter.py:217.
    """

    from openai import OpenAI
    from vanna.legacy.chromadb.chromadb_vector import ChromaDB_VectorStore
    from vanna.legacy.openai.openai_chat import OpenAI_Chat

    scoped_path = CopilotAdapter._scoped_chroma_path(context)
    client = OpenAI(api_key=settings.api_key.get_secret_value(), base_url=settings.base_url)

    class _TenantVannaFixed(ChromaDB_VectorStore, OpenAI_Chat):
        def __init__(self) -> None:
            ChromaDB_VectorStore.__init__(self, config={"path": str(scoped_path)})
            OpenAI_Chat.__init__(self, client=client, config={"model": settings.model})  # FIXED: bound

        def log(self, message: str, title: str = "Info") -> None:
            return None

        def run_sql(self, sql: str, *args: object, **kwargs: object) -> object:
            raise PermissionError("SQL execution is owned by the R8-A authorized bridge")

    return _TenantVannaFixed()


def main() -> int:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    summary: dict = {"stamp": STAMP, "steps": {}}

    # ---------- 1. fixture: business db + audit db ----------
    section("1. FIXTURE: business SQLite + PoC durable audit writer")
    business_db = WORK_DIR / "business.db"
    audit_db = WORK_DIR / "audit.db"
    build_business_db(business_db)
    audit_writer = SqliteAuditWriter(audit_db)
    log(f"business_db={business_db}")
    log(f"audit_db={audit_db} (poC §4-style fields, production writer out of scope)")

    # ---------- 2. real adapter (siliconflow via datara-backend/.env) ----------
    section("2. REAL ADAPTER: CopilotAdapter + vanna + chroma (per-tenant scoped)")
    adapter_events: list = []
    adapter = CopilotAdapter(
        # vanna_factory=corrected_vanna_factory,  # DEFECT FIXED: default factory now works (adapter.py:217 self added)
        audit_hook=lambda ev: adapter_events.append(ev),
    )
    from ai_copilot.config import get_llm_settings

    settings = get_llm_settings()
    log(f"LLM provider={settings.provider} base_url={settings.base_url} model={settings.model}")
    log(f"api_key configured={bool(settings.api_key and settings.api_key.get_secret_value())}")
    gen_port = build_generate_sql_port(adapter)
    dev_ctx = AdapterContext(user_id=1, project_id=1)
    other_ctx = AdapterContext(user_id=2, project_id=2)
    path_a = adapter.chroma_path / f"project-{dev_ctx.project_id}" / f"user-{dev_ctx.user_id}"
    path_b = adapter.chroma_path / f"project-{other_ctx.project_id}" / f"user-{other_ctx.user_id}"
    log(f"scoped chroma A={path_a}")
    log(f"scoped chroma B={path_b}")
    assert path_a != path_b and adapter.chroma_path in path_a.parents and adapter.chroma_path in path_b.parents
    log("ISOLATION: distinct durable chroma stores per (project,user) — OK")

    # ---------- 3. real vanna training (memory writes into scoped chroma) ----------
    section("3. REAL TRAINING: DDL / documentation / question-SQL into scoped chroma")
    t0 = time.perf_counter()
    adapter.add_ddl(
        "CREATE TABLE orders (order_id INTEGER PRIMARY KEY, customer TEXT NOT NULL,"
        " amount REAL NOT NULL, created_at TEXT NOT NULL);",
        dev_ctx,
    )
    adapter.add_documentation("orders 表存储电网客户订单：customer 为客户名称，amount 为订单金额（元），created_at 为下单时间。", dev_ctx)
    adapter.add_sql("订单表里有多少个订单", "SELECT COUNT(*) AS order_count FROM orders", dev_ctx)
    log(f"training writes OK in {time.perf_counter() - t0:.2f}s (chroma path A)")

    # ---------- 4. NL -> SQL: real generate_sql ----------
    section("4. NL -> SQL: REAL generate_sql via siliconflow")
    question = "订单表里总共有多少个订单？金额合计是多少？"
    t0 = time.perf_counter()
    raw_sql = gen_port.generate(question, user_id=dev_ctx.user_id, project_id=dev_ctx.project_id)
    gen_seconds = time.perf_counter() - t0
    sql = strip_sql_fences(raw_sql)
    allowed, violations = evaluate_readonly_sql(sql)
    log(f"question = {question}")
    log(f"generated SQL ({gen_seconds:.1f}s) = {sql}")
    log(f"read-only gate: allowed={allowed} violations={violations}")
    assert isinstance(sql, str) and sql
    summary["steps"]["generate_sql"] = {"question": question, "sql": sql, "seconds": round(gen_seconds, 1)}
    if not allowed:
        log("FINDING: generated SQL failed the read-only gate — recorded honestly, no faking")
        summary["steps"]["generate_sql"]["gate_violations"] = violations
        return 2

    # ---------- 5. authorized execution via REAL R8-A bridge ----------
    section("5. AUTHORIZED EXECUTION: real R8-A bridge envelope + PoC port")
    port = PocSqlExecutionPort({101: business_db})
    app = create_app(
        "sqlite+pysqlite:///:memory:",
        token_secret="p16-prime-poc-secret",
        ai_bridge_ports=AiBridgePorts(handlers={"run_sql": build_run_sql_handler(port)}, audit_writer=audit_writer),
    )
    client = TestClient(app)
    client.__enter__()
    try:
        with app.state.session_factory() as session:
            dev = UserRepository(session).create(username="dev", password="dev-pass", role=Role.DEV)
            viewer = UserRepository(session).create(username="viewer", password="viewer-pass", role=Role.VIEWER)
            outsider = UserRepository(session).create(username="outsider", password="outsider-pass", role=Role.DEV)
            project = ProjectRecord(name="p16-prime", description="", owner_id=dev.id)
            session.add_all((project,))
            session.commit()
            project_id = project.id
            log(f"users dev={dev.id} viewer={viewer.id} outsider={outsider.id}; project={project_id}")
        tokens = {}
        for username, password in (("dev", "dev-pass"), ("viewer", "viewer-pass"), ("outsider", "outsider-pass")):
            resp = client.post("/api/v1/rebuild/login", json={"username": username, "password": password})
            tokens[username] = {"token": resp.json()["data"]["token"]}

        tool_call_id = f"tc-{uuid.uuid4()}"
        t0 = time.perf_counter()
        resp = client.post(
            "/api/v1/rebuild/ai/tool-calls",
            headers=tokens["dev"],
            json={
                "tool_call_id": tool_call_id,
                "tool": "run_sql",
                "tool_version": 1,
                "params": {"project_id": project_id, "datasource_id": 101, "sql": sql},
                "page_context": {"context_type": "SQL", "context_ref": {"tab": "p16-prime"}},
            },
        )
        exec_seconds = time.perf_counter() - t0
        body = resp.json()
        log(f"run_sql status={body['status']} ({exec_seconds:.2f}s) error={body['error']}")
        assert body["status"] == "SUCCESS", body
        result = body["result"]
        log(f"execution_id={result['execution_id']} columns={result['columns']} rows={result['rows']}")
        log(f"row_count={result['row_count']} truncated={result['truncated']} duration_ms={result['duration_ms']}")
        log(f"sql_statement_digest={result['sql_statement_digest'][:16]}… audit_id={body['audit_id']}")
        assert len(port.calls) == 1
        summary["steps"]["run_sql"] = {
            "tool_call_id": tool_call_id,
            "status": body["status"],
            "result": {k: result[k] for k in ("execution_id", "row_count", "truncated", "duration_ms")},
            "seconds": round(exec_seconds, 2),
        }

        # ---------- 6. result interpretation: REAL siliconflow call ----------
        section("6. RESULT INTERPRETATION: real siliconflow interpretation call")
        from openai import OpenAI

        llm = OpenAI(api_key=settings.api_key.get_secret_value(), base_url=settings.base_url)
        preview_rows = result["rows"][:10]
        t0 = time.perf_counter()
        interp = llm.chat.completions.create(
            model=settings.model,
            messages=[
                {
                    "role": "system",
                    "content": "你是数据分析助手，用简洁中文解释查询结果，不要编造数据。",
                },
                {
                    "role": "user",
                    "content": (
                        f"用户问题：{question}\n执行的 SQL：{sql}\n"
                        f"结果列：{[c['name'] for c in result['columns']]}\n"
                        f"结果行（JSON）：{json.dumps(preview_rows, ensure_ascii=False)}\n"
                        "请给出结果解释。"
                    ),
                },
            ],
        )
        interp_seconds = time.perf_counter() - t0
        interpretation = interp.choices[0].message.content or ""
        log(f"interpretation ({interp_seconds:.1f}s):\n{interpretation}")
        summary["steps"]["interpretation"] = {"text": interpretation, "seconds": round(interp_seconds, 1)}

        # ---------- 7. isolation & sovereignty proofs ----------
        section("7. ISOLATION & SOVEREIGNTY PROOFS")
        resp = client.post(
            "/api/v1/rebuild/ai/tool-calls",
            headers=tokens["outsider"],
            json={
                "tool_call_id": "tc-cross-project",
                "tool": "run_sql",
                "tool_version": 1,
                "params": {"project_id": project_id, "datasource_id": 101, "sql": "SELECT 1"},
            },
        )
        body = resp.json()
        log(f"cross-project run_sql (outsider): status={body['status']} code={body['error']['code']}")
        assert body["status"] == "ERROR" and body["error"]["code"] == "PERMISSION_DENIED"
        assert port.calls and len(port.calls) == 1, "denial must precede dispatch — zero extra port calls"
        log("ISOLATION: cross-project denial precedes dispatch (port untouched) — OK")

        resp = client.post(
            "/api/v1/rebuild/ai/tool-calls",
            headers=tokens["viewer"],
            json={
                "tool_call_id": "tc-viewer",
                "tool": "run_sql",
                "tool_version": 1,
                "params": {"project_id": project_id, "datasource_id": 101, "sql": "SELECT 1"},
            },
        )
        body = resp.json()
        log(f"viewer run_sql (role gate): status={body['status']} code={body['error']['code']}")
        assert body["error"]["code"] == "PERMISSION_DENIED"
        log("ISOLATION: VIEWER lacks RUN_INSTANCE — denied before dispatch — OK")

        resp = client.post(
            "/api/v1/rebuild/ai/tool-calls",
            headers=tokens["dev"],
            json={
                "tool_call_id": "tc-write",
                "tool": "run_sql",
                "tool_version": 1,
                "params": {"project_id": project_id, "datasource_id": 101, "sql": "DELETE FROM orders"},
            },
        )
        body = resp.json()
        log(f"write SQL run_sql: status={body['status']} code={body['error']['code']}")
        assert body["error"]["code"] == "INVALID_PARAMS" and body["error"]["details"]["readonly_policy"]
        assert len(port.calls) == 1, "mutating SQL must be rejected before the port"
        log("READ-ONLY layer-1: DELETE rejected before dispatch, port untouched — OK")

        try:
            # DEFECT FIXED: default factory now works; verify run_sql refusal semantics.
            vclient = CopilotAdapter._default_factory(dev_ctx, settings)
            vclient.run_sql("SELECT 1")
            raise AssertionError("adapter client must refuse SQL execution")
        except PermissionError:
            log("SOVEREIGNTY: vanna-internal run_sql refused (execution owned by authorized bridge) — OK")
        summary["steps"]["isolation"] = {
            "cross_project_denied": True,
            "viewer_denied": True,
            "write_rejected_before_port": True,
            "vanna_run_sql_refused": True,
        }

        # ---------- 8. audit persistence proof ----------
        section("8. AUDIT PERSISTENCE PROOF (PoC durable SQLite writer)")
        audit_rows = conn_dump(audit_db)
        for row in audit_rows:
            log(
                f"audit: tool={row['tool']} outcome={row['outcome']} code={row['error_code']} "
                f"user={row['user_id']} roles={row['roles']} project={row['project_id']} "
                f"latency={row['latency_ms']}ms refs={row['refs']}"
            )
        success_records = [r for r in audit_writer.records if r["outcome"] == "SUCCESS" and r["tool"] == "run_sql"]
        assert success_records, "run_sql SUCCESS must be audited"
        rec = success_records[0]
        assert rec["refs"]["execution_id"] and rec["refs"]["datasource_id"] == 101
        assert rec["budget"]["rows_returned"] == result["row_count"]
        assert rec["tool_call_id"] == tool_call_id and rec["user_id"] == dev.id
        assert rec["roles"] == ["dev"] and rec["project_id"] == project_id
        assert rec["started_at"] and rec["finished_at"] and rec["latency_ms"] is not None
        persisted = SqliteAuditWriter(audit_db).persisted_count()
        log(f"audit records in memory={len(audit_writer.records)} persisted_rows={persisted}")
        assert persisted == len(audit_writer.records), "every audit record must be durably persisted"
        log("AUDIT: tool_call_id/user_id/roles/project_id/refs/budget threaded + persisted — OK")
        summary["steps"]["audit"] = {"records": len(audit_writer.records), "persisted": persisted}

        # ---------- 9. adapter-layer audit events dump ----------
        section("9. ADAPTER-LAYER AUDIT EVENTS (no content fields by design)")
        for ev in adapter_events:
            log(f"adapter-audit: action={ev.action} user={ev.user_id} project={ev.project_id} "
                f"category={ev.object_category} outcome={ev.outcome}")
        started_events = [ev for ev in adapter_events if ev.outcome == "started"]
        succeeded_events = [ev for ev in adapter_events if ev.outcome == "succeeded"]
        assert not any(ev.outcome == "failed" for ev in adapter_events), "no adapter event may fail"
        assert len(started_events) == len(succeeded_events), "every started must have a matching succeeded"
        summary["steps"]["adapter_audit_events"] = len(adapter_events)

        section("RESULT: P1-6' real-chain PoC PASS")
        log(json.dumps(summary, ensure_ascii=False, indent=2))
        (WORK_DIR / "result_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0
    finally:
        client.__exit__(None, None, None)


def conn_dump(audit_db: Path) -> list[dict]:
    conn = sqlite3.connect(audit_db)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM audit_records ORDER BY id")]
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
