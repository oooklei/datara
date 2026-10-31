"""FileSyncRuntimeAdapter tests — 2026-10-28 裁决「file_sync 补文件源驱动」.

Covers: CSV read via shared-volume FileSpec, autoCreate DDL + batch write into
a DB-API target (sqlite compat stub), prepare_sync_execution file-source
relaxation, and the factory routing decision.
"""

import json
import sqlite3
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from rebuild.common.db import Base
from common import dsconn
from rebuild.sync.executor import SyncExecutionSpec, prepare_sync_execution
from rebuild.sync.file_runtime import FileSyncRuntimeAdapter, build_sync_driver_factory

# ProjectDatasourceRecord.project_id 的 FK 指向 rebuild_project：
# import 项目模型把表注册进 Base.metadata，否则 create_all 报 NoReferencedTableError
import rebuild.project.models  # noqa: F401


MAPPINGS = (
    {
        "source_column": "id",
        "target_column": "id",
        "source_type": "integer",
        "target_type": "integer",
        "transform_expression": "",
        "mapping_status": "AUTO",
        "nullable": False,
        "default_value": None,
    },
    {
        "source_column": "name",
        "target_column": "name",
        "source_type": "string",
        "target_type": "string",
        "transform_expression": "",
        "mapping_status": "AUTO",
        "nullable": True,
        "default_value": None,
    },
    {
        "source_column": "amount",
        "target_column": "amount",
        "source_type": "number",
        "target_type": "number",
        "transform_expression": "",
        "mapping_status": "AUTO",
        "nullable": True,
        "default_value": None,
    },
)


class _CursorCompat:
    def __init__(self, inner: sqlite3.Cursor) -> None:
        self._inner = inner

    def execute(self, sql: str, params=None):
        return self._inner.execute(sql.replace("%s", "?"), params or ())

    def executemany(self, sql: str, seq):
        return self._inner.executemany(sql.replace("%s", "?"), seq)

    def close(self) -> None:
        self._inner.close()

    @property
    def description(self):
        return self._inner.description


class _ConnectionCompat:
    """sqlite3 → DB-API (%s placeholder) 兼容桩：验证写侧 DDL/DML 拼接。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def cursor(self):
        return _CursorCompat(self._conn.cursor())

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        # 池语义：close = 归还适配桩，不真关共享底层连接（:memory: 一关即库销毁）
        pass


@pytest.fixture()
def file_root(tmp_path, monkeypatch):
    root = tmp_path / "files"
    root.mkdir()
    monkeypatch.setattr(dsconn, "FILES_ROOT", root)
    return root


def _spec(tmp_relative: str = "orders.csv") -> SyncExecutionSpec:
    return SyncExecutionSpec(
        project_id=1,
        workflow_id=9,
        workflow_version=1,
        task_id="sys_exec_ep1",
        source={"file_path": tmp_relative, "schema": "file", "object": "orders.csv"},
        target={"datasource_id": 3, "schema": "main", "object": "orders"},
        mappings=MAPPINGS,
        transform_config={},
        target_properties={},
    )


def _driver(file_params_overrides: dict | None = None) -> tuple[FileSyncRuntimeAdapter, sqlite3.Connection]:
    conn = sqlite3.connect(":memory:")
    # host/port/username/password：写侧 _connect → _draft 必读字段
    target_record = SimpleNamespace(
        kind="sqlite", project_id=1, id=3, database_name="main", name="tgt",
        host="", port=0, username="", password="",
    )

    def connector_factory(project_id: int, datasource_id: int):
        return lambda draft: _ConnectionCompat(conn)

    params = {
        "filePath": "orders.csv",
        "fileType": "csv",
        "fileEncoding": "utf-8",
        "fileDelimiter": ",",
        "fileHeaderRows": 1,
        "autoCreate": True,
    }
    params.update(file_params_overrides or {})
    driver = FileSyncRuntimeAdapter(
        file_params=params,
        target_record=target_record,
        connector_factory=connector_factory,
    )
    return driver, conn


def test_prepare_sync_execution_relaxes_file_source():
    snapshot = {
        "project_id": 1,
        "workflow_id": 9,
        "workflow_version": 1,
        "task_id": "sys_exec_ep1",
        "source": {"file_path": "orders.csv", "schema": "file", "object": "orders.csv"},
        "target": {"datasource_id": 3, "schema": "main", "object": "orders"},
        "mappings": [dict(m) for m in MAPPINGS],
    }
    spec = prepare_sync_execution(snapshot, allow_file_source=True)
    assert spec.source["file_path"] == "orders.csv"
    with pytest.raises(ValueError, match="datasource_id"):
        prepare_sync_execution(snapshot)


def test_file_driver_reads_csv_rows(file_root: "object"):
    (file_root / "orders.csv").write_text(
        "id,name,amount\n1,Ada,10.5\n2,Bob,20\n", encoding="utf-8"
    )
    driver, _conn = _driver()
    rows = list(driver.read_rows(_spec(), batch_size=10))
    assert [dict(r) for r in rows] == [
        {"id": "1", "name": "Ada", "amount": "10.5"},
        {"id": "2", "name": "Bob", "amount": "20"},
    ]


def test_file_driver_writes_with_autocreate(file_root: "object"):
    (file_root / "orders.csv").write_text(
        "id,name,amount\n1,Ada,10.5\n2,Bob,20\n", encoding="utf-8"
    )
    driver, conn = _driver()
    rows = [dict(r) for r in driver.read_rows(_spec(), batch_size=10)]
    result = driver.write_batch(_spec(), rows)
    assert result.success == 2
    assert result.inserted == 2
    cur = conn.execute("SELECT id, name, amount FROM main.orders ORDER BY id")
    assert cur.fetchall() == [(1, "Ada", 10.5), (2, "Bob", 20)]
    conn.close()


def test_file_driver_header_rows_skips_extra_lines(file_root: "object"):
    (file_root / "orders.csv").write_text(
        "# generated 2026-10-28\nid,name,amount\n1,Ada,10.5\n", encoding="utf-8"
    )
    driver, _conn = _driver({"fileHeaderRows": 2})
    rows = list(driver.read_rows(_spec(), batch_size=10))
    assert [dict(r) for r in rows] == [{"id": "1", "name": "Ada", "amount": "10.5"}]


def test_factory_routes_file_sync_snapshot():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    factory = build_sync_driver_factory(session, lambda pid, dsid: (lambda draft: None))
    snapshot = {
        "project_id": 1,
        "filePath": "orders.csv",
        "fileType": "csv",
        "tgtDs": 3,
        "tgtTable": "main.orders",
        "mappings": [dict(m) for m in MAPPINGS],
    }
    from rebuild.datasource.repository import ProjectDatasourceRepository

    repo = ProjectDatasourceRepository(session)
    # 项目 1 无数据源 3 → 目标缺失报错（路由本身命中 file 分支）
    with pytest.raises(ValueError, match="file_sync target datasource"):
        factory(snapshot)
    assert repo is not None


def test_factory_file_driver_synthesizes_refs():
    """有目标数据源记录时：factory 合成 source/target 并返回文件驱动。"""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    # 种一个项目数据源记录
    from rebuild.datasource.models import ProjectDatasourceRecord

    session.add(
        ProjectDatasourceRecord(
            project_id=1,
            name="tgt",
            kind="sqlite",
            host="",
            port=0,
            database_name="main",
            username="",
            password="",
        )
    )
    session.commit()
    factory = build_sync_driver_factory(session, lambda pid, dsid: (lambda draft: None))
    snapshot = {
        "project_id": 1,
        "workflow_id": 9,
        "workflow_version": 1,
        "task_id": "sys_exec_ep1",
        "filePath": "orders.csv",
        "fileType": "csv",
        "tgtDs": 1,
        "tgtTable": "main.orders",
        "mappings": [dict(m) for m in MAPPINGS],
    }
    driver = factory(snapshot)
    assert isinstance(driver, FileSyncRuntimeAdapter)
    # 合成引用已写回快照（prepare 校验消费）
    assert snapshot["source"]["file_path"] == "orders.csv"
    assert snapshot["target"] == {"datasource_id": 1, "schema": "main", "object": "orders"}
    _ = json  # 保持 json import 语义（快照序列化由上游负责）
