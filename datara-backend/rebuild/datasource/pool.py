"""Bounded, process-local SQLAlchemy pools for saved project data sources."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import json
import logging
import os
from threading import RLock
from typing import Callable

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, URL

from rebuild.datasource.contracts import DataSourceDraft

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DatasourcePoolSettings:
    pool_size: int = 2
    max_overflow: int = 2
    pool_timeout: float = 3.0
    pool_recycle: int = 300
    max_profiles: int = 32

    def __post_init__(self) -> None:
        if not 1 <= self.pool_size <= 10:
            raise ValueError("datasource pool_size must be between 1 and 10")
        if not 0 <= self.max_overflow <= 20:
            raise ValueError("datasource max_overflow must be between 0 and 20")
        if not 0 < self.pool_timeout <= 30:
            raise ValueError("datasource pool_timeout must be greater than 0 and at most 30 seconds")
        if not 30 <= self.pool_recycle <= 3600:
            raise ValueError("datasource pool_recycle must be between 30 and 3600 seconds")
        if not 1 <= self.max_profiles <= 128:
            raise ValueError("datasource max_profiles must be between 1 and 128")

    @classmethod
    def from_environment(cls) -> DatasourcePoolSettings:
        try:
            return cls(
                pool_size=int(os.getenv("REBUILD_DS_POOL_SIZE", "2")),
                max_overflow=int(os.getenv("REBUILD_DS_MAX_OVERFLOW", "2")),
                pool_timeout=float(os.getenv("REBUILD_DS_POOL_TIMEOUT", "3")),
                pool_recycle=int(os.getenv("REBUILD_DS_POOL_RECYCLE", "300")),
                max_profiles=int(os.getenv("REBUILD_DS_POOL_MAX_PROFILES", "32")),
            )
        except (TypeError, ValueError) as exc:
            raise RuntimeError("invalid bounded datasource pool configuration") from exc


def _url(draft: DataSourceDraft) -> URL:
    kind = draft.kind.lower()
    drivername = {"mysql": "mysql+pymysql", "postgresql": "postgresql+psycopg"}.get(kind)
    if drivername is None:
        raise ValueError(f"pooled datasource connections do not support kind: {draft.kind}")
    return URL.create(
        drivername,
        username=draft.username,
        password=draft.password,
        host=draft.host,
        port=draft.port,
        database=draft.database,
    )


def _profile_fingerprint(draft: DataSourceDraft) -> str:
    profile = {
        "kind": draft.kind.lower(),
        "host": draft.host,
        "port": draft.port,
        "database": draft.database,
        "username": draft.username,
        "password": draft.password,
    }
    encoded = json.dumps(profile, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class DatasourceEngineRegistry:
    """Caches one bounded engine per project-scoped saved datasource identity."""

    def __init__(
        self,
        *,
        settings: DatasourcePoolSettings | None = None,
        engine_factory: Callable[..., Engine] = create_engine,
    ) -> None:
        self._settings = settings or DatasourcePoolSettings.from_environment()
        self._engine_factory = engine_factory
        self._engines: OrderedDict[tuple[int, int], tuple[str, Engine]] = OrderedDict()
        self._lock = RLock()

    @property
    def engine_count(self) -> int:
        with self._lock:
            return len(self._engines)

    def connect(self, project_id: int, datasource_id: int, draft: DataSourceDraft):
        if draft.kind.lower() not in {"mysql", "postgresql"}:
            raise ValueError(f"pooled datasource connections do not support kind: {draft.kind}")
        identity = (int(project_id), int(datasource_id))
        fingerprint = _profile_fingerprint(draft)
        with self._lock:
            cached = self._engines.get(identity)
            if cached is None or cached[0] != fingerprint:
                if cached is not None:
                    self._engines.pop(identity)
                    cached[1].dispose()
                    logger.info("datasource_pool_profile_changed project_id=%s datasource_id=%s", *identity)
                elif len(self._engines) >= self._settings.max_profiles:
                    idle_identity = next(
                        (
                            pool_identity
                            for pool_identity, (_pool_fingerprint, pool_engine) in self._engines.items()
                            if pool_engine.pool.checkedout() == 0
                        ),
                        None,
                    )
                    if idle_identity is None:
                        logger.warning(
                            "datasource_pool_registry_capacity_reached max_profiles=%s", self._settings.max_profiles
                        )
                        raise RuntimeError("datasource pool registry is at capacity")
                    _idle_fingerprint, idle_engine = self._engines.pop(idle_identity)
                    idle_engine.dispose()
                    logger.info(
                        "datasource_pool_evicted_idle project_id=%s datasource_id=%s", *idle_identity
                    )
                settings = self._settings
                connect_args = (
                    {
                        "connect_timeout": 3,
                        "autocommit": False,
                        "read_timeout": 5,
                        "write_timeout": 3,
                    }
                    if draft.kind.lower() == "mysql"
                    else {"connect_timeout": 3, "autocommit": False}
                )
                engine = self._engine_factory(
                    _url(draft),
                    pool_size=settings.pool_size,
                    max_overflow=settings.max_overflow,
                    pool_timeout=settings.pool_timeout,
                    pool_recycle=settings.pool_recycle,
                    pool_pre_ping=True,
                    connect_args=connect_args,
                )
                self._engines[identity] = (fingerprint, engine)
                logger.info(
                    "datasource_pool_created project_id=%s datasource_id=%s pool_size=%s max_overflow=%s",
                    *identity,
                    settings.pool_size,
                    settings.max_overflow,
                )
            else:
                self._engines.move_to_end(identity)
            return self._engines[identity][1].raw_connection()

    def invalidate(self, project_id: int, datasource_id: int) -> bool:
        identity = (int(project_id), int(datasource_id))
        with self._lock:
            cached = self._engines.pop(identity, None)
        if cached is None:
            return False
        cached[1].dispose()
        logger.info("datasource_pool_invalidated project_id=%s datasource_id=%s", *identity)
        return True

    def dispose_all(self) -> None:
        with self._lock:
            engines = tuple(engine for _, engine in self._engines.values())
            self._engines.clear()
        for engine in engines:
            engine.dispose()
        if engines:
            logger.info("datasource_pools_disposed count=%s", len(engines))

    def __repr__(self) -> str:
        return f"DatasourceEngineRegistry(engine_count={self.engine_count}, settings={self._settings!r})"
