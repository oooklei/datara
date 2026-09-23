"""运行时节点 API（C14 表单下拉，设计 §12）：GET /runtime-nodes 只读列表。

注册/编辑 UI 归 I7（F53），本期仅读 t_runtime_node（含内置 seed『1.9宿主机』）。
I12 新增 GET /runtime-nodes/{node_id}/ls：SSH 注册目录浏览（SFTP 列目录，
C24 文件同步 dir-select 数据源，复用 common.sshprobe 凭据裁定）。
"""

import stat

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.auth import ApiError, get_current_user
from common.db import get_db
from common.models import RuntimeNode, User
from common.resp import fmt_dt, ok
from common.sshprobe import PROBE_TIMEOUT, load_pkey

router = APIRouter(prefix="/runtime-nodes", tags=["runtime-node"])


@router.get("")
def list_runtime_nodes(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """运行时节点列表（只读，SSH 节点 runtimeNode 字段下拉数据源）。"""
    rows = db.query(RuntimeNode).order_by(RuntimeNode.id).all()
    return ok([
        {
            "id": row.id,
            "name": row.name,
            "kind": row.kind,
            "host": row.host,
            "port": row.port,
            "user": row.user,
            "runtimeDir": row.runtime_dir,
            "status": row.status,
            "lastHeartbeat": fmt_dt(row.last_heartbeat),
        }
        for row in rows
    ])


LS_MAX_ENTRIES = 500  # 目录浏览单次返回上限（防止大目录拖垮响应）


def _open_sftp(node: RuntimeNode):
    """SSH 建连并打开 SFTP（凭据裁定复用 common.sshprobe：-----BEGIN→私钥多算法，否则密码明文）。

    返回 (client, sftp)；失败抛异常（含原因），调用方负责关闭 client。
    """
    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        kwargs = {
            "hostname": node.host, "port": int(node.port or 22),
            "username": node.user or "root",
            "timeout": PROBE_TIMEOUT, "banner_timeout": PROBE_TIMEOUT,
            "auth_timeout": PROBE_TIMEOUT,
        }
        cred = str(node.auth or "")
        if cred.startswith("-----BEGIN"):
            kwargs["pkey"] = load_pkey(cred)
        elif cred:
            kwargs["password"] = cred
        client.connect(**kwargs)
        return client, client.open_sftp()
    except Exception:
        client.close()
        raise


@router.get("/{node_id}/ls")
def ls_runtime_node_dir(
    node_id: int,
    path: str = "",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """SSH 注册目录浏览（I12 C24 文件同步 dir-select 数据源）：SFTP 列目录。

    path 缺省为节点 runtime_dir（也为空则用根目录 /），缺省值按 SFTP 家目录语义由远端解析、
    不做绝对路径校验；显式传入的 path 必须以 / 开头。目录在前、名称次之，截断 LS_MAX_ENTRIES 条。
    """
    node = db.get(RuntimeNode, node_id)
    if node is None:
        raise ApiError(4101, "运行时节点不存在", status=404)
    if not str(node.host or "").strip():
        raise ApiError(4002, "节点未配置主机地址", status=400)
    explicit = str(path or "").strip()
    if explicit and not explicit.startswith("/"):
        raise ApiError(4002, "路径必须为绝对路径", status=400)
    base = explicit or str(node.runtime_dir or "").strip() or "/"
    base = base.rstrip("/") or "/"

    try:
        client, sftp = _open_sftp(node)
        try:
            attrs = sftp.listdir_attr(base)
        finally:
            client.close()
    except FileNotFoundError as exc:
        raise ApiError(4002, "路径不存在: %s（%s）" % (base, exc), status=400)
    except Exception as exc:  # noqa: BLE001 连接/认证/列目录失败统一 502
        raise ApiError(5002, "SSH 目录浏览失败: %s" % exc, status=502)

    entries = sorted(
        attrs,
        key=lambda e: (0 if stat.S_ISDIR(e.st_mode or 0) else 1, e.filename),
    )[:LS_MAX_ENTRIES]
    return ok({
        "path": base,
        "entries": [
            {
                "name": e.filename,
                "dir": stat.S_ISDIR(e.st_mode or 0),
                "size": e.st_size,
                "mtime": int(e.st_mtime or 0),
            }
            for e in entries
        ],
    })
