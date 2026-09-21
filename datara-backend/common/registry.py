"""ZK 注册中心封装（kazoo）：注册 / 心跳 / 掉线感知 / 选主，ZK 不可用时降级运行。

对齐海豚 Registry(ZK) Plugin：
- 注册路径：/datara/live/{module}/{ip:port}（临时节点，随会话消失=掉线感知）
- 心跳：ZK 会话级临时节点自动保活 + 进程内 10s 兜底续期（节点丢失则重建）
- 选主：抢占式临时节点；注意 ZK 临时节点不能拥有子节点，而 master 模块自身
  需注册 /datara/live/master/{ip:port}，故选举节点落在 /datara/live/leader
- 降级策略：ZK 连不上仅记 warning 继续跑（不崩溃），后台线程 10s 自动重连重试
"""

import socket
import threading
from typing import Optional, Tuple

from kazoo.client import KazooClient
from kazoo.exceptions import NodeExistsError

from common.config import get_settings
from common.log import get_logger

logger = get_logger("common.registry")

LIVE_ROOT = "/datara/live"
# 选举节点路径（见模块 docstring 说明：不能与 /datara/live/master 注册目录重叠）
LEADER_PATH = "/datara/live/leader"


def detect_ip() -> str:
    """探测本机 IP（容器内取容器 IP）。"""
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return "127.0.0.1"


def list_live_nodes(zk: Optional[KazooClient]) -> Tuple[bool, list]:
    """递归列出 /datara/live 下全部注册节点：[{module, node}]。

    返回 (zkAvailable, nodes)；ZK 不可用时 (False, [])。
    """
    if zk is None or not zk.connected:
        return False, []
    try:
        nodes = []
        for module in sorted(zk.get_children(LIVE_ROOT)):
            for node in sorted(zk.get_children("%s/%s" % (LIVE_ROOT, module))):
                nodes.append({"module": module, "node": node})
        return True, nodes
    except Exception as exc:  # noqa: BLE001 列举失败按不可用处理
        logger.warning("列举注册节点失败: %s", exc)
        return False, []


class ServiceRegistry:
    """模块注册器：后台线程连接 ZK、注册临时节点、断线自动重连。

    用法：registry = ServiceRegistry("worker", 18002); registry.start()
    """

    def __init__(self, module: str, port: int):
        self.module = module
        self.port = port
        self.host_ip = detect_ip()
        self._zk: Optional[KazooClient] = None
        self._node_path: str = "%s/%s/%s:%s" % (LIVE_ROOT, module, self.host_ip, port)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ---- 对外状态 ----

    @property
    def zk(self) -> Optional[KazooClient]:
        return self._zk

    @property
    def connected(self) -> bool:
        return self._zk is not None and self._zk.connected

    def identity(self) -> str:
        return "%s:%s" % (self.host_ip, self.port)

    # ---- 生命周期 ----

    def start(self) -> None:
        """启动后台注册线程（守护线程，不阻塞主流程）。"""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="zk-registry-%s" % self.module, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """停止线程并关闭 ZK 会话（临时节点随之消失）。"""
        self._stop.set()
        zk = self._zk
        if zk is not None:
            try:
                zk.stop()
                zk.close()
            except Exception:  # noqa: BLE001 退出清理尽力而为
                pass
            self._zk = None

    # ---- 内部实现 ----

    def _loop(self) -> None:
        """连接 → 注册 → 保活续期；断开或异常则降级重试，进程不退出。"""
        while not self._stop.is_set():
            zk: Optional[KazooClient] = None
            try:
                zk = KazooClient(hosts=get_settings().zk_hosts, timeout=6)
                zk.start(timeout=6)
                self._zk = zk
                self._register(zk)
                logger.info("ZK 注册成功: %s", self._node_path)
                # 会话保活 + 兜底续期（10s 周期；会话由 ZK 自动维持，此处防节点意外丢失）
                while not self._stop.is_set() and zk.connected:
                    if self._stop.wait(10):
                        break
                    if zk.connected:
                        self._renew(zk)
            except Exception as exc:  # noqa: BLE001 降级运行：不崩溃
                logger.warning("ZK 不可用，降级运行（10s 后自动重连）: %s", exc)
            finally:
                if self._zk is zk and zk is not None:
                    self._zk = None
                    try:
                        zk.stop()
                        zk.close()
                    except Exception:  # noqa: BLE001
                        pass
            if not self._stop.is_set():
                self._stop.wait(10)

    def _register(self, zk: KazooClient) -> None:
        """注册临时节点 /datara/live/{module}/{ip:port}。"""
        if zk.exists(self._node_path):
            # 残留节点（异常退出遗留）先清除再注册
            try:
                zk.delete(self._node_path)
            except Exception:  # noqa: BLE001
                pass
        zk.create(self._node_path, ephemeral=True, makepath=True)

    def _renew(self, zk: KazooClient) -> None:
        """兜底续期：临时节点丢失（如会话短暂抖动）则重建。"""
        try:
            if not zk.exists(self._node_path):
                zk.create(self._node_path, ephemeral=True, makepath=True)
                logger.info("ZK 节点续期重建: %s", self._node_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ZK 节点续期失败: %s", exc)

    # ---- 选主（master 用） ----

    def elect_master(self, path: str = LEADER_PATH) -> bool:
        """抢占式选主：创建临时节点成功即为主，已存在则为 standby。

        ZK 不可用时返回 False（按 standby 处理，服务继续跑）。
        """
        zk = self._zk
        if zk is None or not zk.connected:
            logger.warning("ZK 不可用，选主跳过（降级为主继续运行）")
            return False
        try:
            zk.create(path, self.identity().encode("utf-8"), ephemeral=True, makepath=True)
            return True
        except NodeExistsError:
            return False
        except Exception as exc:  # noqa: BLE001
            logger.warning("选主异常（按 standby 处理）: %s", exc)
            return False
