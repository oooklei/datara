"""S131 信箱回馈处理 + Codex 3 单重派。"""
import json
import uuid
from datetime import datetime, timezone, timedelta

MB = r"d:\需求\数据治理工具\Datara\docs\handoff\mailbox.jsonl"
CST = timezone(timedelta(hours=8))
now = lambda: datetime.now(CST).strftime("%Y-%m-%dT%H:%M:%S")

# 读取现有信箱
with open(MB, "r", encoding="utf-8") as f:
    msgs = [json.loads(line) for line in f if line.strip()]

# 标记已处理的 REPLY 为 done
done_refs = {"ce0d4938", "d86121ac", "t60r3-done", "s129-wf26-done"}
for m in msgs:
    if m["id"] in done_refs and m["status"] == "pending":
        m["status"] = "done"
        m["ack_ts"] = now()

# 重派 Codex 3 单
def task(to, ref, body):
    return {
        "id": f"s131-{uuid.uuid4().hex[:6]}",
        "ts": now(),
        "from": "监督员",
        "to": to,
        "type": "TASK",
        "ref": ref,
        "body": body,
        "status": "pending",
    }

TASKS = [
    task("Codex", "SQLIDE-01-dispatcher-assembly-r3", """S131 SQLIDE-01 重派 r3 | operation→服务编排层（替换 app.py:244-253 501 桩）

【根因】app.py:244-253 仍为 501 桩，24 路由规格未实现。

【任务】新建 operation→服务编排层，覆盖 24 路由规格。

【文件域】
- datara-backend/rebuild/api/app.py:244-253（替换 501 桩）
- 必要时新建 datara-backend/rebuild/operation/ 服务层

【验收】24 路由可调用；SQLIDE-01 测试通过
【边界】.git 只读，改工作区后心跳回报，由监督线代提交；禁 push、禁 aoci_*"""),

    task("Codex", "SQLIDE-06-07-ddl-stage-d-r3", """S131 SQLIDE-06/07 重派 r3 | ConfirmGate 服务 + list_execution_records 服务 + 装配

【根因】SQLIDE-06/07 未实现。

【任务】
1. SQLIDE-06 ConfirmGate 服务
2. SQLIDE-07 list_execution_records 服务
3. 装配 app.py:868-878

【文件域】
- datara-backend/rebuild/sql_ide/（ConfirmGate + list_execution_records）
- datara-backend/rebuild/api/app.py:868-878（装配）

【验收】ConfirmGate + list_execution_records 可调用；SQLIDE-06/07 测试通过
【边界】.git 只读，改工作区后心跳回报，由监督线代提交；禁 push、禁 aoci_*"""),

    task("Codex", "T55-R-RT02-misfire-r4", """S131 T55-R 重派 r4 | RT-02 misfire SKIP 语义修复（验证 + 回归）

【根因】S129 已交付 T55-R（schedule.py + test_schedule_policies.py），需验证回归。

【任务】
1. 验证 S129 交付的 schedule.py + test_schedule_policies.py
2. 跑回归测试确认无破坏
3. 若发现新问题则修复

【文件域】
- datara-backend/master/schedule.py
- datara-backend/tests/test_schedule_policies.py

【验收】回归测试全绿；无新失败
【边界】.git 只读，改工作区后心跳回报，由监督线代提交；禁 push、禁 aoci_*"""),
]

msgs.extend(TASKS)

with open(MB, "w", encoding="utf-8") as f:
    for m in msgs:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")

print(f"已处理 {len(done_refs)} 条 REPLY 为 done")
print(f"已重派 {len(TASKS)} 单给 Codex")
for t in TASKS:
    print(f"  {t['id']} -> {t['to']} | {t['ref']}")
