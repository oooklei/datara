from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.exc import TimeoutError

from rebuild.datasource.contracts import DataSourceDraft
from rebuild.datasource.pool import DatasourceEngineRegistry, DatasourcePoolSettings


def _draft(password: str = "secret-a") -> DataSourceDraft:
    return DataSourceDraft(
        name="warehouse",
        kind="mysql",
        host="localhost",
        port=3306,
        database="analytics",
        username="reader",
        password=password,
    )


def _registry(tmp_path, settings: DatasourcePoolSettings | None = None):
    created = []

    def factory(_url, **kwargs):
        engine = create_engine(f"sqlite+pysqlite:///{tmp_path / f'pool-{len(created)}.db'}", **kwargs)
        created.append(engine)
        return engine

    return DatasourceEngineRegistry(settings=settings, engine_factory=factory), created


def test_reuses_a_bounded_engine_for_the_same_project_datasource_profile(tmp_path):
    registry, created = _registry(tmp_path)
    try:
        first = registry.connect(3, 17, _draft())
        first.close()
        second = registry.connect(3, 17, _draft())
        try:
            with second.cursor() as cursor:
                cursor.execute("SELECT 1")
                assert cursor.fetchone() == (1,)
        finally:
            second.close()

        assert len(created) == 1
        assert created[0].pool.size() == 2
        assert created[0].pool._max_overflow == 2
    finally:
        registry.dispose_all()


def test_never_shares_a_pool_across_project_or_datasource_identity(tmp_path):
    registry, created = _registry(tmp_path)
    try:
        for project_id, datasource_id in ((3, 17), (4, 17), (3, 18)):
            connection = registry.connect(project_id, datasource_id, _draft())
            connection.close()
        assert len(created) == 3
    finally:
        registry.dispose_all()


def test_profile_change_disposes_old_engine_and_rebuilds_without_logging_credentials(tmp_path):
    registry, created = _registry(tmp_path)
    try:
        old_connection = registry.connect(3, 17, _draft())
        old_connection.close()
        old_engine = created[0]

        new_connection = registry.connect(3, 17, _draft("secret-b"))
        new_connection.close()

        assert len(created) == 2
        assert registry.invalidate(3, 17) is True
        assert registry.invalidate(3, 17) is False
        assert "secret-a" not in repr(registry)
        assert "secret-b" not in repr(registry)
        assert old_engine.pool.checkedout() == 0
    finally:
        registry.dispose_all()


def test_pool_timeout_is_bounded_and_shutdown_disposes_all_engines(tmp_path):
    settings = DatasourcePoolSettings(pool_size=1, max_overflow=0, pool_timeout=0.05, pool_recycle=60)
    registry, created = _registry(tmp_path, settings)
    held = registry.connect(3, 17, _draft())
    try:
        try:
            registry.connect(3, 17, _draft())
        except TimeoutError:
            pass
        else:
            raise AssertionError("second checkout must respect the configured pool limit")
    finally:
        held.close()

    registry.dispose_all()
    assert created[0].pool.checkedout() == 0
    assert registry.engine_count == 0


def test_pool_configuration_rejects_unbounded_or_out_of_policy_values():
    for values in (
        {"pool_size": 0},
        {"pool_size": 11},
        {"max_overflow": -1},
        {"max_overflow": 21},
        {"pool_timeout": 0},
        {"pool_timeout": 31},
        {"pool_recycle": 29},
    ):
        try:
            DatasourcePoolSettings(**values)
        except ValueError:
            continue
        raise AssertionError(f"configuration should reject {values}")
