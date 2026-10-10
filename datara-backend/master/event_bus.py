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


def publish_run_event(run_id: str, node_id: str, event_type: str,
                      payload: Optional[dict[str, Any]] = None, rds=None) -> dict:
    message = {"runId": run_id, "nodeId": node_id, "type": event_type,
               "ts": int(time.time() * 1000)}
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
            session.add(TRunEvent(run_id=run_id, node_id=node_id, event_type=event_type,
                                  payload_json=json.dumps(payload, ensure_ascii=False, default=str) if payload else None))
            session.commit()
        finally:
            session.close()
    except Exception as exc:  # durable replay is also non-invasive
        logger.warning("运行事件落库失败: %s", exc)
    return message
