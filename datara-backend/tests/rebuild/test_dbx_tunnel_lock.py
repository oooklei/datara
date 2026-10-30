from threading import Event, Thread

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from rebuild.dbx.tunnel_owner import catalog_write_lock


def test_sqlite_catalog_lock_serializes_independent_sessions(tmp_path):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'tunnels.db'}",
        connect_args={"check_same_thread": False, "timeout": 2},
    )
    first_entered = Event()
    second_attempting = Event()
    second_entered = Event()
    release_first = Event()
    errors = []

    def first_writer():
        try:
            with Session(engine) as session, catalog_write_lock(session):
                first_entered.set()
                release_first.wait(2)
                session.commit()
        except Exception as exc:
            errors.append(exc)

    def second_writer():
        try:
            with Session(engine) as session:
                second_attempting.set()
                with catalog_write_lock(session):
                    second_entered.set()
                    session.commit()
        except Exception as exc:
            errors.append(exc)

    first = Thread(target=first_writer)
    second = Thread(target=second_writer)
    try:
        first.start()
        assert first_entered.wait(2)
        second.start()
        assert second_attempting.wait(2)
        assert not second_entered.wait(0.1)
        release_first.set()
        assert second_entered.wait(2)
    finally:
        release_first.set()
        first.join(2)
        second.join(2)
        engine.dispose()
    assert not errors
