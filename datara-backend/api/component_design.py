"""Component design governance API.

This closes the M1/M2 component-management surface used by the frontend and by
baseline.py. Built-in baseline publishing remains in api.baseline; this module
handles user-scoped component drafts and shared validation helpers.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.auth import ApiError, require_perm
from common.db import get_db
from common.models import Component, ComponentLog, ComponentVersion, User, now
from common.resp import (
    COMP_GATE_FAILED,
    COMP_LOCK_CONFLICT,
    COMP_NOT_FOUND,
    COMP_SPEC_INVALID,
    COMP_STATE_CONFLICT,
    fmt_dt,
    ok,
)

router = APIRouter(prefix="/components", tags=["component-design"])

SPEC_UI_TYPES = frozenset({
    "text",
    "number",
    "select",
    "textarea",
    "bool",
    "rows",
    "resource",
    "mapEditor",
    "args-table",
    "kv-table",
    "params-table",
    "table-picker",
    "field-select",
    "topic-select",
    "dir-select",
    "upstream-ref",
    "var-table",
    "deps-list",
    "exec-node-tag",
    "hint",
})

DISPATCHABLE_EXECUTORS = frozenset({
    "sql",
    "shell",
    "python",
    "ssh",
    "procedure",
    "http",
    "file",
    "sync",
    "file_sync",
    "smoke",
})

FORBIDDEN_TEXT = ("<script", "function", "=>", "def ", "class ", "import ", "eval(", "exec(")


class ComponentCreateBody(BaseModel):
    type: str
    name: str
    profile: str = "dag"
    category: Optional[str] = None
    execution_model: str = "dag-engine"
    executor: Optional[str] = None
    description: Optional[str] = None
    spec: dict[str, Any] = {}


class DraftBody(BaseModel):
    draft_rev: int = 0
    spec: dict[str, Any]
    remark: Optional[str] = None


class PublishBody(BaseModel):
    version: Optional[int] = None
    remark: Optional[str] = None


def _spec_hash(spec: dict[str, Any]) -> str:
    raw = json.dumps(spec or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _walk(value: Any, path: str = "$") -> list[str]:
    msgs: list[str] = []
    if callable(value):
        return [f"{path} must be pure data"]
    if isinstance(value, str):
        low = value.lower()
        if any(token in low for token in FORBIDDEN_TEXT):
            msgs.append(f"{path} contains executable fragment")
    elif isinstance(value, list):
        for i, item in enumerate(value):
            msgs.extend(_walk(item, f"{path}[{i}]"))
    elif isinstance(value, dict):
        for k, item in value.items():
            msgs.extend(_walk(item, f"{path}.{k}"))
    return msgs


def validate_spec_pure_data(spec: dict[str, Any]) -> list[str]:
    return _walk(spec)


def _gate_drop_policy(spec: dict[str, Any]) -> list[str]:
    policy = spec.get("dropPolicy")
    if policy is None:
        return []
    return [] if isinstance(policy, dict) else ["dropPolicy must be object"]


def _gate_references(spec: dict[str, Any]) -> list[str]:
    fields = spec.get("fields") or []
    if not isinstance(fields, list):
        return ["fields must be array"]
    seen = set()
    msgs: list[str] = []
    for i, f in enumerate(fields):
        if not isinstance(f, dict) or not f.get("key"):
            msgs.append(f"fields[{i}].key is required")
            continue
        key = str(f["key"])
        if key in seen:
            msgs.append(f"duplicate field key: {key}")
        seen.add(key)
    return msgs


def _latest_version(db: Session, comp: Component) -> ComponentVersion | None:
    return (
        db.query(ComponentVersion)
        .filter(ComponentVersion.component_id == comp.id)
        .order_by(ComponentVersion.version.desc())
        .first()
    )


def _component_or_404(db: Session, type_name: str) -> Component:
    comp = db.query(Component).filter(Component.type == type_name).first()
    if comp is None:
        raise ApiError(COMP_NOT_FOUND, status=404, msg="component not found")
    return comp


def _version_row(v: ComponentVersion) -> dict[str, Any]:
    return {
        "version": v.version,
        "state": v.state,
        "specHash": v.spec_hash,
        "remark": v.remark,
        "publishedBy": v.published_by,
        "publishedTime": fmt_dt(v.published_time),
        "createdAt": fmt_dt(v.create_time),
    }


@router.get("/registry")
def registry(db: Session = Depends(get_db)):
    rows = db.query(Component).order_by(Component.update_time.desc()).all()
    return ok([
        {
            "type": c.type,
            "name": c.name,
            "profile": c.profile,
            "scope": c.scope,
            "state": c.state,
            "publishedVersion": c.published_version or 0,
            "executionModel": c.execution_model,
            "executor": c.executor,
            "updatedAt": fmt_dt(c.update_time),
        }
        for c in rows
    ])


@router.post("")
def create_component(body: ComponentCreateBody, user: User = Depends(require_perm("design_component")), db: Session = Depends(get_db)):
    if validate_spec_pure_data(body.spec):
        raise ApiError(COMP_SPEC_INVALID, status=422, msg="component spec is not pure data")
    if db.query(Component).filter(Component.type == body.type).first() is not None:
        raise ApiError(COMP_STATE_CONFLICT, status=409, msg="component type already exists")
    comp = Component(
        type=body.type,
        name=body.name,
        category=body.category,
        profile=body.profile,
        scope="user",
        execution_model=body.execution_model,
        executor=body.executor,
        executable=body.execution_model not in ("canvas-device", "passthrough", "template", "nonExecutable"),
        state="draft",
        draft_rev=1,
        description=body.description,
        owner_id=user.id,
    )
    db.add(comp)
    db.flush()
    spec_hash = _spec_hash(body.spec)
    db.add(ComponentVersion(
        component_id=comp.id,
        type=comp.type,
        version=1,
        state="draft",
        spec_json=json.dumps(body.spec, ensure_ascii=False),
        spec_hash=spec_hash,
        remark="initial draft",
    ))
    db.add(ComponentLog(component_id=comp.id, type=comp.type, version=1, action="create", spec_hash=spec_hash, operator=user.user_name))
    db.commit()
    return ok({"type": comp.type, "draftRev": comp.draft_rev, "version": 1, "specHash": spec_hash})


@router.get("/{type_name}/draft")
def get_draft(type_name: str, db: Session = Depends(get_db)):
    comp = _component_or_404(db, type_name)
    ver = _latest_version(db, comp)
    spec = json.loads(ver.spec_json) if ver and ver.spec_json else {}
    return ok({
        "type": comp.type,
        "name": comp.name,
        "state": comp.state,
        "draftRev": comp.draft_rev,
        "spec": spec,
        "specHash": _spec_hash(spec),
    })


@router.put("/{type_name}/draft")
def save_draft(type_name: str, body: DraftBody, user: User = Depends(require_perm("design_component")), db: Session = Depends(get_db)):
    comp = _component_or_404(db, type_name)
    if body.draft_rev != (comp.draft_rev or 0):
        raise ApiError(COMP_LOCK_CONFLICT, status=409, data={"currentRev": comp.draft_rev or 0})
    violations = validate_spec_pure_data(body.spec)
    if violations:
        raise ApiError(COMP_SPEC_INVALID, status=422, data={"violations": violations})
    next_version = (_latest_version(db, comp).version if _latest_version(db, comp) else 0) + 1
    comp.draft_rev = (comp.draft_rev or 0) + 1
    comp.state = "draft"
    spec_hash = _spec_hash(body.spec)
    db.add(ComponentVersion(
        component_id=comp.id,
        type=comp.type,
        version=next_version,
        state="draft",
        spec_json=json.dumps(body.spec, ensure_ascii=False),
        spec_hash=spec_hash,
        remark=body.remark,
    ))
    db.add(ComponentLog(component_id=comp.id, type=comp.type, version=next_version, action="update_draft", spec_hash=spec_hash, operator=user.user_name, remark=body.remark))
    db.commit()
    return ok({"type": comp.type, "draftRev": comp.draft_rev, "version": next_version, "specHash": spec_hash})


@router.get("/{type_name}/versions")
def list_versions(type_name: str, db: Session = Depends(get_db)):
    comp = _component_or_404(db, type_name)
    rows = (
        db.query(ComponentVersion)
        .filter(ComponentVersion.component_id == comp.id)
        .order_by(ComponentVersion.version.desc())
        .all()
    )
    return ok({"items": [_version_row(v) for v in rows]})


@router.post("/{type_name}/versions")
def freeze_version(type_name: str, user: User = Depends(require_perm("design_component")), db: Session = Depends(get_db)):
    comp = _component_or_404(db, type_name)
    ver = _latest_version(db, comp)
    if ver is None:
        raise ApiError(COMP_NOT_FOUND, status=404, msg="draft version not found")
    ver.state = "frozen"
    comp.state = "draft"
    db.add(ComponentLog(component_id=comp.id, type=comp.type, version=ver.version, action="freeze_version", spec_hash=ver.spec_hash, operator=user.user_name))
    db.commit()
    return ok(_version_row(ver))


def run_publish_gates(comp: Component, ver: ComponentVersion) -> list[dict[str, Any]]:
    spec = json.loads(ver.spec_json) if ver.spec_json else {}
    violations = validate_spec_pure_data(spec) + _gate_drop_policy(spec) + _gate_references(spec)
    if comp.execution_model == "dag-engine" and comp.executor and comp.executor not in DISPATCHABLE_EXECUTORS:
        violations.append("executor is not dispatchable")
    return [{"gate": "spec", "ok": not violations, "msg": "; ".join(violations)}]


@router.post("/{type_name}/publish")
def publish_component_version(type_name: str, body: PublishBody, user: User = Depends(require_perm("publish_component")), db: Session = Depends(get_db)):
    comp = _component_or_404(db, type_name)
    ver = (
        db.query(ComponentVersion)
        .filter(ComponentVersion.component_id == comp.id, ComponentVersion.version == body.version)
        .first()
        if body.version
        else _latest_version(db, comp)
    )
    if ver is None:
        raise ApiError(COMP_NOT_FOUND, status=404, msg="version not found")
    gates = run_publish_gates(comp, ver)
    if any(not g["ok"] for g in gates):
        raise ApiError(COMP_GATE_FAILED, status=422, data={"gates": gates})
    ver.state = "published"
    ver.published_by = user.user_name
    ver.published_time = now()
    comp.state = "published"
    comp.published_version = ver.version
    db.add(ComponentLog(component_id=comp.id, type=comp.type, version=ver.version, action="publish", spec_hash=ver.spec_hash, operator=user.user_name, remark=body.remark))
    db.commit()
    return ok({"type": comp.type, "publishedVersion": ver.version, "specHash": ver.spec_hash, "gates": gates})


@router.post("/{type_name}/offline")
def offline_component(type_name: str, user: User = Depends(require_perm("publish_component")), db: Session = Depends(get_db)):
    comp = _component_or_404(db, type_name)
    comp.state = "offline"
    db.add(ComponentLog(component_id=comp.id, type=comp.type, version=comp.published_version or 0, action="offline", operator=user.user_name))
    db.commit()
    return ok(True)


@router.post("/{type_name}/rollback")
def rollback_component(type_name: str, body: PublishBody, user: User = Depends(require_perm("publish_component")), db: Session = Depends(get_db)):
    comp = _component_or_404(db, type_name)
    if body.version is None:
        raise ApiError(COMP_NOT_FOUND, status=404, msg="version is required")
    ver = db.query(ComponentVersion).filter(ComponentVersion.component_id == comp.id, ComponentVersion.version == body.version).first()
    if ver is None:
        raise ApiError(COMP_NOT_FOUND, status=404, msg="version not found")
    comp.published_version = ver.version
    comp.state = "published"
    ver.state = "published"
    db.add(ComponentLog(component_id=comp.id, type=comp.type, version=ver.version, action="rollback", spec_hash=ver.spec_hash, operator=user.user_name, remark=body.remark))
    db.commit()
    return ok({"type": comp.type, "publishedVersion": ver.version})


@router.get("/{type_name}/impact")
def impacted_workflows(type_name: str):
    return ok({"type": type_name, "items": []})
