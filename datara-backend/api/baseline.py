"""组件基线化 API（M-B0 · 目录 35 type 底稿推进 + 认可发 v1 + 声明级血缘图）。

与既有模块的关系：
- M0 只读目录（api/component.py）下发快照（不落库）；M1/M2 治理（api/component_design.py）
  承载用户自建组件（scope=user）。本模块承载**系统内置目录的基线化**：v1 发出前
  t_component 无目录行，进度独立存 t_baseline_progress；「用户认可」时才写
  t_component（scope=builtin）+ t_component_version（v1 published），是治理口径下
  内置组件进入版本链的唯一来源。

端点（路由注意：静态段 /baseline/... 均在 component.py 的 GET /{type_name} 单段
模板覆盖范围外，路径段数不同互不冲突）：
- GET  /components/baseline/progress            进度清单（35 type 全量 + 统计）
- GET  /components/baseline/{type}/draft        读取底稿（无进度行视为空态）
- PUT  /components/baseline/{type}/draft        保存底稿（乐观锁 draft_rev；纯数据 422）
- POST /components/baseline/{type}/check        体检（run_baseline_checks 10 项，只报告不拦截）
- POST /components/{type}/baseline/publish      认可发 v1（publish_component 权限）
- GET  /components/{type}/lineage-decl          声明级血缘读取（未基线化返回空态不报错）
- GET  /lineage/graph                           声明级血缘图 stub（lineage.py 未占用该路径，
                                                故挂本模块 lineage_router；运行时字段级血缘
                                                仍由既有 t_lineage_edge/t_lineage_field 承载）

设计要点：
- 体检只报告不拦截：基线化对象是既有运行系统（目录快照），存量定义允许带红推进，
  由「用户认可」（publish_component 权限 + 人工判断）完成治理闭环，区别于用户组件
  发布的硬闸门（COMP_GATE_FAILED 422）。
- 底稿乐观锁与草稿同口径（§16）：draft_rev 不匹配 409 COMP_LOCK_CONFLICT。
- 认可发版一个事务：t_component / t_component_version / t_component_log / 进度行
  四处写入原子生效，commit 后 logger.info 审计。
"""

import json
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.auth import ApiError, require_perm
from api.component import _load as _load_catalog
from api.component_design import (
    DISPATCHABLE_EXECUTORS,
    SPEC_UI_TYPES,
    _gate_drop_policy,
    _gate_references,
    _spec_hash,
    validate_spec_pure_data,
)
from common.db import get_db
from common.log import get_logger
from common.models import (
    BaselineProgress,
    Component,
    ComponentLog,
    ComponentVersion,
    User,
    now,
)
from common.resp import (
    COMP_DUPLICATE_TYPE,
    COMP_LOCK_CONFLICT,
    COMP_NOT_FOUND,
    COMP_SPEC_INVALID,
    COMP_STATE_CONFLICT,
    fmt_dt,
    ok,
)

logger = get_logger("api.baseline")

# 主路由：与 component.py / component_design.py 同挂 /components 前缀
router = APIRouter(prefix="/components", tags=["component-baseline"])
# 声明级血缘图：api/lineage.py 只占用 /tables /fields /stats /trace，
# /lineage/graph 空闲，故直接挂本模块（免前端改路径）
lineage_router = APIRouter(prefix="/lineage", tags=["lineage"])

# 八段 DSL 的 form 键白名单（M-B0 底稿契约）
FORM_KEYS = frozenset({
    "inputs", "outputs", "params", "conditions", "constraints", "exclusions", "refs", "exports",
})
# 三段字段段（引用完整性的解析全集）
FIELD_SECTIONS = ("inputs", "outputs", "params")
# lineage.assets 的角色 / 资产类型封闭枚举
LINEAGE_ROLES = frozenset({"source", "target"})
ASSET_TYPES = frozenset({"table", "file", "stream"})
# exports[].from 封闭枚举
EXPORT_FROMS = frozenset({"result", "log", "output"})


def _dag_types() -> frozenset:
    """目录快照中 profile=dag 的 type 全集（基线化对象 = 35 type；与用户组件闸门方向相反）。"""
    cat = _load_catalog()
    return frozenset(
        str(c.get("type") or "") for c in cat.get("components", []) if c.get("profile") == "dag"
    ) - {""}


def _dag_meta(type_name: str) -> Optional[dict]:
    """目录快照 → 单 type 元数据（体检 comp_meta 与发版身份字段的唯一来源）。"""
    for c in _load_catalog().get("components", []):
        if c.get("profile") == "dag" and c.get("type") == type_name:
            return c
    return None


def _comp_meta(meta: dict) -> dict:
    """目录条目 → run_baseline_checks 的 comp_meta（只取体检所需键）。"""
    return {
        "type": meta.get("type"),
        "label": meta.get("label"),
        "executionModel": meta.get("executionModel"),
        "executor": meta.get("executor"),
        "runtimeOnly": meta.get("runtimeOnly"),
        "route": meta.get("route"),  # master 路由的控制流节点无 worker executor
        "categories": meta.get("categories") or [],
    }


def _field_keys(form: dict) -> set:
    """三段字段键全集（inputs/outputs/params 的 key 并集；引用完整性解析依据）。"""
    keys: set = set()
    for seg in FIELD_SECTIONS:
        for f in form.get(seg) or []:
            if isinstance(f, dict) and isinstance(f.get("key"), str) and f["key"]:
                keys.add(f["key"])
    return keys


def _load_spec(row: Optional[BaselineProgress]) -> dict:
    """进度行 → 底稿 spec（无行 / 无底稿视为空对象，体检结构项自然报红）。"""
    if row is None or not row.draft_spec:
        return {}
    try:
        spec = json.loads(row.draft_spec)
    except (TypeError, ValueError):
        return {}
    return spec if isinstance(spec, dict) else {}


# ---------------- 基线化体检（10 项纯函数，全项评估不短路；只报告不拦截） ----------------
#
# 与用户组件发布闸门（component_design.run_publish_gates）的关系：同一治理口径的
# 镜像——用户组件闸门拦「外来者与目录重名」，基线化体检确认「目录原住民逐项达标」。
# 全项报告给运营者人工裁决，认可动作（publish）不因红项阻断（治理基础 = 用户认可）。

def _check_form_whitelist(spec: dict) -> list:
    """form 结构 + 八段键白名单 + 三段字段结构 + 段内引用完整性。"""
    form = spec.get("form")
    if not isinstance(form, dict):
        return ["form 必须为对象"]
    msgs: list = []
    for k in form:
        if k not in FORM_KEYS:
            msgs.append("form 键「%s」不在八段白名单（inputs/outputs/params/conditions/"
                        "constraints/exclusions/refs/exports）" % k)
    field_keys = _field_keys(form)
    # 三段字段：key/label/uiType 必填 + uiType 9 基元 + 同段 key 唯一
    for seg in FIELD_SECTIONS:
        seg_val = form.get(seg)
        if seg_val is None:
            continue  # 缺省段按空处理（初始底稿八段全键，兼容手写缺省）
        if not isinstance(seg_val, list):
            msgs.append("form.%s 必须为数组" % seg)
            continue
        seen: set = set()
        for i, f in enumerate(seg_val):
            path = "form.%s[%d]" % (seg, i)
            if not isinstance(f, dict):
                msgs.append("%s 必须为对象" % path)
                continue
            key = f.get("key")
            if not isinstance(key, str) or not key.strip():
                msgs.append("%s.key 不能为空" % path)
            elif key in seen:
                msgs.append("%s.key 重复: %s" % (path, key))
            if isinstance(key, str) and key:
                seen.add(key)
            if not f.get("label"):
                msgs.append("%s.label 不能为空" % path)
            if f.get("uiType") not in SPEC_UI_TYPES:
                msgs.append("%s.uiType「%s」不在白名单（9 基元）" % (path, f.get("uiType")))

    def _ref_msgs(items, extract, label: str) -> list:
        """段内引用逐项解析：引用 key 必须存在于三段字段键全集。"""
        out: list = []
        arr = items if isinstance(items, list) else []
        for i, item in enumerate(arr):
            if not isinstance(item, dict):
                continue
            for ref in extract(item):
                if isinstance(ref, str) and ref and ref not in field_keys:
                    out.append("form.%s[%d] 引用不存在的字段 key: %s" % (label, i, ref))
        return out

    def _targets(item: dict) -> list:
        tg = item.get("targets")
        return tg if isinstance(tg, list) else ([tg] if tg is not None else [])

    def _sub_field(*keys: str):
        def extract(item: dict) -> list:
            out: list = []
            for k in keys:
                sub = item.get(k)
                if isinstance(sub, dict) and sub.get("field") is not None:
                    out.append(sub["field"])
            return out
        return extract

    msgs += _ref_msgs(form.get("conditions"), _targets, "conditions")
    msgs += _ref_msgs(form.get("constraints"), lambda it: [it.get("field")], "constraints")
    msgs += _ref_msgs(form.get("exclusions"), _sub_field("when", "exclude"), "exclusions")
    msgs += _ref_msgs(form.get("refs"), lambda it: [it.get("field")], "refs")
    return msgs


def _check_contract(comp_meta: dict) -> tuple:
    """执行契约（红线 1 镜像）：demo-only 提示性放行；dag-engine 必须绑注册表内 executor；
    passthrough/template/nonExecutable 无执行实现（配置拍平/模板展开/展示型），豁免 executor 绑定。
    dag-engine + route=master 的控制流节点（start/end/conditions/switch/fork/join/merge/
    delay/dependent/loop/assert/stream_*/variable）由 master 引擎直接派发，无 worker executor。"""
    em = comp_meta.get("executionModel")
    route = comp_meta.get("route")
    if em == "demo-only":
        return True, "demo-only 无执行实现，去留在声明层裁决"
    if em in ("passthrough", "template", "nonExecutable"):
        # 直通配置（自身不执行，配置被下游拍平消费）/
        # 编排模板（落图即展开为节点链，无独立运行时路由）/
        # 展示型节点（不产生任务实例）→ 均豁免 executor 绑定
        return True, "%s 组件豁免 executor 绑定" % em
    if em == "dag-engine":
        # master 路由的控制流节点由 master 引擎直接派发，无 worker executor
        if route == "master":
            return True, "dag-engine（master 路由控制流节点，无 worker executor）"
        executor = (comp_meta.get("executor") or "").strip()
        if not executor:
            return False, "dag-engine 组件必须绑定 executor"
        if executor not in DISPATCHABLE_EXECUTORS:
            return False, "executor「%s」不在分派注册表（worker 执行器 + 流三节点）" % executor
    return True, ""


def _check_catalog_consistency(comp_meta: dict, catalog_types: frozenset) -> tuple:
    """目录一致性：基线化对象必须来自目录快照（方向与用户组件同名闸门相反）。"""
    if comp_meta.get("type") in catalog_types:
        return True, ""
    return False, "type「%s」不在系统内置目录 dag profile 集内（基线化对象必须来自目录）" % comp_meta.get("type")


def _check_references(spec: dict, field_keys: set) -> list:
    """引用完整性：复用 _gate_references（八段 DSL 无 fields 键，以三段字段键全集构造视图）。"""
    return _gate_references({
        "fields": [{"key": k} for k in sorted(field_keys)],
        "dropPolicy": spec.get("dropPolicy"),
    })


def _check_lineage_decl(spec: dict, comp_meta: dict, field_keys: set) -> tuple:
    """血缘声明：执行类（executor 非空）必须声明 assets；逻辑控制类豁免。
    runtimeOnly 组件（sync/file_sync）的配置由上游 endpoint_select 合并，
    lineage.pick 允许引用非本表单字段（运行时合并锚点）。"""
    if not (comp_meta.get("executor") or "").strip():
        return True, "逻辑控制类豁免血缘声明"
    lineage = spec.get("lineage")
    if not isinstance(lineage, dict):
        return False, "执行类组件必须声明 lineage 对象"
    assets = lineage.get("assets")
    if not isinstance(assets, list) or not assets:
        return False, "执行类组件 lineage.assets 必须为非空数组"
    # runtimeOnly 组件的 pick 允许引用上游合并字段（非本表单字段）
    runtime_only = bool(comp_meta.get("runtimeOnly"))
    msgs: list = []
    for i, a in enumerate(assets):
        path = "lineage.assets[%d]" % i
        if not isinstance(a, dict):
            msgs.append("%s 必须为对象" % path)
            continue
        if a.get("role") not in LINEAGE_ROLES:
            msgs.append("%s.role「%s」仅允许 source/target" % (path, a.get("role")))
        pick = a.get("pick")
        if not isinstance(pick, str) or not pick:
            msgs.append("%s.pick 必须为字符串" % path)
        elif not runtime_only and pick not in field_keys:
            # 非 runtimeOnly：pick 必须存在于本表单字段键全集
            msgs.append("%s.pick「%s」不在三段字段键全集" % (path, pick))
        if a.get("assetType") not in ASSET_TYPES:
            msgs.append("%s.assetType「%s」仅允许 table/file/stream" % (path, a.get("assetType")))
    return (not msgs), "；".join(msgs)


def _check_exports(form: dict) -> tuple:
    """导出一致性：from 封闭枚举 + key 唯一 + log 须带 logKey；result 项附实测核验提示。"""
    exports = form.get("exports")
    if exports is None:
        return True, ""
    if not isinstance(exports, list):
        return False, "form.exports 必须为数组"
    msgs: list = []
    hints: list = []
    seen: set = set()
    for i, e in enumerate(exports):
        path = "form.exports[%d]" % i
        if not isinstance(e, dict):
            msgs.append("%s 必须为对象" % path)
            continue
        src = e.get("from")
        if src not in EXPORT_FROMS:
            msgs.append("%s.from「%s」仅允许 result/log/output" % (path, src))
        key = e.get("key")
        if isinstance(key, str) and key:
            if key in seen:
                msgs.append("%s.key 重复: %s" % (path, key))
            seen.add(key)
        if src == "log" and not e.get("logKey"):
            msgs.append("%s from=log 必须带 logKey" % path)
        if src == "result":
            hints.append("%s 与 executor 实际产出一致性待 1.9 实测核验" % path)
    return (not msgs), "；".join(msgs + hints)


def run_baseline_checks(spec: dict, comp_meta: dict, *,
                        catalog_types: Optional[frozenset] = None) -> list:
    """基线化体检（10 项）：返回 [{check, ok, msg}]，全项评估不短路。

    纯函数（目录类型集可注入）；体检只报告不拦截——红项不阻断认可发版，
    由 publish_component 权限与人工判断承载治理闭环。
    """
    if catalog_types is None:
        catalog_types = _dag_types()
    form = spec.get("form") if isinstance(spec.get("form"), dict) else {}
    field_keys = _field_keys(form) if form else set()
    pure_msgs = validate_spec_pure_data(spec)
    form_msgs = _check_form_whitelist(spec)
    drop_msgs = _gate_drop_policy(spec)
    ref_msgs = _check_references(spec, field_keys)
    exports_ok, exports_msg = _check_exports(form)
    contract_ok, contract_msg = _check_contract(comp_meta)
    catalog_ok, catalog_msg = _check_catalog_consistency(comp_meta, catalog_types)
    lineage_ok, lineage_msg = _check_lineage_decl(spec, comp_meta, field_keys)
    checks = (
        ("pure_data", not pure_msgs, "；".join(pure_msgs)),
        ("form_whitelist", not form_msgs, "；".join(form_msgs)),
        ("drop_policy", not drop_msgs, "；".join(drop_msgs)),
        ("contract", contract_ok, contract_msg),
        ("catalog_consistency", catalog_ok, catalog_msg),
        ("references", not ref_msgs, "；".join(ref_msgs)),
        ("lineage_decl", lineage_ok, lineage_msg),
        ("exports_consistency", exports_ok, exports_msg),
        ("permission", True, "发布动作由 publish_component 权限承载（认可发版时校验）"),
        ("draft_lock", True, "底稿乐观锁由保存端点承载"),
    )
    return [{"check": name, "ok": is_ok, "msg": msg} for name, is_ok, msg in checks]


# ---------------- 进度清单 / 底稿读写 ----------------


@router.get("/baseline/progress", summary="基线化进度清单（目录 35 type 全量）")
def baseline_progress(
    user: User = Depends(require_perm("view_all")),
    db: Session = Depends(get_db),
):
    """以目录快照 profile=dag 的 35 type 为准，左联 t_baseline_progress（无行视为 pending）。"""
    rows = {r.type: r for r in db.query(BaselineProgress).all()}
    items: list = []
    for c in _load_catalog().get("components", []):
        if c.get("profile") != "dag":
            continue
        r = rows.get(c.get("type"))
        items.append({
            # 目录元数据（只读真源，不落库）
            "type": c.get("type"), "code": c.get("code"), "label": c.get("label"),
            "categories": c.get("categories") or [],
            "executionModel": c.get("executionModel"), "executor": c.get("executor"),
            "paletteVisible": bool(c.get("paletteVisible")),
            "runtimeOnly": bool(c.get("runtimeOnly")),
            # 推进状态（无进度行视为 pending）
            "status": r.status if r else "pending",
            "draftRev": r.draft_rev if r else 0,
            "hasDraft": bool(r and r.draft_spec),
            "confirmedBy": r.confirmed_by if r else None,
            "confirmedAt": fmt_dt(r.confirmed_at) if r else None,
            "updatedAt": fmt_dt(r.update_time) if r else None,
        })
    items.sort(key=lambda x: str(x["code"] or x["type"]))
    by_status: dict = {}
    for it in items:
        by_status[it["status"]] = by_status.get(it["status"], 0) + 1
    return ok({"items": items, "stats": {"total": len(items), "byStatus": by_status}})


@router.get("/baseline/{type_name}/draft", summary="读取基线底稿")
def get_baseline_draft(
    type_name: str,
    user: User = Depends(require_perm("view_all")),
    db: Session = Depends(get_db),
):
    """底稿读取：spec=draft_spec 解析（无底稿 spec={}）；type 不在目录 35 集内 404。"""
    if type_name not in _dag_types():
        raise ApiError(COMP_NOT_FOUND, status=404, msg="type「%s」不在基线化目录内" % type_name)
    row = db.query(BaselineProgress).filter(BaselineProgress.type == type_name).first()
    spec = _load_spec(row)
    return ok({
        "type": type_name,
        "status": row.status if row else "pending",
        "draftRev": row.draft_rev if row else 0,
        "spec": spec,
        "specHash": _spec_hash(spec) if row is not None and row.draft_spec else None,
        "checkReport": row.check_report if row else None,
        "testRecords": row.test_records if row else None,
        "updatedAt": fmt_dt(row.update_time) if row else None,
    })


class BaselineDraftBody(BaseModel):
    draft_rev: int
    spec: dict
    remark: Optional[str] = None


@router.put("/baseline/{type_name}/draft", summary="保存基线底稿（乐观锁）")
def save_baseline_draft(
    type_name: str,
    body: BaselineDraftBody,
    user: User = Depends(require_perm("design_component")),
    db: Session = Depends(get_db),
):
    """保存底稿：乐观锁不匹配 409（data.currentRev）；纯数据违规 422；pending→designing。"""
    if type_name not in _dag_types():
        raise ApiError(COMP_NOT_FOUND, status=404, msg="type「%s」不在基线化目录内" % type_name)
    row = db.query(BaselineProgress).filter(BaselineProgress.type == type_name).first()
    current_rev = row.draft_rev if row else 0
    if row is not None and row.status == "published":
        # 基线一次性：已发版底稿不可直接改写（修订走 redraft 端点，第二批上线）
        raise ApiError(COMP_STATE_CONFLICT, status=409,
                       msg="type「%s」已发版，底稿不可直接修改（修订能力即将上线）" % type_name)
    if body.draft_rev != current_rev:
        raise ApiError(COMP_LOCK_CONFLICT, status=409, data={"currentRev": current_rev})
    violations = validate_spec_pure_data(body.spec)
    if violations:
        raise ApiError(COMP_SPEC_INVALID, status=422,
                       msg="底稿非纯数据", data={"violations": violations})
    if row is None:
        # 显式带 status="pending"：新建对象 flush 前 Column default 未应用，
        # 下方状态机判断依赖读到确定的初始值
        row = BaselineProgress(type=type_name, status="pending")
        db.add(row)
    row.draft_spec = json.dumps(body.spec, ensure_ascii=False)
    row.draft_rev = current_rev + 1
    if row.status == "pending":
        row.status = "designing"  # 首次保存即进入设计态（其余状态不回退）
    db.commit()
    logger.info("保存基线底稿: %s rev=%d（操作人 %s）", type_name, row.draft_rev, user.user_name)
    return ok({"draftRev": row.draft_rev, "specHash": _spec_hash(body.spec), "status": row.status})


@router.post("/baseline/{type_name}/check", summary="基线底稿体检（10 项，只报告不拦截）")
def check_baseline(
    type_name: str,
    user: User = Depends(require_perm("view_all")),
    db: Session = Depends(get_db),
):
    """用当前底稿跑 run_baseline_checks：结果落 check_report（含 checkedAt），不改 status。

    无底稿按空 spec 体检（form/lineage 等结构项自然报红）；含违规项 HTTP 仍 200。
    """
    meta = _dag_meta(type_name)
    if meta is None:
        raise ApiError(COMP_NOT_FOUND, status=404, msg="type「%s」不在基线化目录内" % type_name)
    row = db.query(BaselineProgress).filter(BaselineProgress.type == type_name).first()
    spec = _load_spec(row)
    items = run_baseline_checks(spec, _comp_meta(meta))
    report = {"checkedAt": fmt_dt(now()), "items": items}
    if row is None:  # 无进度行时落报告需建行（status 显式初始为 pending）
        row = BaselineProgress(type=type_name, status="pending")
        db.add(row)
    row.check_report = report
    db.commit()
    logger.info("基线底稿体检: %s（%d 项，%d 项未过，操作人 %s）", type_name, len(items),
                sum(1 for i in items if not i["ok"]), user.user_name)
    return ok({"items": items, "checkedAt": report["checkedAt"]})


# ---------------- 认可发 v1（治理基础：用户认可 = 内置组件进入版本链的唯一来源） ----------------


class BaselinePublishBody(BaseModel):
    remark: Optional[str] = None


@router.post("/{type_name}/baseline/publish", summary="基线化认可，发 v1")
def publish_baseline(
    type_name: str,
    body: BaselinePublishBody,
    user: User = Depends(require_perm("publish_component")),
    db: Session = Depends(get_db),
):
    """认可目录定义发 v1：跑体检全项落 check_report（不拦截），四处写入一个事务。

    - 进度行不存在 404；status=published 409（已认可发过，基线化一次性）；
    - t_component（scope=builtin, state=published, published_version=1）+
      t_component_version（v1 published，spec_json=底稿全文）+ t_component_log
      （action=publish）+ 进度行（status=published + confirmed_by/at）。
    """
    meta = _dag_meta(type_name)
    if meta is None:
        raise ApiError(COMP_NOT_FOUND, status=404, msg="type「%s」不在基线化目录内" % type_name)
    row = db.query(BaselineProgress).filter(BaselineProgress.type == type_name).first()
    if row is None:
        raise ApiError(COMP_NOT_FOUND, status=404,
                       msg="type「%s」无基线化进度行（先保存底稿）" % type_name)
    if row.status == "published":
        raise ApiError(COMP_STATE_CONFLICT, status=409,
                       msg="type「%s」已认可发过 v1" % type_name)
    if db.query(Component).filter(Component.type == type_name).first() is not None:
        # 不应发生（认可发版前 t_component 无目录行；出现即数据漂移，拒绝覆盖）
        raise ApiError(COMP_DUPLICATE_TYPE, status=409,
                       msg="组件 type「%s」已被占用" % type_name)

    spec = _load_spec(row)
    items = run_baseline_checks(spec, _comp_meta(meta))
    row.check_report = {"checkedAt": fmt_dt(now()), "items": items}  # 全项落库，不拦截
    spec_hash = _spec_hash(spec)

    comp = Component(
        type=type_name, name=meta.get("label") or type_name,
        category=(meta.get("categories") or [None])[0],
        profile="dag", scope="builtin", execution_model=meta.get("executionModel") or "dag-engine",
        executor=meta.get("executor"), executable=True, state="published",
        published_version=1, draft_rev=0, description=meta.get("desc"),
    )
    db.add(comp)
    db.flush()  # 取 comp.id
    db.add(ComponentVersion(
        component_id=comp.id, type=type_name, version=1, state="published",
        spec_json=json.dumps(spec, ensure_ascii=False), spec_hash=spec_hash,
        remark=body.remark, published_by=user.user_name, published_time=now(),
    ))
    db.add(ComponentLog(
        component_id=comp.id, type=type_name, version=1, action="publish",
        spec_hash=spec_hash, operator=user.user_name,
        remark=body.remark or "基线化认可，发 v1",
    ))
    row.status = "published"
    row.confirmed_by = user.user_name
    row.confirmed_at = now()
    db.commit()
    logger.info("基线化认可发版: %s v1（操作人 %s，体检 %d 项 %d 项未过）",
                type_name, user.user_name, len(items), sum(1 for i in items if not i["ok"]))
    return ok({
        "type": type_name, "publishedVersion": 1, "specHash": spec_hash,
        "checkItems": items, "confirmedAt": fmt_dt(row.confirmed_at),
    })


# ---------------- 声明级血缘（读取端点 + 声明级血缘图 stub） ----------------


@router.get("/{type_name}/lineage-decl", summary="读取声明级血缘（未基线化空态）")
def get_lineage_decl(
    type_name: str,
    user: User = Depends(require_perm("view_all")),
    db: Session = Depends(get_db),
):
    """查 state=published 最新版本行的 spec.lineage；无发布版返回 unbaseline 空态不报错。"""
    found = (
        db.query(ComponentVersion, Component)
        .join(Component, Component.id == ComponentVersion.component_id)
        .filter(Component.type == type_name, ComponentVersion.state == "published")
        .order_by(ComponentVersion.version.desc())
        .first()
    )
    if found is None:
        return ok({"type": type_name, "baselineState": "unbaseline", "lineage": None})
    ver, _comp = found
    try:
        spec = json.loads(ver.spec_json) if ver.spec_json else {}
    except (TypeError, ValueError):
        spec = {}
    return ok({
        "type": type_name, "baselineState": "published",
        "lineage": spec.get("lineage") if isinstance(spec, dict) else None,
    })


@lineage_router.get("/graph", summary="声明级血缘图（stub）")
def lineage_graph(
    user: User = Depends(require_perm("view_all")),
    db: Session = Depends(get_db),
):
    """声明级静态读写关系：扫全部 published 版本行，解析 spec.lineage.assets 平铺为节点。

    与既有运行时血缘（t_lineage_edge/t_lineage_field，api/lineage.py）互补：本端点
    只表达「组件声明了什么读写」，不做字段级解析；空库返回空数组。edges 留空——
    声明级节点间连线（DAG 拓扑）属运行时事实，后续按需扩展。
    """
    nodes: list = []
    for ver in db.query(ComponentVersion).filter(ComponentVersion.state == "published").all():
        try:
            spec = json.loads(ver.spec_json) if ver.spec_json else {}
        except (TypeError, ValueError):
            continue
        lineage = spec.get("lineage") if isinstance(spec, dict) else None
        assets = lineage.get("assets") if isinstance(lineage, dict) else None
        if not isinstance(assets, list):
            continue
        for a in assets:
            if not isinstance(a, dict):
                continue
            nodes.append({
                "type": ver.type, "role": a.get("role"),
                "pick": a.get("pick"), "assetType": a.get("assetType"),
            })
    return ok({"mode": "declaration", "nodes": nodes, "edges": []})
