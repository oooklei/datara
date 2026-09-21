"""C14 SSH 执行器（I3 §7.2 + I7 F53 标签路由，设计 §3.3）。

两种节点寻址（互斥，execNodeTag 优先）：
- execNodeTag（I7 标签路由）：任务参数带执行节点标签 → t_ssh_node 中 enabled+online
  且含该标签的节点按轮转起点排序逐个尝试；连接失败/不可达 → 转派下一节点（日志留痕）；
  全部不可达 → failure。远端脚本执行失败（退出码≠0）不转派（避免重复执行副作用）。
- runtimeNode（原有）：param.runtimeNode（名称）→ t_runtime_node；纯数字兜底按 id

认证（两表一致）：cred "-----BEGIN" 开头按私钥内容（RSA/Ed25519/ECDSA 依次尝试），
否则按密码明文；空凭证无认证连接。
执行：远端 `cd {runtime_dir} && bash -s 2>&1`（t_ssh_node 无运行时目录则直接 bash），
脚本经 stdin 下发；stdout 逐行实时日志；1s 周期检查 kill → 关闭通道中断。
"""

import io
import time

try:
    import paramiko
except ImportError:  # 依赖缺失不阻断 worker 进程，执行时按 failure 留痕
    paramiko = None

from worker.executor import ExecResult, register
from worker.executors._proc import parse_kv_outputs
from worker.state import FAILURE, KILL, SUCCESS

KILL_POLL_SEC = 1.0
CONNECT_TIMEOUT = 10

# 标签轮转起点（worker 进程内 {tag: 下一起点}；消费循环单线程调用，无并发竞争）
_rr_start: dict = {}


def _load_pkey(content: str):
    """私钥内容 → paramiko PKey（多算法依次尝试）。"""
    last = None
    for cls in (paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey):
        try:
            return cls.from_private_key(io.StringIO(content))
        except Exception as exc:  # noqa: BLE001 换下一算法
            last = exc
    raise ValueError("私钥解析失败: %r" % last)


def _lookup_node(ref):
    """按名称查 t_runtime_node，纯数字兜底按 id。"""
    from common.db import new_session
    from common.models import RuntimeNode

    session = new_session()
    try:
        node = session.query(RuntimeNode).filter(RuntimeNode.name == ref).first()
        if node is None and str(ref).isdigit():
            node = session.get(RuntimeNode, int(ref))
        return node
    finally:
        session.close()


def _route_by_tag(tag: str) -> list:
    """标签路由（I7 F53）：t_ssh_node enabled+online 且含标签的节点，轮转起点排序。"""
    from common.db import new_session
    from common.models import SshNode

    session = new_session()
    try:
        rows = (
            session.query(SshNode)
            .filter(SshNode.enabled.is_(True), SshNode.heartbeat_state == "online")
            .order_by(SshNode.id)
            .all()
        )
        matched = [r for r in rows if tag in (r.tags or [])]
    finally:
        session.close()
    if not matched:
        return []
    start = _rr_start.get(tag, 0) % len(matched)
    _rr_start[tag] = (start + 1) % len(matched)  # 下个任务从下一位起（多节点分摊）
    return matched[start:] + matched[:start]


def _connect(host: str, port, user: str, cred: str, ctx) -> "paramiko.SSHClient":
    """建立 SSH 连接（认证方式留日志）；失败抛异常（含原因）。"""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kwargs = {
        "hostname": host, "port": int(port or 22), "username": user or "root",
        "timeout": CONNECT_TIMEOUT, "banner_timeout": CONNECT_TIMEOUT,
        "auth_timeout": CONNECT_TIMEOUT,
    }
    cred = str(cred or "")
    if cred.startswith("-----BEGIN"):
        kwargs["pkey"] = _load_pkey(cred)
        ctx.log("[ssh] 认证方式: 私钥内容")
    elif cred:
        kwargs["password"] = cred
        ctx.log("[ssh] 认证方式: 密码")
    else:
        ctx.log("[ssh] 认证方式: 无（未配置凭证）")
    client.connect(**kwargs)
    return client


def _run_on_node(name: str, host, port, user, cred, rdir: str, script: str, ctx) -> tuple:
    """单节点连接+执行；返回 (phase, ExecResult)：phase='connect' 连接失败可转派，'exec' 已执行。"""
    if not host:
        return "connect", ExecResult(FAILURE, {}, ["[ssh] 节点未配置主机地址: %s" % name])
    ctx.log("[ssh] 节点: %s (%s:%s)" % (name, host, port or 22))
    try:
        client = _connect(host, port, user, cred, ctx)
    except Exception as exc:  # noqa: BLE001 连接失败 → 可转派
        ctx.log("[ssh] 连接失败: %r" % exc)
        return "connect", ExecResult(FAILURE, {}, [])

    killed = False
    code = -1
    out_parts = []
    try:
        # { ...; } 2>&1 分组：mkdir/cd 失败的 stderr 也并入 stdout（否则执行器读不到，退出码 1 零输出，09-18 实测）
        cmd = ("{{ mkdir -p '%s' && cd '%s' && bash -s; }} 2>&1" % (rdir, rdir)) if rdir else "bash -s 2>&1"
        _stdin, stdout, _stderr = client.exec_command(cmd)
        _stdin.write(script)
        _stdin.flush()
        _stdin.channel.shutdown_write()
        channel = stdout.channel
        while True:
            while channel.recv_ready():
                chunk = channel.recv(65536).decode("utf-8", errors="replace")
                out_parts.append(chunk)
                for line in chunk.splitlines():
                    ctx.log(line)
            if channel.exit_status_ready():
                break
            if ctx.killed():
                killed = True
                ctx.log("[ssh] 收到中断指令，关闭远程通道")
                channel.close()
                break
            time.sleep(KILL_POLL_SEC)
        # 排空通道残留输出
        while channel.recv_ready():
            chunk = channel.recv(65536).decode("utf-8", errors="replace")
            out_parts.append(chunk)
            for line in chunk.splitlines():
                ctx.log(line)
        if not killed:
            code = channel.recv_exit_status()
    except Exception as exc:  # noqa: BLE001 远端执行异常 → failure（不转派）
        ctx.log("[ssh] 执行异常: %r" % exc)
        return "exec", ExecResult(FAILURE, {}, [])
    finally:
        client.close()

    stdout_text = "".join(out_parts)
    if killed:
        return "exec", ExecResult(KILL, {}, [])
    if code != 0:
        ctx.log("[ssh] 远程退出码 %d → failure" % code)
        return "exec", ExecResult(FAILURE, parse_kv_outputs(stdout_text), [])
    ctx.log("[ssh] 远程退出码 0 → success")
    return "exec", ExecResult(SUCCESS, parse_kv_outputs(stdout_text), [])


@register("ssh")
def execute(ctx) -> ExecResult:
    """SSH 任务入口：execNodeTag 标签路由（转派留痕）或 runtimeNode 直连。"""
    if paramiko is None:
        return ExecResult(FAILURE, {}, ["[ssh] paramiko 未安装（requirements 缺失）"])
    param = ctx.param or {}
    script = str(param.get("script") or "")
    if not script.strip():
        return ExecResult(FAILURE, {}, ["[ssh] 脚本内容为空"])

    # I7 F53 标签路由：健康匹配 → 轮转 → 连接失败转派下一节点 → 全不可达走失败策略
    tag = str(param.get("execNodeTag") or "").strip()
    if tag:
        nodes = _route_by_tag(tag)
        if not nodes:
            ctx.log("[ssh] 标签 %r 无健康节点（enabled+online+含标签）→ failure" % tag)
            return ExecResult(FAILURE, {}, [])
        ctx.log("[ssh] 标签 %s 匹配 %d 个健康节点，轮转顺序: %s"
                % (tag, len(nodes), " → ".join(n.name for n in nodes)))
        for node in nodes:
            phase, result = _run_on_node(node.name, node.host, node.port, node.ssh_user,
                                         node.cred_enc or "", "", script, ctx)
            if phase == "connect" and result.state == FAILURE:
                ctx.log("[ssh] 节点 %s 不可达，转派下一节点" % node.name)
                continue
            return result  # 已进入执行（success/failure/kill）或全部尝试完
        ctx.log("[ssh] 标签 %s 全部节点不可达 → failure" % tag)
        return ExecResult(FAILURE, {}, [])

    # 原有 runtimeNode 寻址（t_runtime_node）
    ref = param.get("runtimeNode") or param.get("runtime_node_id")
    if not ref:
        return ExecResult(FAILURE, {}, ["[ssh] 未指定运行时节点（runtimeNode）或执行节点标签（execNodeTag）"])
    node = _lookup_node(ref)
    if node is None:
        return ExecResult(FAILURE, {}, ["[ssh] 运行时节点不存在: %s" % ref])
    _phase, result = _run_on_node(node.name, node.host, node.port, node.user,
                                  node.auth or "", str(node.runtime_dir or "").strip(), script, ctx)
    return result
