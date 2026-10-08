"""组件统一规格下发 API（实施计划 Task 3，方案 §2.3）。

GET /components/spec：一次请求下发全部已发布组件的 8 要素规格骨架，
供前端画布/页面设计器离线装配（本地缓存 + ETag 条件请求增量刷新）。

设计要点：
- 下发范围：主表 state=published 的组件，精确 join 其 published_version 对应的
  state=published 版本行（不靠 order_by+去重，避免同 type 多版本行的歧义）；
- 8 要素骨架（identity/description/inputs/outputs/visual/behaviors/dropPolicy/
  extensions）缺失项显式 None 而非缺键——前端可稳定按键取值；
- 不走统一响应包：直接返回 {"items": [...]}，ETag 需确定性（统一包的时间戳等
  附加元数据会破坏缓存语义）；ETag 取 SHA-256(body) 前 32 位，清单按 Component.id
  确定性排序（顺序依赖 DB 返回序会使同内容产出不同 ETag，侵蚀 304 缓存价值），
  且响应体即哈希所依据的原始字节；
- 挂载顺序约束：main.py 中必须先于 component.router 注册，否则本路径会被
  api/component.py 的 GET /{type_name} 动态路由吞掉（返回 404 组件不存在）。
"""

import hashlib
import json

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import and_
from sqlalchemy.orm import Session

from common.db import get_db
from common.models import Component, ComponentVersion

router = APIRouter(prefix="/components", tags=["component-spec"])


def _spec_item(comp: Component, ver: ComponentVersion) -> dict:
    """单组件 8 要素骨架映射：spec 未声明的要素显式 None（§2.3 契约）。"""
    # published 行经发布闸门校验、损坏仅可能源于外部改库——解析失败直接抛错快速失败，
    # 不静默兜底，避免把半成品规格下发到前端
    spec = json.loads(ver.spec_json or "{}")
    return {
        "type": comp.type,
        # Task 15（方案 §4.3）：发布版本号随骨架下发——前端引用角标以 published_version
        # 对比 componentRef.version 判定「有新版本可用」（specVersion 是声明格式版本，非此语义）
        "publishedVersion": comp.published_version,
        "identity": {
            "type": comp.type,
            "displayName": comp.name,
            "aliases": spec.get("aliases", []),
        },
        "description": {
            "summary": spec.get("summary", ""),
            "description": spec.get("description"),
            "category": spec.get("category"),
            "docUrl": spec.get("docUrl"),
        },
        "inputs": spec.get("fields", []),
        "outputs": spec.get("outputs", []),
        "visual": {
            "icon": spec.get("icon", ""),
            "color": spec.get("color"),
            "shape": spec.get("shape", "default"),
            "badge": spec.get("badge"),
        },
        "behaviors": spec.get("behaviors"),
        "dropPolicy": spec.get("dropPolicy"),
        "extensions": spec.get("extensions"),
        "specVersion": spec.get("specVersion"),
        "ports": spec.get("ports"),
    }


@router.get("/spec")
def get_components_spec(request: Request, db: Session = Depends(get_db)):
    """下发全部已发布组件规格（ETag/304 条件请求）。"""
    rows = (
        db.query(Component, ComponentVersion)
        .join(
            ComponentVersion,
            and_(
                ComponentVersion.component_id == Component.id,
                ComponentVersion.version == Component.published_version,
                ComponentVersion.state == "published",
            ),
        )
        .filter(Component.state == "published")
        # 确定性排序：同内容必须产出同 ETag，否则 304 缓存失效被顺序漂移侵蚀
        .order_by(Component.id)
        .all()
    )
    payload = [_spec_item(comp, ver) for comp, ver in rows]
    body = json.dumps({"items": payload}, ensure_ascii=False, default=str)
    etag = '"' + hashlib.sha256(body.encode()).hexdigest()[:32] + '"'
    if request.headers.get("if-none-match") == etag:
        # 304 无 body（RFC 7232：仅回 ETag 供缓存续用）
        return Response(status_code=304, headers={"ETag": etag})
    # 直接以哈希所依据的字节作为响应体：ETag 与响应字节精确对应，且免去二次序列化
    return Response(content=body, media_type="application/json", headers={"ETag": etag})
