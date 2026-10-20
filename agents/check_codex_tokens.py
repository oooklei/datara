# -*- coding: utf-8 -*-
"""Codex token 消耗调查 · 阶段1：schema/文件分布探查（只读，零写入 .codex）"""
import sqlite3
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

BASE = r"C:\Users\Administrator\.codex"
DBS = [
    "thread_history_1.sqlite",
    "logs_2.sqlite",
    "state_5.sqlite",
    "queue_1.sqlite",
    "goals_1.sqlite",
    "memories_1.sqlite",
    os.path.join("sqlite", "codex-dev.db"),
]

print("== ROOT LISTING ==")
for entry in sorted(os.listdir(BASE)):
    full = os.path.join(BASE, entry)
    kind = "D" if os.path.isdir(full) else "F"
    size = "" if os.path.isdir(full) else f" size={os.path.getsize(full)}"
    print(f"  [{kind}] {entry}{size}")

for name in DBS:
    path = os.path.join(BASE, name)
    if not os.path.exists(path):
        print(f"\n=== {name}: MISSING")
        continue
    print(f"\n=== {name} size={os.path.getsize(path)}")
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        cur = conn.cursor()
        tables = [r[0] for r in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        for t in tables:
            cols = [c[1] for c in cur.execute(f"PRAGMA table_info('{t}')")]
            try:
                n = cur.execute(f"SELECT COUNT(*) FROM '{t}'").fetchone()[0]
            except Exception as e:
                n = f"COUNT_ERR {e}"
            print(f"  table={t} rows={n} cols={cols}")
        conn.close()
    except Exception as e:
        print(f"  OPEN_ERROR: {e}")

print("\n== JSON/JSONL SIDECASTS ==")
for f in [".codex-global-state.json", "history.jsonl",
          "session_index.jsonl", "transcription-history.jsonl"]:
    p = os.path.join(BASE, f)
    print(f"  {f}: {'size=' + str(os.path.getsize(p)) if os.path.exists(p) else 'MISSING'}")

print("\n== SESSIONS DIR ==")
sess = os.path.join(BASE, "sessions")
if os.path.isdir(sess):
    total = 0
    for root, _dirs, files in os.walk(sess):
        for fn in files:
            total += 1
            if total <= 5:
                fp = os.path.join(root, fn)
                print(f"  sample: {fp} size={os.path.getsize(fp)}")
    print(f"  total files under sessions/: {total}")
else:
    print("  sessions/ MISSING")
