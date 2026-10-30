"""dbx 数据源同步适配层单元测试。

覆盖：上行字段映射与归属标记、下行归属过滤、E1b 冲突策略、时间戳缺失降级、
敏感字段脱敏。测试自包含（自建 sqlite 内存库），不依赖 ``tests/conftest.py``。
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# 让 ``rebuild`` 包可被导入（pytest 默认只把本测试目录加入 sys.path）。
_BACKEND = Path(__file__).resolve().parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from rebuild.datasource.dbx_sync import (  # noqa: E402
    DBX_REF_KEY,
    DBX_UPDATED_AT_KEY,
    DbxConnectionClient,
    _SYNC_STATE_STORE,
    poll_dbx_connections,
    push_datasource_to_dbx,
    resolve_conflict,
)
from rebuild.datasource.models import ProjectDatasourceRecord  # noqa: E402
from rebuild.datasource.repository import ProjectDatasourceRepository  # noqa: E402
# 注册 FK 目标表 rebuild_project，使 project_id 列类型可解析
from rebuild.project.models import ProjectRecord  # noqa: E402, F401

_LOGGER = "rebuild.datasource.dbx_sync"


@pytest.fixture()
def session_factory():
    """sqlite 内存库 + 数据源表；StaticPool 保证建表对所有会话可见。"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    ProjectDatasourceRecord.__table__.create(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    engine.dispose()


def _record(**overrides):
    """构造 datara 数据源记录（瞬态对象，不入库）。"""
    fields = {
        "id": 1,
        "project_id": 3,
        "name": "warehouse",
        "kind": "mysql",
        "host": "mysql-host",
        "port": 3306,
        "database_name": "analytics",
        "username": "reader",
        "password": "s3cret-pw",
        "updated_at": datetime(2026, 1, 1, 12, 0, 0),
    }
    fields.update(overrides)
    return ProjectDatasourceRecord(**fields)


def _remote(
    ref,
    *,
    name="warehouse",
    host="mysql-host",
    port=3306,
    database="analytics",
    db_type="mysql",
    username="reader",
    password="pw",
    datara_updated_at=None,
):
    params = {}
    if ref is not None:
        params[DBX_REF_KEY] = ref
    if datara_updated_at is not None:
        params[DBX_UPDATED_AT_KEY] = datara_updated_at
    return {
        "id": "dbx-1",
        "name": name,
        "db_type": db_type,
        "host": host,
        "port": port,
        "database": database,
        "username": username,
        "password": password,
        "external_config": params,
    }


def _recording_transport(saved):
    """记录每次 HTTP 调用的 method/url/body 并返回成功响应。"""

    def transport(method, url, body, headers):  # noqa: ANN001, ANN002, ANN003, ANN202
        saved.append(
            {
                "method": method,
                "url": url,
                "body": json.loads(body.decode("utf-8")) if body else None,
            }
        )
        return {"ok": True}

    return transport


def _list_transport(connections):
    def transport(method, url, body, headers):  # noqa: ANN001, ANN002, ANN003, ANN202
        # dbx 的 load_connections 返回裸 JSON 数组（Json<Vec<ConnectionConfig>>）。
        return connections

    return transport


def _raising_transport():
    def transport(method, url, body, headers):  # noqa: ANN001, ANN002, ANN003, ANN202
        raise OSError("connection refused")

    return transport


def test_push_maps_fields_and_writes_ownership_markers():
    record = _record()
    saved: list[dict] = []
    client = DbxConnectionClient(transport=_recording_transport(saved))

    assert push_datasource_to_dbx(record, client=client) is True
    assert len(saved) == 1
    call = saved[0]
    assert call["method"] == "POST"
    # dbx 以 DBX_PUBLIC_BASE_PATH=/ide 运行，API 挂在 /api 下。
    assert call["url"].endswith("/ide/api/connection/save")
    payload = call["body"]
    # SaveConnectionsRequest 带 camelCase：configs / removedIds。
    assert payload["removedIds"] == []
    connection = payload["configs"][0]
    # 字段映射
    assert connection["name"] == "warehouse"
    assert connection["db_type"] == "mysql"
    assert connection["host"] == "mysql-host"
    assert connection["port"] == 3306
    assert connection["database"] == "analytics"
    assert connection["username"] == "reader"
    assert connection["password"] == "s3cret-pw"
    # 归属标记承载在 external_config（url_params 会被驱动拒绝）
    assert connection["external_config"][DBX_REF_KEY] == "3:1"
    assert connection["external_config"][DBX_UPDATED_AT_KEY]
    assert "url_params" not in connection


def test_push_records_sync_state_with_remote_key():
    """上行成功后登记同步状态（对端标识 + 上次同步时间），闭合设计 Storage 要求。"""
    record = _record()
    saved: list[dict] = []
    client = DbxConnectionClient(transport=_recording_transport(saved))

    assert push_datasource_to_dbx(record, client=client) is True

    state = _SYNC_STATE_STORE.get(3, 1)
    assert state is not None
    assert state.remote_key == "datara-3-1"
    assert state.name == "warehouse"
    assert state.last_synced_at is not None
    assert state.conflict_flag is False


def test_poll_records_sync_state_for_create_and_conflict(session_factory):
    """下行回灌后登记状态：新建无冲突、远端覆盖本地时置 conflict_flag。"""
    # 先放一条本地记录，远端带更新戳 → 覆盖本地（conflict=True）
    with session_factory() as session:
        session.add(
            _record(
                id=7,
                project_id=33,
                name="warehouse",
                host="old-host",
                updated_at=datetime(2026, 1, 1, 12, 0, 0),
            )
        )
        session.commit()
    connections = [
        _remote(
            "33:7",
            name="warehouse",
            host="new-host",
            datara_updated_at="2026-01-01T13:00:00",
        ),
        _remote("33:41", name="reporting", port=5432),
    ]
    client = DbxConnectionClient(transport=_list_transport(connections))

    synced = poll_dbx_connections(33, client=client, session_factory=session_factory)

    assert synced == 2
    created = _SYNC_STATE_STORE.get(33, 41)
    assert created is not None
    assert created.name == "reporting"
    assert created.remote_key == "dbx-1"
    assert created.conflict_flag is False
    assert created.last_synced_at is not None

    overwritten = _SYNC_STATE_STORE.get(33, 7)
    assert overwritten is not None
    assert overwritten.name == "warehouse"
    assert overwritten.conflict_flag is True


def test_push_maps_postgresql_kind_to_dbx_postgres():
    record = _record(kind="postgresql")
    saved: list[dict] = []
    client = DbxConnectionClient(transport=_recording_transport(saved))

    assert push_datasource_to_dbx(record, client=client) is True
    connection = saved[0]["body"]["configs"][0]
    # dbx 的 DatabaseType 是 postgres，不是 postgresql。
    assert connection["db_type"] == "postgres"


def test_poll_imports_only_datara_owned_connections(session_factory):
    # 3 条连接：2 条含 datara_ref（3:1 / 3:2），1 条无归属标记
    connections = [
        _remote("3:1", name="warehouse"),
        _remote("3:2", name="reporting", port=5432),
        _remote(None, name="external", db_type="postgres"),
    ]
    client = DbxConnectionClient(transport=_list_transport(connections))

    synced = poll_dbx_connections(3, client=client, session_factory=session_factory)

    assert synced == 2
    with session_factory() as session:
        names = sorted(
            record.name for record in ProjectDatasourceRepository(session).list_for_project(3)
        )
    assert names == ["reporting", "warehouse"]


def test_resolve_conflict_prefers_newer_timestamp():
    local = _record(updated_at=datetime(2026, 1, 1, 12, 0, 0))
    older = _remote("3:1", datara_updated_at="2026-01-01T11:00:00")
    newer = _remote("3:1", datara_updated_at="2026-01-01T13:00:00")

    assert resolve_conflict(local, older) == "local"
    assert resolve_conflict(local, newer) == "remote"


def test_resolve_conflict_falls_back_to_four_tuple_when_timestamp_missing():
    local = _record(updated_at=datetime(2026, 1, 1, 12, 0, 0))
    # 无 datara_updated_at，且四元组一致 → datara 优先
    same = _remote("3:1")
    assert resolve_conflict(local, same) == "local"
    # 四元组不一致 → 远端胜
    changed = _remote("3:1", host="other-host")
    assert resolve_conflict(local, changed) == "remote"


def test_password_is_not_logged(caplog):
    record = _record()
    client = DbxConnectionClient(transport=_raising_transport())

    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        assert push_datasource_to_dbx(record, client=client) is False

    assert "dbx_push_failed" in caplog.text
    assert "s3cret-pw" not in caplog.text


def test_poll_falls_back_to_name_when_ref_id_missing(session_factory):
    """ref 指向的 id 本地不存在，但存在同名记录 → 按冲突策略更新，不新增。"""
    with session_factory() as session:
        session.add(
            _record(
                id=34,
                project_id=33,
                name="warehouse",
                host="old-host",
                updated_at=datetime(2026, 1, 1, 12, 0, 0),
            )
        )
        session.commit()
    client = DbxConnectionClient(
        transport=_list_transport(
            [
                _remote(
                    "33:41",
                    name="warehouse",
                    host="new-host",
                    datara_updated_at="2026-01-01T13:00:00",
                )
            ]
        )
    )

    synced = poll_dbx_connections(33, client=client, session_factory=session_factory)

    assert synced == 1
    with session_factory() as session:
        records = ProjectDatasourceRepository(session).list_for_project(33)
    assert len(records) == 1
    assert records[0].id == 34
    assert records[0].host == "new-host"


def test_poll_second_round_does_not_duplicate_or_raise(session_factory):
    """ref 指向的 id 本地不存在且无同名记录 → 首次新建；再次轮询不重复建号。"""
    connections = [_remote("33:41", name="warehouse", host="mysql-host")]
    client = DbxConnectionClient(transport=_list_transport(connections))

    first = poll_dbx_connections(33, client=client, session_factory=session_factory)
    assert first == 1
    with session_factory() as session:
        assert len(ProjectDatasourceRepository(session).list_for_project(33)) == 1

    # 第二轮：ref 仍指向不存在的 41，但同名记录已存在 → 走冲突策略，不撞唯一约束。
    second = poll_dbx_connections(33, client=client, session_factory=session_factory)

    assert second == 0
    with session_factory() as session:
        records = ProjectDatasourceRepository(session).list_for_project(33)
    assert len(records) == 1


def test_poll_isolates_bad_connection_and_keeps_syncing(session_factory):
    """一批连接中混入会触发唯一约束冲突的坏连接 → 不抛异常，好连接仍处理。"""
    with session_factory() as session:
        session.add(
            _record(
                id=1,
                project_id=33,
                name="alpha",
                updated_at=datetime(2026, 1, 1, 12, 0, 0),
            )
        )
        session.add(
            _record(
                id=2,
                project_id=33,
                name="warehouse",
                updated_at=datetime(2026, 1, 1, 12, 0, 0),
            )
        )
        session.commit()
    # 两条远端连接同名 "warehouse"：good 命中 id=2（同名更新，无冲突）；
    # bad 命中 id=1（alpha）却被改名成 "warehouse" → 撞 uq 唯一约束。
    connections = [
        _remote("33:2", name="warehouse", datara_updated_at="2026-01-01T13:00:00"),
        _remote("33:1", name="warehouse", datara_updated_at="2026-01-01T13:00:00"),
    ]
    client = DbxConnectionClient(transport=_list_transport(connections))

    synced = poll_dbx_connections(33, client=client, session_factory=session_factory)

    assert synced >= 1
    with session_factory() as session:
        records = ProjectDatasourceRepository(session).list_for_project(33)
    assert len(records) == 2
    by_id = {record.id: record for record in records}
    # 坏连接被回滚：id=1 仍为 alpha
    assert by_id[1].name == "alpha"
    assert by_id[2].name == "warehouse"
