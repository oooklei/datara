"""SQLAlchemy 2.0 引擎与会话（PyMySQL）。

- 懒加载引擎（首次使用才建连接池，内存优化）
- init_db()：create_all 兜底建表 —— 除 01_meta.sql 外的第二道幂等保障
"""

import threading
from typing import Iterator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from common.config import get_settings
from common.log import get_logger

logger = get_logger("common.db")

_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker] = None
_lock = threading.Lock()


def get_engine() -> Engine:
    """双重检查懒加载引擎（线程安全，pool_pre_ping 防连失效）。"""
    global _engine, _session_factory
    if _engine is None:
        with _lock:
            if _engine is None:
                settings = get_settings()
                _engine = create_engine(
                    settings.db_url,
                    pool_pre_ping=True,  # 取连接前探活，避免 MySQL 8h 断连
                    pool_recycle=3600,
                    pool_size=5,
                    max_overflow=10,
                )
                _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def new_session() -> Session:
    """新建一个会话（调度/执行等非 FastAPI 场景用，调用方自行 close）。"""
    get_engine()
    assert _session_factory is not None
    return _session_factory()


def get_db() -> Iterator[Session]:
    """FastAPI 依赖：请求级会话，用完即关（资源及时释放）。"""
    session = new_session()
    try:
        yield session
    finally:
        session.close()


def seed_dict_tables(session) -> None:
    """I18 字典种子：分层/业务域/引擎（幂等，存在即跳过）。

    分层/规范文案对齐 prototype/assets/data.js DB.dwLayers。
    """
    from common.models import BizDomain, DwLayer, EngineType

    if session.query(DwLayer).count() == 0:
        session.add_all([
            DwLayer(code="ODS", name="原始数据层", rule="ods_源库名_源表名，保留原始字段", color="#0891b2", seq=1),
            DwLayer(code="DWD", name="明细数据层", rule="dwd_业务_过程，一个过程一张表", color="#1668dc", seq=2),
            DwLayer(code="DWS", name="汇总数据层", rule="dws_主题_粒度，预聚合指标", color="#7c3aed", seq=3),
            DwLayer(code="ADS", name="应用数据层", rule="ads_应用_场景，直接服务报表", color="#16a34a", seq=4),
            DwLayer(code="DIM", name="维度层", rule="dim_维度名，全局唯一", color="#d97706", seq=5),
        ])
    if session.query(BizDomain).count() == 0:
        session.add_all([
            BizDomain(name="交易域"), BizDomain(name="用户域"),
            BizDomain(name="商品域"), BizDomain(name="流量域"),
        ])
    if session.query(EngineType).count() == 0:
        session.add_all([
            EngineType(name="MySQL", ddl="mysql", xc=False),
            EngineType(name="Apache Doris", ddl="doris", xc=False),
            EngineType(name="GreatDB", ddl="greatdb", xc=True),
        ])
    session.commit()


def init_db() -> None:
    """create_all 兜底建表：幂等（存在的表跳过）。
    create_all 对已存在的表不会补列 —— 增量列由 _ensure_column 显式 ALTER 保障。
    """
    from common import models  # noqa: F401  确保模型已注册到 Base.metadata

    engine = get_engine()
    Base = models.Base
    Base.metadata.create_all(engine)
    _ensure_column(
        engine,
        "t_ide_history",
        "rendered_sql",
        "MEDIUMTEXT NULL COMMENT '渲染后 SQL 全文（重放分页/导出用，09-22 加列）'",
    )
    _ensure_column(
        engine,
        "t_lineage_edge",
        "src_type",
        "VARCHAR(16) NOT NULL DEFAULT 'runtime' COMMENT '血缘来源 runtime/design（design 行 instance_id=0）'",
    )
    _ensure_column(
        engine,
        "t_lineage_field",
        "src_type",
        "VARCHAR(16) NOT NULL DEFAULT 'runtime' COMMENT '血缘来源 runtime/design（对齐边表）'",
    )
    _s = new_session()
    try:
        seed_dict_tables(_s)
    finally:
        _s.close()
    logger.info("create_all 完成（meta 表兜底建表，幂等；增量列已保障）")


def _ensure_column(engine: Engine, table: str, col: str, ddl: str) -> None:
    """对已存在的历史表增量补列（create_all 不 ALTER 已有表）。
    通过 information_schema 查列是否存在，不存在则 ALTER TABLE ADD COLUMN。
    """
    try:
        with engine.connect() as conn:
            exists = conn.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"
                ),
                {"t": table, "c": col},
            ).scalar()
            if not exists:
                conn.execute(text(f"ALTER TABLE `{table}` ADD COLUMN `{col}` {ddl}"))
                conn.commit()
                logger.info("增量列保障：%s.%s 已 ALTER 补列", table, col)
    except Exception as exc:  # noqa: BLE001  启动不因补列失败中断，记警告待人工处理
        logger.warning("增量列保障失败 %s.%s: %s", table, col, exc)


def check_db() -> bool:
    """健康检查：SELECT 1 探活。"""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001 健康检查吞掉具体异常，只报状态
        logger.warning("db 探活失败: %s", exc)
        return False
