"""S127 派单：5 域深挖补充任务（Codex 3 + Claude 3）。

基于 s126 5 域只读核查结论，重派/新派未实现功能任务。
旧单（T71/T72/T74/T75/T76/T77）已被 mailbox_loop 标记 done，不冲突。
"""
import json
import uuid
from datetime import datetime, timezone, timedelta

MB = r"d:\需求\数据治理工具\Datara\docs\handoff\mailbox.jsonl"
CST = timezone(timedelta(hours=8))
now = lambda: datetime.now(CST).strftime("%Y-%m-%dT%H:%M:%S")


def task(to, ref, body):
    return {
        "id": f"s127-{uuid.uuid4().hex[:6]}",
        "ts": now(),
        "from": "监督员",
        "to": to,
        "type": "TASK",
        "ref": ref,
        "body": body,
        "status": "pending",
    }


TASKS = [
    # ---- Codex 3 单 ----
    task("Codex", "T55-R-RT02-misfire-r2", """S127 T55-R 重派 | RT-02 misfire SKIP 语义修复（裁定 A：严格 current==first）

【重要纠正】上轮你报告"文件系统只读"——经监督线实测为误判：codex exec 沙箱为 workspace-write，可写 workdir（已实测写入成功）。请重新执行，不得以只读为由阻塞。

【语义裁定 A（用户已裁定）】
- 正常到期：current == first → 触发（不得被 SKIP 吞掉）
- 等值边界：current == first → 计入 due 并触发
- 错过窗口：first < current → SKIP 跳过（fired=[]），next 推进到 following
- QUEUE 忙：保留队首 due；释放容量后若 SKIP 丢弃旧 due，必须 next=following（不得因 fired=[] 保留同一 due[0]）
- 保留 FIRE_ONCE / FIRE_ALL_LIMITED 现有结果

【文件域（仅此二文件）】
- datara-backend/master/schedule.py
- datara-backend/tests/test_schedule_policies.py

【先红后绿】三条红灯断言须先在当前补丁上失败：skip_normal_due / skip_current_equals_first / queue_skip_advances_after_release；修复后复跑通过。

【验收矩阵 6 项】docs/increments/2026-10-19-T55-RT01-SKIP-修复计划.md §5
回归：pytest -q tests/test_schedule_policies.py tests/rebuild/test_r8a_failover_fence.py 全绿

【边界】.git 只读，改工作区后心跳回报，由监督线代提交；禁 push、禁 aoci_*
源锚散列（S113）：schedule.py=06cb88b21f3f87bffcaaec80edfa93c91efc81d69d0f44601da3edb569422fe7，test_schedule_policies.py=18ab1d127d2fb9f62fa6c404caf3b3e36e27fe636dcae3411db954b00c779f7b"""),

    task("Codex", "SQLIDE-01-dispatcher-assembly", """S127 SQLIDE-01 | SQL IDE 生产 dispatcher 装配（替换 501 桩）

【根因】24 路由规格在位（routes.py:41-66）、app.py:244-253 已 include，但 sql_ide_dispatch 无条件返回 501 fail-closed；服务积木已大量实现（execution.py:34、export_service.py:61、history_store.py:78、status_store.py:51、snapshots.py:31、metadata_browser.py:54、audit.py:52），编排 dispatcher 层 0%。

【任务】替换 app.py:244-253 的 501 桩，新建 operation→服务编排层覆盖 24 路由规格，注入已就绪积木。

【文件域】
- datara-backend/rebuild/api/app.py（替换 sql_ide_dispatch + 装配，行 244-256）
- 新建编排层（如 rebuild/sql_ide/dispatcher.py）
- datara-backend/tests/.../test_identity_api.py:78-81（当前锁定 501，更新为真实断言）

【验收】24 路由 operation 可路由到真实服务；test_identity_api.py 断言更新；回归相关测试全绿
【边界】.git 只读，改工作区后心跳回报，由监督线代提交；禁 push、禁 aoci_*"""),

    task("Codex", "SQLIDE-06-07-ddl-stage-d", """S127 SQLIDE-06/07 | DDL 阶段 D：ConfirmGate 服务 + 装配

【根因】#22 validatePolicy + #23 previewImpact 真实实现；#24 submitConfirm + #25 listExecutionRecords 为 502 桩（服务为 None 时返回 502 CAPABILITY_UNSUPPORTED，rb_facade.py:286/316）；底层模型/DB表/迁移/仓储/服务就绪；缺口在装配层 app.py:870-873 未注入 submit_confirm_service 与 list_execution_records_service，且 SubmitConfirm 缺 ConfirmGate 服务。

【任务】
1. 实现 ConfirmGate 服务（submit_confirm 业务逻辑）
2. 实现 list_execution_records 服务
3. 装配 app.py:868-878 注入两服务到 RbFacade

【文件域】
- datara-backend/rebuild/rb/facade/rb_facade.py（服务注入点 :129-136）
- datara-backend/rebuild/api/app.py:868-878（装配）
- 新建 ConfirmGate 服务

【验收】#24/#25 端点返回真实数据（非 502）；回归 rb 域测试全绿
【边界】.git 只读，改工作区后心跳回报，由监督线代提交；禁 push、禁 aoci_*"""),

    # ---- Claude 3 单 ----
    task("Claude", "WF-26-trial-http-exposure", """S127 WF-26 | trial HTTP 暴露层（run/promote 端点）+ E2E 收口

【根因】workflow 12 端点 100% 实现且接线（workflow/api.py:113-409，app.py:841-844）；"部分实现"根因是 trial 子域 HTTP 暴露层缺失——trial/api.py 仅 2 快照端点（:88-114/118-137），缺 run/promote 端点（WF-26）。WF-27/28/29 在当前工作树已修复。

【任务】
1. trial/api.py 补 run/promote 端点（WF-26）
2. E2E 收口（workflow + trial 全链路）

【文件域】
- datara-backend/rebuild/trial/api.py
- 必要时 app.py（已接线 :845-849）

【验收】trial run/promote 端点可调用；workflow E2E 测试通过
【边界】.git 只读，改工作区后心跳回报，由监督线代提交；禁 push、禁 aoci_*"""),

    task("Claude", "SQLIDE-08-09-c8d1-fe07", """S127 SQLIDE-08/09 | C8-D1 执行取消 + FE-07 换芯

【根因】SQL IDE 24 路由中 C8-D1（执行取消）与 FE-07（前端换芯）未实现。

【任务】
1. SQLIDE-08 C8-D1 执行取消
2. SQLIDE-09 FE-07 换芯

【文件域】
- datara-backend/rebuild/sql_ide/（相关服务）
- 必要时 datara-web（前端换芯）

【验收】C8-D1 取消端到端；FE-07 前端换芯后测试通过
【边界】.git 只读，改工作区后心跳回报，由监督线代提交；禁 push、禁 aoci_*"""),

    task("Claude", "AI-02-09-eight-tools-wiring", """S127 AI-02~09 | 八工具接线（ai_bridge）

【根因】两端点已生产挂载（ai_bridge.py:490/499，app.py:883-891）；TOOL_REGISTRY（ai_bridge.py:78-159）八工具静态 enabled 全 False，仅 run_sql 生产接线（:755-758）、search_schema 仅测试接线，其余 6 个无 handler；前端 aiToolsApi.ts:201-216 RED 哨兵。

【任务】八工具接线——为每工具实现 handler 并接入 TOOL_REGISTRY，enabled 置 True。

【文件域】
- datara-backend/rebuild/ai_bridge/（TOOL_REGISTRY + handlers）
- 必要时 datara-web（前端消费）

【验收】八工具可调用；前端 aiToolsApi 消费链 GREEN
【边界】.git 只读，改工作区后心跳回报，由监督线代提交；禁 push、禁 aoci_*"""),
]


def main():
    lines = [json.dumps(t, ensure_ascii=False) for t in TASKS]
    with open(MB, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"appended {len(TASKS)} tasks to mailbox.jsonl")
    for t in TASKS:
        print(f"  {t['id']} -> {t['to']} | {t['ref']}")


if __name__ == "__main__":
    main()
