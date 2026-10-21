import hashlib

from sqlalchemy import Engine

from rebuild.sec.models import SEC_TABLES


revision = "r10_0001_sec_access_log"
_DDL_MANIFEST = (
    "r10_0001 sec access log v1: single table rebuild_sec_access_log; no FKs;"
    " checks rows_seen>=0 and result in (allow,deny); indexes user_time/result_time"
)
checksum = hashlib.sha256(_DDL_MANIFEST.encode("utf-8")).hexdigest()


def upgrade(engine: Engine) -> None:
    from rebuild.common.db import Base

    Base.metadata.create_all(bind=engine, tables=list(SEC_TABLES), checkfirst=True)
