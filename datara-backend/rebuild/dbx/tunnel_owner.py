"""Owner filtering for dbx's single-user tunnel profile catalog."""

from __future__ import annotations

from copy import deepcopy
from threading import RLock
from typing import Any

from rebuild.dbx import DbxError
from rebuild.dbx.ai_owner import valid_config_id


KIND = "tunnel-profile"
SAVE_LOCK = RLock()
_HIDDEN_KEYS = {
    "password", "keypassphrase", "token", "secret", "apikey", "privatekey",
    "keypath", "sshagentsockpath", "proxycommand",
}


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
