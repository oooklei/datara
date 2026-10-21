"""Cluster-node aggregation copied from the legacy monitor endpoint."""

from __future__ import annotations

from datetime import datetime
from typing import Callable, Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from rebuild.sshnode.models import SshNodeRecord

MONITOR_MODULES = ("master", "worker")
METRICS_TTL_SEC = 90

LiveNodesReader = Callable[[], tuple[bool, list[dict[str, str]]]]
KnownNodesReader = Callable[[str], Mapping[str, float]]
MetricsReader = Callable[[str, str], Mapping[str, object] | None]


def _date(value: datetime | None) -> str | None:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value is not None else None


class MonitorService:
    """Merge ZK liveness, Redis metrics and rebuild SSH registry rows."""

    def __init__(
        self,
        session: Session,
        live_nodes_reader: LiveNodesReader,
        known_nodes_reader: KnownNodesReader,
        metrics_reader: MetricsReader,
        *,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._session = session
        self._live_nodes_reader = live_nodes_reader
        self._known_nodes_reader = known_nodes_reader
        self._metrics_reader = metrics_reader
        self._now = now

    def nodes(self) -> dict[str, object]:
        # The legacy contract fails closed only for authentication. ZK and Redis
        # are observability dependencies, so their failures degrade the payload.
        try:
            zk_available, live = self._live_nodes_reader()
        except Exception:  # noqa: BLE001 - frozen degraded behavior
            zk_available, live = False, []

        live_by_module = {
            module: {
                str(item["node"])
                for item in live
                if item.get("module") == module and item.get("node") is not None
            }
            for module in MONITOR_MODULES
        }
        generated_at = self._now()
        rows: list[dict[str, object]] = []
        for module in MONITOR_MODULES:
            try:
                known = dict(self._known_nodes_reader(module))
            except Exception:  # noqa: BLE001 - Redis outage degrades to live only
                known = {}
            for node in sorted(live_by_module[module] | set(known)):
                try:
                    metrics = dict(self._metrics_reader(module, node) or {})
                except Exception:  # noqa: BLE001 - missing metrics are stale
                    metrics = {}
                reported_at = float(metrics.get("reportedAt") or known.get(node) or 0)
                age = generated_at.timestamp() - reported_at if reported_at else None
                rows.append(
                    {
                        "module": module,
                        "node": node,
                        "cpu": metrics.get("cpu"),
                        "mem": metrics.get("mem"),
                        "memUsedMb": metrics.get("memUsedMb"),
                        "memTotalMb": metrics.get("memTotalMb"),
                        "disk": metrics.get("disk"),
                        "heartbeat": (
                            "online" if node in live_by_module[module] else "offline"
                        )
                        if zk_available
                        else "unknown",
                        "metricState": (
                            "fresh" if age is not None and age <= METRICS_TTL_SEC else "stale"
                        ),
                        "lastSeen": _date(datetime.fromtimestamp(reported_at)) if reported_at else None,
                        "tags": [],
                    }
                )

        ssh_nodes = self._session.scalars(select(SshNodeRecord).order_by(SshNodeRecord.id)).all()
        for record in ssh_nodes:
            rows.append(
                {
                    "module": "ssh",
                    "node": record.name,
                    "cpu": None,
                    "mem": None,
                    "memUsedMb": None,
                    "memTotalMb": None,
                    "disk": None,
                    "heartbeat": record.heartbeat_state,
                    "metricState": "unsupported",
                    "lastSeen": _date(record.last_seen),
                    "tags": record.tags or [],
                }
            )
        return {"zkAvailable": bool(zk_available), "generatedAt": _date(generated_at), "nodes": rows}
