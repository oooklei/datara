"""worker 模块入口：python -m worker.main

同时启动：
- 内部健康 HTTP（18002，compose healthcheck 用）
- ZK 注册心跳线程
- 任务消费主循环（BRPOP datara:tasks）
- 流引擎宿主（I8 裁定②：常驻线程 + 控制订阅 + 收割自愈，启动自动恢复 host=me 任务）
"""

import threading

import uvicorn
from fastapi import FastAPI

from common.log import get_logger, setup_logging
from worker.executor import run_loop
from worker.heartbeat import WorkerHeartbeat
from worker.stream import get_engine


def create_health_app() -> FastAPI:
    """内部健康应用（仅容器 healthcheck 用）。"""
    app = FastAPI(doc_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    def health():
        return {"status": "UP", "module": "worker"}

    return app


def main() -> None:
    setup_logging("worker")
    logger = get_logger("worker")
    logger.info("worker 模块启动")

    heartbeat = WorkerHeartbeat(port=18002)
    heartbeat.start()

    server = uvicorn.Server(
        uvicorn.Config(create_health_app(), host="0.0.0.0", port=18002, log_level="warning")
    )
    threading.Thread(target=server.run, name="worker-health", daemon=True).start()

    stop = threading.Event()
    engine = get_engine()
    engine.start()
    try:
        run_loop(stop)
    except KeyboardInterrupt:
        logger.info("收到中断，worker 退出")
    finally:
        stop.set()
        engine.stop()
        heartbeat.stop()


if __name__ == "__main__":
    main()
