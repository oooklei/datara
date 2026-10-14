"""独立 Backend 的 SQLAlchemy 基础元数据。"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def configure_engine(url: str):
    """按运行环境创建引擎；调用方负责连接池参数和生命周期。"""
    from sqlalchemy import create_engine

    return create_engine(url, pool_pre_ping=True)

