"""Published component specification reader and deterministic serializer."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from common.models import Component, ComponentVersion
from rebuild.component_spec.catalogue import (
    DESIGN_COMPONENT_TYPES,
    FORM_SECTIONS,
    RUNTIME_ONLY_TYPES,
    WORKFLOW_COMPONENT_TYPES,
    empty_form,
    validate_declaration,
    workflow_kind,
)


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
    violations = validate_declaration(spec)
    if violations:
        raise ComponentSpecError(f"invalid declaration for {component.type}: {'; '.join(violations)}")
    render = spec.get("render") if isinstance(spec.get("render"), dict) else {}
    form = spec.get("form") if isinstance(spec.get("form"), dict) else empty_form()
    # Historical rows without a form are exposed through the canonical eight
    # sections; published rows that declare a form must pass the exact gate.
    form = {section: list(form.get(section, [])) for section in FORM_SECTIONS}
    params = form.get("params") if isinstance(form.get("params"), list) else []
    fields = spec.get("fields")
    if not isinstance(fields, list):
        fields = [
            _param_to_field(param) for param in params if isinstance(param, dict) and isinstance(param.get("key"), str)
        ]
    ports = spec.get("ports")
    if not isinstance(ports, dict):
        ports = render.get("ports") if isinstance(render.get("ports"), dict) else None
    visual = {
        "icon": spec.get("icon") or render.get("icon") or "",
        "color": spec.get("color") if spec.get("color") is not None else render.get("color"),
        "shape": spec.get("shape") or render.get("shape") or "default",
        "badge": spec.get("badge"),
    }
    # D1 闸门 §13-5 / 同步编排设计态分离（权威设计 v3 L515）：runtime-only 组件
    # （C17 sync / C24 file_sync，execution_model=dag-engine）显式 paletteVisible=false，
    # 消费方 FE Palette 按此过滤（设计态禁运行态组件，四排除·palette 侧）。
    runtime_only = component.type in RUNTIME_ONLY_TYPES
    if runtime_only:
        visual["paletteVisible"] = False
    return {
        "type": component.type,
        "publishedVersion": component.published_version,
        "componentRef": {"type": component.type, "version": component.published_version},
        "workflowTypes": [
            kind for kind, component_types in WORKFLOW_COMPONENT_TYPES.items() if component.type in component_types
        ],
        "runtimeOnly": runtime_only,
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
        "form": form,
        "visual": visual,
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

    def published_document(self, requested_workflow_kind: str | None = None) -> ComponentSpecDocument:
        kind = workflow_kind(requested_workflow_kind)
        if requested_workflow_kind is not None and kind is None:
            raise ComponentSpecError("workflow_type must be NORMAL, SYNC, or STREAM")
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
        allowed = frozenset(WORKFLOW_COMPONENT_TYPES[kind]) if kind else DESIGN_COMPONENT_TYPES
        # Validate every published row before filtering. A corrupt hidden row
        # is still a governance failure and must not be concealed by a narrow
        # workflow-type request.
        validated = [(component, _spec_item(component, version)) for component, version in rows]
        if kind:
            present = {component.type for component, _item in validated}
            missing = [
                component_type for component_type in WORKFLOW_COMPONENT_TYPES[kind] if component_type not in present
            ]
            if missing:
                raise ComponentSpecError(f"{kind} catalogue is incomplete: {missing}")
        payload = {
            "items": [
                item
                for component, item in validated
                if component.type in allowed and component.type not in RUNTIME_ONLY_TYPES
            ]
        }
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        etag = f'"{hashlib.sha256(body).hexdigest()}"'
        return ComponentSpecDocument(body=body, etag=etag)
