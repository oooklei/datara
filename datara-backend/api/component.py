"""Read-only component catalog API.

The source of truth is common/dag_catalog.json, generated from the frontend
profiles. This module intentionally does not persist catalog rows.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from common.resp import ok

router = APIRouter(prefix="/components", tags=["components"])

CATALOG_PATH = Path(__file__).resolve().parents[1] / "common" / "dag_catalog.json"


@lru_cache(maxsize=1)
def _load() -> dict[str, Any]:
    with CATALOG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _components() -> list[dict[str, Any]]:
    return list(_load().get("components") or [])


def _matches(item: dict[str, Any], *, q: str, profile: str, route: str, palette_visible: bool | None) -> bool:
    if profile and item.get("profile") != profile:
        return False
    if route and item.get("route") != route:
        return False
    if palette_visible is not None and bool(item.get("paletteVisible")) is not palette_visible:
        return False
    if q:
        hay = " ".join(str(item.get(k) or "") for k in ("type", "label", "code", "desc", "executor"))
        if q.lower() not in hay.lower():
            return False
    return True


def _row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": item.get("type"),
        "code": item.get("code"),
        "label": item.get("label"),
        "profile": item.get("profile"),
        "route": item.get("route"),
        "executor": item.get("executor"),
        "executionModel": item.get("executionModel"),
        "executionNote": item.get("executionNote") or item.get("route") or "",
        "categories": item.get("categories") or [],
        "paletteVisible": bool(item.get("paletteVisible")),
        "runtimeOnly": bool(item.get("runtimeOnly")),
        "formFieldCount": item.get("formFieldCount") or 0,
        "desc": item.get("desc"),
    }


@router.get("", summary="List read-only system components")
def list_components(
    q: str = "",
    profile: str = "",
    route: str = "",
    paletteVisible: bool | None = Query(default=None),
):
    items = [
        _row(c)
        for c in _components()
        if _matches(c, q=q, profile=profile, route=route, palette_visible=paletteVisible)
    ]
    return ok({"total": len(items), "items": items, "catalogHash": _load().get("catalogHash")})


@router.get("/stats", summary="Component catalog statistics")
def component_stats():
    cat = _load()
    return ok({
        "catalogHash": cat.get("catalogHash"),
        "generatedAt": cat.get("generatedAt"),
        "stats": cat.get("stats") or {},
        "profiles": cat.get("profiles") or [],
    })


@router.get("/catalog", summary="Raw component catalog snapshot")
def raw_catalog():
    return ok(_load())


@router.get("/{type_name}", summary="Component detail")
def component_detail(type_name: str):
    backend_only = set((_load().get("stats") or {}).get("backendOnlyTypes") or [])
    if type_name in backend_only:
        raise HTTPException(status_code=409, detail=f"type {type_name} has no frontend NodeSchema")
    for item in _components():
        if item.get("type") == type_name:
            d = dict(_row(item))
            d["formFields"] = item.get("formFields") or []
            d["formFieldCount"] = len(d["formFields"])
            d["defaults"] = item.get("defaults") or {}
            return ok(d)
    raise HTTPException(status_code=404, detail="component not found")
