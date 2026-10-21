"""Immediate SSH echo probe used by the rebuild registry.

R-35 makes Paramiko a required increment-17 dependency. Host-key verification
still uses the legacy AutoAddPolicy and is recorded as security debt; changing
that behavior requires a separately frozen known-hosts contract.
"""

from __future__ import annotations

import io

import paramiko

PROBE_TIMEOUT_SECONDS = 3


def _private_key(content: str):
    last_error: Exception | None = None
    for key_type in (paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey):
        try:
            return key_type.from_private_key(io.StringIO(content))
        except Exception as exc:  # pragma: no cover - algorithm fallback
            last_error = exc
    raise ValueError("private key parse failed") from last_error


def probe(host: str, port: int, user: str, cred: str) -> tuple[bool, str]:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        options = {
            "hostname": host,
            "port": port,
            "username": user,
            "timeout": PROBE_TIMEOUT_SECONDS,
            "banner_timeout": PROBE_TIMEOUT_SECONDS,
            "auth_timeout": PROBE_TIMEOUT_SECONDS,
        }
        if cred.startswith("-----BEGIN"):
            options["pkey"] = _private_key(cred)
        elif cred:
            options["password"] = cred
        client.connect(**options)
        _stdin, stdout, _stderr = client.exec_command("echo ok", timeout=PROBE_TIMEOUT_SECONDS)
        output = (stdout.read() or b"").decode("utf-8", errors="replace").strip()
        return output == "ok", "echo check passed" if output == "ok" else f"unexpected output: {output!r}"
    except Exception as exc:  # Connection failures are part of the probe result.
        return False, str(exc)
    finally:
        client.close()
