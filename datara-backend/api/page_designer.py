"""页面设计器 API：资源目录（设计态元数据+运行态变量）与数据预览（LIMIT 100 只读）。

- GET /page-designer/resources 系统资源目录（适配性绑定候选来源）：
  数据源 / 工作流及其变量 / 全局参数 / 时间参数（系统内置）/ 组件清单
- POST /page-designer/preview 数据预览：仅 SELECT/WITH，每查询硬编码 LIMIT 100（§8 不配置化）
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.auth import require_perm
from common.db import get_db
from common.models import Component, DataSource, GlobalParam, WfDefinition, WfVariable
from common.resp import ok

router = APIRouter(prefix="/page-designer", tags=["page-designer"])

# 系统时间参数（前端展示标签 + 示例值；运行态由页面运行时按当前时间求值）
TIME_PARAMS = [
    {"path": "$system.date", "label": "当前日期", "sample": "2026-10-03"},
    {"path": "$system.datetime", "label": "当前时间", "sample": "2026-10-03 00:00:00"},
    {"path": "$system.month", "label": "当前月份", "sample": "2026-10"},
]


@router.get("/resources", summary="系统资源目录（适配性绑定候选来源）")
def resources(db: Session = Depends(get_db), _user=Depends(require_perm("design_component"))):
    return ok({
        "datasources": [
            {"id": d.id, "name": d.name, "type": d.type, "db": d.db_name or ""}
            for d in db.query(DataSource).order_by(DataSource.name).all()],
        "workflows": [
            {"code": w.code, "name": w.name,
             "vars": [{"path": f"$wf.{v.name}", "label": v.name, "type": v.type}
                      for v in db.query(WfVariable).filter(WfVariable.wf_code == w.code).all()]}
            for w in db.query(WfDefinition).order_by(WfDefinition.name).all()],
        "globalParams": [
            {"path": f"$param.{p.name}", "label": p.name}
            for p in db.query(GlobalParam).order_by(GlobalParam.name).all()],
        "timeParams": TIME_PARAMS,
        "components": [
            {"type": c.type, "name": c.name, "state": c.state,
             "publishedVersion": c.published_version}
            for c in db.query(Component).order_by(Component.type).all()],
    })
