"""Redis 封装：任务队列（Stream 消费组）+ 状态上报流 + 会话 token + kill 标记。

- datara:stream:tasks:{high|normal|low}  任务流（master XADD → worker XREADGROUP + XACK）
- datara:stream:task_state               状态上报流（worker XADD → master XREADGROUP + XACK）
- datara:kill:{taskId}                   任务中断标记（master SETEX → worker 执行器周期检查）
- datara:token:{tk}                      登录会话（SETEX TTL）

I3 精化（设计文档 §3.2）：I1 Redis List at-most-once → Stream 消费组 at-least-once；
重复投递由 worker 幂等校验（以 t_task_instance 状态为准）防护；worker 启动时
XAUTOCLAIM 认领 idle 超阈值的 pending 消息补执行。
"""

import json
import os
import socket
import threading
from typing import Any, Optional

import redis

from common.config import get_settings
from common.log import get_logger

logger = get_logger("common.queue")

TASK_STREAM_PREFIX = "datara:stream:tasks:"
STREAM_HIGH = TASK_STREAM_PREFIX + "high"
STREAM_NORMAL = TASK_STREAM_PREFIX + "normal"
STREAM_LOW = TASK_STREAM_PREFIX + "low"
TASK_STREAMS = (STREAM_HIGH, STREAM_NORMAL, STREAM_LOW)
STATE_STREAM = "datara:stream:task_state"
TOKEN_PREFIX = "datara:token:"
KILL_PREFIX = "datara:kill:"

MASTER_GROUP = "datara-master"
WORKER_GROUP = "datara-worker"


def master_consumer() -> str:
    """master 消费者名（host-pid）。"""
    return "%s-%s" % (socket.gethostname(), os.getpid())


def worker_consumer() -> str:
    """worker 消费者名（host-pid）。"""
    return "%s-%s" % (socket.gethostname(), os.getpid())


_client: Optional[redis.Redis] = None
_lock = threading.Lock()


def get_client() -> redis.Redis:
    """双重检查懒加载 Redis 客户端（decode_responses 直接收发 str）。"""
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                _client = redis.Redis.from_url(
                    get_settings().redis_url,
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=3,
                )
    return _client


def dumps(value: Any) -> str:
    """统一 JSON 序列化（队列载荷/会话内容共用）。"""
    return json.dumps(value, ensure_ascii=False)


def _loads(raw: Any) -> dict:
    return json.loads(raw) if isinstance(raw, str) else (raw or {})


# ---------- 消费组管理 ----------

def ensure_group(stream: str, group: str) -> None:
    """幂等创建消费组（组不存在则从 0-0 建，BUSYGROUP 忽略）。"""
    try:
        get_client().xgroup_create(stream, group, id="0-0", mkstream=True)
    except redis.exceptions.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def ensure_all_groups() -> None:
    """master/worker 启动时调用：建齐全部流与消费组。"""
    for stream in TASK_STREAMS:
        ensure_group(stream, WORKER_GROUP)
    ensure_group(STATE_STREAM, MASTER_GROUP)


# ---------- 任务流（master → worker） ----------

def priority_stream(priority: int) -> str:
    """优先级 1~5 → 三档流（4~5→high，3→normal，1~2→low）。"""
    if priority >= 4:
        return STREAM_HIGH
    if priority <= 2:
        return STREAM_LOW
    return STREAM_NORMAL


def add_task(payload: dict, priority: int = 3) -> str:
    """任务消息入流（master 派发；默认 normal 档）。"""
    return get_client().xadd(priority_stream(priority), {"data": dumps(payload)})


def read_tasks(consumer: str, block_ms: int = 1000, count: int = 1) -> list:
    """worker 消费任务：一次按 high→normal→low 读新消息。返回 [(stream, msg_id, payload)]。"""
    client = get_client()
    streams = {s: ">" for s in TASK_STREAMS}
    try:
        result = client.xreadgroup(
            WORKER_GROUP, consumer, streams, count=count, block=block_ms
        )
    except redis.exceptions.ResponseError as exc:
        # 消费组缺失（如 Redis 重启丢流）时自愈重建
        if "NOGROUP" in str(exc):
            ensure_all_groups()
            return []
        raise
    items = []
    for stream, entries in result:
        for msg_id, fields in entries:
            items.append((stream, msg_id, _loads(fields.get("data"))))
    return items


def ack_task(stream: str, msg_id: str) -> None:
    """worker 处理完成确认（从 pending list 移除）。"""
    get_client().xack(stream, WORKER_GROUP, msg_id)


def claim_stale_tasks(consumer: str, min_idle_ms: int = 60000) -> list:
    """worker 启动/周期认领：接管 idle 超阈值的 pending 消息（worker 崩溃自愈）。"""
    client = get_client()
    items = []
    for stream in TASK_STREAMS:
        try:
            result = client.xautoclaim(
                stream, WORKER_GROUP, consumer, min_idle_time=min_idle_ms,
                start_id="0-0", count=10,
            )
        except redis.exceptions.ResponseError:
            ensure_all_groups()
            continue
        # redis-py 5.x 返回 [next_start_id, [(msg_id, fields), ...], [deleted]]
        for msg_id, fields in (result[1] if result else []):
            payload = fields.get("data")
            if payload is None:
                continue
            items.append((stream, msg_id, _loads(payload)))
    return items


# ---------- 状态上报流（worker → master） ----------

def add_state(payload: dict) -> str:
    """任务状态上报入流（worker）。"""
    return get_client().xadd(STATE_STREAM, {"data": dumps(payload)})


def read_states(consumer: str, block_ms: int = 1000, count: int = 5) -> list:
    """master 消费状态上报。返回 [(msg_id, payload)]。"""
    client = get_client()
    try:
        result = client.xreadgroup(
            MASTER_GROUP, consumer, {STATE_STREAM: ">"}, count=count, block=block_ms
        )
    except redis.exceptions.ResponseError as exc:
        if "NOGROUP" in str(exc):
            ensure_all_groups()
            return []
        raise
    items = []
    for _stream, entries in result:
        for msg_id, fields in entries:
            items.append((msg_id, _loads(fields.get("data"))))
    return items


def ack_state(msg_id: str) -> None:
    """master 消费完成确认。"""
    get_client().xack(STATE_STREAM, MASTER_GROUP, msg_id)


# ---------- kill 中断标记 ----------

def set_kill(task_id: int, reason: str = "stop", ttl: int = 86400) -> None:
    """任务中断标记（master：取消/超时时设置，worker 执行器周期检查）。

    reason 区分来源：stop=用户停止，timeout=引擎超时扫描（worker 按 failure 收口，§14 项7）。
    """
    get_client().setex(KILL_PREFIX + str(task_id), ttl, reason or "stop")


def check_kill(task_id: int) -> str:
    """worker 执行器查询中断原因：未中断返回 ""（falsy），否则 "stop"/"timeout"。"""
    value = get_client().get(KILL_PREFIX + str(task_id))
    if not value:
        return ""
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def clear_kill(task_id: int) -> None:
    """任务结束清理标记位。"""
    get_client().delete(KILL_PREFIX + str(task_id))


# ---------- 会话 token ----------

def save_token(token: str, user_json: str, ttl: int) -> None:
    """SETEX 存会话，TTL 到期自动失效。"""
    get_client().setex(TOKEN_PREFIX + token, ttl, user_json)


def get_token(token: str) -> Optional[str]:
    """读会话内容（不存在/过期返回 None）。"""
    return get_client().get(TOKEN_PREFIX + token)


def delete_token(token: str) -> None:
    """登出删除会话。"""
    get_client().delete(TOKEN_PREFIX + token)


def ping() -> bool:
    """健康检查探活。"""
    try:
        return bool(get_client().ping())
    except Exception as exc:  # noqa: BLE001 健康检查只报状态
        logger.warning("redis 探活失败: %s", exc)
        return False
