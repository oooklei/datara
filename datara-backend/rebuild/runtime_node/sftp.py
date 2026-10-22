"""SFTP directory listing for rebuild runtime nodes (B6-2).

Faithful merge of api/runtime_node.py `_open_sftp` + `sftp.listdir_attr`:
credential adjudication reuses common.sshprobe (-----BEGIN prefix → private
key via load_pkey, otherwise plaintext password). Host-key policy stays
legacy AutoAddPolicy (R-35 security debt); the client is closed on every
exit path so FileNotFoundError / connection errors propagate to the service
layer for 4002/5002 classification.
"""

from __future__ import annotations

from common.sshprobe import PROBE_TIMEOUT, load_pkey


def list_dir(node, base: str):
    """SSH 建连并 SFTP 列目录，返回 listdir_attr 结果（错误分类归 service 层）。"""
    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        kwargs = {
            "hostname": node.host,
            "port": int(node.port or 22),
            "username": node.user or "root",
            "timeout": PROBE_TIMEOUT,
            "banner_timeout": PROBE_TIMEOUT,
            "auth_timeout": PROBE_TIMEOUT,
        }
        cred = str(node.auth or "")
        if cred.startswith("-----BEGIN"):
            kwargs["pkey"] = load_pkey(cred)
        elif cred:
            kwargs["password"] = cred
        client.connect(**kwargs)
        sftp = client.open_sftp()
        return sftp.listdir_attr(base)
    finally:
        client.close()
