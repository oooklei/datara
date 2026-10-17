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
import urllib.request
from datetime import datetime, timedelta

REPO = r"d:\需求\数据治理工具\Datara"
HANDOFF = os.path.join(REPO, "docs", "handoff", "2026-10-16-并行协作分工.md")
CMD_FILE = os.path.join(REPO, "tools", "watchdog_cmd.txt")
STATE_FILE = os.path.join(REPO, "tools", "watchdog_state.json")

POLL_SEC = 10
SILENCE_ALERT_MIN = 8
ALERT_DEDUP_MIN = 12
SCAN_EVERY_N_POLLS = 6          # 60s 一次 handoff 尾部扫描
NOTIFY_KEYWORDS = ("请裁", "待裁定", "待监督线", "申请复验", "待评审", "待派单", "待确认")
NOTIFY_DEDUP_MIN = 30
ENV_FILE = os.path.join(REPO, "datara-backend", ".env")
SUMMARY_FILE = os.path.join(REPO, "tools", "watchdog_summary.txt")

# v3: per-line silence detection (a single silent line must not be masked by
# other lines' activity) + dispatch->claim closed-loop check.
LINE_SILENCE_MIN = 3
LINE_NOTIFY_DEDUP_MIN = 30

# v4: auto-wake engine — inject the built-in wakeup text into a silent line's
# CLI session. AUTO_WAKE_DRY_RUN=False = real injection enabled (user-approved
# 2026-10-18 after dry-run observation; codex exec confirmed unattended-capable).
# Lines without a template fall back to popup + manual wakeup. Deduped per line.
AUTO_WAKE_DRY_RUN = False
AUTO_WAKE_DEDUP_MIN = 30
WAKE_CMD_TEMPLATES = {
    # Official desktop CLI (0.162.x, gpt-6-luna capable). The PATH codex.exe is
    # a CodeBuddy-bundled 0.146 build that 400s on ChatGPT accounts.
    "Codex": [r"C:\Users\Administrator\AppData\Local\OpenAI\Codex\bin\2e5e00daee91c61d\codex.exe",
              "exec", "{wakeup}"],
    "Trae": None,       # deprecated line
    "Claude": ["claude", "-p", "{wakeup}", "--continue"],  # user-approved 2026-10-18 (CLI 2.1.276 verified)
    "监督线": None,      # user-driven session
    "守护线": None,      # no unattended CLI confirmed
}
# subject 中最早出现的标识决定归线（防监督 subject 提及 Trae/Codex 时误归线）。
LINE_KEYS = (("AOCI守护", "守护线"), ("监督", "监督线"), ("Trae", "Trae"), ("Claude", "Claude"), ("Codex", "Codex"))
DISPATCH_RE = re.compile(r"派单[^。\n]*→\s*(Trae|Codex)")
CLAIM_RE = r"###\s*[^\n]{0,100}%s[^\n]{0,100}(领单|接单|回执|交付)"
WAKEUP_TEXTS = {
    "Trae": ("【监督线唤醒令 · Trae 实施线】立即执行：① cd d:\\需求\\数据治理工具\\Datara && git pull --ff-only；"
             "② git log --oneline -15 核对最新心跳号；③ 读 docs/handoff/2026-10-16-并行协作分工.md 尾部 60 行，"
             "认领你名下未竟派单/回执/修订，即领即做；④ 常驻值守铁律（#158/#165）：无任务落静默标记心跳、"
             "存活以 git 产出为准、30 分钟内必须回执；⑤ pathspec 单文件、零业务触碰、禁 aoci_*、禁 push。现在开始。"),
    "Codex": ("【监督线唤醒令 · Codex 实施线】立即执行：① cd d:\\需求\\数据治理工具\\Datara && git pull --ff-only；"
              "② git log --oneline -15 核对最新心跳号；③ 读 docs/handoff/2026-10-16-并行协作分工.md 尾部 60 行，"
              "认领你名下未竟派单/回执/评审，即领即做；④ 常驻值守铁律（#158/#165）：无任务落静默标记心跳、"
              "存活以 git 产出为准、30 分钟内必须回执；⑤ pathspec 单文件、零业务触碰、禁 aoci_*、禁 push。现在开始。"),
    "Claude": ("【监督线唤醒令 · Claude 实施线】立即执行：① cd d:\\需求\\数据治理工具\\Datara && git pull --ff-only；"
               "② git log --oneline -15 核对最新心跳号；③ 读 docs/handoff/2026-10-16-并行协作分工.md 尾部 60 行，"
               "认领你名下未竟派单/回执/修订，即领即做；④ 留守循环条款（#204/#210）：无任务落静默标记心跳"
               "（待命状态+轮询锚点+无活时动作），存活以 git 产出为准、30 分钟内必须回执；"
               "⑤ pathspec 单文件、零业务触碰、禁 aoci_*、禁 push。现在开始。"),
}


def notify_popup(text):
    """Windows popup: try msg.exe, fallback to async PowerShell MessageBox."""
    try:
        r = subprocess.run(["msg", "*", text], capture_output=True, timeout=10)
        if r.returncode == 0:
            return "msg"
    except Exception:
        pass
    try:
        esc = text.replace("'", "''")
        subprocess.Popen(
            ["powershell", "-NoProfile", "-Command",
             "Add-Type -AssemblyName System.Windows.Forms;"
             "[System.Windows.Forms.MessageBox]::Show('%s','Datara Duty Watchdog')" % esc],
            creationflags=0x00000008)
        return "powershell"
    except Exception as e:
        log("notify failed: %r" % e)
        return None


def load_llm_env():
    cfg = {}
    try:
        with open(ENV_FILE, "r", encoding="utf-8-sig", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    if k in ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY"):
                        cfg[k] = v.strip()
    except Exception:
        return {}
    return cfg if cfg.get("LLM_API_KEY") and cfg.get("LLM_BASE_URL") else {}


def llm_summary(tail_text):
    """Advisory digest only (never a ruling). Best-effort, silent on failure."""
    cfg = load_llm_env()
    if not cfg:
        return None
    prompt = (
        "你是 Datara 项目监督值守程序的摘要器。以下是协作台账最新心跳片段。"
        "只输出 6 行以内中文摘要：1) 各线最新动作一行一条；2) 明确列出待裁定/待评审/待派单事项及其归属；"
        "3) 结尾一行写「摘要仅供参考，裁定权在监督会话」。不要给任何裁定结论。\n\n" + tail_text[-4000:])
    body = json.dumps({
        "model": cfg.get("LLM_MODEL", ""),
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 400, "temperature": 0.1,
    }).encode("utf-8")
    req = urllib.request.Request(
        cfg["LLM_BASE_URL"].rstrip("/") + "/chat/completions", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + cfg["LLM_API_KEY"]})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log("llm summary failed: %r" % e)
        return None


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


def scan_and_notify(state):
    """60s cadence: scan handoff tail for pending-ruling/review keywords; popup-notify
    the user + write LLM advisory digest. Dedup per heartbeat number and time."""
    try:
        with open(HANDOFF, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        tail = text[-6000:]
        no = max_heartbeat_no(text)
        last_no = state.get("last_notified_no") or 0
        if no <= last_no:
            return
        hits = [k for k in NOTIFY_KEYWORDS if k in tail]
        if not hits:
            state["last_notified_no"] = no
            return
        last_dt = state.get("last_notify_iso")
        if last_dt and (datetime.now() - datetime.fromisoformat(last_dt)).total_seconds() / 60.0 < NOTIFY_DEDUP_MIN:
            return
        summary = llm_summary(tail)
        if summary:
            try:
                with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
                    f.write("[%s] heartbeat #%d\n%s\n" % (
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"), no, summary))
            except Exception:
                pass
        popup = ("Datara 监督提醒：台账心跳 #%d 含待办事项（%s），请在 Trae 监督会话发送「继续」唤醒监督线处理。"
                 % (no, "/".join(hits[:3])))
        how = notify_popup(popup)
        log("notify #%d via %s keywords=%s summary=%s" % (
            no, how, ",".join(hits[:3]), "yes" if summary else "no"))
        state["last_notified_no"] = no
        state["last_notify_iso"] = datetime.now().isoformat(timespec="seconds")
    except SystemExit:
        raise
    except Exception as e:
        log("scan error: %r" % e)


def line_of_subject(subject):
    best, best_pos = None, len(subject)
    for key, name in LINE_KEYS:
        p = subject.find(key)
        if p >= 0 and p < best_pos:
            best, best_pos = name, p
    return best


def line_last_commits(limit=60):
    """Map line name -> its most recent commit (subject-anchored attribution)."""
    r = git(["log", "-%d" % limit, "--format=%h|%ad|%s", "--date=iso"])
    out = {}
    if r.returncode != 0:
        return out
    for ln in r.stdout.strip().splitlines():
        try:
            h, ad, subject = ln.split("|", 2)
            dt = datetime.fromisoformat(ad)
        except ValueError:
            continue
        name = line_of_subject(subject)
        if name and name not in out:
            out[name] = {"hash": h, "time": dt, "subject": subject}
    return out


def auto_wake(state, name, silent_min):
    """v4: inject the built-in wakeup text into a silent line's CLI session.
    DRY_RUN logs the would-be command only. Returns True if handled."""
    cmd = WAKE_CMD_TEMPLATES.get(name)
    if not cmd or name not in WAKEUP_TEXTS:
        return False
    aw = state.setdefault("auto_wake", {})
    last_iso = aw.get(name)
    if last_iso and (datetime.now() - datetime.fromisoformat(last_iso)).total_seconds() / 60.0 < AUTO_WAKE_DEDUP_MIN:
        return True  # deduped: already handled within window
    full_cmd = [c.replace("{wakeup}", WAKEUP_TEXTS[name]) if "{wakeup}" in c else c for c in cmd]
    if AUTO_WAKE_DRY_RUN:
        log("auto-wake DRY-RUN %s silent=%.0fmin would inject via: %s" % (name, silent_min, full_cmd[0]))
    else:
        try:
            subprocess.Popen(full_cmd, cwd=REPO, creationflags=0x00000008)
            log("auto-wake INJECTED %s (silent %.0fmin) via %s" % (name, silent_min, full_cmd[0]))
        except Exception as e:
            log("auto-wake %s inject failed (fall back to manual): %r" % (name, e))
            return False
    aw[name] = datetime.now().isoformat(timespec="seconds")
    return True


def check_line_silence(state):
    """Per-line silence: popup (not heartbeat) so one silent line cannot be
    masked by other lines still committing. Deduped per line."""
    per_line = line_last_commits()
    notified = state.setdefault("line_notify", {})
    for name in ("Trae", "Codex", "Claude", "监督线", "守护线"):
        info = per_line.get(name)
        if not info:
            continue
        t = info["time"]
        silent_min = (datetime.now(t.tzinfo) - t).total_seconds() / 60.0
        if silent_min < LINE_SILENCE_MIN:
            continue
        last_iso = notified.get(name)
        if last_iso and (datetime.now() - datetime.fromisoformat(last_iso)).total_seconds() / 60.0 < LINE_NOTIFY_DEDUP_MIN:
            continue
        if name in WAKEUP_TEXTS:
            try:
                with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
                    f.write("[%s] %s 静默 %.0f 分钟\n\n%s\n" % (
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"), name,
                        silent_min, WAKEUP_TEXTS[name]))
            except Exception:
                pass
            popup = ("Datara 值守提醒：%s 最后产出 %s（%s），已静默 %.0f 分钟，疑似掉线。"
                     "请将 tools/watchdog_summary.txt 中的唤醒令转发给该线。"
                     % (name, t.strftime("%H:%M"), info["hash"], silent_min))
        else:
            popup = ("Datara 值守提醒：%s 已静默 %.0f 分钟（最后产出 %s）。"
                     "请在监督会话发送「继续」唤醒监督线。"
                     % (name, silent_min, t.strftime("%H:%M")))
        how = notify_popup(popup)
        woke = auto_wake(state, name, silent_min)
        log("line-silence notify %s %.0fmin via %s auto-wake=%s" % (
            name, silent_min, how,
            ("dry-run" if AUTO_WAKE_DRY_RUN else "injected") if woke else "n/a"))
        notified[name] = datetime.now().isoformat(timespec="seconds")
        save_state(state)


def check_unclaimed_dispatch(state):
    """Dispatch->claim closed loop: any 派单→X in the handoff tail without a
    later X claim/receipt heading means the dispatch may be unclaimed."""
    try:
        with open(HANDOFF, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception:
        return
    tail = text[-20000:]
    pending = set()
    for m in DISPATCH_RE.finditer(tail):
        line_name = m.group(1)
        if not re.search(CLAIM_RE % line_name, tail[m.end():]):
            pending.add(line_name)
    key = ",".join(sorted(pending))
    if not pending:
        if state.get("unclaimed_dispatch"):
            state["unclaimed_dispatch"] = None
            save_state(state)
        return
    last_iso = state.get("unclaimed_notify_iso")
    if state.get("unclaimed_dispatch") == key and last_iso and (
            datetime.now() - datetime.fromisoformat(last_iso)).total_seconds() / 60.0 < LINE_NOTIFY_DEDUP_MIN:
        return
    wakeup = WAKEUP_TEXTS.get(sorted(pending)[0], "")
    try:
        with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
            f.write("[%s] 疑似未领派单（→ %s）\n\n%s\n" % (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"), key, wakeup))
    except Exception:
        pass
    popup = ("Datara 值守提醒：台账存在疑似未领派单（→ %s）。请核实该线状态；"
             "唤醒令已写入 tools/watchdog_summary.txt，可直接转发。" % key)
    how = notify_popup(popup)
    log("unclaimed dispatch notify (%s) via %s" % (key, how))
    state["unclaimed_dispatch"] = key
    state["unclaimed_notify_iso"] = datetime.now().isoformat(timespec="seconds")
    save_state(state)


def main():
    log("watchdog v4 started: poll=%ds silence_alert=%dmin dedup=%dmin auto_wake=%s summary=advisory" %
        (POLL_SEC, SILENCE_ALERT_MIN, ALERT_DEDUP_MIN,
         "DRY-RUN(observation)" if AUTO_WAKE_DRY_RUN else "INJECT-ENABLED"))
    state = load_state()
    if "last_notified_no" not in state:
        try:
            with open(HANDOFF, "r", encoding="utf-8", errors="replace") as f:
                state["last_notified_no"] = max_heartbeat_no(f.read())
        except Exception:
            state["last_notified_no"] = 0
    poll_count = 0
    while True:
        try:
            state = handle_cmd(state)
            with open(os.path.join(REPO, "tools", "watchdog_alive.txt"), "w", encoding="utf-8") as f:
                f.write("alive %s pid=%s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), os.getpid()))
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
            poll_count += 1
            if poll_count % SCAN_EVERY_N_POLLS == 0:
                before = json.dumps(state, sort_keys=True)
                scan_and_notify(state)
                check_line_silence(state)
                check_unclaimed_dispatch(state)
                if json.dumps(state, sort_keys=True) != before:
                    save_state(state)
        except SystemExit:
            raise
        except Exception as e:
            log("loop error (continue): %r" % e)
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
