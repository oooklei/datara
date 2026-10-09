"""Shared adapter for the versioned DAG component catalog.

The committed JSON snapshot remains the single source of truth.  This module only
centralizes loading for HTTP routes and internal consumers; it never maintains a
second handwritten runtime catalog.
"""

import json
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException

CATALOG_FILE = Path(__file__).resolve().parent / "dag_catalog.json"


@lru_cache(maxsize=1)
def catalog_payload() -> dict:
    """Return the committed catalog snapshot or a clear service error."""
    if not CATALOG_FILE.is_file():
        raise HTTPException(status_code=503, detail="组件目录快照缺失")
    try:
        return json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="组件目录快照损坏") from exc
