"""master 心跳与选主：注册 /datara/live/master/{ip:18001}，周期抢占选主节点；
I7 F55 附带 psutil 指标上报（monitor:master:{node}，随 10s 循环）。

ZK 不可用降级为主（单机部署现实口径）：连续 3 轮（30s）ZK 不可达即自认 leader，
引擎线程照常运行；ZK 恢复后若主已被其他节点持有则保持降级并告警日志（多主机 HA 归 I7）。
"""

import threading
from typing import Optional

from common.log import get_logger
from common.monitor import report_metrics
from common.registry import LEADER_PATH, ServiceRegistry

logger = get_logger("master.heartbeat")

ZK_FAIL_GRACE = 3  # 连续不可达轮数阈值（10s/轮 → 30s）


class MasterHeartbeat:
    """注册 + 选主线程（10s 周期）：未持主则尝试抢占；ZK 不可用降级为主。"""

    def __init__(self, port: int = 18001):
        self.registry = ServiceRegistry("master", port)
        self.is_master = False
        self._zk_fail_streak = 0
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def is_leader(self) -> bool:
        return self.is_master

    def start(self) -> None:
        self.registry.start()
        self._thread = threading.Thread(target=self._loop, name="master-heartbeat", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.registry.stop()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                report_metrics("master", self.registry.identity())  # I7 F55：随循环上报指标
            except Exception as exc:  # noqa: BLE001 指标上报不阻断选主
                logger.warning("master 指标上报异常: %r", exc)
            try:
                if not self.is_master:
                    if self.registry.elect_master(LEADER_PATH):
                        self.is_master = True
                        self._zk_fail_streak = 0
                        logger.info("选主成功：本节点成为 master（%s）", self.registry.identity())
                    elif not self.registry.connected:
                        self._zk_fail_streak += 1
                        if self._zk_fail_streak >= ZK_FAIL_GRACE:
                            self.is_master = True
                            logger.warning(
                                "ZK 连续 %d 轮不可达，降级为主继续运行（单机口径）",
                                self._zk_fail_streak,
                            )
                        else:
                            logger.info("ZK 不可达（%d/%d），10s 后重试", self._zk_fail_streak, ZK_FAIL_GRACE)
                    else:
                        self._zk_fail_streak = 0
                        logger.info("standby 待命（master 已存在，10s 后重试）")
            except Exception as exc:  # noqa: BLE001 心跳线程防崩
                logger.warning("选主心跳异常: %s", exc)
            self._stop.wait(10)
