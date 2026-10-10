"""alert 模块入口：python -m alert.main

- 内部健康 HTTP（18003，compose healthcheck 用）
- ZK 注册（/datara/live/alert/{ip:18003}）
- 循环 5s 扫 t_alert_record(state='wait') → 通道确认成功后置 sent，失败置 fail
"""

import threading

import uvicorn
from fastapi import FastAPI

from alert.channels import DeliveryError, deliver
from common.db import new_session
from common.log import get_logger, setup_logging
from common.models import AlertRecord, now
from common.registry import ServiceRegistry

logger = get_logger("alert")


def create_health_app() -> FastAPI:
    """内部健康应用（仅容器 healthcheck 用）。"""
    app = FastAPI(doc_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    def health():
        return {"status": "UP", "module": "alert"}

    return app


def _deliver_record(record: AlertRecord) -> None:
    """独立收口一条告警，避免单条失败阻塞同批其他记录。"""
    try:
        deliver(record.channel, record.title, record.content)
    except DeliveryError as exc:
        record.state = "fail"
        logger.error("告警投递失败 alertId=%s channel=%s error=%s", record.id, record.channel, exc)
    else:
        record.state = "sent"
        logger.info("告警投递成功 alertId=%s channel=%s", record.id, record.channel or "system")
    record.update_time = now()


def alert_loop(stop) -> None:
    """5s 一轮扫描并投递待发送告警。"""
    logger.info("alert 轮询循环启动（5s/轮）")
    while not stop.is_set():
        try:
            session = new_session()
            try:
                records = (
                    session.query(AlertRecord)
                    .filter(AlertRecord.state == "wait")
                    .order_by(AlertRecord.id)
                    .limit(20)
                    .all()
                )
                for record in records:
                    _deliver_record(record)
                    session.commit()
            finally:
                session.close()
        except Exception as exc:  # noqa: BLE001 服务循环防崩
            logger.error("告警扫描异常: %s", exc)
        stop.wait(5)
    logger.info("alert 轮询循环退出")


def main() -> None:
    setup_logging("alert")
    logger.info("alert 模块启动")

    registry = ServiceRegistry("alert", 18003)
    registry.start()

    server = uvicorn.Server(uvicorn.Config(create_health_app(), host="0.0.0.0", port=18003, log_level="warning"))
    threading.Thread(target=server.run, name="alert-health", daemon=True).start()

    stop = threading.Event()
    try:
        alert_loop(stop)
    except KeyboardInterrupt:
        logger.info("收到中断，alert 退出")
    finally:
        stop.set()
        registry.stop()


if __name__ == "__main__":
    main()
