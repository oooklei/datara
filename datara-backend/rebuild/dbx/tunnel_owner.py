"""Owner filtering for dbx's single-user tunnel profile catalog."""

from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
from threading import RLock
from typing import Any, Iterator

from sqlalchemy import text
from sqlalchemy.orm import Session

from rebuild.dbx import DbxError
from rebuild.dbx.ai_owner import valid_config_id


KIND = "tunnel-profile"
SAVE_LOCK = RLock()
_POSTGRES_LOCK_KEY = 0x44425854554E4E45
_MYSQL_LOCK_NAME = "datara_dbx_tunnel_profiles"
_HIDDEN_KEYS = {
    "password", "keypassphrase", "token", "secret", "apikey", "privatekey",
    "keypath", "sshagentsockpath", "proxycommand",
}


class TunnelCatalogLockUnavailable(RuntimeError):
    pass


def profile_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(
        not isinstance(row, dict) or not valid_config_id(row.get("id")) for row in value
    ):
        raise DbxError()
    return value


def redact_shared_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Keep type and ID for selectors while hiding stored connection material."""
    item = deepcopy(profile)

    def scrub(value: Any) -> Any:
        if isinstance(value, dict):
            result = {}
            for key, child in value.items():
                normalized = key.lower().replace("_", "").replace("-", "")
                if normalized in _HIDDEN_KEYS:
                    result[key] = "" if isinstance(child, str) else None
                elif normalized == "url" and isinstance(child, str):
                    result[key] = "https://shared-config.invalid"
                else:
                    result[key] = scrub(child)
            return result
        if isinstance(value, list):
            return [scrub(child) for child in value]
        return value

    return scrub(item)


@contextmanager
def catalog_write_lock(session: Session) -> Iterator[None]:
    """Serialize catalog replacement across Datara workers sharing a database."""
    dialect = session.get_bind().dialect.name
    if dialect == "sqlite":
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
    elif dialect == "postgresql":
        session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _POSTGRES_LOCK_KEY})
    elif dialect in {"mysql", "mariadb"}:
        acquired = session.scalar(text("SELECT GET_LOCK(:name, 15)"), {"name": _MYSQL_LOCK_NAME})
        if acquired != 1:
            raise TunnelCatalogLockUnavailable("DBX tunnel catalog lock unavailable")
    else:
        raise TunnelCatalogLockUnavailable(f"DBX tunnel catalog lock unsupported for {dialect}")
    try:
        yield
    finally:
        if dialect in {"mysql", "mariadb"}:
            session.scalar(text("SELECT RELEASE_LOCK(:name)"), {"name": _MYSQL_LOCK_NAME})
