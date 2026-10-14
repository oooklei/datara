import hashlib

from sqlalchemy import Engine

from rebuild.governance.models import GOVERNANCE_TABLES


revision = "r3_0001_governance_catalog"
_DDL_MANIFEST = (
    "r3_0001 governance catalog v1: asset,field,tag,asset_tag,lineage,quality_rule,quality_run,"
    "standard,semantic_metric,migration_batch,migration_item,audit_event; all FKs/checks/unique constraints"
)
checksum = hashlib.sha256(_DDL_MANIFEST.encode("utf-8")).hexdigest()


def upgrade(engine: Engine) -> None:
    from rebuild.common.db import Base

    Base.metadata.create_all(bind=engine, tables=list(GOVERNANCE_TABLES), checkfirst=True)
