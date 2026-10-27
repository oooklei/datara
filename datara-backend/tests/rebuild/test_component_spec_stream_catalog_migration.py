"""Stream catalogue convergence migration guards."""

import json

from sqlalchemy import create_engine, text

from rebuild.component_spec.catalogue import FORM_SECTIONS, validate_declaration
from rebuild.component_spec.migrations import COMPONENT_SPEC_MIGRATIONS, apply_component_spec_migrations
from rebuild.component_spec.revisions import v0003_stream_component_catalog as revision


def test_v0003_publishes_complete_stream_catalogue() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    apply_component_spec_migrations(engine)

    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "select c.type, c.state, c.published_version, v.state as version_state, v.spec_json "
                "from t_component c join t_component_version v "
                "on v.component_id=c.id and v.version=c.published_version "
                "where c.type in ('stream_input','stream_fuse','stream_output','page_board') "
                "order by c.type"
            )
        ).mappings().all()
    assert {row["type"] for row in rows} == set(revision.STREAM_COMPONENT_TYPES)
    for row in rows:
        assert row["state"] == "published"
        assert row["version_state"] == "published"
        spec = json.loads(row["spec_json"])
        assert tuple(spec["form"]) == FORM_SECTIONS
        assert validate_declaration(spec) == []


def test_v0003_is_idempotent_and_does_not_replace_existing_published_spec() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    apply_component_spec_migrations(engine)
    with engine.begin() as connection:
        before = connection.execute(
            text("select spec_json from t_component_version where type='stream_input' and version=1")
        ).scalar_one()

    revision.upgrade(engine)

    with engine.connect() as connection:
        after = connection.execute(
            text("select spec_json from t_component_version where type='stream_input' and version=1")
        ).scalar_one()
        count = connection.execute(
            text("select count(*) from t_component_version where type='stream_input'")
        ).scalar_one()
    assert after == before
    assert count == 1


def test_v0003_is_registered() -> None:
    assert len(revision.checksum) == 64
    assert COMPONENT_SPEC_MIGRATIONS[2].revision == revision.revision
