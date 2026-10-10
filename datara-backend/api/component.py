"""组件目录 API（M0 · 只读系统组件清单）

组件管理功能的第一个里程碑。前端组件注册表（`datara-web/src/graph/profiles/*.ts`）
此前只存在于 Vue bundle 内，后端无法校验、无法版本化、无法服务给其他客户端。
本模块把系统组件目录以**只读**方式下发，作为 M1（用户自建组件）的基线。

- GET  /components           ：组件清单（可按 profile / route / paletteVisible / q 过滤）
- GET  /components/stats     ：汇总统计（含注册表漂移指标）
- GET  /components/{type}    ：单组件详情（含表单字段清单）
- GET  /components/catalog   ：原始目录快照（schemaVersion/catalogHash/stats/components）

数据来源：`common/dag_catalog.json`，由 `scripts/export_dag_catalog.py` 从前端
profile 源码生成并提交（git 内唯一真源，可 diff、可评审）。
**刻意不落库**：落库会产生"生成物与代码不同步"的漂移陷阱；用户自建组件才需要
` t_component` 表（M1 引入，承载 version/owner/release_state）。

M0 为只读，不接受任何写操作。发布/草稿/版本治理属 M2。
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from common.component_catalog import catalog_payload
from common.db import get_db
from common.log import get_logger
from common.models import Component
from common.resp import ok

logger = get_logger("api.component")

router = APIRouter(prefix="/components", tags=["component"])


def _load() -> dict:
    """读取共享适配器提供的、随代码发布的目录快照。"""
    return catalog_payload()


@router.get("", summary="组件清单")
def list_components(
    profile: Optional[str] = Query(None, description="按 ViewProfile 过滤：dag/etl/stream/topo"),
    route: Optional[str] = Query(None, description="按派发方式过滤：master/worker/template/nonExecutable/UNROUTED"),
    palette_visible: Optional[bool] = Query(None, alias="paletteVisible", description="是否只在 Palette 可见"),
    q: Optional[str] = Query(None, description="按 type/label/desc 模糊搜索"),
) -> dict:
    """组件清单。默认返回全部 74 个（含 4 个 profile）。"""
    cat = _load()
    items = cat["components"]

    if profile:
        items = [c for c in items if c["profile"] == profile]
    if route:
        items = [c for c in items if c["route"] == route]
    if palette_visible is not None:
        items = [c for c in items if bool(c["paletteVisible"]) is palette_visible]
    if q:
        needle = q.strip().lower()
        items = [
            c
            for c in items
            if needle in (c["type"] or "").lower()
            or needle in (c["label"] or "").lower()
            or needle in (c["desc"] or "").lower()
            or needle in (c["code"] or "").lower()
        ]

    # 精简列表视图：去掉逐字段明细（详情走 /components/{type}）
    brief = [
        {
            "type": c["type"],
            "profile": c["profile"],
            "dagRelevant": c["dagRelevant"],
            "executionModel": c["executionModel"],
            "executionNote": c["executionNote"],
            "code": c["code"],
            "label": c["label"],
            "icon": c["icon"],
            "color": c["color"],
            "desc": c["desc"],
            "categories": c["categories"],
            "shape": c["shape"],
            "runtimeOnly": c["runtimeOnly"],
            "route": c["route"],
            "executor": c["executor"],
            "paletteVisible": c["paletteVisible"],
            "paletteGroup": c["paletteGroup"],
            "initTemplate": c.get("initTemplate"),
            "formFieldCount": c["formFieldCount"],
            "requiredFieldCount": sum(1 for f in c["formFields"] if f["required"]),
            "flags": c["flags"],
        }
        for c in items
    ]

    return ok(
        {
            "total": len(brief),
            "catalogHash": cat["catalogHash"],
            "schemaVersion": cat["schemaVersion"],
            "items": brief,
        }
    )


@router.get("/stats", summary="组件目录统计")
def stats() -> dict:
    """汇总统计。`consistencyErrors` 非空即表示目录与源码/后端路由不自洽。"""
    cat = _load()
    return ok(
        {
            "catalogHash": cat["catalogHash"],
            "generatedAt": cat["generatedAt"],
            "source": cat["source"],
            "stats": cat["stats"],
            "profiles": cat["profiles"],
        }
    )


@router.get("/catalog", summary="目录原始快照")
def raw_catalog() -> dict:
    """完整快照（含逐组件逐字段明细）。供 M1 设计器与服务端校验复用。"""
    return ok(_load())


@router.get("/registry", summary="用户组件注册表（M2 D3）")
def registry(db: Session = Depends(get_db)) -> dict:
    """t_component 全量轻量清单（type→state/publishedVersion，不含 spec 全文）。

    前端两大消费方（M2 D3）：
    - 画布保存序列化注入 componentRef（graphApi.save；version 供给，与
      scripts/backfill_component_ref.py 同口径：published or 不注入）；
    - 目录页「用户组件」生命周期标签区（§8：draft/published/offline）。
    无权限位（与 M0 只读端点同口径，登录态由全局鉴权承载）：只暴露治理元数据。
    注意路由顺序：必须注册在 GET /{type_name} 之前，否则被单组件详情路径吞掉。
    """
    rows = db.query(Component).order_by(Component.type).all()
    return ok(
        {
            "items": [
                {
                    "type": r.type,
                    "name": r.name,
                    "profile": r.profile,
                    "scope": r.scope,
                    "state": r.state,
                    "publishedVersion": r.published_version,
                    "executionModel": r.execution_model,
                    "category": r.category,
                }
                for r in rows
            ],
        }
    )


@router.get("/{type_name}", summary="单组件详情")
def get_component(type_name: str) -> dict:
    """单组件详情，含表单字段清单（key/label/type/required/dsTypes/联动标记）。

    注意：`formFields[].type` 是**控件类型**（当前 22 种），与组件 `type` 无关。
    控件类型收敛目标见 docs/DAG组件声明契约与Plan产物设计.md §3.3（27 → 9）。
    """
    cat = _load()
    for c in cat["components"]:
        if c["type"] == type_name:
            return ok(c)
    # 区分"存在但不在前端"（如 src_select/tgt_select/smoke）与"完全不存在"
    known_backend = set(cat["stats"].get("backendOnlyTypes") or [])
    if type_name in known_backend:
        raise HTTPException(status_code=409, detail=f"{type_name} 为后端保留类型，无前端 NodeSchema（预期行为）")
    raise HTTPException(status_code=404, detail=f"组件不存在: {type_name}")


# 删除组件（DELETE /components/{type}）由 M1 治理设计端点承载（api/component_design.py）：
# 仅草稿可删 + scope=builtin 保护 + 审计留痕。M0 目录保持只读，不接受写操作。


__all__ = ["router"]
