"""撤销 S131 重派到 mailbox.jsonl 的 3 单（S131 已裁定 mailbox.jsonl 非有效信道）。"""
import json
from datetime import datetime, timezone, timedelta

MB = r"d:\需求\数据治理工具\Datara\docs\handoff\mailbox.jsonl"
CST = timezone(timedelta(hours=8))
now = lambda: datetime.now(CST).strftime("%Y-%m-%dT%H:%M:%S")

with open(MB, "r", encoding="utf-8") as f:
    msgs = [json.loads(line) for line in f if line.strip()]

# 标记 S131 重派的 3 单为 done（撤销）
s131_refs = {"s131-2369d5", "s131-afaea6", "s131-ae7b4f"}
for m in msgs:
    if m["id"] in s131_refs and m["status"] == "pending":
        m["status"] = "done"
        m["ack_ts"] = now()
        m["body"] = "[撤销] " + m["body"][:50] + "..."

with open(MB, "w", encoding="utf-8") as f:
    for m in msgs:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")

print(f"已撤销 {len(s131_refs)} 单 S131 重派")
