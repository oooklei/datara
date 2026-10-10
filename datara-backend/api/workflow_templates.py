"""Workflow template CRUD, version history, instantiation, and optional upgrades."""

import copy
import json
import re
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.auth import ApiError, get_current_user, require_perm
from common.db import get_db
from common.models import WfDefinition, WfDefinitionLog, WfTemplate, WfTemplateVersion, WorkflowInstance
from common.resp import WF_NOT_FOUND, WF_PARAM_INVALID, WF_RELEASED_LOCKED, WF_VERSION_CONFLICT, fmt_dt, ok
from master.state import INSTANCE_RUNNING_STATES
from api.wf_definition import _next_code

router = APIRouter(prefix="/workflow-templates", tags=["workflow-template"])


class TemplateBody(BaseModel):
    name: str
    category: str = ""
    description: Optional[str] = None
    template_json: dict = Field(alias="templateJson")
    base_version: Optional[int] = Field(None, alias="baseVersion")


class InstantiateBody(BaseModel):
    name: Optional[str] = None


class UpgradeBody(BaseModel):
    base_version: Optional[int] = Field(None, alias="baseVersion")
    template_version: Optional[int] = Field(None, alias="templateVersion")
    target_template_version: Optional[int] = Field(None, alias="targetTemplateVersion")


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


# 图内身份字符串形如 n_12 / e_21 / br_8；复合引用形如 "n_13:input"
_ID_RE = re.compile(r"^([a-z]+)_(\d+)$")
_TEXT_KEYS = {"name", "value", "description"}


def _rewrite_graph_ids(doc: dict, allocate) -> dict:
    """重建文档，将所有 id 样式字符串经 allocate(old) 重写（含 "id:handle" 复合引用）。"""

    def walk(value: Any, key: str = "") -> Any:
        if isinstance(value, dict):
            return {k: walk(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v, key) for v in value]
        if isinstance(value, str) and key not in _TEXT_KEYS:
            if _ID_RE.match(value):
                return allocate(value)
            head, sep, tail = value.partition(":")
            if sep and _ID_RE.match(head):
                return allocate(head) + sep + tail
        return value

    return walk(doc)


def _fresh_graph(source: dict, wf_id: str, name: str, template_id: int, template_version: int) -> dict:
    """Clone a template while replacing every graph-owned identity and its references.

    新 ID 确定性生成：按前缀取全文档最大序号（含嵌套 data 中的 id）+1 起依序递增。
    """
    doc = copy.deepcopy(source)
    max_seq: dict[str, int] = {}

    def scan(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                scan(v, k)
        elif isinstance(value, list):
            for v in value:
                scan(v, key)
        elif isinstance(value, str) and key not in _TEXT_KEYS:
            m = _ID_RE.match(value)
            if m:
                prefix, seq = m.group(1), int(m.group(2))
                if seq > max_seq.get(prefix, 0):
                    max_seq[prefix] = seq

    scan(doc)
    counters = dict(max_seq)
    mappings: dict[str, str] = {}

    def allocate(old: str) -> str:
        fresh = mappings.get(old)
        if fresh is None:
            prefix = _ID_RE.match(old).group(1)
            counters[prefix] = counters.get(prefix, 0) + 1
            fresh = f"{prefix}_{counters[prefix]}"
            mappings[old] = fresh
        return fresh

    for collection in ("nodes", "edges", "variables", "groups"):
        for item in doc.get(collection) or []:
            old = item.get("id") if isinstance(item, dict) else None
            if isinstance(old, str) and _ID_RE.match(old):
                allocate(old)  # 仅登记 旧→新 映射；重写统一在 walk 阶段完成

    doc = _rewrite_graph_ids(doc, allocate)
    doc["id"] = wf_id
    doc["name"] = name
    doc["version"] = 1
    meta = dict(doc.get("meta") or {})
    meta.update({"templateId": template_id, "templateVersion": template_version})
    doc["meta"] = meta
    return doc


def _normalized_graph(doc: dict) -> dict:
    """归一化图文档供跨版本 diff：仅保留四集合，身份按位置重编（模板/实例 ID 体系不同）。"""
    counters: dict[str, int] = {}
    mappings: dict[str, str] = {}

    def allocate(old: str) -> str:
        fresh = mappings.get(old)
        if fresh is None:
            prefix = _ID_RE.match(old).group(1)
            counters[prefix] = counters.get(prefix, 0) + 1
            fresh = f"{prefix}_{counters[prefix]}"
            mappings[old] = fresh
        return fresh

    norm: dict[str, Any] = {}
    for collection in ("nodes", "edges", "variables", "groups"):
        for item in doc.get(collection) or []:
            if isinstance(item, dict) and isinstance(item.get("id"), str) and _ID_RE.match(item["id"]):
                allocate(item["id"])  # 先按集合顺序登记 旧→新；重写统一在 walk 阶段完成
        norm[collection] = list(doc.get(collection) or [])
    return _rewrite_graph_ids(norm, allocate)


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
def list_templates(user=Depends(get_current_user), db: Session = Depends(get_db)):
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
def upgrade_status(wf_id: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
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
def preview_upgrade(template_id: int, wf_id: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    template = _template_or_404(db, template_id)
    wf = db.get(WfDefinition, wf_id)
    if wf is None:
        raise ApiError(WF_NOT_FOUND, status=404)
    current = json.loads(wf.graph_json or "{}")
    meta = current.get("meta") or {}
    if meta.get("templateId") != template.id:
        raise ApiError(WF_PARAM_INVALID, "实例并非从该模板创建", status=409)
    target = json.loads(template.template_json)
    return ok({"workflowVersion": wf.version, "currentVersion": int(meta.get("templateVersion") or 0),
               "latestVersion": template.version,
               "diff": _diff(_normalized_graph(current), _normalized_graph(target))})


@router.post("/{template_id}/upgrade/{wf_id}")
def confirm_upgrade(template_id: int, wf_id: str, body: UpgradeBody,
                    user=Depends(require_perm("edit_definition")), db: Session = Depends(get_db)):
    template = _template_or_404(db, template_id)
    wf = db.get(WfDefinition, wf_id)
    if wf is None:
        raise ApiError(WF_NOT_FOUND, status=404)
    db.refresh(wf)  # 升级前读库取最新状态，防同会话缓存（如其他会话直改 release_state/version）
    current = json.loads(wf.graph_json or "{}")
    meta = current.get("meta") or {}
    if meta.get("templateId") != template.id:
        raise ApiError(WF_PARAM_INVALID, "实例并非从该模板创建", status=409)
    if body.base_version is not None and body.base_version != wf.version:
        raise ApiError(WF_VERSION_CONFLICT, "工作流已被他人更新，请刷新后重试", status=409)
    if body.template_version is not None and body.template_version != int(meta.get("templateVersion") or 0):
        raise ApiError(WF_VERSION_CONFLICT, "实例模板版本已过期，请刷新后重试", status=409)
    if wf.release_state == "online":
        raise ApiError(WF_RELEASED_LOCKED, status=409)
    running = (db.query(WorkflowInstance)
               .filter(WorkflowInstance.wf_code == wf.code,
                       WorkflowInstance.state.in_(INSTANCE_RUNNING_STATES))
               .count())
    if running:
        raise ApiError(WF_RELEASED_LOCKED, "实例运行中，禁止升级模板", status=409)
    doc = _fresh_graph(json.loads(template.template_json), wf.id, wf.name, template.id, template.version)
    wf.version += 1
    doc["version"] = wf.version
    wf.graph_json = json.dumps(doc, ensure_ascii=False)
    db.add(WfDefinitionLog(wf_code=wf.code, version=wf.version, graph_json=wf.graph_json,
                           operator=user.user_name, remark=f"升级模板至 v{template.version}"))
    db.commit()
    return ok(doc)


@router.get("/{template_id}")
def get_template(template_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(_item(_template_or_404(db, template_id), True))


@router.put("/{template_id}")
def update_template(template_id: int, body: TemplateBody, user=Depends(require_perm("edit_definition")), db: Session = Depends(get_db)):
    row = _template_or_404(db, template_id)
    name = body.name.strip()
    if not name:
        raise ApiError(WF_PARAM_INVALID, "模板名称不能为空", status=400)
    if body.base_version is not None and body.base_version != row.version:
        raise ApiError(WF_VERSION_CONFLICT, "模板已被他人更新，请刷新后重试", status=409)
    row.name, row.category, row.description = name, body.category.strip(), body.description
    row.template_json = json.dumps(body.template_json, ensure_ascii=False)
    row.version += 1
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
def list_versions(template_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
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
