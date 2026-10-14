"""Add normalized tables that preserve the legacy I18-I23 governance semantics."""

import hashlib
from importlib import import_module

from sqlalchemy import Engine

from rebuild.governance.models import LEGACY_CARRY_FORWARD_TABLES


revision = "r3_0002_legacy_governance_carryforward"
_DDL_MANIFEST = (
    "r3_0002 legacy governance carry-forward v1: domain,warehouse layer/engine/model/field/relation/version,"
    "metadata extensions/tag definitions/references,semantic metric profile/dimension/version,"
    "quality task/rule/run details/exception/report/alarm,"
    "standard element/code set/value/naming/mapping/approval/check report,legacy identity map;"
    "source identity,batch FK,source timestamps,runtime timestamps,project/user FKs and unique constraints"
)
checksum = hashlib.sha256(_DDL_MANIFEST.encode("utf-8")).hexdigest()


def upgrade(engine: Engine) -> None:
    # Register referenced tables in the shared metadata before emitting this revision.
    import_module("rebuild.project.models")
    import_module("rebuild.identity.models")
    from rebuild.common.db import Base

    Base.metadata.create_all(bind=engine, tables=list(LEGACY_CARRY_FORWARD_TABLES), checkfirst=True)
