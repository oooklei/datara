"""Upgrade legacy per-attempt statistics to the authoritative run snapshot contract."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from sqlalchemy import Engine, inspect, text

revision = "r9_0003_run_snapshot_contract"
down_revision = "r9_0002_run_statistics"
_DDL_MANIFEST = (
    "r9_0003 workflow_run_stat one-per-instance bigint checked counts fk workflow_instance;"
    "reconcile detail unique object pair fk cascade;execution receipt_identity nonnull unique"
)
checksum = hashlib.sha256(_DDL_MANIFEST.encode("utf-8")).hexdigest()

_STAT = "workflow_run_stat"
_DETAIL = "workflow_run_reconcile_detail"
_EVENT = "execution_event"


def upgrade(engine: Engine) -> None:
    if engine.dialect.name == "sqlite":
        _upgrade_sqlite(engine)
    elif engine.dialect.name == "mysql":
        _upgrade_mysql(engine)
    else:
        raise RuntimeError(f"unsupported execution migration dialect: {engine.dialect.name}")


def _columns(engine: Engine, table: str) -> set[str]:
    return {item["name"] for item in inspect(engine).get_columns(table)}


def _upgrade_sqlite(engine: Engine) -> None:
    # SQLite cannot reliably alter nullability, checks, FKs or composite uniques;
    # rebuild all affected tables while FK enforcement is deliberately suspended.
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        transaction = connection.begin()
        try:
            tables = set(inspect(connection).get_table_names())
            if _STAT in tables:
                stat_columns = {item["name"] for item in inspect(connection).get_columns(_STAT)}
                connection.exec_driver_sql(f"ALTER TABLE {_DETAIL} RENAME TO {_DETAIL}_r9_0002")
                connection.exec_driver_sql(f"ALTER TABLE {_STAT} RENAME TO {_STAT}_r9_0002")
                connection.exec_driver_sql("DROP INDEX IF EXISTS x_wrrd_run_stat")
                connection.exec_driver_sql("DROP INDEX IF EXISTS x_wrs_project_created")
                connection.exec_driver_sql("DROP INDEX IF EXISTS x_wrs_workflow_instance")
                connection.exec_driver_sql("DROP INDEX IF EXISTS x_wrs_workflow_started")
                connection.exec_driver_sql("DROP INDEX IF EXISTS x_wrs_type_started")
                _create_sqlite_stat_tables(connection)
                _copy_sqlite_stats(connection, stat_columns)
                _copy_sqlite_details(connection)
                connection.exec_driver_sql(f"DROP TABLE {_DETAIL}_r9_0002")
                connection.exec_driver_sql(f"DROP TABLE {_STAT}_r9_0002")
            event_columns = {item["name"] for item in inspect(connection).get_columns(_EVENT)}
            if "receipt_identity" not in event_columns or not _event_unique_ready(inspect(connection)):
                connection.exec_driver_sql(f"ALTER TABLE {_EVENT} RENAME TO {_EVENT}_r9_0002")
                connection.exec_driver_sql("DROP INDEX IF EXISTS x_ee_instance_kind")
                _create_sqlite_event_table(connection)
                connection.exec_driver_sql(
                    f"""INSERT INTO {_EVENT}
                    (id, workflow_instance_id, task_instance_id, receipt_identity, attempt_no,
                     event_kind, payload_json, event_time, created_at, updated_at, generated_at)
                    SELECT MIN(id), workflow_instance_id, task_instance_id,
                           CASE WHEN task_instance_id IS NULL THEN '__workflow__'
                                ELSE 'task:' || task_instance_id END,
                           attempt_no, event_kind, MAX(payload_json), MIN(event_time),
                           MIN(created_at), MAX(updated_at), MAX(generated_at)
                    FROM {_EVENT}_r9_0002
                    GROUP BY workflow_instance_id,
                             CASE WHEN task_instance_id IS NULL THEN '__workflow__'
                                  ELSE 'task:' || task_instance_id END,
                             attempt_no, event_kind"""
                )
                connection.exec_driver_sql(f"DROP TABLE {_EVENT}_r9_0002")
            transaction.commit()
        except Exception:
            transaction.rollback()
            raise
        finally:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()


def _create_sqlite_stat_tables(connection) -> None:
    connection.exec_driver_sql(
        f"""CREATE TABLE {_STAT} (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL, workflow_id INTEGER NOT NULL,
        workflow_version_id INTEGER NOT NULL,
        workflow_instance_id INTEGER NOT NULL,
        instance_type VARCHAR(16) NOT NULL, status VARCHAR(16) NOT NULL,
        dag_name VARCHAR(256) NOT NULL, data_param_json TEXT,
        source_count BIGINT, target_count BIGINT,
        success_count BIGINT DEFAULT 0 NOT NULL,
        failure_count BIGINT DEFAULT 0 NOT NULL,
        skipped_count BIGINT DEFAULT 0 NOT NULL,
        total_count BIGINT DEFAULT 0 NOT NULL,
        started_at DATETIME NOT NULL, finished_at DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
        generated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
        CONSTRAINT uq_wrs_workflow_instance UNIQUE (workflow_instance_id),
        CONSTRAINT fk_wrs_workflow_instance FOREIGN KEY(workflow_instance_id)
          REFERENCES workflow_instance (id) ON DELETE CASCADE,
        CONSTRAINT ck_wrs_success_nonnegative CHECK (success_count >= 0),
        CONSTRAINT ck_wrs_failure_nonnegative CHECK (failure_count >= 0),
        CONSTRAINT ck_wrs_skipped_nonnegative CHECK (skipped_count >= 0),
        CONSTRAINT ck_wrs_total_consistent CHECK (total_count = success_count + failure_count))"""
    )
    connection.exec_driver_sql(f"CREATE INDEX x_wrs_project_created ON {_STAT} (project_id, created_at)")
    connection.exec_driver_sql(f"CREATE INDEX x_wrs_workflow_started ON {_STAT} (workflow_id, started_at)")
    connection.exec_driver_sql(f"CREATE INDEX x_wrs_type_started ON {_STAT} (instance_type, started_at)")
    connection.exec_driver_sql(
        f"""CREATE TABLE {_DETAIL} (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        run_stat_id INTEGER NOT NULL,
        source_object VARCHAR(256) NOT NULL, target_object VARCHAR(256) NOT NULL,
        source_count BIGINT, target_count BIGINT,
        success_count BIGINT DEFAULT 0 NOT NULL,
        failure_count BIGINT DEFAULT 0 NOT NULL,
        skipped_count BIGINT DEFAULT 0 NOT NULL, difference_count BIGINT,
        data_param_json TEXT, started_at DATETIME, finished_at DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
        generated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
        CONSTRAINT uq_wrrd_object_pair UNIQUE (run_stat_id, source_object, target_object),
        CONSTRAINT fk_wrrd_run_stat FOREIGN KEY(run_stat_id)
          REFERENCES workflow_run_stat (id) ON DELETE CASCADE)"""
    )
    connection.exec_driver_sql(f"CREATE INDEX x_wrrd_run_stat ON {_DETAIL} (run_stat_id)")


def _copy_sqlite_stats(connection, columns: set[str]) -> None:
    def expr(column: str, fallback: str) -> str:
        return f"s.{column}" if column in columns else fallback

    source = expr("source_count", "NULL")
    target = expr("target_count", "NULL")
    data_param = expr("data_param_json", "NULL")
    connection.exec_driver_sql(
        f"""INSERT INTO {_STAT}
        (id, project_id, workflow_id, workflow_version_id, workflow_instance_id,
         instance_type, status, dag_name, data_param_json, source_count, target_count,
         success_count, failure_count, skipped_count, total_count, started_at, finished_at,
         created_at, updated_at, generated_at)
        SELECT MIN(s.id), MIN(s.project_id), MIN(s.workflow_id), MIN(s.workflow_version_id),
               s.workflow_instance_id,
               COALESCE(MIN({expr('instance_type', 'NULL')}), MIN(w.instance_type)),
               COALESCE(MAX({expr('status', 'NULL')}), MAX(w.status)),
               COALESCE(MAX({expr('dag_name', 'NULL')}), 'workflow-' || MIN(s.workflow_id)),
               MAX({data_param}),
               CASE WHEN COUNT({source}) = 0 THEN NULL ELSE SUM({source}) END,
               CASE WHEN COUNT({target}) = 0 THEN NULL ELSE SUM({target}) END,
               SUM(COALESCE(s.success_count, 0)), SUM(COALESCE(s.failure_count, 0)),
               SUM(COALESCE(s.skipped_count, 0)),
               SUM(COALESCE(s.success_count, 0)) + SUM(COALESCE(s.failure_count, 0)),
               COALESCE(MIN({expr('started_at', 'NULL')}), MIN(w.started_at), MIN(s.created_at)),
               MAX({expr('finished_at', 'NULL')}), MIN(s.created_at), MAX(s.updated_at), MAX(s.generated_at)
        FROM {_STAT}_r9_0002 s JOIN workflow_instance w ON w.id = s.workflow_instance_id
        GROUP BY s.workflow_instance_id"""
    )


def _copy_sqlite_details(connection) -> None:
    old_columns = {item["name"] for item in inspect(connection).get_columns(f"{_DETAIL}_r9_0002")}

    def expr(column: str, fallback: str) -> str:
        return f"d.{column}" if column in old_columns else fallback

    connection.exec_driver_sql(
        f"""INSERT INTO {_DETAIL}
        (id, run_stat_id, source_object, target_object, source_count, target_count,
         success_count, failure_count, skipped_count, difference_count, data_param_json,
         started_at, finished_at, created_at, updated_at, generated_at)
        SELECT MIN(d.id), MIN(n.id), d.source_object, d.target_object,
               CASE WHEN COUNT(d.source_count)=0 THEN NULL ELSE SUM(d.source_count) END,
               CASE WHEN COUNT(d.target_count)=0 THEN NULL ELSE SUM(d.target_count) END,
               SUM(COALESCE(d.success_count,0)), SUM(COALESCE(d.failure_count,0)),
               SUM(COALESCE(d.skipped_count,0)),
               CASE WHEN COUNT(d.difference_count)=0 THEN NULL ELSE SUM(d.difference_count) END,
               MAX({expr('data_param_json', 'NULL')}), MIN({expr('started_at', 'NULL')}),
               MAX({expr('finished_at', 'NULL')}), MIN(d.created_at), MAX(d.updated_at), MAX(d.generated_at)
        FROM {_DETAIL}_r9_0002 d
        JOIN {_STAT}_r9_0002 o ON o.id=d.run_stat_id
        JOIN {_STAT} n ON n.workflow_instance_id=o.workflow_instance_id
        GROUP BY n.workflow_instance_id, d.source_object, d.target_object"""
    )


def _create_sqlite_event_table(connection) -> None:
    connection.exec_driver_sql(
        f"""CREATE TABLE {_EVENT} (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        workflow_instance_id INTEGER NOT NULL, task_instance_id INTEGER,
        receipt_identity VARCHAR(64) DEFAULT '__workflow__' NOT NULL,
        attempt_no INTEGER, event_kind VARCHAR(32) NOT NULL, payload_json TEXT,
        event_time DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
        generated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
        CONSTRAINT uq_ee_result_receipt UNIQUE
          (workflow_instance_id, receipt_identity, attempt_no, event_kind))"""
    )
    connection.exec_driver_sql(
        f"CREATE INDEX x_ee_instance_kind ON {_EVENT} (workflow_instance_id, event_kind)"
    )


def _upgrade_mysql(engine: Engine) -> None:
    # MySQL DDL auto-commits. Every statement is guarded by reflected state so a
    # failed deployment can safely resume at the next invocation.
    inspector = inspect(engine)
    with engine.begin() as connection:
        event_columns = {item["name"] for item in inspector.get_columns(_EVENT)}
        if "receipt_identity" not in event_columns:
            connection.execute(text(
                f"ALTER TABLE {_EVENT} ADD COLUMN receipt_identity VARCHAR(64) "
                "NOT NULL DEFAULT '__workflow__' AFTER task_instance_id"
            ))
        connection.execute(text(
            f"UPDATE {_EVENT} SET receipt_identity=CONCAT('task:', task_instance_id) "
            "WHERE task_instance_id IS NOT NULL AND receipt_identity='__workflow__'"
        ))
        uniques = {
            item.get("name"): tuple(item["column_names"])
            for item in inspect(engine).get_unique_constraints(_EVENT)
        }
        if uniques.get("uq_ee_result_receipt") != (
            "workflow_instance_id", "receipt_identity", "attempt_no", "event_kind"
        ):
            if "uq_ee_result_receipt" in uniques:
                connection.execute(text(f"ALTER TABLE {_EVENT} DROP INDEX uq_ee_result_receipt"))
            connection.execute(text(
                f"ALTER TABLE {_EVENT} ADD CONSTRAINT uq_ee_result_receipt UNIQUE "
                "(workflow_instance_id, receipt_identity, attempt_no, event_kind)"
            ))
        # Existing production installs may contain per-attempt rows. Aggregate
        # into temporary tables before destructive changes; temporary tables are
        # connection-scoped, so a failed run can be retried from reflected state.
        stat_columns = {item["name"] for item in inspect(engine).get_columns(_STAT)}
        if "task_identity" in stat_columns:
            connection.execute(text(
                "CREATE TEMPORARY TABLE r9_0003_stat_rollup AS "
                f"SELECT MIN(id) keeper_id, workflow_instance_id, MIN(project_id) project_id, "
                "MIN(workflow_id) workflow_id, MIN(workflow_version_id) workflow_version_id, "
                "MIN(instance_type) instance_type, MAX(status) status, "
                "SUM(source_count) source_count, SUM(target_count) target_count, "
                "SUM(success_count) success_count, SUM(failure_count) failure_count, "
                "SUM(skipped_count) skipped_count, MIN(created_at) started_at, "
                "MAX(finished_at) finished_at, MIN(created_at) created_at, "
                "MAX(updated_at) updated_at, MAX(generated_at) generated_at "
                f"FROM {_STAT} GROUP BY workflow_instance_id"
            ))
            connection.execute(text(
                "CREATE TEMPORARY TABLE r9_0003_detail_rollup AS "
                f"SELECT MIN(d.id) id, r.workflow_instance_id, d.source_object, d.target_object, "
                "SUM(d.source_count) source_count, SUM(d.target_count) target_count, "
                "SUM(d.success_count) success_count, SUM(d.failure_count) failure_count, "
                "SUM(d.skipped_count) skipped_count, SUM(d.difference_count) difference_count, "
                "MIN(d.created_at) created_at, MAX(d.updated_at) updated_at, MAX(d.generated_at) generated_at "
                f"FROM {_DETAIL} d JOIN {_STAT} r ON r.id=d.run_stat_id "
                "GROUP BY r.workflow_instance_id,d.source_object,d.target_object"
            ))
            connection.execute(text(f"DELETE FROM {_DETAIL}"))
            connection.execute(text(f"DELETE FROM {_STAT}"))
            connection.execute(text(
                f"INSERT INTO {_STAT} (id,project_id,workflow_id,workflow_version_id,workflow_instance_id,"
                "task_identity,attempt_no,instance_type,status,source_count,target_count,success_count,"
                "failure_count,skipped_count,started_at,finished_at,created_at,updated_at,generated_at) "
                "SELECT keeper_id,project_id,workflow_id,workflow_version_id,workflow_instance_id,"
                "'__snapshot__',0,instance_type,status,source_count,target_count,success_count,failure_count,"
                "skipped_count,started_at,finished_at,created_at,updated_at,generated_at FROM r9_0003_stat_rollup"
            ))
            connection.execute(text(
                f"INSERT INTO {_DETAIL} (id,run_stat_id,source_object,target_object,source_count,target_count,"
                "success_count,failure_count,skipped_count,difference_count,created_at,updated_at,generated_at) "
                "SELECT d.id,s.id,d.source_object,d.target_object,d.source_count,d.target_count,d.success_count,"
                "d.failure_count,d.skipped_count,d.difference_count,d.created_at,d.updated_at,d.generated_at "
                f"FROM r9_0003_detail_rollup d JOIN {_STAT} s ON s.workflow_instance_id=d.workflow_instance_id"
            ))
            stat_uniques = {
                item.get("name"): tuple(item["column_names"])
                for item in inspect(engine).get_unique_constraints(_STAT)
            }
            if "uq_wrs_instance_task_attempt" in stat_uniques:
                connection.execute(text(f"ALTER TABLE {_STAT} DROP INDEX uq_wrs_instance_task_attempt"))
            if stat_uniques.get("uq_wrs_workflow_instance") != ("workflow_instance_id",):
                connection.execute(text(
                    f"ALTER TABLE {_STAT} ADD CONSTRAINT uq_wrs_workflow_instance "
                    "UNIQUE (workflow_instance_id)"
                ))
            for column in ("task_instance_id", "task_identity", "attempt_no"):
                if column in {item["name"] for item in inspect(engine).get_columns(_STAT)}:
                    connection.execute(text(f"ALTER TABLE {_STAT} DROP COLUMN {column}"))
        additions = {
            "dag_name": "VARCHAR(256) NOT NULL DEFAULT ''",
            "data_param_json": "TEXT NULL",
            "total_count": "BIGINT NOT NULL DEFAULT 0",
        }
        current = {item["name"] for item in inspect(engine).get_columns(_STAT)}
        for column, ddl in additions.items():
            if column not in current:
                connection.execute(text(f"ALTER TABLE {_STAT} ADD COLUMN {column} {ddl}"))
        detail_additions = {
            "data_param_json": "TEXT NULL",
            "started_at": "DATETIME NULL",
            "finished_at": "DATETIME NULL",
        }
        detail_current = {item["name"] for item in inspect(engine).get_columns(_DETAIL)}
        for column, ddl in detail_additions.items():
            if column not in detail_current:
                connection.execute(text(f"ALTER TABLE {_DETAIL} ADD COLUMN {column} {ddl}"))
        connection.execute(text(
            f"UPDATE {_STAT} SET total_count=success_count+failure_count, "
            "dag_name=IF(dag_name='', CONCAT('workflow-', workflow_id), dag_name), "
            "started_at=COALESCE(started_at,created_at)"
        ))
        for column in ("source_count", "target_count"):
            connection.execute(text(f"ALTER TABLE {_STAT} MODIFY {column} BIGINT NULL"))
        for column in ("success_count", "failure_count", "skipped_count", "total_count"):
            connection.execute(text(f"ALTER TABLE {_STAT} MODIFY {column} BIGINT NOT NULL DEFAULT 0"))
        connection.execute(text(f"ALTER TABLE {_STAT} MODIFY started_at DATETIME NOT NULL"))
        for column in ("source_count", "target_count", "difference_count"):
            connection.execute(text(f"ALTER TABLE {_DETAIL} MODIFY {column} BIGINT NULL"))
        for column in ("success_count", "failure_count", "skipped_count"):
            connection.execute(text(f"ALTER TABLE {_DETAIL} MODIFY {column} BIGINT NOT NULL DEFAULT 0"))
        stat_foreign_keys = {
            tuple(item["constrained_columns"]): item for item in inspect(engine).get_foreign_keys(_STAT)
        }
        if ("workflow_instance_id",) not in stat_foreign_keys:
            connection.execute(text(
                f"ALTER TABLE {_STAT} ADD CONSTRAINT fk_wrs_workflow_instance "
                "FOREIGN KEY (workflow_instance_id) REFERENCES workflow_instance(id) ON DELETE CASCADE"
            ))
        detail_foreign_keys = {
            tuple(item["constrained_columns"]): item for item in inspect(engine).get_foreign_keys(_DETAIL)
        }
        if ("run_stat_id",) not in detail_foreign_keys:
            connection.execute(text(
                f"ALTER TABLE {_DETAIL} ADD CONSTRAINT fk_wrrd_run_stat "
                "FOREIGN KEY (run_stat_id) REFERENCES workflow_run_stat(id) ON DELETE CASCADE"
            ))
        stat_indexes = {item["name"] for item in inspect(engine).get_indexes(_STAT)}
        for name, columns in (
            ("x_wrs_project_created", "project_id, created_at"),
            ("x_wrs_workflow_started", "workflow_id, started_at"),
            ("x_wrs_type_started", "instance_type, started_at"),
        ):
            if name not in stat_indexes:
                connection.execute(text(f"CREATE INDEX {name} ON {_STAT} ({columns})"))
        checks = {item.get("name") for item in inspect(engine).get_check_constraints(_STAT)}
        for name, expression in (
            ("ck_wrs_success_nonnegative", "success_count >= 0"),
            ("ck_wrs_failure_nonnegative", "failure_count >= 0"),
            ("ck_wrs_skipped_nonnegative", "skipped_count >= 0"),
            ("ck_wrs_total_consistent", "total_count = success_count + failure_count"),
        ):
            if name not in checks:
                connection.execute(text(f"ALTER TABLE {_STAT} ADD CONSTRAINT {name} CHECK ({expression})"))


def _normal(sql: str | None) -> str:
    return re.sub(r"[\s`()]+", "", (sql or "").lower())


def _type_ready(column: dict[str, Any], family: str, length: int | None = None) -> bool:
    column_type = column["type"]
    if column_type.__class__.__name__.upper() != family:
        return False
    return length is None or getattr(column_type, "length", None) == length


def _fk_ready(inspector, table: str, columns: tuple[str, ...], referent: str) -> bool:
    for foreign_key in inspector.get_foreign_keys(table):
        if tuple(foreign_key["constrained_columns"]) != columns:
            continue
        ondelete = (foreign_key.get("options") or {}).get("ondelete", "")
        if foreign_key.get("referred_table") == referent and str(ondelete).upper() == "CASCADE":
            return True
    if inspector.bind.dialect.name == "sqlite" and len(columns) == 1:
        with inspector.bind.connect() as connection:
            rows = connection.exec_driver_sql(f"PRAGMA foreign_key_list({table})").mappings()
            return any(
                row["from"] == columns[0]
                and row["table"] == referent
                and str(row["on_delete"]).upper() == "CASCADE"
                for row in rows
            )
    return False


def _unique_ready(inspector, table: str, columns: tuple[str, ...]) -> bool:
    constraints = {tuple(item["column_names"]) for item in inspector.get_unique_constraints(table)}
    unique_indexes = {
        tuple(item["column_names"]) for item in inspector.get_indexes(table) if item.get("unique")
    }
    return columns in constraints | unique_indexes


def _event_unique_ready(inspector) -> bool:
    return _unique_ready(
        inspector, _EVENT, ("workflow_instance_id", "receipt_identity", "attempt_no", "event_kind")
    )


def postflight(engine: Engine) -> dict[str, object]:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if not {_STAT, _DETAIL, _EVENT} <= tables:
        return {"verdict": "BLOCKED", "reason": "missing tables"}
    stat = {item["name"]: item for item in inspector.get_columns(_STAT)}
    detail = {item["name"]: item for item in inspector.get_columns(_DETAIL)}
    event = {item["name"]: item for item in inspector.get_columns(_EVENT)}
    required_stat = {
        "id", "project_id", "workflow_id", "workflow_version_id", "workflow_instance_id",
        "instance_type", "status", "dag_name", "data_param_json", "source_count", "target_count",
        "success_count", "failure_count", "skipped_count", "total_count", "started_at", "finished_at",
        "created_at", "updated_at", "generated_at",
    }
    required_detail = {
        "id", "run_stat_id", "source_object", "target_object", "source_count", "target_count",
        "success_count", "failure_count", "skipped_count", "difference_count", "data_param_json",
        "started_at", "finished_at", "created_at", "updated_at", "generated_at",
    }
    ready = required_stat == set(stat) and required_detail == set(detail)
    ready = ready and {"receipt_identity", "attempt_no", "event_kind", "workflow_instance_id"} <= set(event)
    if ready:
        ready = _type_ready(stat["instance_type"], "VARCHAR", 16)
        ready = ready and _type_ready(stat["status"], "VARCHAR", 16)
        ready = ready and _type_ready(stat["dag_name"], "VARCHAR", 256)
        ready = ready and all(
            _type_ready(stat[name], "BIGINT") for name in
            ("source_count", "target_count", "success_count", "failure_count", "skipped_count", "total_count")
        )
        ready = ready and _type_ready(event["receipt_identity"], "VARCHAR", 64)
        ready = ready and _type_ready(detail["source_object"], "VARCHAR", 256)
        ready = ready and _type_ready(detail["target_object"], "VARCHAR", 256)
        ready = ready and all(
            _type_ready(detail[name], "BIGINT") for name in
            ("source_count", "target_count", "success_count", "failure_count", "skipped_count", "difference_count")
        )
        required_nonnull = {
            "id", "project_id", "workflow_id", "workflow_version_id", "workflow_instance_id",
            "instance_type", "status", "dag_name", "success_count", "failure_count", "skipped_count",
            "total_count", "started_at", "created_at", "updated_at", "generated_at",
        }
        ready = ready and all(not stat[name]["nullable"] for name in required_nonnull)
        ready = ready and not event["receipt_identity"]["nullable"]
        ready = ready and all(
            not detail[name]["nullable"] for name in
            ("id", "run_stat_id", "source_object", "target_object", "success_count", "failure_count",
             "skipped_count", "created_at", "updated_at", "generated_at")
        )
        ready = ready and inspector.get_pk_constraint(_STAT).get("constrained_columns") == ["id"]
        ready = ready and inspector.get_pk_constraint(_DETAIL).get("constrained_columns") == ["id"]
        ready = ready and _fk_ready(inspector, _STAT, ("workflow_instance_id",), "workflow_instance")
        ready = ready and _fk_ready(inspector, _DETAIL, ("run_stat_id",), _STAT)
        ready = ready and _unique_ready(inspector, _STAT, ("workflow_instance_id",))
        ready = ready and _unique_ready(inspector, _DETAIL, ("run_stat_id", "source_object", "target_object"))
        ready = ready and _event_unique_ready(inspector)
        indexes = {tuple(item["column_names"]) for item in inspector.get_indexes(_STAT)}
        ready = ready and {
            ("project_id", "created_at"), ("workflow_id", "started_at"), ("instance_type", "started_at")
        } <= indexes
        detail_indexes = {tuple(item["column_names"]) for item in inspector.get_indexes(_DETAIL)}
        ready = ready and ("run_stat_id",) in detail_indexes
        ready = ready and all(stat[name].get("default") is not None for name in
                              ("success_count", "failure_count", "skipped_count", "total_count"))
        ready = ready and all(detail[name].get("default") is not None for name in
                              ("success_count", "failure_count", "skipped_count"))
        ready = ready and event["receipt_identity"].get("default") is not None
        checks = {_normal(item.get("sqltext")) for item in inspector.get_check_constraints(_STAT)}
        ready = ready and {
            "success_count>=0", "failure_count>=0", "skipped_count>=0",
            "total_count=success_count+failure_count",
        } <= checks
    return {"verdict": "READY" if ready else "BLOCKED", "tables": [_STAT, _DETAIL, _EVENT]}

