# -*- coding: utf-8 -*-
"""Codex token 消耗调查 · 阶段3：rollout 解析（每轮 input/cached/output）+ 注入源大小"""
import os
import sys
import json

sys.stdout.reconfigure(encoding="utf-8")

BASE = r"C:\Users\Administrator\.codex"
REPO = r"d:\需求\数据治理工具\Datara"

print("== H. 注入源文件大小 ==")
targets = [
    (REPO, "AGENTS.md"),
    (REPO, "docs\\handoff\\STATE.md"),
    (os.path.join(BASE), "AGENTS.md"),
    (REPO, "README.md"),
]
for root, fn in targets:
    p = os.path.join(root, fn)
    if os.path.exists(p):
        size = os.path.getsize(p)
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        print(f"  {fn}: {size} bytes, {len(text)} chars, {len(text.splitlines())} lines")
    else:
        print(f"  {fn}: MISSING")

rollouts = []
day20 = os.path.join(BASE, "sessions", "2026", "10", "20")
if os.path.isdir(day20):
    for fn in sorted(os.listdir(day20)):
        if fn.endswith(".jsonl"):
            rollouts.append(os.path.join(day20, fn))

print(f"\n== I. 今日 rollout 文件 ==")
for p in rollouts:
    print(f"  {os.path.basename(p)} size={os.path.getsize(p)}")

def parse_rollout(path):
    name = os.path.basename(path)
    turn_counts = []          # 每次 token_count 的 last_token_usage
    total_usage = None
    meta = None
    n_lines = 0
    item_types = {}
    biggest_items = []        # (chars, type, snippet)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            n_lines += 1
            try:
                rec = json.loads(line)
            except Exception:
                continue
            t = rec.get("type")
            payload = rec.get("payload") or {}
            pt = payload.get("type")
            key = f"{t}/{pt}"
            item_types[key] = item_types.get(key, 0) + 1
            if pt == "token_count":
                info = payload.get("info") or {}
                last = info.get("last_token_usage")
                if last:
                    turn_counts.append(last)
                tu = info.get("total_token_usage")
                if tu:
                    total_usage = tu
            elif t == "session_meta":
                meta = payload
            elif t == "response_item":
                s = len(line)
                biggest_items.append((s, payload.get("type"), str(payload)[:100]))
    biggest_items.sort(reverse=True)
    return name, meta, turn_counts, total_usage, n_lines, item_types, biggest_items[:5]

for p in rollouts:
    name, meta, turns, total, n_lines, item_types, big5 = parse_rollout(p)
    print(f"\n== J. {name} ==")
    print(f"  lines={n_lines}")
    if meta:
        cwd = meta.get("cwd")
        instr = meta.get("instructions") or ""
        print(f"  cwd={cwd} instructions_chars={len(instr)}")
        ag = meta.get("aggregated_agts") or meta.get("agents") or None
        if ag:
            print(f"  extra_meta_keys={list(meta.keys())}")
    print(f"  token_count events={len(turns)}")
    if turns:
        sum_in = sum(t.get("input_tokens", 0) for t in turns)
        sum_cached = sum(t.get("cached_input_tokens", 0) for t in turns)
        sum_out = sum(t.get("output_tokens", 0) for t in turns)
        sum_reason = sum(t.get("reasoning_output_tokens", 0) for t in turns)
        print(f"  SUM last_token_usage: input={sum_in} cached_input={sum_cached} output={sum_out} reasoning={sum_reason}")
        print(f"  (un-cached input = {sum_in - sum_cached}, cache_hit_ratio={(sum_cached/sum_in*100 if sum_in else 0):.1f}%)")
        # 增长曲线抽样：每5个事件打一行
        print("  per-event samples (every 5th):")
        for i in range(0, len(turns), 5):
            t = turns[i]
            print(f"    #{i}: input={t.get('input_tokens')} cached={t.get('cached_input_tokens')} out={t.get('output_tokens')}")
        t = turns[-1]
        print(f"    LAST: input={t.get('input_tokens')} cached={t.get('cached_input_tokens')} out={t.get('output_tokens')}")
    if total:
        print(f"  total_token_usage={json.dumps(total)}")
    top_types = sorted(item_types.items(), key=lambda kv: -kv[1])[:12]
    print(f"  record types: {top_types}")
    if big5:
        print("  biggest response_items:")
        for s, it, snip in big5:
            print(f"    {s} chars type={it} {snip[:90]!r}")
