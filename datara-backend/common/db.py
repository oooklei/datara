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


def init_db() -> None:
    """create_all 兜底建表：幂等（存在的表跳过）。
    create_all 对已存在的表不会补列 —— 增量列由 _ensure_column 显式 ALTER 保障。
    """
    from common import models  # noqa: F401  确保模型已注册到 Base.metadata

    engine = get_engine()
    Base = models.Base
    Base.metadata.create_all(engine)
    _ensure_column(engine, "t_ide_history", "rendered_sql",
                   "MEDIUMTEXT NULL COMMENT '渲染后 SQL 全文（重放分页/导出用，09-22 加列）'")
    logger.info("create_all 完成（meta 表兜底建表，幂等；增量列已保障）")


def _ensure_column(engine: Engine, table: str, col: str, ddl: str) -> None:
    """对已存在的历史表增量补列（create_all 不 ALTER 已有表）。
    通过 information_schema 查列是否存在，不存在则 ALTER TABLE ADD COLUMN。
    """
    try:
        with engine.connect() as conn:
            exists = conn.execute(
                text("SELECT COUNT(*) FROM information_schema.COLUMNS "
                     "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"),
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
