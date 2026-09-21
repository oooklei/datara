"""SSH 节点探活线程（I7 F53，设计 §3.3）：master 侧 30s/节点 `echo ok`。

- 仅 leader 执行（LeaderGate 放行，避免多 master 重复探活）
- enabled=1 节点逐个探活：通过 → online + last_seen；失败 → 连续 3 次置 offline
  （失败计数内存态 {node_id: streak}，探活通过即清零；节点删除/停用后清理条目防泄漏）
- 状态落库供派发路由（worker ssh 执行器按 heartbeat_state 过滤）与监控页展示
"""

import threading
from datetime import datetime

from common.db import new_session
from common.log import get_logger
from common.models import SshNode
from common.sshprobe import probe

logger = get_logger("master.ssh_probe")

INTERVAL_SEC = 30
OFFLINE_STREAK = 3  # 连续失败次数阈值 → offline


def ssh_probe_loop(stop: threading.Event, gate) -> None:
    """探活主循环：异常只记日志不崩线程。"""
    logger.info("SSH 探活线程启动（%ds/轮）", INTERVAL_SEC)
    streaks: dict = {}
    while not stop.is_set():
        if gate.check():
            try:
                _probe_round(streaks)
            except Exception as exc:  # noqa: BLE001 单轮失败不影响下轮
                logger.warning("探活轮次异常: %r", exc)
        stop.wait(INTERVAL_SEC)
    logger.info("SSH 探活线程退出")


def _probe_round(streaks: dict) -> None:
    """单轮探活：enabled 节点逐个 echo ok，更新状态与失败计数。"""
    session = new_session()
    try:
        nodes = session.query(SshNode).filter(SshNode.enabled.is_(True)).all()
        live_ids = set()
        for node in nodes:
            live_ids.add(node.id)
            ok_flag, msg = probe(node.host, node.port, node.ssh_user, node.cred_enc or "")
            if ok_flag:
                if node.heartbeat_state != "online":
                    logger.info("SSH 节点上线: %s (%s:%s)", node.name, node.host, node.port)
                streaks.pop(node.id, None)  # 通过即清零（内存条目回收）
                node.heartbeat_state = "online"
                node.last_seen = datetime.now()
            else:
                n = streaks.get(node.id, 0) + 1
                streaks[node.id] = n
                if n >= OFFLINE_STREAK and node.heartbeat_state != "offline":
                    logger.warning("SSH 节点连续 %d 次探活失败置 offline: %s (%s:%s) — %s",
                                   n, node.name, node.host, node.port, msg)
                    node.heartbeat_state = "offline"
                elif n == 1:
                    logger.warning("SSH 节点探活失败（1/%d）: %s — %s", OFFLINE_STREAK, node.name, msg)
        # 清理已停用/删除节点的计数条目（防内存泄漏）
        for gone in [nid for nid in streaks if nid not in live_ids]:
            streaks.pop(gone, None)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
