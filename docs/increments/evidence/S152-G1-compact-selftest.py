#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S152 G1 自验：mailbox_loop compact 三类场景 + 现网只读检查。

场景 A：未达阈值不动（done 占比 40%、行数 50，均低于默认阈值）
场景 B：占比触发（done 50/90 = 55.6% > 50%）
场景 C：行数触发（600 行 > 500，done 占比 33.3% < 50%）
现网只读检查：高阈值下不误触发；默认阈值如实判定（不写文件）。

运行：python docs/increments/evidence/S152-G1-compact-selftest.py
退出码：0 = 全绿；1 = 存在失败。
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
spec = importlib.util.spec_from_file_location(
    "mailbox_loop", os.path.join(REPO, "agents", "mailbox_loop.py"))
ml = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ml)

KEEP = 20
RATIO = 0.5
THRESHOLD = 500

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def write_msgs(path, msgs):
    with open(path, "w", encoding="utf-8") as f:
        for m in msgs:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")


def read_raw_lines(path):
    with open(path, "r", encoding="utf-8") as f:
        return [ln for ln in f.read().splitlines() if ln.strip()]


def read_msgs(path):
    return [json.loads(ln) for ln in read_raw_lines(path)]


def mk_msgs(n_done, n_pending, tag):
    """构造样例：done 在前、pending 在后，id 递增，行序确定。"""
    msgs = []
    for i in range(n_done):
        msgs.append({"id": f"{tag}-d{i:04d}", "ts": "2026-10-20T00:00:00",
                     "from": "监督员", "to": "Claude", "type": "REPLY",
                     "body": f"done {i}", "status": "done"})
    for i in range(n_pending):
        msgs.append({"id": f"{tag}-p{i:04d}", "ts": "2026-10-20T00:00:00",
                     "from": "监督员", "to": "Claude", "type": "TASK",
                     "body": f"pending {i}", "status": "pending"})
    return msgs


def scenario_untriggered(tmp):
    print("场景 A：未达阈值不动（50 行，done 20 = 40%）")
    mb = os.path.join(tmp, "mailbox.jsonl")
    arch = os.path.join(tmp, "archive-a")
    msgs = mk_msgs(20, 30, "a")
    write_msgs(mb, msgs)
    before = read_raw_lines(mb)
    triggered, n_arch, n_kept, apath, reason = ml.compact_mailbox(mb, arch, RATIO, THRESHOLD, KEEP)
    check("A1 不触发", not triggered, reason)
    check("A2 主文件逐行不变", read_raw_lines(mb) == before)
    check("A3 无归档产出", not os.path.exists(os.path.join(arch, "mailbox-2026-10-20-compact.jsonl")))


def scenario_ratio(tmp):
    print("场景 B：占比触发（90 行，done 50 = 55.6% > 50%）")
    mb = os.path.join(tmp, "mailbox.jsonl")
    arch = os.path.join(tmp, "archive-b")
    msgs = mk_msgs(50, 40, "b")
    write_msgs(mb, msgs)
    orig_done_ids = [m["id"] for m in msgs if m["status"] == "done"]
    orig_pending_ids = [m["id"] for m in msgs if m["status"] == "pending"]
    triggered, n_arch, n_kept, apath, reason = ml.compact_mailbox(mb, arch, RATIO, THRESHOLD, KEEP)
    check("B1 触发", triggered, reason)
    check("B2 归档 30 条（50 done - keep 20）", n_arch == 30, f"n_arch={n_arch}")
    check("B3 主文件 60 行（40 pending + 20 done）", n_kept == 60, f"n_kept={n_kept}")
    # 归档完整且合法
    arch_msgs = read_msgs(apath)
    check("B4 归档每行 JSON 合法且 status=done",
          all(isinstance(m, dict) and m.get("status") == "done" for m in arch_msgs))
    check("B5 归档 id = 原 done 去掉最近 20 条",
          [m["id"] for m in arch_msgs] == orig_done_ids[:-KEEP])
    # pending 无丢失
    kept_msgs = read_msgs(mb)
    kept_pending_ids = [m["id"] for m in kept_msgs if m["status"] == "pending"]
    check("B6 pending 无丢失", kept_pending_ids == orig_pending_ids)
    # 行序不变：主文件 = 原文件过滤掉被归档 done 后的顺序
    archived_ids = set(orig_done_ids[:-KEEP])
    expect_order = [m["id"] for m in msgs if m["id"] not in archived_ids]
    check("B7 行序不变（保留消息相对顺序）",
          [m["id"] for m in kept_msgs] == expect_order)
    # 保留的 done = 最近 20 条
    kept_done_ids = [m["id"] for m in kept_msgs if m["status"] == "done"]
    check("B8 保留最近 20 条 done", kept_done_ids == orig_done_ids[-KEEP:])


def scenario_lines(tmp):
    print("场景 C：行数触发（600 行 > 500，done 200 = 33.3% < 50%）")
    mb = os.path.join(tmp, "mailbox.jsonl")
    arch = os.path.join(tmp, "archive-c")
    msgs = mk_msgs(200, 400, "c")
    write_msgs(mb, msgs)
    orig_done_ids = [m["id"] for m in msgs if m["status"] == "done"]
    orig_pending_ids = [m["id"] for m in msgs if m["status"] == "pending"]
    triggered, n_arch, n_kept, apath, reason = ml.compact_mailbox(mb, arch, RATIO, THRESHOLD, KEEP)
    check("C1 触发", triggered, reason)
    check("C2 归档 180 条（200 done - keep 20）", n_arch == 180, f"n_arch={n_arch}")
    check("C3 主文件 420 行（400 pending + 20 done）", n_kept == 420, f"n_kept={n_kept}")
    arch_msgs = read_msgs(apath)
    check("C4 归档 id = 原 done 去掉最近 20 条",
          [m["id"] for m in arch_msgs] == orig_done_ids[:-KEEP])
    kept_msgs = read_msgs(mb)
    check("C5 pending 无丢失",
          [m["id"] for m in kept_msgs if m["status"] == "pending"] == orig_pending_ids)
    archived_ids = set(orig_done_ids[:-KEEP])
    check("C6 行序不变",
          [m["id"] for m in kept_msgs] == [m["id"] for m in msgs if m["id"] not in archived_ids])


def scenario_same_day_append(tmp):
    print("场景 D（补充）：同日二次触发追加写归档，不覆盖")
    mb = os.path.join(tmp, "mailbox.jsonl")
    arch = os.path.join(tmp, "archive-d")
    msgs = mk_msgs(30, 20, "d")  # 60 行，done 50% —— 不 > 50%，改用 40 done/20 pending
    msgs = mk_msgs(40, 20, "d")  # 60 行，done 66.7% > 50%
    write_msgs(mb, msgs)
    t1, a1, _, p1, _ = ml.compact_mailbox(mb, arch, RATIO, THRESHOLD, KEEP)
    # 主文件现为 20 pending + 20 done = 40 行，done 50% 不 > 50%，需再补 done 触发
    with open(mb, "a", encoding="utf-8") as f:
        for i in range(30):
            f.write(json.dumps({"id": f"d2-d{i:04d}", "ts": "2026-10-20T00:00:00",
                                "from": "x", "to": "y", "type": "REPLY",
                                "body": "late done", "status": "done"},
                               ensure_ascii=False) + "\n")
    t2, a2, _, p2, _ = ml.compact_mailbox(mb, arch, RATIO, THRESHOLD, KEEP)
    check("D1 两次均触发", t1 and t2)
    arch_lines = read_raw_lines(p2)
    check("D2 归档为两次追加（20 + 30 = 50 行）", len(arch_lines) == 50, f"lines={len(arch_lines)}")
    check("D3 归档全部 JSON 合法", all(isinstance(json.loads(l), dict) for l in arch_lines))


def readonly_production():
    print("现网只读检查（docs/handoff/mailbox.jsonl，不写任何文件）")
    mb = os.path.join(REPO, "docs", "handoff", "mailbox.jsonl")
    msgs = ml.read_mail(mb)
    total = len(msgs)
    n_done = sum(1 for m in msgs if m.get("status") == "done")
    r = n_done / total if total else 0
    print(f"  现网：total={total} done={n_done} ratio={r:.2%}")
    # 高阈值只读检查：确认不误触发
    t, reason = ml.should_compact(msgs, ratio=0.9, threshold=2000)
    check("P1 高阈值（ratio=0.9, threshold=2000）不误触发", not t, reason)
    # 默认阈值如实判定（只读，不执行 compact）
    t_def, reason_def = ml.should_compact(msgs, RATIO, THRESHOLD)
    print(f"  默认阈值（ratio=0.5, threshold=500）判定：triggered={t_def} — {reason_def}")
    check("P2 默认阈值判定与手工计算一致",
          t_def == (r > RATIO or total > THRESHOLD))


def main():
    print("=" * 60)
    print("S152 G1 mailbox compact 自验")
    print("=" * 60)
    tmp = tempfile.mkdtemp(prefix="s152-g1-")
    try:
        scenario_untriggered(tmp)
        scenario_ratio(tmp)
        scenario_lines(tmp)
        scenario_same_day_append(tmp)
        readonly_production()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    failed = [r for r in results if not r[1]]
    print("=" * 60)
    print(f"总计 {len(results)} 项，通过 {len(results) - len(failed)}，失败 {len(failed)}")
    if failed:
        for name, _, detail in failed:
            print(f"  FAILED: {name} — {detail}")
        sys.exit(1)
    print("全绿。")


if __name__ == "__main__":
    main()
