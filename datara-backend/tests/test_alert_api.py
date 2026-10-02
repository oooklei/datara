from datetime import datetime

from api.alerts import alert_payload
from common.models import AlertRecord


def test_alert_payload_routes_instance_alerts() -> None:
    row = AlertRecord(
        id=7, instance_id="inst-1", title="工作流失败", content="task 3 failed",
        channel="system", state="sent", create_time=datetime(2026, 10, 1, 12, 30),
        update_time=datetime(2026, 10, 1, 12, 31),
    )
    assert alert_payload(row)["target"] == "/dag/instances"
    assert alert_payload(row)["createTime"] == "2026-10-01 12:30:00"


def test_stream_alert_routes_to_stream_list() -> None:
    row = AlertRecord(id=8, title="流任务失败: orders", state="fail")
    assert alert_payload(row)["target"] == "/stream/list"
