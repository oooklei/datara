# -*- coding: utf-8 -*-
"""Datara supervision duty watchdog (infinite loop, runs until QUIT).

Duties while looping:
1. Poll git every POLL_SEC seconds; track last commit time of the whole repo.
2. If repo-wide silence exceeds SILENCE_ALERT_MIN minutes -> append a duty-alert
   heartbeat to the handoff file and commit (deduped by ALERT_DEDUP_MIN).
3. Accept commands from tools/watchdog_cmd.txt (one line, consumed each poll):
   STATUS | ALERT_NOW | QUIT
Console prints one ASCII status line per poll so the user can see it is alive.

Red lines: never touches datara-backend/ or datara-web/; never pushes; appends
only mechanically formatted heartbeat blocks (no semantic authoring).
"""
import json
import os
import re
import subprocess
import time
from datetime import datetime, timedelta

REPO = r"d:\需求\数据治理工具\Datara"
HANDOFF = os.path.join(REPO, "docs", "handoff", "2026-10-16-并行协作分工.md")
CMD_FILE = os.path.join(REPO, "tools", "watchdog_cmd.txt")
STATE_FILE = os.path.join(REPO, "tools", "watchdog_state.json")

POLL_SEC = 60
SILENCE_ALERT_MIN = 20
ALERT_DEDUP_MIN = 30


def log(msg):
    print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg), flush=True)


def git(args):
    return subprocess.run(
        ["git", "-C", REPO] + args,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"last_alert_iso": None}


def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception as e:
        log("state save failed: %r" % e)


def max_heartbeat_no(text):
    nums = [int(m) for m in re.findall(r"心跳\s*#(\d+)", text)]
    return max(nums) if nums else 0


def append_alert(reason):
    """Append a mechanical duty-alert heartbeat and commit. Returns commit hash or None."""
    if not os.path.exists(HANDOFF):
        log("handoff missing, skip alert")
        return None
    with open(HANDOFF, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    no = max_heartbeat_no(text) + 1
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    block = (
        "\n\n### 值守告警（程序 watchdog）— 心跳 #%d\n\n"
        "- 触发时间：%s\n- 判定：%s\n"
        "- 性质：程序化哨兵告警（机械留痕，无语义裁定）；请任一在线会话按「谁活着谁值岗」"
        "协议（心跳 #165）核实并处置；事实以 git log 实锚为准。\n"
        "- 写窗：pathspec 单文件；程序零业务触碰；无远端 push。\n"
        "- Resolved：告警落账，等待响应。\n" % (no, now, reason)
    )
    with open(HANDOFF, "a", encoding="utf-8", newline="\n") as f:
        f.write(block)
    git(["add", "--", os.path.relpath(HANDOFF, REPO)])
    c = git(["commit", "-m",
             "handoff: watchdog duty alert heartbeat #%d (%s)" % (no, reason),
             "--", os.path.relpath(HANDOFF, REPO)])
    if c.returncode != 0:
        log("alert commit failed: %s" % (c.stderr or "").strip()[:200])
        return None
    out = (c.stdout or "").strip().splitlines()
    for line in out:
        m = re.search(r"\[main\s+(\w+)\]", line)
        if m:
            log("alert committed #%d -> %s" % (no, m.group(1)))
            return m.group(1)
    log("alert committed #%d" % no)
    return "ok"


def repo_last_commit():
    r = git(["log", "-1", "--format=%h|%ad|%s", "--date=iso"])
    if r.returncode != 0 or not r.stdout.strip():
        return None
    h, ad, subject = r.stdout.strip().split("|", 2)
    try:
        dt = datetime.fromisoformat(ad)
    except Exception:
        return None
    return {"hash": h, "time": dt, "subject": subject}


def handle_cmd(state):
    try:
        with open(CMD_FILE, "r", encoding="utf-8") as f:
            cmd = f.read().strip()
    except Exception:
        return state
    if not cmd:
        return state
    log("CMD received: %s" % cmd)
    try:
        os.remove(CMD_FILE)
    except Exception:
        pass
    if cmd.upper().startswith("QUIT"):
        save_state(state)
        log("QUIT -> exiting watchdog loop")
        raise SystemExit(0)
    if cmd.upper().startswith("STATUS"):
        log("STATUS: last_alert=%s" % state.get("last_alert_iso"))
        return state
    if cmd.upper().startswith("ALERT_NOW"):
        append_alert("manual ALERT_NOW via watchdog_cmd.txt")
        state["last_alert_iso"] = datetime.now().isoformat(timespec="seconds")
        return state
    return state


def main():
    log("watchdog started: poll=%ds silence_alert=%dmin dedup=%dmin" %
        (POLL_SEC, SILENCE_ALERT_MIN, ALERT_DEDUP_MIN))
    state = load_state()
    while True:
        try:
            state = handle_cmd(state)
            last = repo_last_commit()
            if last is None:
                log("WARN: cannot read last commit")
            else:
                silent_min = (datetime.now(last["time"].tzinfo) - last["time"]).total_seconds() / 60.0
                log("alive. last=%s %s (+%0.1fmin) %s" %
                    (last["hash"], last["time"].strftime("%H:%M"), silent_min, last["subject"][:60]))
                last_alert = state.get("last_alert_iso")
                last_alert_dt = datetime.fromisoformat(last_alert) if last_alert else None
                need_alert = silent_min >= SILENCE_ALERT_MIN and (
                    last_alert_dt is None
                    or (datetime.now() - last_alert_dt).total_seconds() / 60.0 >= ALERT_DEDUP_MIN
                )
                if need_alert:
                    reason = "全库静默 %.0f 分钟（最后提交 %s %s），无任何线产出或告警响应" % (
                        silent_min, last["time"].strftime("%H:%M"), last["hash"])
                    append_alert(reason)
                    state["last_alert_iso"] = datetime.now().isoformat(timespec="seconds")
                    save_state(state)
        except SystemExit:
            raise
        except Exception as e:
            log("loop error (continue): %r" % e)
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
