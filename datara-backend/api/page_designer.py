"""页面设计器 API：资源目录（设计态元数据+运行态变量）与数据预览（LIMIT 100 只读）。

- GET /page-designer/resources 系统资源目录（适配性绑定候选来源）：
  数据源 / 工作流及其变量 / 全局参数 / 时间参数（系统内置）/ 组件清单
- POST /page-designer/preview 数据预览：仅 SELECT/WITH，每查询硬编码 LIMIT 100（§8 不配置化）
"""

import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.auth import ApiError, require_perm
from common.db import get_db
from common.models import Component, DataSource, GlobalParam, WfDefinition, WfVariable
from common.resp import PAGE_PREVIEW_SQL_FORBIDDEN, ok

router = APIRouter(prefix="/page-designer", tags=["page-designer"])

# 系统时间参数（前端展示标签 + 示例值；运行态由页面运行时按当前时间求值）
TIME_PARAMS = [
    {"path": "$system.date", "label": "当前日期", "sample": "2026-10-03"},
    {"path": "$system.datetime", "label": "当前时间", "sample": "2026-10-03 00:00:00"},
    {"path": "$system.month", "label": "当前月份", "sample": "2026-10"},
]


@router.get("/resources", summary="系统资源目录（适配性绑定候选来源）")
def resources(db: Session = Depends(get_db), _user=Depends(require_perm("design_component"))):
    return ok(
        {
            "datasources": [
                {"id": d.id, "name": d.name, "type": d.type, "db": d.db_name or ""}
                for d in db.query(DataSource).order_by(DataSource.name).all()
            ],
            "workflows": [
                {
                    "code": w.code,
                    "name": w.name,
                    "vars": [
                        {"path": f"$wf.{v.name}", "label": v.name, "type": v.type}
                        for v in db.query(WfVariable).filter(WfVariable.wf_code == w.code).all()
                    ],
                }
                for w in db.query(WfDefinition).order_by(WfDefinition.name).all()
            ],
            "globalParams": [
                {"path": f"$param.{p.name}", "label": p.name}
                for p in db.query(GlobalParam).order_by(GlobalParam.name).all()
            ],
            "timeParams": TIME_PARAMS,
            "components": [
                {"type": c.type, "name": c.name, "state": c.state, "publishedVersion": c.published_version}
                for c in db.query(Component).order_by(Component.type).all()
            ],
        }
    )


# ---------------------------------------------------------------- 数据预览

PREVIEW_ROW_CAP = 100  # 设计文档 §8：硬编码上限，不配置化
SELECT_RE = re.compile(r"\s*(WITH|SELECT)\b", re.IGNORECASE)


class PreviewQuery(BaseModel):
    id: str
    datasourceId: int
    sql: str
    db: str | None = None


class PreviewBody(BaseModel):
    queries: list[PreviewQuery] = Field(default_factory=list)


def _run_readonly(ds: DataSource, sql: str, cap: int) -> dict:
    """只读连接执行单查询，最多取 cap 行（复用 common.dsconn 连接工厂，IDE 同口径）。

    - 短连接 + read_timeout 缺省 60s（IDE 口径）；fetchmany 分批取行防大结果集驻留
    - 仅连接型数据源（mysql/greatdb）可执行；其它类型/连接失败均入 error 不抛
    """
    from common.dsconn import open_connection

    result = {"id": "", "columns": [], "rows": [], "truncated": False, "error": ""}
    try:
        conn = open_connection(ds)
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                result["columns"] = [c[0] for c in cur.description or []]
                while len(result["rows"]) < cap:
                    batch = cur.fetchmany(min(200, cap - len(result["rows"])))
                    if not batch:
                        break
                    result["rows"] += [[str(v) for v in row] for row in batch]
                result["truncated"] = cur.fetchone() is not None or len(result["rows"]) >= cap
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    return result


@router.post("/preview", summary="数据预览（每查询 LIMIT 100，只读）")
def preview(body: PreviewBody, db: Session = Depends(get_db), _user=Depends(require_perm("design_component"))):
    results = {}
    for q in body.queries:
        sql = (q.sql or "").strip().rstrip(";")
        if not SELECT_RE.match(sql):
            raise ApiError(PAGE_PREVIEW_SQL_FORBIDDEN, status=422)
        ds = db.get(DataSource, q.datasourceId)
        if ds is None:
            results[q.id] = {"columns": [], "rows": [], "truncated": False, "error": f"数据源 {q.datasourceId} 不存在"}
            continue
        item = _run_readonly(ds, f"SELECT * FROM ({sql}) _pv LIMIT {PREVIEW_ROW_CAP}", PREVIEW_ROW_CAP)
        item["id"] = q.id
        results[q.id] = item
    # 失败组件聚合（按 queries 顺序而非 dict 序，保证稳定；成功项不进，前端汇总提示用）
    widget_errors = [{"id": q.id, "error": results[q.id]["error"]} for q in body.queries if results[q.id].get("error")]
    return ok({"results": results, "rowCap": PREVIEW_ROW_CAP, "widgetErrors": widget_errors})
