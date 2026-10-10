"""Best-effort run event publishing: Redis fan-out plus durable replay rows."""

import json
import threading
import time
from typing import Any, Optional

import redis

from common.config import get_settings
from common.db import new_session
from common.log import get_logger
from common.models import TRunEvent

logger = get_logger("master.event_bus")

PROGRESS_EVENT = "progress"
# 方案 R6（设计文档 §9.3 #6）：大图高频 progress 事件洪水 → 200ms 合帧。
# 同一 (run_id, node_id) 在窗口内只保留最新值，到点只发一条（发布+落库同样只合帧后一条）；
# 其余事件类型不受节流，即时直发。
PROGRESS_FRAME_SEC = 0.2

_client: Optional[redis.Redis] = None
_lock = threading.Lock()


def _get_client() -> redis.Redis:
    """双重检查懒加载 Redis 客户端（复用连接，惯例同 common.queue.get_client）。"""
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                _client = redis.from_url(get_settings().redis_url)
    return _client


def publish_run_event(
    run_id: str, node_id: str, event_type: str, payload: Optional[dict[str, Any]] = None, rds=None
) -> dict:
    """公共发布入口：progress 走 200ms 合帧（方案 R6，见 _ProgressFramer），其余类型即时直发。

    progress 返回值为窗口内将要发出的合成消息（非实际发送时刻）；best-effort 语义不变。
    """
    if event_type == PROGRESS_EVENT:
        try:
            _framer.submit(run_id, node_id, payload, rds)
        except Exception as exc:  # 合帧绝不影响调度（best-effort 同主线），失败降级直发
            logger.warning("progress 合帧提交失败，降级直发: %s", exc)
            return _deliver(run_id, node_id, event_type, payload, rds)
        return {"runId": run_id, "nodeId": node_id, "type": event_type, "ts": int(time.time() * 1000)}
    return _deliver(run_id, node_id, event_type, payload, rds)


def _deliver(run_id: str, node_id: str, event_type: str, payload: Optional[dict[str, Any]] = None, rds=None) -> dict:
    message = {"runId": run_id, "nodeId": node_id, "type": event_type, "ts": int(time.time() * 1000)}
    if payload:
        message["payload"] = payload
    try:
        client = rds or _get_client()
        client.publish("datara:run_events:%s" % run_id, json.dumps(message, ensure_ascii=False, default=str))
    except Exception as exc:  # delivery must never affect scheduling
        logger.warning("运行事件 Redis 发布失败: %s", exc)
    try:
        session = new_session()
        try:
            session.add(
                TRunEvent(
                    run_id=run_id,
                    node_id=node_id,
                    event_type=event_type,
                    payload_json=json.dumps(payload, ensure_ascii=False, default=str) if payload else None,
                )
            )
            session.commit()
        finally:
            session.close()
    except Exception as exc:  # durable replay is also non-invasive
        logger.warning("运行事件落库失败: %s", exc)
    return message


class _ProgressFramer:
    """progress 事件 200ms 合帧器（方案 R6）。

    - 帧 key 为 (run_id, node_id)：首条入队起算窗口，窗口内后续 progress 只覆盖
      缓存值（due 不变），到点仅发最新一条——持续高频时每帧间隔 ≥ 窗口长度；
    - flush 在锁外执行（Redis/落库慢不阻塞 submit）；失败仅 warn（best-effort 同主线）；
    - daemon flusher 线程惰性启动、空闲挂起（Condition.wait），进程退出自动回收。
    """

    def __init__(self, window: float = PROGRESS_FRAME_SEC):
        self._window = window
        self._cond = threading.Condition()
        self._pending: dict[tuple[str, str], list] = {}  # key -> [due, run_id, node_id, payload, rds]
        self._inflight = 0  # 已出队正在发送的条数（wait_drained 判定发送完成）
        self._flusher: Optional[threading.Thread] = None

    def submit(self, run_id: str, node_id: str, payload: Optional[dict[str, Any]], rds=None) -> None:
        with self._cond:
            key = (run_id, node_id)
            slot = self._pending.get(key)
            if slot is None:
                self._pending[key] = [time.monotonic() + self._window, run_id, node_id, payload, rds]
                self._spawn()
            else:
                slot[3] = payload  # 窗口内合帧：只保留最新值，due 不变
            self._cond.notify_all()

    def _spawn(self) -> None:  # 持锁调用
        if self._flusher is None or not self._flusher.is_alive():
            self._flusher = threading.Thread(target=self._loop, name="progress-framer", daemon=True)
            self._flusher.start()

    def _loop(self) -> None:
        while True:
            with self._cond:
                now = time.monotonic()
                batch = [self._pending.pop(k) for k, slot in list(self._pending.items()) if slot[0] <= now]
                if not batch:
                    if self._pending:
                        self._cond.wait(max(0.0, min(slot[0] for slot in self._pending.values()) - now))
                    else:
                        self._cond.wait()  # 空闲挂起，submit notify 唤醒
                    continue
                self._inflight += len(batch)
            for _due, run_id, node_id, payload, rds in batch:
                _deliver(run_id, node_id, PROGRESS_EVENT, payload, rds)
            with self._cond:
                self._inflight -= len(batch)
                self._cond.notify_all()

    def wait_drained(self, timeout: float) -> bool:
        """等待全部挂起 progress 合帧完成（测试辅助，生产不调用）。"""
        deadline = time.monotonic() + timeout
        with self._cond:
            while self._pending or self._inflight:
                left = deadline - time.monotonic()
                if left <= 0:
                    return False
                self._cond.wait(min(left, 0.05))
            return True


_framer = _ProgressFramer()
