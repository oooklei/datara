"""节点监控聚合路由（I7 F55，设计 §3.4）：GET /api/v1/monitor/nodes。

- ZK live 路径列举（复用 api 容器 ServiceRegistry 的 ZK 连接）→ master/worker 在线节点
- 每节点合并 Redis monitor:{module}:{node} 指标（TTL 90s，缺=未上报/已过期）
- SSH 节点取 t_ssh_node（heartbeat_state/last_seen 即心跳口径；无主机指标——远端采集后置）
- ZK 不可用降级：live 为空列表，ssh 节点照常返回（监控页不阻断）
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from api.auth import get_current_user
from common.db import get_db
from common.models import SshNode, User
from common.monitor import METRICS_TTL_SEC, read_known_nodes, read_metrics
from common.registry import list_live_nodes
from common.resp import fmt_dt, ok

router = APIRouter(prefix="/monitor", tags=["monitor"])

# 监控聚合展示的模块（api 自身为网关不展示；ssh 走 t_ssh_node 单独合并）
MONITOR_MODULES = ("master", "worker")


@router.get("/nodes")
def monitor_nodes(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """节点监控列表：master/worker（ZK live + Redis 指标）+ ssh（注册表心跳）。"""
    registry = getattr(request.app.state, "registry", None)
    zk_ok, live = list_live_nodes(registry.zk if registry is not None else None)

    rows = []
    live_by_module = {module: {item["node"] for item in live if item["module"] == module} for module in MONITOR_MODULES}
    current_ts = datetime.now().timestamp()
    for module in MONITOR_MODULES:
        known = read_known_nodes(module)
        for node in sorted(live_by_module[module] | set(known)):
            m = read_metrics(module, node) or {}
            reported_at = float(m.get("reportedAt") or known.get(node) or 0)
            age = current_ts - reported_at if reported_at else None
            metric_state = "fresh" if age is not None and age <= METRICS_TTL_SEC else "stale"
            heartbeat = ("online" if node in live_by_module[module] else "offline") if zk_ok else "unknown"
            rows.append(
                {
                    "module": module,
                    "node": node,
                    "cpu": m.get("cpu"),
                    "mem": m.get("mem"),
                    "memUsedMb": m.get("memUsedMb"),
                    "memTotalMb": m.get("memTotalMb"),
                    "disk": m.get("disk"),
                    "heartbeat": heartbeat,
                    "metricState": metric_state,
                    "lastSeen": fmt_dt(datetime.fromtimestamp(reported_at)) if reported_at else None,
                    "tags": [],
                }
            )

    for node_row in db.query(SshNode).order_by(SshNode.id).all():
        rows.append(
            {
                "module": "ssh",
                "node": node_row.name,
                "cpu": None,
                "mem": None,
                "memUsedMb": None,
                "memTotalMb": None,
                "disk": None,
                "heartbeat": node_row.heartbeat_state,
                "metricState": "unsupported",
                "lastSeen": fmt_dt(node_row.last_seen),
                "tags": node_row.tags or [],
            }
        )

    return ok({"zkAvailable": zk_ok, "generatedAt": fmt_dt(datetime.now()), "nodes": rows})
