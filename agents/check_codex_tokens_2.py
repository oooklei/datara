# -*- coding: utf-8 -*-
"""Codex token 消耗调查 · 阶段2：threads 表 token 统计（只读）"""
import sqlite3
import os
import sys
import json
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding="utf-8")

BASE = r"C:\Users\Administrator\.codex"
CST = timezone(timedelta(hours=8))

conn = sqlite3.connect(f"file:{os.path.join(BASE, 'state_5.sqlite')}?mode=ro", uri=True)
cur = conn.cursor()

print("== A. tokens_used 按 cwd 分组 ==")
for row in cur.execute("""
    SELECT cwd, COUNT(*), SUM(tokens_used), MAX(tokens_used)
    FROM threads GROUP BY cwd ORDER BY SUM(tokens_used) DESC LIMIT 20"""):
    print(f"  cwd={row[0]!r} threads={row[1]} sum_tokens={row[2]} max_thread={row[3]}")

print("\n== B. 总览 ==")
row = cur.execute("""
    SELECT COUNT(*), SUM(tokens_used), MIN(created_at_ms), MAX(updated_at_ms)
    FROM threads""").fetchone()
print(f"  total_threads={row[0]} sum_tokens={row[1]} first={datetime.fromtimestamp(row[2]/1000, CST) if row[2] else None} last={datetime.fromtimestamp(row[3]/1000, CST) if row[3] else None}")

print("\n== C. Datara 相关线程按日 tokens_used ==")
for row in cur.execute("""
    SELECT date(created_at_ms/1000, 'unixepoch', '+8 hours') AS d,
           COUNT(*), SUM(tokens_used), MAX(tokens_used)
    FROM threads
    WHERE (cwd LIKE '%Datara%' OR rollout_path LIKE '%Datara%')
    GROUP BY d ORDER BY d DESC LIMIT 15"""):
    print(f"  day={row[0]} threads={row[1]} sum_tokens={row[2]} max_single={row[3]}")

print("\n== D. Datara Top15 单线程 tokens_used ==")
for row in cur.execute("""
    SELECT id, tokens_used, model, title, created_at_ms, rollout_path, thread_source
    FROM threads
    WHERE (cwd LIKE '%Datara%' OR rollout_path LIKE '%Datara%')
    ORDER BY tokens_used DESC LIMIT 15"""):
    ts = datetime.fromtimestamp(row[4]/1000, CST).strftime('%m-%d %H:%M') if row[4] else '?'
    print(f"  id={row[0]} tokens={row[1]} model={row[2]} at={ts} src={row[6]}\n    title={str(row[3])[:80]!r}\n    rollout={row[5]}")

print("\n== E. 全库 Top10 单线程 tokens_used（含其他项目对照） ==")
for row in cur.execute("""
    SELECT id, tokens_used, model, cwd, title, created_at_ms
    FROM threads ORDER BY tokens_used DESC LIMIT 10"""):
    ts = datetime.fromtimestamp(row[5]/1000, CST).strftime('%m-%d %H:%M') if row[5] else '?'
    print(f"  id={row[0]} tokens={row[1]} model={row[2]} cwd={row[3]!r} at={ts} title={str(row[4])[:60]!r}")

print("\n== F. thread_spawn_edges 中的 Datara 线程派生 ==")
row = cur.execute("""
    SELECT COUNT(*) FROM thread_spawn_edges
    WHERE parent_thread_id IN (SELECT id FROM threads WHERE cwd LIKE '%Datara%')
       OR child_thread_id IN (SELECT id FROM threads WHERE cwd LIKE '%Datara%')""").fetchone()
print(f"  spawn_edges involving Datara threads: {row[0]}")

print("\n== G. 今天(10-20)新建的 Datara 线程明细 ==")
for row in cur.execute("""
    SELECT id, tokens_used, model, source, thread_source, created_at_ms, updated_at_ms, title
    FROM threads
    WHERE (cwd LIKE '%Datara%' OR rollout_path LIKE '%Datara%')
      AND created_at_ms >= ?
    ORDER BY created_at_ms""", (int(datetime(2026, 10, 20, tzinfo=CST).timestamp()*1000),)):
    c = datetime.fromtimestamp(row[5]/1000, CST).strftime('%H:%M:%S')
    u = datetime.fromtimestamp(row[6]/1000, CST).strftime('%H:%M:%S')
    print(f"  id={row[0]} tokens={row[1]} model={row[2]} src={row[3]}/{row[4]} created={c} updated={u} title={str(row[7])[:70]!r}")

conn.close()
