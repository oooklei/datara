"""Upload and run an unsaved Python/Shell draft on a selected SSH node."""

from __future__ import annotations

import io
import time
import uuid
from typing import Any

import paramiko

from rebuild.sshnode.models import SshNodeRecord
from rebuild.sshnode.probe import _private_key


class SshTrialError(RuntimeError):
    pass


def run_ssh_trial(node: SshNodeRecord, kind: str, content: str, *, timeout_seconds: int = 30) -> dict[str, Any]:
    if kind not in {"python", "shell"}:
        raise ValueError("SSH trial supports Python and Shell only")
    timeout = min(max(timeout_seconds, 1), 30)
    directory = f"/tmp/datara-script-{uuid.uuid4().hex}"
    filename = "script.py" if kind == "python" else "script.sh"
    command = "python3 script.py" if kind == "python" else "/bin/sh script.sh"
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    started = time.monotonic()
    made_directory = False
    try:
        options: dict[str, Any] = {
            "hostname": node.host, "port": node.port, "username": node.ssh_user,
            "timeout": 5, "banner_timeout": 5, "auth_timeout": 5,
        }
        if node.cred.startswith("-----BEGIN"):
            options["pkey"] = _private_key(node.cred)
        elif node.cred:
            options["password"] = node.cred
        client.connect(**options)
        _stdin, stdout, stderr = client.exec_command(f"mkdir -m 700 {directory}", timeout=5)
        if stdout.channel.recv_exit_status() != 0:
            raise SshTrialError("remote temporary directory creation failed")
        made_directory = True
        sftp = client.open_sftp()
        try:
            sftp.putfo(io.BytesIO(content.encode("utf-8")), f"{directory}/{filename}")
        finally:
            sftp.close()
        _stdin, stdout, stderr = client.exec_command(f"cd {directory} && {command}", timeout=timeout)
        channel = stdout.channel
        out = bytearray()
        err = bytearray()
        deadline = time.monotonic() + timeout
        timed_out = False
        while True:
            if channel.recv_ready():
                out.extend(channel.recv(4096)[: max(0, 20000 - len(out))])
            if channel.recv_stderr_ready():
                err.extend(channel.recv_stderr(4096)[: max(0, 20000 - len(err))])
            if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                break
            if time.monotonic() >= deadline:
                timed_out = True
                channel.close()
                break
            time.sleep(0.02)
        return {
            "executed": True,
            "exitCode": -1 if timed_out else channel.recv_exit_status(),
            "timedOut": timed_out,
            "timeoutSeconds": timeout,
            "elapsedMs": round((time.monotonic() - started) * 1000),
            "stdout": out.decode("utf-8", errors="replace"),
            "stderr": err.decode("utf-8", errors="replace"),
        }
    except (OSError, paramiko.SSHException, EOFError) as exc:
        raise SshTrialError(f"SSH trial failed: {type(exc).__name__}") from None
    finally:
        if made_directory:
            try:
                client.exec_command(f"rm -rf -- {directory}", timeout=5)
            except Exception:
                pass
        client.close()
