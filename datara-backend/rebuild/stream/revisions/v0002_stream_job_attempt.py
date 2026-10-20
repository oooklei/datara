"""Create stream_job_attempt table (DEP-05: design §13.7 five-table model).

DEP-05: Design §13.7 lists stream_job_attempt as one of five runtime tables.
Implementation had folded attempt into stream_job.attempt_no counter (4+1 model).
User ruling (2026-10-19, DEPLOY): 独立建表 (方案 A) — this migration adds the
independent stream_job_attempt table; per-retry slices persist there instead
of being folded into the stream_job counter.
"""

from __future__ import annotations

import hashlib

from sqlalchemy import Engine, inspect, text

from rebuild.common.db import Base
from rebuild.stream.models import StreamJobAttemptRecord  # noqa: F401 (re-export for migration binding)

revision = "r8_0002_stream_job_attempt"
STREAM_TABLES = (StreamJobAttemptRecord.__table__,)
_DDL_MANIFEST = (
    "r8_0002 stream_job_attempt table; unique (job_id, attempt_no); "
    "indexes on job_id"
)
checksum = hashlib.sha256(_DDL_MANIFEST.encode("utf-8")).hexdigest()


def upgrade(engine: Engine) -> None:
    """Create stream_job_attempt table if missing."""
    Base.metadata.create_all(
        bind=engine,
        tables=[StreamJobAttemptRecord.__table__],
        checkfirst=True,
    )

    inspector = inspect(engine)
    if "stream_job_attempt" not in inspector.get_table_names():
        raise RuntimeError("stream_job_attempt table was not created")


def downgrade(engine: Engine) -> None:
    """Drop stream_job_attempt table."""
    inspector = inspect(engine)
    if "stream_job_attempt" in inspector.get_table_names():
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE stream_job_attempt"))
