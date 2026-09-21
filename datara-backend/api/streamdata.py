"""流任务实时数据端点（I8 F41 主验通道，设计 §3.3）：

- GET  /stream-jobs/{id}/data?mode=poll|sse：轮询（http 封装 token 头）或 SSE（EventSource
  无法自定义 header → token 查询参数鉴权）；SSE 每秒推送快照 {fields, rows, metrics}
- WS   /stream-jobs/{id}/data/ws?token=：同快照推送（WebSocket 鉴权同口径）

数据源：datara:flink:buf:{job}（ApiSink Last-N，新→旧）+ datara:flink:metrics:{job} Hash。
fields 优先取 C20 schemaText 声明（spec 解析），空则前端按行键并集兜底。
"""

import asyncio
import json

from fastapi import APIRouter, Depends, Query, Request, WebSocket
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from api.auth import ApiError, TOKEN_INVALID
from common import queue
from common.db import get_db
from common.log import get_logger
from common.models import StreamJob
from common.resp import ok

logger = get_logger("api.streamdata")

router = APIRouter(prefix="/stream-jobs", tags=["stream-data"])

PUSH_INTERVAL = 1.0     # SSE/WS 快照周期（秒）
DEFAULT_LIMIT = 100     # 轮询/SSE 单帧行数上限


def _query_token_ok(request: Request, token: str) -> bool:
    """SSE/WS 鉴权：查询参数 token 优先，回退 header（与 auth._request_token 同口径）。"""
    tok = (token or "").strip() or request.headers.get("token") or ""
    if not tok:
        auth_header = request.headers.get("authorization") or ""
        if auth_header.lower().startswith("bearer "):
            tok = auth_header[7:].strip()
    return bool(tok) and queue.get_token(tok) is not None


def _snapshot(job: StreamJob, client, limit: int) -> dict:
    """单帧快照：{fields, rows(新→旧), metrics}；buf 行为 JSON 串，坏行跳过。"""
    fields: list[str] = []
    try:
        spec = json.loads(job.spec_json or "{}")
        for n in spec.get("nodes") or []:
            if n.get("type") == "stream_output":
                schema = str((n.get("params") or {}).get("schemaText") or "")
                fields = [s.strip() for s in schema.split(",") if s.strip()]
                if fields:
                    break
    except (ValueError, AttributeError):
        pass
    raw = client.lrange(f"datara:flink:buf:{job.id}", 0, limit - 1)
    rows = []
    for item in raw:
        try:
            obj = json.loads(item)
            if isinstance(obj, dict):
                rows.append(obj)
        except ValueError:
            continue
    try:
        metrics = client.hgetall(f"datara:flink:metrics:{job.id}") or None
    except Exception:  # noqa: BLE001 指标缺失不阻断数据帧
        metrics = None
    return {"fields": fields, "rows": rows, "metrics": metrics}


@router.get("/{job_id}/data")
async def stream_data(
    job_id: int,
    request: Request,
    mode: str = Query(default="poll", pattern="^(poll|sse)$"),
    token: str = Query(default=""),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """实时数据：mode=poll 单帧返回；mode=sse 持续推送（token 查询参数鉴权）。"""
    job = db.get(StreamJob, job_id)
    if job is None:
        raise ApiError(3001, "流任务不存在", status=404)
    if not _query_token_ok(request, token):
        raise ApiError(TOKEN_INVALID, status=401)

    client = queue.get_client()
    if mode == "poll":
        return ok(_snapshot(job, client, limit))

    async def gen():
        try:
            while True:
                if await request.is_disconnected():
                    return
                frame = _snapshot(job, client, limit)
                status = (frame.get("metrics") or {}).get("status") or ""
                yield f"data: {json.dumps(frame, ensure_ascii=False)}\n\n"
                if status in ("stopped", "failed"):
                    return
                await asyncio.sleep(PUSH_INTERVAL)
        except Exception:  # noqa: BLE001 客户端断开/写超时 → 结束推送
            return

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.websocket("/{job_id}/data/ws")
async def stream_data_ws(
    websocket: WebSocket,
    job_id: int,
    token: str = Query(default=""),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """WebSocket 快照推送（token 查询参数鉴权；无效拒绝 4401）。"""
    if not _query_token_ok(websocket, token):
        await websocket.close(code=4401)
        return
    job = db.get(StreamJob, job_id)
    if job is None:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    client = queue.get_client()
    try:
        while True:
            frame = _snapshot(job, client, limit)
            await websocket.send_json(frame)
            status = (frame.get("metrics") or {}).get("status") or ""
            if status in ("stopped", "failed"):
                return
            await asyncio.sleep(PUSH_INTERVAL)
    except Exception:  # noqa: BLE001 断开即止
        return
