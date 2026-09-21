#!/usr/bin/env python
"""I9 API 冒烟（F57 门6）：冒烟链路（命令消费）+ 注册中心 + real 通道探活。

在 datara-worker 容器内运行：python /tmp/i9_smoke.py
检查项：
  1) login → token
  2) POST /smoke/run → t_command 由 master 消费（state 离开 wait）
  3) GET /registry/nodes → ZK 可用且 live 节点 >=1
  4) real 通道探活：/datasources /workflow-definitions /stream-jobs
"""
import json
import time

import requests

API = "http://datara-api:8000/api/v1"
TOKEN = ""


def _api(method, path, body=None):
    r = requests.request(method, API + path, json=body, headers={"token": TOKEN}, timeout=15)
    d = r.json()
    if d.get("code") != 0:
        raise SystemExit(f"API {method} {path} 失败: {d}")
    return d["data"]


def main():
    global TOKEN
    checks = {}
    TOKEN = _api("POST", "/login", {"user_name": "admin", "user_pwd": "Admin@123"})["token"]
    checks["login"] = "PASS"

    # ① 冒烟链路：提交 START_PROCESS_SMOKE → master 2s 轮询消费
    cid = _api("POST", "/smoke/run", {"name": "i9-smoke", "delaySec": 1})["commandId"]
    from common.db import new_session
    from common.models import Command
    state, delay_sec = "wait", 40
    dl = time.time() + delay_sec
    while time.time() < dl:
        s = new_session()
        try:
            row = s.query(Command).filter(Command.id == cid).first()
            state = row.state if row else "(missing)"
        finally:
            s.close()
        if state != "wait":
            break
        time.sleep(2)
    checks["smoke_command"] = "PASS" if state not in ("wait", "failed", "error") else f"FAIL(state={state})"
    print(f"[smoke] commandId={cid} 终态={state}")

    # ② 注册中心（ZK live 节点）
    reg = _api("GET", "/registry/nodes")
    nodes = reg.get("nodes") or []
    checks["registry"] = "PASS" if reg.get("zkAvailable") and len(nodes) >= 1 else \
        f"FAIL(zkAvailable={reg.get('zkAvailable')},nodes={len(nodes)})"
    print(f"[smoke] zkAvailable={reg.get('zkAvailable')} nodes={[n.get('name') if isinstance(n, dict) else n for n in nodes][:6]}")

    # ③ real 通道探活（F56d 已接真页面背后的 API）
    for name, path in [("datasources", "/datasources?page_no=1&page_size=10"),
                       ("wf_definitions", "/workflow-definitions?page_no=1&page_size=10"),
                       ("stream_jobs", "/stream-jobs?page_size=10")]:
        try:
            _api("GET", path)
            checks[f"api_{name}"] = "PASS"
        except SystemExit as e:
            checks[f"api_{name}"] = f"FAIL({str(e)[:100]})"

    print("[smoke] VERDICT " + json.dumps(checks, ensure_ascii=False))
    raise SystemExit(0 if all(v == "PASS" for v in checks.values()) else 1)


if __name__ == "__main__":
    main()
