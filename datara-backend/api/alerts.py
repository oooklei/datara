"""持久化告警查询 API，供真实模式下的站内消息中心使用。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.auth import require_perm
from common.db import get_db
from common.models import AlertRecord
from common.resp import fmt_dt, ok

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _target(record: AlertRecord) -> str:
    if record.instance_id:
        return "/dag/instances"
    if (record.title or "").startswith("流任务"):
        return "/stream/list"
    return "/dep/alarm"


def alert_payload(record: AlertRecord) -> dict:
    return {
        "id": record.id,
        "instanceId": record.instance_id,
        "title": record.title or "Datara 告警",
        "content": record.content or "",
        "channel": record.channel or "system",
        "state": record.state,
        "createTime": fmt_dt(record.create_time),
        "updateTime": fmt_dt(record.update_time),
        "target": _target(record),
    }


@router.get("")
def list_alerts(
    limit: int = Query(default=20, ge=1, le=100),
    user=Depends(require_perm("view_all")),
    db: Session = Depends(get_db),
):
    rows = db.query(AlertRecord).order_by(AlertRecord.id.desc()).limit(limit).all()
    return ok([alert_payload(row) for row in rows])
