"""Add the I19 unresolved-tag and I20 structured-dimension tables."""

import hashlib

from sqlalchemy import Engine

from rebuild.governance.models import GOVERNANCE_I19_I20_TABLES


revision = "r3_0003_metadata_metric_carry_forward"
_DDL_MANIFEST = (
    "r3_0003 main-line I19/I20 carry-forward v1: unresolved asset tag and "
    "structured metric dimension tables; LegacySourceMixin nullable source identity, "
    "RESTRICT batch and parent FKs, project scope, unique source and business keys"
)
checksum = hashlib.sha256(_DDL_MANIFEST.encode("utf-8")).hexdigest()


def upgrade(engine: Engine) -> None:
    from rebuild.common.db import Base

    Base.metadata.create_all(bind=engine, tables=list(GOVERNANCE_I19_I20_TABLES), checkfirst=True)
