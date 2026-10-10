#!/usr/bin/env python3
"""同步编排重构 1.9 实测驱动：登录 → 触发 3 用例 → 轮询实例终态 → 打印任务明细与 outputs。
在 datara-master 容器内运行（网络直达 datara-api:8000）。"""

import json
import time
import urllib.request

BASE = "http://datara-api:8000/api/v1"
WFS = ["wf_orch_src_base", "wf_orch_tgt_base", "wf_orch_file_sync"]
# 活动态前缀（小写）：命中则继续轮询；其余视为终态
ACTIVE_PREFIX = ("running", "submitted", "ready", "wait", "delay", "dispatch", "start", "prepare")


def resolve_wf_codes(token):
    """用例数字 code 动态解析（seed 重建按 max(code)+1 递增，code 会漂移，勿硬编码）。"""
    rows = call("GET", "/workflow-definitions?page_no=1&page_size=100", token=token)["list"]
    by_id = {str(r.get("id") or ""): r.get("code") for r in rows}
    codes = {int(by_id[w]) for w in WFS if w in by_id}
    if len(codes) != len(WFS):
        raise RuntimeError("workflow-definitions 缺用例: %s（现有 %s）" % (WFS, sorted(by_id)))
    return codes


def call(method, path, body=None, token=None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("token", token)
    data = json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(req, data, timeout=30) as r:
        resp = json.loads(r.read().decode())
    if resp.get("code") not in (0, None):
        raise RuntimeError("%s -> %s" % (path, resp))
    return resp.get("data")


def main():
    global WF_CODES
    token = call("POST", "/login", {"user_name": "admin", "user_pwd": "Admin@123"})["token"]
    print("[1] login OK")
    WF_CODES = resolve_wf_codes(token)
    print("[1a] 用例 code 解析: %s" % sorted(WF_CODES))
    # 触发前既有实例快照（历史遗留同 code 实例，轮询与终态判定一律忽略）
    pre = {
        str(r["instanceId"])
        for r in call("GET", "/instances?page_no=1&page_size=50", token=token)["list"]
        if r.get("wfCode") in WF_CODES
    }
    print("[1b] 触发前既有实例 %d 个（忽略）" % len(pre))
    for wf in WFS:
        d = call("POST", "/workflow-definitions/%s/run" % wf, {}, token)
        print("[2] %s run commandId=%s" % (wf, d.get("commandId")))

    final = {}
    deadline = time.time() + 480
    while time.time() < deadline:
        rows = call("GET", "/instances?page_no=1&page_size=50", token=token)["list"]
        mine = [r for r in rows if r.get("wfCode") in WF_CODES and str(r["instanceId"]) not in pre]
        states = {}
        for r in sorted(mine, key=lambda x: str(x["instanceId"]), reverse=True):
            states.setdefault(r["wfCode"], (r["instanceId"], str(r.get("state"))))
        active = [s for s in states.values() if s[1].lower().startswith(ACTIVE_PREFIX)]
        print("[poll] %s active=%d" % (states, len(active)))
        if states and not active and len(states) == 3:
            final = states
            break
        time.sleep(6)
    if not final:
        print("[FAIL] 轮询超时（480s），实例未全部到终态")
        return 1

    print("[3] 实例任务明细：")
    bad = 0
    for wf_code, (iid, state) in sorted(final.items()):
        d = call("GET", "/instances/%s" % iid, token=token)
        print("== wfCode=%s instance=%s state=%s ==" % (wf_code, iid, state))
        for t in d.get("taskInstances") or []:
            out = t.get("outputs") or {}
            keep = {
                k: v
                for k, v in out.items()
                if k
                in (
                    "rows_read",
                    "rows_written",
                    "rows_skipped",
                    "schemas_included",
                    "error",
                    "targetTable",
                    "filePath",
                    "rows",
                    "strategy",
                    "flagColumn",
                )
            }
            print(
                "  %-14s %-10s %-8s %s"
                % (
                    t.get("nodeType"),
                    t.get("name"),
                    t.get("state"),
                    json.dumps(keep, ensure_ascii=False) if keep else "",
                )
            )
            if t.get("state") not in ("success", "skipped", "skip"):
                bad += 1
                if t.get("logPath"):
                    print("    logPath=%s" % t["logPath"])
    print("[4] 非成功任务数：%d" % bad)
    return 0 if bad == 0 else 2


if __name__ == "__main__":
    sys_exit = main()
    raise SystemExit(sys_exit)
