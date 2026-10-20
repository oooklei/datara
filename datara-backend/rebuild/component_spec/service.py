"""Published component specification reader and deterministic serializer."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from common.models import Component, ComponentVersion


class ComponentSpecError(RuntimeError):
    """Published data cannot be represented by the frozen component-spec contract."""


@dataclass(frozen=True)
class ComponentSpecDocument:
    body: bytes
    etag: str


def _param_to_field(param: dict[str, Any]) -> dict[str, Any]:
    field = dict(param)
    field.pop("cap", None)
    if isinstance(param.get("hint"), str) and not param.get("desc"):
        field["desc"] = field.pop("hint")
    return field


def _spec_item(component: Component, version: ComponentVersion) -> dict[str, Any]:
    try:
        spec = json.loads(version.spec_json)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ComponentSpecError(f"invalid published specification for {component.type}") from exc
    if not isinstance(spec, dict):
        raise ComponentSpecError(f"published specification for {component.type} must be an object")
    render = spec.get("render") if isinstance(spec.get("render"), dict) else {}
    form = spec.get("form") if isinstance(spec.get("form"), dict) else {}
    params = form.get("params") if isinstance(form.get("params"), list) else []
    fields = spec.get("fields")
    if not isinstance(fields, list):
        fields = [
            _param_to_field(param)
            for param in params
            if isinstance(param, dict) and isinstance(param.get("key"), str)
        ]
    ports = spec.get("ports")
    if not isinstance(ports, dict):
        ports = render.get("ports") if isinstance(render.get("ports"), dict) else None
    return {
        "type": component.type,
        "publishedVersion": component.published_version,
        "identity": {
            "type": component.type,
            "displayName": component.name,
            "aliases": spec.get("aliases", []),
        },
        "description": {
            "summary": spec.get("summary") or render.get("summary") or "",
            "description": spec.get("description"),
            "category": spec.get("category"),
            "docUrl": spec.get("docUrl"),
        },
        "inputs": fields,
        "outputs": spec.get("outputs") if isinstance(spec.get("outputs"), list) else [],
        "visual": {
            "icon": spec.get("icon") or render.get("icon") or "",
            "color": spec.get("color") if spec.get("color") is not None else render.get("color"),
            "shape": spec.get("shape") or render.get("shape") or "default",
            "badge": spec.get("badge"),
        },
        "behaviors": spec.get("behaviors"),
        "dropPolicy": spec.get("dropPolicy"),
        "extensions": spec.get("extensions"),
        "specVersion": spec.get("specVersion"),
        "ports": ports,
    }


class ComponentSpecService:
    """Read the existing governance tables through a rebuild-owned adapter."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def published_document(self) -> ComponentSpecDocument:
        rows = self._session.execute(
            select(Component, ComponentVersion)
            .join(
                ComponentVersion,
                and_(
                    ComponentVersion.component_id == Component.id,
                    ComponentVersion.version == Component.published_version,
                    ComponentVersion.state == "published",
                ),
            )
            .where(Component.state == "published")
            .order_by(Component.id)
        ).all()
        payload = {"items": [_spec_item(component, version) for component, version in rows]}
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        etag = f'"{hashlib.sha256(body).hexdigest()}"'
        return ComponentSpecDocument(body=body, etag=etag)
