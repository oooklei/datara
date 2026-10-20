# -*- coding: utf-8 -*-
"""Codex token 消耗调查 · 阶段4：固定注入内容构成抽查（只读）"""
import os
import sys
import json

sys.stdout.reconfigure(encoding="utf-8")

BASE = r"C:\Users\Administrator\.codex"
R1 = os.path.join(BASE, "sessions", "2026", "10", "20",
                  "rollout-2026-10-20T02-49-33-01a1557f-6066-7152-aa53-ed395c6a4a62.jsonl")

seen = {}
char_budget = {}   # payload type -> total chars
with open(R1, "r", encoding="utf-8", errors="replace") as f:
    for line in f:
        try:
            rec = json.loads(line)
        except Exception:
            continue
        t = rec.get("type")
        payload = rec.get("payload") or {}
        pt = payload.get("type") or t
        key = pt or t
        char_budget[key] = char_budget.get(key, 0) + len(line)
        if key in ("additional_tools", "message", "user_instructions", "world_state", "turn_context", "session_meta") and key not in seen:
            seen[key] = line

print("== K. s135_01 rollout 各记录类型字符总量 Top15 ==")
for k, v in sorted(char_budget.items(), key=lambda kv: -kv[1])[:15]:
    print(f"  {k}: {v} chars")

print("\n== L. additional_tools 头部 700 chars ==")
line = seen.get("additional_tools", "")
try:
    rec = json.loads(line)
    p = rec.get("payload", rec)
    tools = p.get("tools") or p.get("additional_tools") or p
    if isinstance(tools, list):
        names = []
        for tt in tools:
            if isinstance(tt, dict):
                names.append(tt.get("name") or (tt.get("function") or {}).get("name") or tt.get("type"))
        print(f"  tool_count={len(tools)}")
        print(f"  tool_names={names}")
    s = json.dumps(p, ensure_ascii=False)
    print(f"  head: {s[:700]}")
except Exception as e:
    print(f"  parse err {e}; raw head: {line[:700]}")

print("\n== M. developer message 头部 700 chars ==")
line = seen.get("message", "")
try:
    rec = json.loads(line)
    p = rec.get("payload", rec)
    content = p.get("content")
    text = ""
    if isinstance(content, list):
        text = "".join(c.get("text", "") for c in content if isinstance(c, dict))
    elif isinstance(content, str):
        text = content
    print(f"  role={p.get('role')} total_chars={len(text)}")
    print(f"  head: {text[:500]}")
    print(f"  tail: {text[-300:]}")
except Exception as e:
    print(f"  parse err {e}")

print("\n== N. config.toml ==")
p = os.path.join(BASE, "config.toml")
with open(p, "r", encoding="utf-8", errors="replace") as f:
    print(f.read())

print("\n== O. .codex-global-state.json 顶层键 + mcp 相关 ==")
p = os.path.join(BASE, ".codex-global-state.json")
with open(p, "r", encoding="utf-8", errors="replace") as f:
    gs = json.load(f)
print(f"  top keys: {list(gs.keys())}")
for k in gs:
    v = gs[k]
    if isinstance(v, dict):
        print(f"  {k}: dict[{len(v)}]")
    elif isinstance(v, list):
        print(f"  {k}: list[{len(v)}]")
# mcp servers
mcp = gs.get("mcp_servers") or gs.get("mcpServers") or {}
if mcp:
    print(f"  mcp_servers: {list(mcp.keys()) if isinstance(mcp, dict) else mcp}")
