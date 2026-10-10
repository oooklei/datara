"""Stable, dependency-aware signatures for checkpointable workflow nodes."""

from __future__ import annotations

import hashlib
import json
from typing import Mapping


def node_signature(
    class_type: str,
    spec_version: int | str | None,
    params: Mapping[str, object] | None,
    upstream_signatures: Mapping[str, str] | None = None,
) -> str:
    """Hash only execution-relevant configuration and sorted upstream results."""
    payload = {
        "classType": class_type,
        "specVersion": spec_version,
        "params": params or {},
        "upstream": dict(sorted((k, v) for k, v in (upstream_signatures or {}).items() if v is not None)),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
