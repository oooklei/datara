from datetime import datetime

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from rebuild.common.db import Base
from rebuild.governance.legacy_dry_run import semantic_fingerprint
from rebuild.governance.legacy_mapping import LegacyMappingContext, map_legacy_row
from rebuild.governance.snapshot_repository import LegacyI18TargetSnapshotRepository
from rebuild.identity.models import UserRecord
from rebuild.project.models import ProjectRecord


def test_target_snapshot_is_project_scoped_read_only_and_semantics_match_legacy_mapper():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    created = datetime(2026, 10, 12, 22, 25, 28)
    with Session(engine) as session:
        session.add_all(
            [
                UserRecord(id=1, username="owner", password_hash="not-a-real-password", role="admin"),
                ProjectRecord(id=41, name="target", description="", owner_id=1),
                ProjectRecord(id=42, name="other", description="", owner_id=1),
            ]
        )
        session.flush()
        from rebuild.governance.models import (
            GovernanceDomainRecord,
            WarehouseLayerRecord,
            ModelEngineRecord,
            WarehouseModelRecord,
            WarehouseModelFieldRecord,
            WarehouseModelRelationRecord,
            WarehouseModelRelationFieldRecord,
            WarehouseModelVersionRecord,
        )

        session.add_all(
            [
                GovernanceDomainRecord(
                    id=9,
                    project_id=41,
                    name="交易",
                    description="订单域",
                    source_system="datara_meta",
                    source_table="t_biz_domain",
                    source_id="5",
                    source_created_at=created,
                    source_updated_at=created,
                ),
                WarehouseLayerRecord(
                    id=8,
                    project_id=41,
                    code="DWD",
                    name="明细层",
                    naming_rule="dwd_*",
                    color="#123456",
                    sequence=2,
                    source_system="datara_meta",
                    source_table="t_dw_layer",
                    source_id="DWD",
                    source_created_at=created,
                    source_updated_at=created,
                ),
                ModelEngineRecord(
                    id=10,
                    project_id=41,
                    name="Doris",
                    ddl_dialect="doris",
                    vendor_flag=True,
                    source_system="datara_meta",
                    source_table="t_engine_type",
                    source_id="Doris",
                    source_created_at=created,
                    source_updated_at=created,
                ),
                WarehouseModelRecord(
                    id=501,
                    project_id=41,
                    code="orders",
                    name="订单",
                    layer_id=8,
                    model_type="明细表",
                    domain_id=9,
                    engine_id=10,
                    legacy_datasource_id=3,
                    database_name="warehouse",
                    security_level="内部",
                    status="published",
                    version=1,
                    er_position_json='{"x":1,"y":2}',
                    last_ddl_snapshot="CREATE TABLE orders (id BIGINT)",
                    built_at=None,
                    built_by=None,
                    owner_name="data-team",
                    description="订单主模型",
                    source_system="datara_meta",
                    source_table="t_dw_model",
                    source_id="17",
                    source_created_at=created,
                    source_updated_at=created,
                ),
                WarehouseModelFieldRecord(
                    id=601,
                    model_id=501,
                    ordinal_position=1,
                    field_name="order_id",
                    data_type="BIGINT",
                    length="",
                    precision="",
                    nullable=False,
                    default_value="",
                    description="订单号",
                    is_primary_key=True,
                    is_partition_key=False,
                    dictionary_reference="",
                    source_system="datara_meta",
                    source_table="t_dw_model_field",
                    source_id="29",
                    source_created_at=created,
                    source_updated_at=created,
                ),
                WarehouseModelVersionRecord(
                    id=701,
                    model_id=501,
                    version=1,
                    snapshot_json='{"model":{}}',
                    change_note="首次建模",
                    created_by="designer",
                    source_system="datara_meta",
                    source_table="t_dw_model_version",
                    source_id="72",
                    source_created_at=created,
                    source_updated_at=created,
                ),
                WarehouseModelRecord(
                    id=502,
                    project_id=42,
                    code="other",
                    name="other",
                    source_system="datara_meta",
                    source_table="t_dw_model",
                    source_id="18",
                    source_created_at=created,
                    source_updated_at=created,
                ),
            ]
        )
        session.flush()
        relation = WarehouseModelRelationRecord(
            id=801,
            project_id=41,
            source_model_id=501,
            target_model_id=501,
            relation_type="1:1",
            join_description="自身映射",
            created_by="designer",
            source_system="datara_meta",
            source_table="t_dw_model_relation",
            source_id="91",
            source_created_at=created,
            source_updated_at=created,
        )
        session.add(relation)
        session.flush()
        session.add(
            WarehouseModelRelationFieldRecord(
                id=901,
                relation_id=801,
                ordinal_position=1,
                source_field_name="order_id",
                target_field_name="order_id",
            )
        )
        session.commit()

    statements = []

    def record_read_only_sql(_connection, _cursor, statement, *_args):
        statements.append(statement.lstrip().split(None, 1)[0].upper())
        assert statements[-1] in {"SELECT", "PRAGMA"}

    event.listen(engine, "before_cursor_execute", record_read_only_sql)
    with Session(engine) as session:
        snapshot = LegacyI18TargetSnapshotRepository(session).read_project_snapshot(41)

    assert set(snapshot.target_ids) == {
        ("t_biz_domain", "5"),
        ("t_biz_domain", "交易"),
        ("t_dw_layer", "DWD"),
        ("t_engine_type", "Doris"),
        ("t_dw_model", "17"),
        ("t_dw_model_field", "29"),
        ("t_dw_model_relation", "91"),
        ("t_dw_model_version", "72"),
    }
    context = LegacyMappingContext(
        target_project_id=41,
        target_ids=snapshot.target_ids,
    )
    source_model = {
        "id": 17,
        "code": "orders",
        "name": "订单",
        "layer": "DWD",
        "type": "明细表",
        "biz_domain": "交易",
        "engine": "Doris",
        "ds_id": 3,
        "db_name": "warehouse",
        "security_level": "内部",
        "status": "published",
        "version": 1,
        "er_pos": {"x": 1, "y": 2},
        "last_ddl": "CREATE TABLE orders (id BIGINT)",
        "owner": "data-team",
        "remark": "订单主模型",
        "create_time": created,
        "update_time": created,
    }
    mapped_model = map_legacy_row("t_dw_model", source_model, context)
    assert snapshot.row_fingerprints[("t_dw_model", "17")] == semantic_fingerprint(mapped_model)
    expected_source_rows = [
        map_legacy_row(
            "t_biz_domain",
            {"id": 5, "name": "交易", "remark": "订单域", "create_time": created, "update_time": created},
            context,
        ),
        map_legacy_row(
            "t_dw_layer",
            {
                "code": "DWD",
                "name": "明细层",
                "rule": "dwd_*",
                "color": "#123456",
                "seq": 2,
                "create_time": created,
                "update_time": created,
            },
            context,
        ),
        map_legacy_row(
            "t_engine_type",
            {"name": "Doris", "ddl": "doris", "xc": True, "create_time": created, "update_time": created},
            context,
        ),
        mapped_model,
        map_legacy_row(
            "t_dw_model_field",
            {
                "id": 29,
                "model_id": 17,
                "seq": 1,
                "name": "order_id",
                "data_type": "BIGINT",
                "nullable": False,
                "comment": "订单号",
                "is_pk": True,
                "create_time": created,
                "update_time": created,
            },
            context,
        ),
        map_legacy_row(
            "t_dw_model_relation",
            {
                "id": 91,
                "src_model_id": 17,
                "tgt_model_id": 17,
                "rel_type": "1:1",
                "src_fields": '["order_id"]',
                "tgt_fields": '["order_id"]',
                "join_desc": "自身映射",
                "created_by": "designer",
                "create_time": created,
                "update_time": created,
            },
            context,
        ),
        map_legacy_row(
            "t_dw_model_version",
            {
                "id": 72,
                "model_id": 17,
                "version": 1,
                "snapshot_json": '{"model":{}}',
                "change_note": "首次建模",
                "created_by": "designer",
                "create_time": created,
                "update_time": created,
            },
            context,
        ),
    ]
    for mapped in expected_source_rows:
        identity = (mapped.source_table, mapped.source_id)
        assert snapshot.row_fingerprints[identity] == semantic_fingerprint(mapped), identity
    assert snapshot.model_fields[501] == frozenset({"order_id"})
    assert snapshot.project_id == 41
    assert statements and set(statements) == {"SELECT"}
    assert len(snapshot.digest) == 64
    assert snapshot.captured_at.tzinfo is not None


def test_target_snapshot_digest_tracks_content_not_capture_time():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    from rebuild.governance.models import GovernanceDomainRecord

    with Session(engine) as session, session.begin():
        session.add(UserRecord(id=1, username="owner", password_hash="test", role="admin"))
        session.add(ProjectRecord(id=41, name="target", description="", owner_id=1))

    with Session(engine) as session:
        first = LegacyI18TargetSnapshotRepository(session).read_project_snapshot(41)
    with Session(engine) as session:
        repeated = LegacyI18TargetSnapshotRepository(session).read_project_snapshot(41)
    assert first.captured_at != repeated.captured_at
    assert first.digest == repeated.digest

    with Session(engine) as session, session.begin():
        session.add(GovernanceDomainRecord(project_id=41, name="交易域", description="订单"))
    with Session(engine) as session:
        changed = LegacyI18TargetSnapshotRepository(session).read_project_snapshot(41)

    assert changed.digest != first.digest
    engine.dispose()
