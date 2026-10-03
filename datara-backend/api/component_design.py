"""组件草稿 API（M1 · 治理设计 §18.2 五端点 + §16 乐观锁 + 红线 2 纯数据校验）。

与 M0 只读目录（api/component.py）的关系：M0 下发系统内置目录（快照文件，不落库），
本模块承载**用户自建组件**（t_component 三表，scope=user）。路由同挂 /components 前缀，
路径段数不同（/draft、/versions 后缀）互不冲突。

- POST /components                    创建组件草稿（type 全局唯一，同建 v1 草稿版本）
- GET  /components/{type}/draft       读取草稿（主表身份 + 草稿 spec + draft_rev）
- PUT  /components/{type}/draft       保存草稿（乐观锁 draft_rev；纯数据校验 422）
- POST /components/{type}/versions    冻结草稿为不可变版本（B5）
- GET  /components/{type}/versions    版本列表（B5）
- POST /components/{type}/publish     发布指定 frozen 版本（M2 D1，跑 §13 八项闸门）
- POST /components/{type}/offline     下线组件（M2 D3，§8：published→offline）
- POST /components/{type}/rollback    回滚到历史发布版本（M2 D3，§8：offline→published）
- GET  /components/{type}/impacted    影响面查询（M2 D3，§9.4：引用该组件的工作流清单）
- POST /components/{type}/refresh-refs 刷新引用（页面设计器 §9 发布即刷新，幂等）

设计要点（对齐治理文档）：
- 草稿内容不进主表：存 t_component_version 中 state=draft 的行（§16 设计决策），
  主表只存身份与状态（§7.1 不存 spec_json）
- 冻结语义（B5，§8 状态机自环）：草稿行 state→frozen（不可变），同时自动开启
  v+1 空草稿供继续迭代；publish 属 M2（frozen→published），M1 无发布入口
- 不可变性保证：应用层没有任何路径 UPDATE 非 draft 版本行（save_draft 只触达
  state=draft 行），冻结内容随行固化；spec_hash 规范化哈希供 §15 一致性校验
- 乐观锁仅在保存时校验（§16）：不匹配 409 COMP_LOCK_CONFLICT，data 带当前 draft_rev
- 纯数据校验（红线 2）：严格 JSON 往返（拒 NaN/Infinity）+ 递归扫描函数/代码片段
  + dropPolicy.autoName 占位符白名单（仅 {type}/{n}）
- 审计只追加（§7.3）：create / update_draft / freeze_version 落 t_component_log，含内容哈希
"""

import hashlib
import json
import re
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.auth import ApiError, require_perm
from api.graph_rules import _catalog as _load_catalog
from common.db import get_db
from common.log import get_logger
from common.models import (
    Component, ComponentLog, ComponentVersion, DataSource, GlobalParam, User,
    WfDefinition, WfDefinitionLog, WfVariable, now,
)
from common.resp import (
    COMP_DUPLICATE_TYPE,
    COMP_GATE_FAILED,
    COMP_LOCK_CONFLICT,
    COMP_NOT_FOUND,
    COMP_SPEC_INVALID,
    COMP_STATE_CONFLICT,
    fail,
    fmt_dt,
    ok,
)
from components.catalog import DISPATCHABLE_EXECUTORS as _CATALOG_DISPATCHABLE

logger = get_logger("api.component_design")

router = APIRouter(prefix="/components", tags=["component-design"])

PROFILES = ("dag", "etl", "stream", "topo")
EXECUTION_MODELS = ("dag-engine", "canvas-device", "demo-only", "runtime-only", "page")

# 红线 2：声明中禁止出现的函数/代码片段（大小写敏感子串，设计器产出为结构化 UI
# 文本，出现这些模式即异常；宁可误伤也不放行——B4 白名单校验是主闸门，此为兜底）
FORBIDDEN_SNIPPETS = (
    "function", "=>", "eval(", "new Function", "Function(",
    "<script", "javascript:", "__import__", "import ", "import(",
    "def ", "lambda ", "require(", "module.exports",
    "exec(", "subprocess", "os.system", "child_process",
    "${", "`",
)

# dropPolicy.autoName 模板仅允许的占位符（治理文档 §11）
_ALLOWED_PLACEHOLDERS = {"type", "n"}


def _spec_hash(spec: dict) -> str:
    """规范化内容哈希（键排序后 sha256）：B5 冻结版本与审计共用。"""
    canonical = json.dumps(spec, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _scan_pure_data(node, path: str, violations: list) -> None:
    """递归扫描 dict/list/字符串：键与字符串值命中禁用片段即记违规。"""
    if isinstance(node, dict):
        for k, v in node.items():
            key_path = "%s.%s" % (path, k)
            if isinstance(k, str):
                low = k.lower()
                for s in FORBIDDEN_SNIPPETS:
                    if s in k or s.lower() in low:
                        violations.append("字段名含代码片段「%s」: %s" % (s, key_path))
                        break
            _scan_pure_data(v, key_path, violations)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _scan_pure_data(v, "%s[%d]" % (path, i), violations)
    elif isinstance(node, str):
        for s in FORBIDDEN_SNIPPETS:
            if s in node:
                violations.append("%s 含代码片段「%s」" % (path or "声明", s))
                break


# 页面设计器 page DSL（execution_model=page）：widget kind 白名单 / 绑定 kind 与
# 必填字段（手动输入兜底 placeholder 即默认值）/ 画布尺寸钳制（设计器画布上限）
_WIDGET_KINDS = frozenset({
    # 布局容器
    "grid-row", "card", "tabs", "collapse", "divider", "spacer",
    # 基础元素
    "text", "heading", "rich-text", "image", "icon", "button", "badge", "link",
    # 表单输入
    "input", "number", "select", "date", "date-range", "switch", "slider",
    "radio", "checkbox", "cascader", "textarea", "upload",
    # 数据展示
    "table", "list", "descriptions", "statistic", "progress", "timeline", "tree",
    # 图表
    "chart-bar", "chart-line", "chart-pie", "chart-area", "chart-gauge", "chart-scatter",
    # 绑定元素
    "meta-field", "var-label", "query-result", "sys-status",
})
_BINDING_KINDS = frozenset({"metadata", "variable", "query", "static"})
# 必填字段表（§9.1 绑定形状）：query 特判——数据源引用型（datasourceId）与显式 SQL 型
# （query）二者有其一即合法（数据源引用型绑定 SQL 后续在数据集钻取中补），见 _validate_page_spec
_BINDING_KIND_FIELDS = {"metadata": "path", "variable": "path", "static": "fallback"}


def _validate_page_spec(spec, violations: list) -> None:
    """page 声明结构校验：非 page 声明（无 page 键）不介入，行为零影响。"""
    page = spec.get("page") if isinstance(spec, dict) else None
    if page is None:
        return
    if not isinstance(page, dict) or page.get("version") != 1 or not isinstance(page.get("widgets"), list):
        violations.append("page: 结构非法（需 version=1 与 widgets 数组）")
        return
    canvas = page.get("canvas")
    width = canvas.get("width") if isinstance(canvas, dict) else None
    height = canvas.get("height") if isinstance(canvas, dict) else None
    if not (isinstance(width, (int, float)) and not isinstance(width, bool)
            and isinstance(height, (int, float)) and not isinstance(height, bool)
            and 140 <= width <= 520 and 320 <= height <= 1200):
        violations.append("page.canvas: 尺寸越界（宽 140-520 / 高 320-1200）")

    def walk(widgets, prefix):
        for i, w in enumerate(widgets):
            p = "%swidgets[%d]" % (prefix, i)
            if not isinstance(w, dict):
                violations.append("%s: 非对象" % p)
                continue
            if not w.get("id"):
                violations.append("%s.widget.id: 缺失" % p)
            if w.get("kind") not in _WIDGET_KINDS:
                violations.append("%s.widget.kind: 未知 kind=%r" % (p, w.get("kind")))
            rect = w.get("rect")
            if not isinstance(rect, dict):
                violations.append("%s.widget.rect: 缺失" % p)
            for key, b in (w.get("bindings") or {}).items():
                bp = "%s.bindings.%s" % (p, key)
                if not isinstance(b, dict) or b.get("kind") not in _BINDING_KINDS:
                    violations.append("%s.kind: 非法" % bp)
                    continue
                if b["kind"] == "query":
                    if not b.get("query") and b.get("datasourceId") is None:
                        violations.append("%s.query: 需 datasourceId 或 query 其一" % bp)
                    continue
                field = _BINDING_KIND_FIELDS[b["kind"]]
                if not b.get(field):
                    violations.append("%s.%s: 缺失（手动输入兜底 placeholder 即默认值）" % (bp, field))
            walk(w.get("children") or [], p + ".")

    walk(page["widgets"], "")


def validate_spec_pure_data(spec) -> list:
    """纯数据校验（红线 2，实施计划 Task B2）：返回违规描述清单（空=通过）。

    1) 严格 JSON 往返：NaN/Infinity/不可序列化对象即违规（pydantic 已保 dict，
       此处防 json.loads 放进来的非严格字面量）；
    2) 递归扫描函数/代码片段；
    3) dropPolicy.autoName 占位符白名单（仅 {type}/{n}）；
    4) page 声明结构校验（widget kind 白名单/绑定必填字段/画布尺寸钳制）。
    纯函数，可独立单测。
    """
    violations: list = []
    if not isinstance(spec, dict):
        return ["声明必须是 JSON 对象"]
    try:
        json.dumps(spec, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        violations.append("声明不是严格 JSON 数据: %s" % exc)
        return violations
    _scan_pure_data(spec, "", violations)
    auto_name = (spec.get("dropPolicy") or {}).get("autoName")
    if isinstance(auto_name, str):
        for ph in re.findall(r"\{([^{}]*)\}", auto_name):
            if ph not in _ALLOWED_PLACEHOLDERS:
                violations.append(
                    "dropPolicy.autoName 占位符 {%s} 不在白名单（仅允许 {type}/{n}）" % ph)
    _validate_page_spec(spec, violations)
    return violations


class ComponentCreateBody(BaseModel):
    type: str
    name: str
    profile: Literal["dag", "etl", "stream", "topo"]
    execution_model: Literal["dag-engine", "canvas-device", "demo-only", "runtime-only", "page"]
    category: Optional[str] = None
    executor: Optional[str] = None
    executable: bool = True
    description: Optional[str] = None
    tags: Optional[list] = None
    spec: dict = {}


class DraftSaveBody(BaseModel):
    draft_rev: int
    spec: dict
    remark: Optional[str] = None


def _get_or_404(db: Session, type_name: str) -> Component:
    row = db.query(Component).filter(Component.type == type_name).first()
    if row is None:
        raise ApiError(COMP_NOT_FOUND, status=404)
    return row


def _draft_version(db: Session, component_id: int) -> ComponentVersion:
    """取 state=draft 的草稿版本行（§16：草稿存版本表，缺失=已被冻结且无新草稿）。"""
    row = (
        db.query(ComponentVersion)
        .filter(ComponentVersion.component_id == component_id,
                ComponentVersion.state == "draft")
        .first()
    )
    if row is None:
        raise ApiError(COMP_STATE_CONFLICT, status=409, msg="无进行中的草稿，请新建草稿版本")
    return row


def _append_log(db: Session, comp: Component, version: int, action: str,
                spec_hash: str, operator: str, remark: Optional[str]) -> None:
    db.add(ComponentLog(
        component_id=comp.id, type=comp.type, version=version, action=action,
        spec_hash=spec_hash, operator=operator, remark=remark,
    ))


@router.post("", summary="创建组件草稿")
def create_component(
    body: ComponentCreateBody,
    user: User = Depends(require_perm("design_component")),
    db: Session = Depends(get_db),
):
    """创建用户组件（scope=user）：主表身份行 + v1 草稿版本行 + 审计 create。"""
    type_name = (body.type or "").strip()
    if not type_name or not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", type_name):
        return fail(COMP_SPEC_INVALID, "type 须为小写字母开头的 [a-z0-9_]（2~64 位）")
    if not (body.name or "").strip():
        return fail(COMP_SPEC_INVALID, "组件名称不能为空")
    if db.query(Component).filter(Component.type == type_name).first() is not None:
        raise ApiError(COMP_DUPLICATE_TYPE, status=409,
                       msg="组件 type「%s」已被占用" % type_name)
    violations = validate_spec_pure_data(body.spec)
    if violations:
        raise ApiError(COMP_SPEC_INVALID, status=422,
                       msg="初始声明非纯数据", data={"violations": violations})
    # 页面设计器产出的 UI 组件不可执行（page 模型红线）
    if body.execution_model == "page" and body.executable:
        raise ApiError(COMP_SPEC_INVALID, status=422,
                       msg="execution_model=page 组件 executable 必须为 false")

    comp = Component(
        type=type_name, name=body.name.strip(), category=body.category,
        profile=body.profile, scope="user", execution_model=body.execution_model,
        executor=body.executor, executable=body.executable, state="draft",
        published_version=None, draft_rev=0, description=body.description,
        tags=body.tags or [], owner_id=user.id,
    )
    db.add(comp)
    db.flush()  # 取 comp.id
    db.add(ComponentVersion(
        component_id=comp.id, type=type_name, version=1, state="draft",
        spec_json=json.dumps(body.spec, ensure_ascii=False), spec_hash=_spec_hash(body.spec),
        remark="初始草稿",
    ))
    _append_log(db, comp, 1, "create", _spec_hash(body.spec), user.user_name, None)
    db.commit()
    logger.info("创建组件草稿: %s（%s，操作人 %s）", type_name, body.profile, user.user_name)
    return ok({"type": type_name, "draftRev": 0, "draftVersion": 1})


@router.get("/{type_name}/draft", summary="读取组件草稿")
def get_draft(
    type_name: str,
    user: User = Depends(require_perm("design_component")),
    db: Session = Depends(get_db),
):
    comp = _get_or_404(db, type_name)
    draft = _draft_version(db, comp.id)
    return ok({
        "type": comp.type, "name": comp.name, "category": comp.category,
        "profile": comp.profile, "scope": comp.scope,
        "executionModel": comp.execution_model, "executor": comp.executor,
        "executable": comp.executable, "state": comp.state,
        "publishedVersion": comp.published_version,
        "draftRev": comp.draft_rev, "draftVersion": draft.version,
        "description": comp.description, "tags": comp.tags or [],
        "spec": json.loads(draft.spec_json) if draft.spec_json else {},
        "specHash": draft.spec_hash,
        "updatedAt": fmt_dt(comp.update_time),
    })


@router.put("/{type_name}/draft", summary="保存组件草稿（乐观锁）")
def save_draft(
    type_name: str,
    body: DraftSaveBody,
    user: User = Depends(require_perm("design_component")),
    db: Session = Depends(get_db),
):
    """保存草稿：draft_rev 不匹配 409（data.currentRev 供前端 diff）；纯数据 422。

    通过后 spec_json 原地更新（draft 行可变）、draft_rev+1、审计 update_draft。
    """
    comp = _get_or_404(db, type_name)
    if body.draft_rev != comp.draft_rev:
        raise ApiError(COMP_LOCK_CONFLICT, status=409,
                       data={"currentRev": comp.draft_rev})
    violations = validate_spec_pure_data(body.spec)
    if violations:
        raise ApiError(COMP_SPEC_INVALID, status=422,
                       msg="声明非纯数据", data={"violations": violations})
    draft = _draft_version(db, comp.id)
    draft.spec_json = json.dumps(body.spec, ensure_ascii=False)
    draft.spec_hash = _spec_hash(body.spec)
    comp.draft_rev += 1
    _append_log(db, comp, draft.version, "update_draft", draft.spec_hash,
                user.user_name, body.remark)
    db.commit()
    logger.info("保存组件草稿: %s rev=%d（操作人 %s）", type_name, comp.draft_rev, user.user_name)
    return ok({"draftRev": comp.draft_rev, "specHash": draft.spec_hash,
               "savedAt": fmt_dt(now())})


# ---------------- B5 冻结版本（实施计划 20260926 Task B5；§18.2 versions 两端点） ----------------

class FreezeBody(BaseModel):
    remark: Optional[str] = None


@router.post("/{type_name}/versions", summary="冻结草稿为不可变版本")
def freeze_version(
    type_name: str,
    body: FreezeBody,
    user: User = Depends(require_perm("design_component")),
    db: Session = Depends(get_db),
):
    """冻结：草稿行 state→frozen（内容随行固化不可变）+ 自动开启 v+1 空草稿（§8 自环）。

    publish 属 M2（frozen→published）；冻结不 bump draft_rev（草稿内容未变）。
    冻结备注只落审计日志（草稿行 remark 保留保存草稿时的语义）。
    """
    comp = _get_or_404(db, type_name)
    draft = _draft_version(db, comp.id)
    spec = json.loads(draft.spec_json) if draft.spec_json else {}
    violations = validate_spec_pure_data(spec)
    if violations:
        raise ApiError(COMP_SPEC_INVALID, status=422,
                       msg="草稿声明非纯数据，不可冻结", data={"violations": violations})
    frozen_version = draft.version
    draft.state = "frozen"
    db.add(ComponentVersion(
        component_id=comp.id, type=comp.type, version=frozen_version + 1,
        state="draft", spec_json=json.dumps({}, ensure_ascii=False),
        spec_hash=_spec_hash({}), remark="冻结 v%d 后自动开启" % frozen_version,
    ))
    _append_log(db, comp, frozen_version, "freeze_version", draft.spec_hash,
                user.user_name, body.remark)
    db.commit()
    logger.info("冻结组件版本: %s v%d（操作人 %s，新草稿 v%d）",
                type_name, frozen_version, user.user_name, frozen_version + 1)
    return ok({"frozenVersion": frozen_version, "draftVersion": frozen_version + 1,
               "draftRev": comp.draft_rev})


@router.get("/{type_name}/versions", summary="版本列表")
def list_versions(
    type_name: str,
    user: User = Depends(require_perm("design_component")),
    db: Session = Depends(get_db),
):
    """版本列表（version 倒序；不回 spec 全文——草稿经 /draft 读，冻结版按需在 M2 扩详情）。"""
    comp = _get_or_404(db, type_name)
    rows = (
        db.query(ComponentVersion)
        .filter(ComponentVersion.component_id == comp.id)
        .order_by(ComponentVersion.version.desc())
        .all()
    )
    return ok({
        "type": comp.type,
        "publishedVersion": comp.published_version,
        "items": [
            {
                "version": r.version,
                "state": r.state,
                "specHash": r.spec_hash,
                "remark": r.remark,
                "publishedBy": r.published_by,
                "publishedAt": fmt_dt(r.published_time),
                "createdAt": fmt_dt(r.create_time),
            }
            for r in rows
        ],
    })


# ---------------- M2 发布闸门（实施计划 20260926 Task D1；治理设计 §13 八项） ----------------
#
# 闸门逐项落位（§13 表格序号）：
#   1 权限        → require_perm("publish_component") 路由依赖（无权限 403，admin 独占 §14）
#   2 纯数据      → 闸门项 pure_data（复用 B2 validate_spec_pure_data）
#   3 字段白名单  → 闸门项 whitelist（uiType ∈ B3 收敛 9 基元 + pick 键白名单 §10.2）
#   4 dropPolicy  → 闸门项 drop_policy（键/枚举/模板占位符合法性，§11）
#   5 执行契约    → 闸门项 contract（红线 1：demo-only 禁发布；dag-engine 必绑 executor 且
#                   在分派注册表；canvas-device 必须 executable=false；runtime-only 强制
#                   paletteVisible=false——只能被装载物化消费，不出设计态 palette）
#   6 同名一致    → 闸门项 hash_consistency（与系统内置目录同名即拒绝：库内 type 全局唯一
#                   不可能跨 Profile 重复，唯一重名源是目录快照；快照无 spec_hash 可比，
#                   采纳保守裁定——拒绝发布杜绝 componentRef 引用歧义，§15）
#   7 乐观锁      → 端点前置校验（409 COMP_LOCK_CONFLICT，§16「保存草稿与发布时校验」）
#   8 引用完整性  → 闸门项 references（prefillFromUpstream ⊆ fields[].key；脚本库等外部
#                   实体引用位 M1 声明契约尚未定义，预留 db 注入扩展点）
# 任一闸门项失败 → 422 COMP_GATE_FAILED，data.items 返回**全部**逐项结果（一次反馈全量违规）。
# 不可绕过（§13 设计决策）：请求体仅 version/draft_rev/remark 三字段，pydantic 丢弃多余键，
# 无 force / 无豁免开关。

# 分派注册表（闸门第 5 项真源）：G-19 单一真源 — 由 components.catalog 统一定义
# （worker 执行器 ∪ 流三节点，master 引擎分派表 _exec_stream 承载流节点，数据面 worker/stream）。
# api 进程复用 catalog 常量（纯模块无副作用），不复制清单即无漂移可能。
DISPATCHABLE_EXECUTORS = _CATALOG_DISPATCHABLE

# uiType 白名单：B3 收敛 FieldKind 9 基元（前端 services/componentSpec.ts SPEC_UI_TYPES 同口径）
SPEC_UI_TYPES = frozenset({
    "text", "number", "bool", "select", "expr", "hint", "rows", "mapEditor", "resource",
})

# pick 键白名单（§10.2 的 17 键 + 2026-09-26 校验补充的 upstreamMax/fmSrcIndex/fmTgtIndex；
# 与前端 graph/profiles/types.ts ResourcePick 接口字段一一对应）
PICK_KEYS = frozenset({
    "mode", "dsKey", "tableKey", "nodeKey", "dsTypes", "src", "upstreamIndex", "multi",
    "writeAs", "insertKey", "excludeDsKey", "srcNodeType", "tgtNodeType", "srcDsKey",
    "srcTableKey", "tgtDsKey", "tgtTableKey", "upstreamMax", "fmSrcIndex", "fmTgtIndex",
})

# dropPolicy 键白名单（§11 封闭表：openInspectorOnDrop 已废弃不收）
DROP_POLICY_KEYS = frozenset({"snapToGrid", "autoName", "prefillFromUpstream", "autoConnect", "maxInstances"})
AUTO_CONNECT_VALUES = frozenset({"nearest", "none"})


def _gate_whitelist(spec: dict) -> list:
    """§13-3：fields 结构 + uiType 9 基元 + pick 键白名单。

    page DSL 声明（page 根节点）不适用 fields 白名单——结构合法性由
    _validate_page_spec（纯数据闸门内嵌，Task 2）承担（设计文档 §9.1 page 分支闸门）。
    """
    if isinstance(spec, dict) and "page" in spec:
        return []
    fields = spec.get("fields")
    if not isinstance(fields, list):
        return ["fields 必须为数组"]
    msgs: list = []
    seen: set = set()
    for i, f in enumerate(fields):
        path = "fields[%d]" % i
        if not isinstance(f, dict):
            msgs.append("%s 必须为对象" % path)
            continue
        key = f.get("key")
        if not isinstance(key, str) or not key.strip():
            msgs.append("%s.key 不能为空" % path)
        elif key in seen:
            msgs.append("%s.key 重复: %s" % (path, key))
        if isinstance(key, str):
            seen.add(key)
        if f.get("uiType") not in SPEC_UI_TYPES:
            msgs.append("%s.uiType「%s」不在白名单（9 基元）" % (path, f.get("uiType")))
        pick = f.get("pick")
        if pick is not None:
            if not isinstance(pick, dict):
                msgs.append("%s.pick 必须为对象" % path)
            else:
                for k in pick:
                    if k not in PICK_KEYS:
                        msgs.append("%s.pick 键「%s」不在白名单" % (path, k))
    return msgs


def _gate_drop_policy(spec: dict) -> list:
    """§13-4：dropPolicy 键白名单 + 枚举/类型合法性（占位符与函数禁用由纯数据闸门覆盖）。"""
    dp = spec.get("dropPolicy")
    if dp is None:
        return []
    if not isinstance(dp, dict):
        return ["dropPolicy 必须为对象"]
    msgs: list = []
    for k in dp:
        if k not in DROP_POLICY_KEYS:
            msgs.append("dropPolicy 键「%s」不在白名单（§11 封闭表）" % k)
    if "snapToGrid" in dp and not isinstance(dp["snapToGrid"], bool):
        msgs.append("dropPolicy.snapToGrid 必须为布尔值")
    if "autoName" in dp and not isinstance(dp["autoName"], str):
        msgs.append("dropPolicy.autoName 必须为字符串模板")
    pfu = dp.get("prefillFromUpstream")
    if pfu is not None and (not isinstance(pfu, list) or any(not isinstance(x, str) for x in pfu)):
        msgs.append("dropPolicy.prefillFromUpstream 必须为字符串数组")
    ac = dp.get("autoConnect")
    if ac is not None:
        if not isinstance(ac, dict):
            msgs.append("dropPolicy.autoConnect 必须为对象")
        else:
            for side in ("upstream", "downstream"):
                v = ac.get(side)
                if v is not None and v not in AUTO_CONNECT_VALUES:
                    msgs.append("dropPolicy.autoConnect.%s「%s」仅允许 nearest/none" % (side, v))
    mi = dp.get("maxInstances")
    if mi is not None and (isinstance(mi, bool) or not isinstance(mi, int) or mi < 0):
        msgs.append("dropPolicy.maxInstances 必须为非负整数（0=不限）")
    return msgs


def _gate_contract(comp: Component, spec: dict, executor_registry: frozenset) -> list:
    """§13-5 执行契约（红线 1，闸门核心）：按 execution_model 逐一裁定可执行性。"""
    em = comp.execution_model
    if em == "demo-only":
        return ["execution_model=demo-only 禁止发布（无执行实现，红线 1）"]
    if em == "dag-engine":
        executor = (comp.executor or "").strip()
        if not executor:
            return ["dag-engine 组件必须绑定 executor"]
        if executor not in executor_registry:
            return ["executor「%s」不在分派注册表（worker 执行器 + 流三节点）" % executor]
        return []
    if em == "canvas-device":
        if comp.executable:
            return ["canvas-device 组件必须 executable=false（画布装饰件不执行）"]
        return []
    if em == "runtime-only":
        if spec.get("paletteVisible") is not False:
            return ["runtime-only 组件必须声明 paletteVisible=false（仅装载期物化消费，不出设计态 palette）"]
        return []
    if em == "page":
        # 页面设计器产出的 UI 组件不可执行（Task 1 创建红线同款，发布侧闭环）
        if comp.executable:
            return ["page 组件必须 executable=false（页面设计器产出的 UI 组件不可执行）"]
        return []
    return ["execution_model「%s」不在执行契约范围" % em]


def _gate_references(spec: dict) -> list:
    """§13-8 引用完整性：声明内引用必须可解析。

    M1 声明契约的引用位只有 dropPolicy.prefillFromUpstream（目标=fields[].key）；
    脚本库脚本等外部实体引用位 M1 未定义（设计器不产出），扩展时在此函数加 db
    注入的实体存在性校验即可（函数保持纯数据入参）。
    """
    dp = spec.get("dropPolicy")
    pfu = dp.get("prefillFromUpstream") if isinstance(dp, dict) else None
    if not pfu or not isinstance(pfu, list):
        return []
    field_keys = {f.get("key") for f in spec.get("fields") or [] if isinstance(f, dict)}
    return [
        "dropPolicy.prefillFromUpstream 引用不存在的字段 key: %s" % k
        for k in pfu
        if isinstance(k, str) and k not in field_keys
    ]


def _gate_page_bindings(db: Session, spec: dict) -> list:
    """§9.1 page 分支发布闸门：绑定引用资源存在性（结构合法性由纯数据闸门承担）。

    - variable：$wf.x → 存在任一 WfVariable.name == 'x'（wf 维度最小实现：全局按 name 匹配）；
      $param.x → GlobalParam.name；$system.* 内置时间参数直接通过；
    - query：datasourceId 必须存在（db.get(DataSource, id) 非 None）；显式 SQL 内容不做校验；
    - metadata：path 三段结构（ds/库/表.字段）非空且末段含点号（不做 DB 连通验证）；
    - static：字面量兜底无引用，跳过。
    违规逐条返回：bindings.<槽>: 引用资源不存在（<引用>）。
    """
    page = spec.get("page") if isinstance(spec, dict) else None
    if not isinstance(page, dict):
        return []
    violations: list = []

    def walk(widgets) -> None:
        for w in widgets or []:
            if not isinstance(w, dict):
                continue
            for key, b in (w.get("bindings") or {}).items():
                if not isinstance(b, dict):
                    continue
                kind = b.get("kind")
                if kind == "variable":
                    path = b.get("path")
                    if not isinstance(path, str):
                        continue
                    if path.startswith("$system."):
                        continue  # 内置时间参数
                    model, name = None, ""
                    if path.startswith("$wf."):
                        model, name = WfVariable, path[len("$wf."):]
                    elif path.startswith("$param."):
                        model, name = GlobalParam, path[len("$param."):]
                    if model is not None and (
                            not name or db.query(model).filter(model.name == name).first() is None):
                        violations.append("bindings.%s: 引用资源不存在（%s）" % (key, path))
                elif kind == "query":
                    ds_id = b.get("datasourceId")
                    if isinstance(ds_id, bool) or not isinstance(ds_id, int) \
                            or db.get(DataSource, ds_id) is None:
                        violations.append("bindings.%s: 引用资源不存在（ds:%s）" % (key, ds_id))
                elif kind == "metadata":
                    path = b.get("path")
                    segs = path.split("/") if isinstance(path, str) else []
                    if len(segs) != 3 or not all(s.strip() for s in segs) or "." not in segs[2]:
                        violations.append("bindings.%s: 引用资源不存在（%s）" % (key, path))
                # static：字面量兜底，无引用，跳过
            walk(w.get("children"))

    walk(page.get("widgets"))
    return violations


def run_publish_gates(
    comp: Component,
    spec: dict,
    *,
    db: Optional[Session] = None,
    catalog_types: frozenset = frozenset(),
    executor_registry: frozenset = DISPATCHABLE_EXECUTORS,
) -> list:
    """发布闸门（§13 第 2/3/4/5/6/8 项 + §9.1 page 分支）：返回逐项结果 [{gate, ok, msg}]。

    纯函数为主（目录类型集/注册表注入；db 仅 §9.1 page 绑定存在性闸门使用，未注入时跳过）；
    第 1 项权限由路由依赖承载、第 7 项乐观锁由端点前置校验（409）——均不在本函数清单内。
    全项评估不短路，一次返回全部违规。
    """
    checks = [
        ("pure_data", validate_spec_pure_data(spec)),
        ("whitelist", _gate_whitelist(spec)),
        ("drop_policy", _gate_drop_policy(spec)),
        ("contract", _gate_contract(comp, spec, executor_registry)),
        ("hash_consistency",
         ["type「%s」与系统内置目录同名，同名定义一致性无法证明，拒绝发布（§13 第 6 项/§15）" % comp.type]
         if comp.type in catalog_types else []),
        ("references", _gate_references(spec)),
    ]
    if isinstance(spec, dict) and isinstance(spec.get("page"), dict):
        # §9.1 page 分支闸门：绑定资源存在性。仅 page 根节点介入，非 page 声明闸门清单零变化
        checks.append(("page_bindings", _gate_page_bindings(db, spec) if db is not None else []))
    return [
        {"gate": name, "ok": not msgs, "msg": "；".join(msgs)}
        for name, msgs in checks
    ]


class PublishBody(BaseModel):
    version: int
    draft_rev: int
    remark: Optional[str] = None


@router.post("/{type_name}/publish", summary="发布组件版本（§13 闸门）")
def publish_version(
    type_name: str,
    body: PublishBody,
    user: User = Depends(require_perm("publish_component")),
    db: Session = Depends(get_db),
):
    """发布指定 frozen 版本：跑 §13 八项闸门，通过后 frozen→published。

    - 仅 frozen 可发布（draft 需先冻结；published/offline 走 D3 rollback/offline 语义）；
      发布 vN 时已 published 的旧版本行自动转 offline 让位（既有工作流引用不受阻，§8）。
    - 乐观锁（§16）：draft_rev 与服务端不一致 → 409 COMP_LOCK_CONFLICT。
    - 闸门失败 → 422 COMP_GATE_FAILED，data.items 为逐项结果；失败不落任何状态变更。
    """
    comp = _get_or_404(db, type_name)
    if body.draft_rev != comp.draft_rev:
        raise ApiError(COMP_LOCK_CONFLICT, status=409,
                       data={"currentRev": comp.draft_rev})
    ver = (
        db.query(ComponentVersion)
        .filter(ComponentVersion.component_id == comp.id,
                ComponentVersion.version == body.version)
        .first()
    )
    if ver is None:
        raise ApiError(COMP_STATE_CONFLICT, status=409, msg="版本不存在")
    if ver.state != "frozen":
        raise ApiError(COMP_STATE_CONFLICT, status=409,
                       msg="仅 frozen 版本可发布（当前 %s）" % ver.state)
    spec = json.loads(ver.spec_json) if ver.spec_json else {}
    items = run_publish_gates(
        comp, spec, db=db, catalog_types=frozenset(_catalog_types()))
    failed = [i for i in items if not i["ok"]]
    if failed:
        logger.info("发布闸门拦截: %s v%d（%d 项未过，操作人 %s）",
                    type_name, body.version, len(failed), user.user_name)
        raise ApiError(COMP_GATE_FAILED, status=422, data={"items": items})

    superseded = 0
    for prev in (
        db.query(ComponentVersion)
        .filter(ComponentVersion.component_id == comp.id,
                ComponentVersion.state == "published",
                ComponentVersion.version != ver.version)
        .all()
    ):
        prev.state = "offline"  # 旧 published 让位：既有工作流引用仍可运行（§8 关键语义）
        superseded = max(superseded, prev.version)
    ver.state = "published"
    ver.published_by = user.user_name
    ver.published_time = now()
    comp.state = "published"
    comp.published_version = ver.version
    _append_log(db, comp, ver.version, "publish", ver.spec_hash, user.user_name,
                body.remark if body.remark else ("取代 v%d" % superseded if superseded else None))
    db.commit()
    logger.info("发布组件版本: %s v%d（操作人 %s%s）", type_name, ver.version,
                user.user_name, "，取代 v%d" % superseded if superseded else "")
    payload = {
        "type": comp.type, "publishedVersion": ver.version,
        "specHash": ver.spec_hash, "supersededVersion": superseded or None,
        "publishedAt": fmt_dt(ver.published_time),
    }
    payload["refresh"] = _refresh_refs(db, comp, user.user_name)  # §9 发布即刷新
    return ok(payload)


def _catalog_types() -> set:
    """系统内置目录 type 全集（闸门第 6 项同名拦截依据；复用 graph_rules 进程内缓存）。"""
    cat = _load_catalog()
    return {str(c.get("type") or "") for c in cat.get("components", [])} - {""}


# ---------------- D3 下线 / 回滚 / 影响面（实施计划 20260926 Task D3；§8 状态机 / §9.4） ----------------
#
# 状态机落位（§8 图）：published --offline--> offline --rollback--> published。
# - offline 不阻断既有流（红线 3 同款裁定）：published_version **保留**——R6 版本供给
#   （wf_definition._comp_versions）不变，既有工作流的 componentRef 校验照常通过；
#   「禁止新引用」由 UI 层拦截（§12.1 offline 组件拖入直接拒绝，palette 不展示）。
# - rollback 不重跑闸门（§13 拦的是「发布」；回滚目标行内容与当年通过闸门发布时
#   逐字节一致——版本行不可变），审计 rollback 留痕即可。
# - published_by/published_time 语义 = 首次发布归属，回滚不改写（操作人/时间在审计）。

class OfflineBody(BaseModel):
    remark: Optional[str] = None


class RollbackBody(BaseModel):
    version: int
    remark: Optional[str] = None


@router.post("/{type_name}/offline", summary="下线组件（§8：published→offline，幂等）")
def offline_component(
    type_name: str,
    body: OfflineBody,
    user: User = Depends(require_perm("publish_component")),
    db: Session = Depends(get_db),
):
    """下线：当前生效版本行 state→offline + 主表 state→offline（published_version 保留）。

    下线后既有工作流引用照常运行/发布（§8 关键语义：历史可复现优先于管控便利性）；
    重新上线走 rollback（历史版本）或正常 publish（新版本）。
    """
    comp = _get_or_404(db, type_name)
    if comp.state == "offline":
        return ok({"type": comp.type, "state": comp.state,
                   "publishedVersion": comp.published_version})  # 幂等
    if comp.state != "published" or comp.published_version is None:
        raise ApiError(COMP_STATE_CONFLICT, status=409,
                       msg="仅已发布组件可下线（当前 %s）" % comp.state)
    ver = (
        db.query(ComponentVersion)
        .filter(ComponentVersion.component_id == comp.id,
                ComponentVersion.version == comp.published_version)
        .first()
    )
    if ver is not None:
        ver.state = "offline"
    comp.state = "offline"
    _append_log(db, comp, ver.version if ver else (comp.published_version or 0),
                "offline", ver.spec_hash if ver else "", user.user_name, body.remark)
    db.commit()
    logger.info("下线组件: %s（生效版本 v%s 保留，操作人 %s）",
                type_name, comp.published_version, user.user_name)
    return ok({"type": comp.type, "state": comp.state,
               "publishedVersion": comp.published_version})


@router.post("/{type_name}/rollback", summary="回滚到历史发布版本（§8：offline→published）")
def rollback_component(
    type_name: str,
    body: RollbackBody,
    user: User = Depends(require_perm("publish_component")),
    db: Session = Depends(get_db),
):
    """回滚：指定「曾发布后下线」的版本行重新生效（offline→published）。

    - 当前 published 行（若有）自动转 offline 让位（与 publish 同款让位语义，§8）；
    - 目标行必须 state=offline 且 published_time 非空（曾发布）——draft/frozen/
      从未发布的行不是合法回滚目标；
    - 已有工作流引用其他版本（含被让位的高版本）不受影响，但其 componentRef 与
      新 published_version 的对齐由发布闸门显式把关（§9.3：published_version 变更
      不触发任何自动升级/降级）。
    """
    comp = _get_or_404(db, type_name)
    ver = (
        db.query(ComponentVersion)
        .filter(ComponentVersion.component_id == comp.id,
                ComponentVersion.version == body.version)
        .first()
    )
    if ver is None:
        raise ApiError(COMP_STATE_CONFLICT, status=409, msg="版本不存在")
    if ver.state != "offline" or ver.published_time is None:
        raise ApiError(COMP_STATE_CONFLICT, status=409,
                       msg="仅曾发布后下线的版本可回滚（v%s 当前 %s）" % (body.version, ver.state))
    superseded = 0
    for prev in (
        db.query(ComponentVersion)
        .filter(ComponentVersion.component_id == comp.id,
                ComponentVersion.state == "published",
                ComponentVersion.version != ver.version)
        .all()
    ):
        prev.state = "offline"
        superseded = max(superseded, prev.version)
    ver.state = "published"
    comp.state = "published"
    comp.published_version = ver.version
    _append_log(db, comp, ver.version, "rollback", ver.spec_hash, user.user_name,
                body.remark if body.remark else ("让位 v%d" % superseded if superseded else None))
    db.commit()
    logger.info("回滚组件版本: %s → v%s（操作人 %s%s）", type_name, ver.version,
                user.user_name, "，让位 v%d" % superseded if superseded else "")
    return ok({"type": comp.type, "publishedVersion": ver.version,
               "supersededVersion": superseded or None})


@router.get("/{type_name}/impacted", summary="影响面查询（§9.4：引用该组件的工作流清单）")
def impacted_workflows(
    type_name: str,
    user: User = Depends(require_perm("view_all")),
    db: Session = Depends(get_db),
):
    """扫描 t_wf_definition.graph_json 中 componentRef.type 命中的工作流（升级/下线前评估）。

    - 与回填脚本同口径：物化节点（sys_exec_ 前缀，运行态注入 ref）一并计入——
      同样表达「该工作流用到此组件」的运行期事实；
    - behind = 任一引用版本落后于当前 published_version（升级向导的目标集）；
      aligned = 全部引用版本恰等于 published_version（回滚降版后高版本引用为不对齐）；
    - 无 ref 的节点不计入（存量未回填文档在影响面里不可见——发布闸门会先拦，不留盲区）。
    """
    comp = _get_or_404(db, type_name)
    items: list = []
    for definition in db.query(WfDefinition).all():
        if not definition.graph_json:
            continue
        try:
            doc = json.loads(definition.graph_json)
        except (TypeError, ValueError):
            continue
        nodes = doc.get("nodes")
        if not isinstance(nodes, list):
            continue
        ref_versions: set = set()
        for node in nodes:
            if not isinstance(node, dict):
                continue
            data = node.get("data")
            ref = data.get("componentRef") if isinstance(data, dict) else None
            if isinstance(ref, dict) and ref.get("type") == type_name:
                v = ref.get("version")
                if isinstance(v, int) and not isinstance(v, bool):
                    ref_versions.add(v)
        if not ref_versions:
            continue
        pub = comp.published_version
        items.append({
            "id": definition.id, "code": definition.code, "name": definition.name,
            "version": definition.version, "releaseState": definition.release_state,
            "refVersions": sorted(ref_versions),
            "behind": pub is not None and any(v < pub for v in ref_versions),
            "aligned": pub is not None and all(v == pub for v in ref_versions),
        })
    items.sort(key=lambda x: (not x["behind"], str(x["code"] or x["id"])))
    return ok({"type": comp.type, "publishedVersion": comp.published_version,
               "state": comp.state, "items": items})


# ---------------- 发布即刷新（实施计划 2026-10-03 Task 3；设计文档 §9） ----------------
#
# §9 发布即刷新：发布成功后服务端自动批量升级所有引用图的 componentRef 版本，
# 替代手动逐个 upgradeOne（M1 声明组件同样受益）。落点三处：
# - _refresh_refs：扫描 t_wf_definition.graph_json（口径与 R6 校验/影响面查询一致——
#   node.data.componentRef），ref.type 匹配且 version < published_version 的节点
#   批量升级至 published_version（幂等：已对齐的图零写入零提交）；
# - POST /{type_name}/refresh-refs：手动触发（存量回填/补偿场景）；
# - publish_version 成功后自动挂载 refresh 结果（响应 data.refresh，见上）。

def _refresh_refs(db: Session, comp: Component, operator: str) -> dict:
    """发布即刷新：批量升级落后引用（幂等）。命中即 bump wf.version 并刷 update_time，
    追加 WfDefinitionLog 版本快照（对齐保存/回滚日志链，回滚可取到刷新后的图）；
    快照与定义变更同一事务收口，无命中零写入。
    """
    published = comp.published_version or 0
    items: list = []
    refreshed = 0
    for wf in db.query(WfDefinition).filter(WfDefinition.graph_json.isnot(None)).all():
        try:
            doc = json.loads(wf.graph_json or "{}")
        except (TypeError, ValueError):
            continue
        changed = False
        for node in doc.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            data = node.get("data")
            if not isinstance(data, dict):
                continue
            ref = data.get("componentRef")
            if (isinstance(ref, dict) and ref.get("type") == comp.type
                    and isinstance(ref.get("version"), int) and not isinstance(ref["version"], bool)
                    and ref["version"] < published):
                ref["version"] = published
                changed = True
        if changed:
            wf.graph_json = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
            wf.version = (wf.version or 1) + 1
            wf.update_time = now()
            db.add(WfDefinitionLog(
                wf_code=wf.code, version=wf.version, graph_json=wf.graph_json,
                operator=operator, remark="组件 %s 发布即刷新引用至 v%d" % (comp.type, published),
            ))
            refreshed += 1
            items.append({"wfId": wf.id, "wfName": wf.name})
    if refreshed:
        db.commit()
    return {"refreshed": refreshed, "publishedVersion": published, "items": items}


@router.post("/{type_name}/refresh-refs", summary="刷新引用（发布即刷新，幂等）")
def refresh_refs(
    type_name: str,
    user: User = Depends(require_perm("design_component")),
    db: Session = Depends(get_db),
):
    """手动触发引用刷新：仅 published 组件；publish 成功已自动执行（data.refresh）。"""
    comp = _get_or_404(db, type_name)
    if comp.state != "published":
        raise ApiError(COMP_STATE_CONFLICT, status=409, msg="仅 published 组件可刷新引用")
    result = _refresh_refs(db, comp, user.user_name)
    logger.info("刷新组件引用: %s（命中 %d 个图，操作人 %s）",
                type_name, result["refreshed"], user.user_name)
    return ok(result)
