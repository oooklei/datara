#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mailbox_loop.py — 信箱循环实体程序 v1.1 (Datara 多终端协同)

设计（对应监督员 2026-10-19 裁定）:
  while True:
    1. 从 handoff 信箱 + 台账心跳中提取"匹配本角色"的新记录（角色由监督员指定）
    2. 同轮全部 pending 消息合并为一次子智能体调用（P-OPT-2，省 token）
    3. 把子智能体的回复写回信箱（发给消息来源方），并 append 确认接收本次任务的回执
    4. sleep(3 秒)
  退出条件：收到 to=本角色 且 type=STOP 的消息（先确认回执、终止子智能体，再退出），
           或子智能体连续多轮启动失败（--max-fail）。

信道：
  信箱   docs/handoff/mailbox.jsonl   每行一条 JSON 消息（精确双向信道）
         {id, ts, from, to, type: MSG|STOP|ACK|REPLY, body, status: pending|done, ref, ack_ts}
  基线   docs/handoff/STATE.md   冷启动首读现状快照（新纪元唯一权威起点）
  台账   docs/handoff/2026-10-16-并行协作分工.md   历史考古区（冻结只读，辅助扫描）

用法：
  python agents/mailbox_loop.py --role 监督员 [--agent-cmd "claude -p {model}"] [--model deepseek-v4.1-flash] [--interval 3]
  各终端发消息：向 mailbox.jsonl append 一行 JSON；停止本循环：发 {"type":"STOP","to":"<role>"}。
"""
import argparse
import json
import os
import shlex
import subprocess
import time
import uuid
from datetime import datetime

# 回复引用化纪律（P-OPT-2：mailbox 消息 body 只允许结论+路径+提交号，禁贴全文）
CITATION_RULE = (
    "回复引用化纪律：只写结论（≤3行）+ 涉及文件路径 + 提交号；"
    "禁止粘贴大段原文/日志/代码全文，需要时只给路径与行号。"
)

# 角色提示词（子智能体的身份锚点；监督员可按需增改 ROLE_PROMPTS 或用 --role-prompt-file 覆盖）
DEFAULT_ROLE_PROMPT = (
    "你是 Datara 项目协作成员（角色：{role}）。先读 docs/handoff/STATE.md 对齐现状基线，"
    "裁定争议查 docs/increments/多终端多智能体项目管理标准规范-裁定索引.md，再处理下方消息。"
    "纪律：pathspec 单文件提交、领单+交付两次心跳、零业务越界、无 push、中文。"
)
ROLE_PROMPTS = {
    "监督员": (
        "你是 Datara 项目质量监督员（只做裁定/派单/验收/台账/协调，业务一律派单；"
        "AOCI 全权在你，唯一可调 aoci_* 工具者）。"
        "先读 docs/handoff/STATE.md 对齐现状基线，再处理下方消息。"
    ),
}


def now():
    return datetime.now().isoformat(timespec="seconds")


def log(repo, line):
    entry = f"{now()} {line}"
    print(entry, flush=True)
    try:
        with open(os.path.join(repo, "agents", "mailbox_loop.log"), "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except OSError:
        pass


def read_mail(path):
    msgs = []
    if not os.path.exists(path):
        return msgs
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    msgs.append(obj)
            except json.JSONDecodeError:
                continue  # 半写入行：跳过，下轮重读
    return msgs


def append_mail(path, msg):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(msg, ensure_ascii=False) + "\n")


def rewrite_mark_done(path, done_ids):
    """把已处理消息标 done 重写回文件（append-only 信道上唯一重写方=本循环，冲突窗口极小）。"""
    msgs = read_mail(path)
    out = []
    for m in msgs:
        if m.get("id") in done_ids and m.get("status") == "pending":
            m["status"] = "done"
            m["ack_ts"] = now()
        out.append(json.dumps(m, ensure_ascii=False))
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + ("\n" if out else ""))
    os.replace(tmp, path)


def scan_handoff(repo, role, last_anchor):
    """扫描台账与 handoff 目录：返回含本角色关键词的新行（心跳号或文件 mtime 做增量锚点）。"""
    keywords = ("派单", "唤醒", "回执", "裁定", "请答复", "待你", role)
    hits, anchor = [], last_anchor
    ledger = os.path.join(repo, "docs", "handoff", "2026-10-16-并行协作分工.md")
    try:
        with open(ledger, "r", encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
        for i, ln in enumerate(lines):
            if i + 1 <= last_anchor:
                continue
            if role in ln or any(k in ln for k in keywords):
                hits.append(f"台账L{i+1}: {ln.strip()[:200]}")
                anchor = i + 1
    except OSError:
        pass
    return hits, anchor


def run_agent(agent_argv, prompt, repo, timeout):
    """拉起一次性子智能体处理消息；stdout 即回复正文。"""
    try:
        r = subprocess.run(
            [*agent_argv, prompt],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, cwd=repo,
        )
        out = (r.stdout or "").strip()
        if r.returncode != 0 and not out:
            return f"[agent rc={r.returncode} stderr={(r.stderr or '')[:200]}]", False
        return out or "[agent 无输出]", True
    except subprocess.TimeoutExpired:
        return "[agent 超时]", False
    except Exception as e:  # 启动失败（CLI 不存在等）
        return f"[agent 启动失败: {e}]", False


def main():
    ap = argparse.ArgumentParser(description="Datara 信箱循环实体程序")
    ap.add_argument("--role", required=True, help="本角色名（如 监督员/Codex/Claude）")
    ap.add_argument("--mailbox", default="docs/handoff/mailbox.jsonl")
    ap.add_argument("--agent-cmd", default="claude -p",
                    help="一次性子智能体命令，可用 {model} 占位（如 \"claude -p --model {model}\"）")
    ap.add_argument("--model", default="",
                    help="模型分级路由（P-OPT-5）：例行任务用轻模型如 deepseek-v4.1-flash；裁定/评审留空走默认重模型")
    ap.add_argument("--interval", type=float, default=3.0)
    ap.add_argument("--timeout", type=float, default=900.0, help="单次子智能体超时秒")
    ap.add_argument("--max-fail", type=int, default=3, help="子智能体连续失败退出阈值")
    ap.add_argument("--no-scan", action="store_true", help="关闭台账辅助扫描")
    ap.add_argument("--repo", default=".")
    args = ap.parse_args()

    repo = os.path.abspath(args.repo)
    mb = os.path.join(repo, args.mailbox)
    agent_argv = shlex.split(args.agent_cmd, posix=False)
    if args.model:
        if any("{model}" in a for a in agent_argv):
            agent_argv = [a.replace("{model}", args.model) for a in agent_argv]
        else:
            agent_argv = agent_argv + ["--model", args.model]
    role_prompt = ROLE_PROMPTS.get(args.role, DEFAULT_ROLE_PROMPT.format(role=args.role))

    os.makedirs(os.path.dirname(mb), exist_ok=True)
    open(mb, "a").close()
    log(repo, f"loop START role={args.role} mailbox={mb} agent={args.agent_cmd}")

    last_anchor = 0
    fail_streak = 0
    while True:
        # ---- 1. 读信箱，取发给我的待处理消息 ----
        try:
            msgs = read_mail(mb)
        except OSError as e:
            log(repo, f"mailbox read error: {e}")
            time.sleep(args.interval)
            continue

        pending = [m for m in msgs if m.get("to") == args.role and m.get("status") == "pending"]
        stops = [m for m in pending if m.get("type") == "STOP"]

        # ---- 退出条件：子智能体（一次性，天然已停）确认收尾 → 本循环退出 ----
        if stops:
            for s in stops:
                append_mail(mb, {"id": uuid.uuid4().hex[:8], "ts": now(), "from": args.role,
                                 "to": s.get("from"), "type": "ACK", "ref": s.get("id"),
                                 "body": "STOP 已确认，循环实体退出", "status": "pending"})
            log(repo, f"STOP received ({len(stops)}) — exit")
            break

        # ---- 2. 台账辅助扫描（增量，防重复） ----
        scan_note = ""
        if not args.no_scan and not pending:
            hits, last_anchor = scan_handoff(repo, args.role, last_anchor)
            if hits:
                scan_note = "【台账新动态（供参考，勿重复已办事项）】\n" + "\n".join(hits[-10:])

        # ---- 3. 合并单轮处理（P-OPT-2）：逐条 ACK 回执 → 一次子智能体调用 → 一条汇总 REPLY ----
        done_ids = []
        if pending:
            for m in pending:
                mid = m.get("id") or uuid.uuid4().hex[:8]
                m["id"] = mid
                append_mail(mb, {"id": uuid.uuid4().hex[:8], "ts": now(), "from": args.role,
                                 "to": m.get("from"), "type": "ACK", "ref": mid,
                                 "body": f"已接收任务 {mid}", "status": "pending"})
            blocks = "\n\n".join(
                f"--- 消息 #{m['id']} 来自 {m.get('from')} type={m.get('type')} ---\n{m.get('body', '')}"
                for m in pending)
            prompt = (f"{role_prompt}\n\n【本轮待处理消息（共 {len(pending)} 条，合并单轮处理）】\n{blocks}"
                      f"\n\n{scan_note}\n\n{CITATION_RULE}\n\n"
                      "处理完成后把回复正文输出到 stdout（按消息编号分点，简洁无寒暄；"
                      "若需他方跟进，在结尾以『下一单：<内容>』标注）。")
            reply, ok = run_agent(agent_argv, prompt, repo, args.timeout)
            fail_streak = 0 if ok else fail_streak + 1
            append_mail(mb, {"id": uuid.uuid4().hex[:8], "ts": now(), "from": args.role,
                             "to": pending[0].get("from"), "type": "REPLY",
                             "ref": ",".join(m["id"] for m in pending),
                             "body": reply, "status": "pending"})
            done_ids = [m["id"] for m in pending]
            log(repo, f"processed batch={len(pending)} ok={ok} reply={len(reply)}chars")

        if done_ids:
            rewrite_mark_done(mb, done_ids)

        # ---- 子智能体连续失败 → 视为子智能体停止 → 退出（保留信箱供人工接管） ----
        if fail_streak >= args.max_fail:
            log(repo, f"agent failed {fail_streak}x consecutively — exit")
            break

        time.sleep(args.interval)

    log(repo, "loop EXIT")


if __name__ == "__main__":
    main()
