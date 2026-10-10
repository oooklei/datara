"""Workflow template CRUD, version history, instantiation, and optional upgrades."""

import copy
import json
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.auth import ApiError, require_perm
from common.db import get_db
from common.models import WfDefinition, WfDefinitionLog, WfTemplate, WfTemplateVersion
from common.resp import WF_NOT_FOUND, WF_PARAM_INVALID, fmt_dt, ok
from api.wf_definition import _next_code

router = APIRouter(prefix="/workflow-templates", tags=["workflow-template"])


class TemplateBody(BaseModel):
    name: str
    category: str = ""
    description: Optional[str] = None
    template_json: dict = Field(alias="templateJson")


class InstantiateBody(BaseModel):
    name: Optional[str] = None


def _template_or_404(db: Session, template_id: int) -> WfTemplate:
    row = db.get(WfTemplate, template_id)
    if row is None:
        raise ApiError(WF_NOT_FOUND, "工作流模板不存在", status=404)
    return row


def _item(row: WfTemplate, include_json: bool = False) -> dict:
    result = {
        "id": row.id, "name": row.name, "category": row.category,
        "description": row.description or "", "version": row.version,
        "createdBy": row.created_by or "", "updatedAt": fmt_dt(row.updated_at),
    }
    if include_json:
        result["templateJson"] = json.loads(row.template_json)
    return result


def _snapshot(db: Session, row: WfTemplate) -> None:
    db.add(WfTemplateVersion(
        template_id=row.id, version=row.version, name=row.name, category=row.category,
        description=row.description, template_json=row.template_json, created_by=row.created_by,
    ))


def _fresh_graph(source: dict, wf_id: str, name: str, template_id: int, template_version: int) -> dict:
    """Clone a template while replacing every graph-owned identity and its references."""
    doc = copy.deepcopy(source)
    mappings: dict[str, str] = {}
    for collection, prefix in (("nodes", "n"), ("edges", "e"), ("variables", "v"), ("groups", "g")):
        for item in doc.get(collection) or []:
            old = item.get("id")
            if isinstance(old, str):
                mappings[old] = f"{prefix}_{uuid.uuid4().hex[:12]}"
                item["id"] = mappings[old]

    def replace_refs(value: Any, key: str = "") -> Any:
        if isinstance(value, dict):
            return {k: replace_refs(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [replace_refs(v, key) for v in value]
        if isinstance(value, str) and value in mappings and key not in {"name", "value", "description"}:
            return mappings[value]
        return value

    doc = replace_refs(doc)
    doc["id"] = wf_id
    doc["name"] = name
    doc["version"] = 1
    meta = dict(doc.get("meta") or {})
    meta.update({"templateId": template_id, "templateVersion": template_version})
    doc["meta"] = meta
    return doc


def _diff(before: Any, after: Any, path: str = "") -> list[dict]:
    if before == after:
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        out: list[dict] = []
        for key in sorted(set(before) | set(after)):
            out.extend(_diff(before.get(key), after.get(key), f"{path}.{key}".lstrip(".")))
        return out
    if isinstance(before, list) and isinstance(after, list):
        out = []
        for idx in range(max(len(before), len(after))):
            out.extend(_diff(before[idx] if idx < len(before) else None,
                             after[idx] if idx < len(after) else None, f"{path}[{idx}]"))
        return out
    return [{"path": path, "before": before, "after": after}]


@router.get("")
def list_templates(db: Session = Depends(get_db)):
    return ok([_item(row) for row in db.query(WfTemplate).order_by(WfTemplate.updated_at.desc()).all()])


@router.post("")
def create_template(body: TemplateBody, user=Depends(require_perm("edit_definition")), db: Session = Depends(get_db)):
    name = body.name.strip()
    if not name:
        raise ApiError(WF_PARAM_INVALID, "模板名称不能为空", status=400)
    row = WfTemplate(name=name, category=body.category.strip(), description=body.description,
                     template_json=json.dumps(body.template_json, ensure_ascii=False), version=1,
                     created_by=user.user_name)
    db.add(row)
    db.flush()
    _snapshot(db, row)
    db.commit()
    return ok(_item(row, True))


@router.get("/upgrade-status/{wf_id}")
def upgrade_status(wf_id: str, db: Session = Depends(get_db)):
    wf = db.get(WfDefinition, wf_id)
    if wf is None:
        raise ApiError(WF_NOT_FOUND, status=404)
    doc = json.loads(wf.graph_json or "{}")
    meta = doc.get("meta") or {}
    template_id = meta.get("templateId")
    current = int(meta.get("templateVersion") or 0)
    template = db.get(WfTemplate, template_id) if template_id else None
    latest = template.version if template else current
    return ok({"upgradeAvailable": bool(template and latest > current), "templateId": template_id,
               "currentVersion": current, "latestVersion": latest})


@router.get("/{template_id}/diff/{wf_id}")
def preview_upgrade(template_id: int, wf_id: str, db: Session = Depends(get_db)):
    template = _template_or_404(db, template_id)
    wf = db.get(WfDefinition, wf_id)
    if wf is None:
        raise ApiError(WF_NOT_FOUND, status=404)
    current = json.loads(wf.graph_json or "{}")
    meta = current.get("meta") or {}
    target = json.loads(template.template_json)
    return ok({"currentVersion": int(meta.get("templateVersion") or 0), "latestVersion": template.version,
               "diff": _diff(current, target)})


@router.post("/{template_id}/upgrade/{wf_id}")
def confirm_upgrade(template_id: int, wf_id: str, user=Depends(require_perm("edit_definition")), db: Session = Depends(get_db)):
    template = _template_or_404(db, template_id)
    wf = db.get(WfDefinition, wf_id)
    if wf is None:
        raise ApiError(WF_NOT_FOUND, status=404)
    doc = _fresh_graph(json.loads(template.template_json), wf.id, wf.name, template.id, template.version)
    wf.version += 1
    doc["version"] = wf.version
    wf.graph_json = json.dumps(doc, ensure_ascii=False)
    db.add(WfDefinitionLog(wf_code=wf.code, version=wf.version, graph_json=wf.graph_json,
                           operator=user.user_name, remark=f"升级模板至 v{template.version}"))
    db.commit()
    return ok(doc)


@router.get("/{template_id}")
def get_template(template_id: int, db: Session = Depends(get_db)):
    return ok(_item(_template_or_404(db, template_id), True))


@router.put("/{template_id}")
def update_template(template_id: int, body: TemplateBody, user=Depends(require_perm("edit_definition")), db: Session = Depends(get_db)):
    row = _template_or_404(db, template_id)
    name = body.name.strip()
    if not name:
        raise ApiError(WF_PARAM_INVALID, "模板名称不能为空", status=400)
    row.name, row.category, row.description = name, body.category.strip(), body.description
    row.template_json = json.dumps(body.template_json, ensure_ascii=False)
    row.version += 1
    row.created_by = user.user_name
    _snapshot(db, row)
    db.commit()
    return ok(_item(row, True))


@router.delete("/{template_id}")
def delete_template(template_id: int, user=Depends(require_perm("edit_definition")), db: Session = Depends(get_db)):
    row = _template_or_404(db, template_id)
    db.query(WfTemplateVersion).filter(WfTemplateVersion.template_id == row.id).delete()
    db.delete(row)
    db.commit()
    return ok(True)


@router.get("/{template_id}/versions")
def list_versions(template_id: int, db: Session = Depends(get_db)):
    _template_or_404(db, template_id)
    rows = db.query(WfTemplateVersion).filter(WfTemplateVersion.template_id == template_id).order_by(WfTemplateVersion.version.desc()).all()
    return ok([{"version": row.version, "name": row.name, "category": row.category,
                "description": row.description or "", "templateJson": json.loads(row.template_json),
                "createdBy": row.created_by or "", "updatedAt": fmt_dt(row.created_at)} for row in rows])


@router.post("/{template_id}/instantiate")
def instantiate(template_id: int, body: InstantiateBody, user=Depends(require_perm("edit_definition")), db: Session = Depends(get_db)):
    template = _template_or_404(db, template_id)
    wf_id = "wf_" + uuid.uuid4().hex[:8]
    name = (body.name or template.name).strip() or template.name
    doc = _fresh_graph(json.loads(template.template_json), wf_id, name, template.id, template.version)
    wf = WfDefinition(id=wf_id, code=_next_code(db), name=name, version=1, release_state="offline",
                      flag="yes", project_code="default", tags=[], graph_json=json.dumps(doc, ensure_ascii=False),
                      owner_id=user.id)
    db.add(wf)
    db.flush()
    db.add(WfDefinitionLog(wf_code=wf.code, version=1, graph_json=wf.graph_json,
                           operator=user.user_name, remark=f"从模板 {template.name} v{template.version} 创建"))
    db.commit()
    return ok({"id": wf.id, "code": wf.code, "version": wf.version})
