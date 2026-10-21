"""Create the rebuild SSH node registry."""

import hashlib

from sqlalchemy import Engine

from rebuild.common.db import Base
from rebuild.sshnode.models import SSH_NODE_TABLES

revision = "i17_0001_ssh_node_registry"
checksum = hashlib.sha256(
    b"i17_0001 rebuild_ssh_node unique name state index credential compatibility"
).hexdigest()


def upgrade(engine: Engine) -> None:
    Base.metadata.create_all(bind=engine, tables=list(SSH_NODE_TABLES), checkfirst=True)
