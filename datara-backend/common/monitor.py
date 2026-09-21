"""节点监控指标（I7 F55，设计 §3.4）：psutil 采集 + Redis `monitor:{module}:{node}` 存储。

- 上报：master/worker 心跳线程周期采集 → SET key json EX 90（TTL 兜底，过期=心跳失联）
- 读取：api/monitor.py 聚合时按节点读 Redis 指标合并 ZK live 状态
- psutil 缺失时 collect 返回 None（调用方跳过上报，不阻断心跳线程）
- cpu_percent(interval=None) 非阻塞取自上次调用以来的均值（周期调用即周期均值）
"""

import json
from typing import Optional

from common import queue as redis_queue
from common.log import get_logger

logger = get_logger("common.monitor")

METRICS_TTL_SEC = 90


def metrics_key(module: str, node: str) -> str:
    return "monitor:%s:%s" % (module, node)


def collect_metrics() -> Optional[dict]:
    """psutil 采集本机指标；psutil 缺失/异常返回 None。"""
    try:
        import psutil
    except ImportError:
        return None
    try:
        vm = psutil.virtual_memory()
        du = psutil.disk_usage("/")
        return {
            "cpu": round(psutil.cpu_percent(interval=None), 1),
            "mem": round(vm.percent, 1),
            "memUsedMb": int(vm.used / 1024 / 1024),
            "memTotalMb": int(vm.total / 1024 / 1024),
            "disk": round(du.percent, 1),
        }
    except Exception as exc:  # noqa: BLE001 采集失败按无指标处理
        logger.warning("指标采集失败: %r", exc)
        return None


def report_metrics(module: str, node: str) -> None:
    """采集并上报本机指标（心跳线程周期调用）。"""
    data = collect_metrics()
    if data is None:
        return
    try:
        redis_queue.get_client().set(
            metrics_key(module, node), json.dumps(data), ex=METRICS_TTL_SEC)
    except Exception as exc:  # noqa: BLE001 上报失败不影响心跳主流程
        logger.warning("指标上报失败: %s/%s %r", module, node, exc)


def read_metrics(module: str, node: str) -> Optional[dict]:
    """读取节点指标（Redis 不可达/无 key 返回 None）。"""
    try:
        raw = redis_queue.get_client().get(metrics_key(module, node))
        return json.loads(raw) if raw else None
    except Exception as exc:  # noqa: BLE001 读取失败按无指标
        logger.warning("指标读取失败: %s/%s %r", module, node, exc)
        return None
