import json

from common.db import new_session
from common.models import DataSource
from worker.executor import TaskContext
from worker.executors import sql as sql_executor

session = new_session()
try:
    datasource = session.query(DataSource).filter(DataSource.type.in_(["mysql", "greatdb", "doris", "starrocks"])).first()
    if datasource is None:
        raise RuntimeError("no MySQL-compatible datasource is configured")
    datasource_name = datasource.name
finally:
    session.close()

logs = []


def run(statement):
    context = TaskContext(
        task_id="sql-live-probe",
        instance_id="sql-live-probe",
        node_type="sql",
        name="SQL live probe",
        attempt=1,
        param={"datasource": datasource_name, "sql": statement, "transaction": "none"},
        hidden_inputs={},
        constraints={},
        log=logs.append,
        killed=lambda: False,
    )
    return sql_executor.execute(context)


first = run("SELECT 1 AS value")
if first.state != "success" or first.outputs.get("row_count") != 1:
    raise RuntimeError("read-only SQL probe failed")
pooled_after_read = len(sql_executor._conn_pool)
second = run("SET @datara_live_probe = 1")
if second.state != "success":
    raise RuntimeError("session-affecting SQL probe failed")
pooled_after_session_statement = len(sql_executor._conn_pool)
if pooled_after_read != 1 or pooled_after_session_statement != 0:
    raise RuntimeError(
        "connection reuse safety invariant failed: "
        f"read={pooled_after_read}, session={pooled_after_session_statement}"
    )
print(json.dumps({
    "state": "success",
    "row_count": first.outputs["row_count"],
    "pool_after_read": pooled_after_read,
    "pool_after_session_statement": pooled_after_session_statement,
    "log_count": len(logs),
}, separators=(",", ":")))
