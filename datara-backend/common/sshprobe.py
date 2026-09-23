"""SSH echo ok 探活（I7 F53 共用件）：api 手动探活与 master 探活线程同一实现。

- 认证：cred "-----BEGIN" 开头按私钥内容（RSA/Ed25519/ECDSA 依次尝试），否则按密码明文
- 返回 (ok, message)：ok=远端输出恰为 "ok"；message=成功描述或失败原因
- paramiko 缺失不抛异常（返回失败消息，不阻断调用方流程）
"""

import io

PROBE_TIMEOUT = 3  # 连接与命令超时（秒）


def _load_pkey(content: str):
    """私钥内容 → paramiko PKey（多算法依次尝试）。"""
    import paramiko

    last = None
    for cls in (paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey):
        try:
            return cls.from_private_key(io.StringIO(content))
        except Exception as exc:  # noqa: BLE001 换下一算法
            last = exc
    raise ValueError("私钥解析失败: %r" % last)


# 公开别名（I12 T12）：api/runtime_node.py 等外部模块经 load_pkey 复用，_load_pkey 保留内部名
load_pkey = _load_pkey


def probe(host: str, port: int, user: str, cred: str) -> tuple:
    """SSH 执行 `echo ok` 探活。"""
    try:
        import paramiko
    except ImportError:
        return False, "paramiko 未安装"
    if not str(host or "").strip():
        return False, "主机地址为空"

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        kwargs = {
            "hostname": host, "port": int(port or 22), "username": user or "root",
            "timeout": PROBE_TIMEOUT, "banner_timeout": PROBE_TIMEOUT, "auth_timeout": PROBE_TIMEOUT,
        }
        cred = str(cred or "")
        if cred.startswith("-----BEGIN"):
            kwargs["pkey"] = _load_pkey(cred)
        elif cred:
            kwargs["password"] = cred
        client.connect(**kwargs)
        _stdin, stdout, _stderr = client.exec_command("echo ok", timeout=PROBE_TIMEOUT)
        out = (stdout.read() or b"").decode("utf-8", errors="replace").strip()
        return (out == "ok", "echo 校验%s（输出 %r）" % ("通过" if out == "ok" else "异常", out))
    except Exception as exc:  # noqa: BLE001 连接失败统一返回消息
        return False, str(exc)
    finally:
        client.close()
