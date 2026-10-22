"""Create the rebuild runtime node registry."""

import hashlib

from sqlalchemy import Engine

from rebuild.common.db import Base
from rebuild.runtime_node.models import RUNTIME_NODE_TABLES

revision = "i17_0002_runtime_node_registry"
checksum = hashlib.sha256(
    b"i17_0002 rebuild_runtime_node seventeen-column legacy parity seed 1.9 host"
).hexdigest()


def upgrade(engine: Engine) -> None:
    Base.metadata.create_all(bind=engine, tables=list(RUNTIME_NODE_TABLES), checkfirst=True)
