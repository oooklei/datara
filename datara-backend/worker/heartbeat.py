"""worker 心跳：注册 /datara/live/worker/{ip:18002}（临时节点，10s 兜底续期）
+ I7 F55 指标上报（psutil 采集 → Redis monitor:worker:{node}，TTL 90s，10s 周期）。
"""

import threading

from common.log import get_logger
from common.monitor import report_metrics
from common.registry import ServiceRegistry

logger = get_logger("worker.heartbeat")

REPORT_INTERVAL_SEC = 10


class WorkerHeartbeat:
    """注册 + 指标上报（注册续期由 ServiceRegistry 内部 10s 周期兜底）。"""

    def __init__(self, port: int = 18002):
        self.registry = ServiceRegistry("worker", port)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self.registry.start()
        self._thread = threading.Thread(target=self._report_loop, name="worker-metrics", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.registry.stop()

    def _report_loop(self) -> None:
        """指标上报循环：psutil 缺失时 report_metrics 内部跳过，循环保持空转开销极低。"""
        node = self.registry.identity()
        logger.info("worker 指标上报启动（%ds/次 → monitor:worker:%s）", REPORT_INTERVAL_SEC, node)
        while not self._stop.is_set():
            try:
                report_metrics("worker", node)
            except Exception as exc:  # noqa: BLE001 上报异常不崩线程
                logger.warning("指标上报异常: %r", exc)
            self._stop.wait(REPORT_INTERVAL_SEC)
