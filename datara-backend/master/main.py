"""master 模块入口：python -m master.main

多线程编排（设计文档 §3.1，仅 leader 持有引擎线程）：
- 内部健康 HTTP（18001，compose healthcheck 用）
- ZK 注册心跳 + 选主线程（ZK 不可用降级为主）
- LeaderGate 联动的四个引擎线程：命令消费 / 状态消费 / 定时调度 / 超时扫描
  （首次成为 leader 时由 LeaderGate 执行一次容错恢复）
"""

import threading

import uvicorn
from fastapi import FastAPI

from common.log import get_logger, setup_logging
from master.heartbeat import MasterHeartbeat
from master.scheduler import LeaderGate, command_loop, state_loop, timeout_loop
from master.schedule import schedule_loop
from master.ssh_probe import ssh_probe_loop


def create_health_app() -> FastAPI:
    """内部健康应用（仅容器 healthcheck 用，无业务路由）。"""
    app = FastAPI(doc_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    def health():
        return {"status": "UP", "module": "master"}

    return app


def main() -> None:
    setup_logging("master")
    logger = get_logger("master")
    logger.info("master 模块启动")

    heartbeat = MasterHeartbeat(port=18001)
    heartbeat.start()

    # 内部健康 HTTP 在独立线程运行（uvicorn 非主线程自动跳过信号注册）
    server = uvicorn.Server(
        uvicorn.Config(create_health_app(), host="0.0.0.0", port=18001, log_level="warning")
    )
    health_thread = threading.Thread(target=server.run, name="master-health", daemon=True)
    health_thread.start()

    stop = threading.Event()
    gate = LeaderGate(heartbeat)
    engine_threads = [
        threading.Thread(target=command_loop, args=(stop, gate), name="master-command", daemon=True),
        threading.Thread(target=state_loop, args=(stop, gate), name="master-state", daemon=True),
        threading.Thread(target=schedule_loop, args=(stop, gate), name="master-schedule", daemon=True),
        threading.Thread(target=timeout_loop, args=(stop, gate), name="master-timeout", daemon=True),
        # I7 F53：SSH 节点探活（30s/轮，仅 leader）
        threading.Thread(target=ssh_probe_loop, args=(stop, gate), name="master-ssh-probe", daemon=True),
    ]
    for thread in engine_threads:
        thread.start()
    try:
        while True:
            stop.wait(3600)
    except KeyboardInterrupt:
        logger.info("收到中断，master 退出")
    finally:
        stop.set()
        heartbeat.stop()


if __name__ == "__main__":
    main()
