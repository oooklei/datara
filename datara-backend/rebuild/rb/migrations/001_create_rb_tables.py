"""R5-B 三表迁移脚本（§2.2）。

依 P2-3 v3 实施设计 §2.2 + S36 勘误②：
统一 ENGINE=InnoDB CHARSET=utf8mb4。

表：
- rb_policy_snapshots
- rb_impact_snapshots
- rb_execution_records
"""
from __future__ import annotations

import sqlite3


def apply(conn: sqlite3.Connection) -> None:
    """应用迁移：创建三张 R5-B 表。"""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS rb_policy_snapshots (
            snapshot_id      VARCHAR(36) PRIMARY KEY,
            project_id       INT NOT NULL,
            datasource_id    INT NOT NULL,
            object_ref       JSON NOT NULL,
            source_version   VARCHAR(128) NOT NULL,
            next_ddl_digest  CHAR(64) NOT NULL,
            policy_version   VARCHAR(32) NOT NULL,
            findings         JSON NOT NULL,
            blocked          BOOLEAN NOT NULL,
            created_at       DATETIME NOT NULL,
            expires_at       DATETIME NOT NULL,
            INDEX idx_project_object (project_id, datasource_id, object_ref(64)),
            INDEX idx_expires (expires_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

        CREATE TABLE IF NOT EXISTS rb_impact_snapshots (
            snapshot_id      VARCHAR(36) PRIMARY KEY,
            project_id       INT NOT NULL,
            datasource_id    INT NOT NULL,
            object_ref       JSON NOT NULL,
            source_version   VARCHAR(128) NOT NULL,
            next_ddl_digest  CHAR(64) NOT NULL,
            policy_snapshot_id  VARCHAR(36) NOT NULL,
            impacts          JSON NOT NULL,
            unknown_reasons  JSON NOT NULL,
            created_at       DATETIME NOT NULL,
            expires_at       DATETIME NOT NULL,
            INDEX idx_policy_snapshot (policy_snapshot_id),
            INDEX idx_expires (expires_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

        CREATE TABLE IF NOT EXISTS rb_execution_records (
            record_id          VARCHAR(36) PRIMARY KEY,
            project_id         INT NOT NULL,
            datasource_id      INT NOT NULL,
            object_ref         JSON NOT NULL,
            action             VARCHAR(64) NOT NULL,
            script_hash        CHAR(64) NOT NULL,
            executed_at        DATETIME NOT NULL,
            status             VARCHAR(32) NOT NULL,
            failure_summary    TEXT,
            policy_snapshot_id VARCHAR(36) NOT NULL,
            impact_snapshot_id VARCHAR(36) NOT NULL,
            compensation_refs  JSON,
            actor_id           INT NOT NULL,
            INDEX idx_project_object (project_id, datasource_id, object_ref(64)),
            INDEX idx_actor (actor_id),
            INDEX idx_executed_at (executed_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)


def rollback(conn: sqlite3.Connection) -> None:
    """回滚迁移：删除三张 R5-B 表。"""
    conn.executescript("""
        DROP TABLE IF EXISTS rb_policy_snapshots;
        DROP TABLE IF EXISTS rb_impact_snapshots;
        DROP TABLE IF EXISTS rb_execution_records;
    """)


if __name__ == "__main__":
    import sys
    db_path = sys.argv[1] if len(sys.argv) > 1 else ":memory:"
    conn = sqlite3.connect(db_path)
    apply(conn)
    conn.commit()
    print(f"Migration applied to {db_path}")
    conn.close()
