#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dispatch_s152.py — S152 全量派单（监督线程序化写信箱，参照 dispatch_s150.py）

前置验收（2026-10-20 监督线三单全部 PASS）：
1. S151（Trae）：预先存在 11 失败修复 i19/i20/i23，复跑 865P/1s/0F；
2. P1-6'（Claude）：adapter.py:217 修复已入库 10069ac + 默认工厂重跑证据 PASS；
3. P-OPT-1（Claude）：落地缺口盘点在位，G1 方案待实施。

用户指令「所有任务全部派单他们」+ FE 裁定（2026-10-20）：FE 继续暂缓（等用户审前端方案）。

动作：
1. 标 done 9 条（三单 TASK/ACK/REPLY + s149-705c78 通知 + s129-sqlide-done 重复回报）；
2. 派 TASK 6 条：
   - to=Claude：G1 mailbox compact（先派先领）；C21r（WF-10~29+WF-24/25 修订）；
   - to=Trae：T55r（RT-01~04+RT-06）/ T56r（RBAC-01/02/03）/ T57r（DEP-01）/ T58r（GOV-01/02），
     串行排 T46r→T47r→T48r 之后。
   不派：RT-05（S109 暂缓）、RBAC-08（S109 暂缓）、FE-01/02/05/06+FE-07a/b+FE-21（用户裁定暂缓）、
   五域 P1/P2（待 P0 批次完成后续派）。
"""
import json
import os
import uuid
from datetime import datetime

MB = os.path.join("docs", "handoff", "mailbox.jsonl")

# 与已完成并验收任务相关的待清理条目
DONE_IDS = [
    "s149-705c78",    # MSG to=Trae：s129 两单清理通知（早已完成）
    "s149-1a5ef9",    # TASK Claude：P1-6' 收尾（本轮验收 PASS）
    "s149-b5d644",    # TASK Claude：P-OPT-1 收尾（本轮验收 PASS）
    "s149-930530",    # TASK Trae：11 失败修复（S151 验收 PASS，865P/0F）
    "s149-ack-p16",   # ACK
    "s149-ack-popt1", # ACK
    "fefd6ece",       # REPLY Claude：P-OPT-1 交付回报（验收 PASS）
    "s149-p16-done",  # REPLY Claude：P1-6' 交付回报（验收 PASS）
    "s129-sqlide-done",  # REPLY：与 s129-cb8436-done 重复回报（后者已 done）
]

BOUNDARY_TRAE = "【边界】.git 只读，改工作区后心跳回报，由监督线代提交；禁 push、禁 aoci_*。串行提示：你线当前顺序 T46r→T47r→T48r 不变，本单排在 T48r 之后（T55r→T56r→T57r→T58r），每单交付后心跳回报等验收。"

BOUNDARY_CLAUDE = "【边界】.git 只读，改工作区后心跳回报，由监督线代提交；禁 push、禁 aoci_*。"


def now():
    return datetime.now().isoformat(timespec="seconds")


def read_mail(path):
    msgs = []
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
                continue
    return msgs


def envelope(to, ref, body, mtype):
    return {
        "id": f"s152-{uuid.uuid4().hex[:6]}",
        "ts": now(),
        "from": "监督员",
        "to": to,
        "type": mtype,
        "ref": ref,
        "body": body,
        "status": "pending",
    }


BODY_G1 = """S152 G1 | mailbox.jsonl done 消息清出机制（compact）落地（P-OPT-1 缺口收尾）

【根因】P-OPT-1 盘点确认缺口 G1：mailbox.jsonl done 消息占比约 46%，无定期清出机制，持续膨胀。方案已列（docs/increments/2026-10-20-P-OPT-1-落地缺口盘点与收尾.md），采用方案 1（循环实体内置 compact）。

【任务】
1. agents/mailbox_loop.py 增加 compact 逻辑 + --compact-threshold 参数：done 消息占比超 50% 或总行数超 500 时触发；触发时全部 done 消息移入 docs/handoff/archive/mailbox-<日期>-compact.jsonl，主文件保留全部 pending + 最近 N 条 done（N 默认 20）。
2. compact 写入与现有领单/写信箱一致采用 tmp+os.replace 原子重写。
3. 自验：构造样例 mailbox 覆盖三类场景（未达阈值不动 / 占比触发 / 行数触发），断言归档完整、pending 无丢失、JSON 合法行序不变。

【文件域】
- agents/mailbox_loop.py（唯一代码改动）
- docs/handoff/archive/（compact 产出归档文件，运行期产物）
- docs/increments/evidence/（自验证据）

【验收】三类场景自验全绿；对现网 mailbox.jsonl 只读检查确认不误触发；证据落盘。

【边界】""" + BOUNDARY_CLAUDE + """注意：改后不重启现有循环实体，重启由监督线择机执行；compact 逻辑注意与领单写入的并发安全。

""" + BOUNDARY_CLAUDE

BODY_C21R = """S152 C21r | 工作流域收口 WF-10~29 + WF-24/25 修订（大盘缺口 #2/#12/#14/#26）

【根因】大盘盘点缺口 #2（TRIAL 八能力）/ #12（草稿快照）/ #14（trial HTTP 暴露）/ #26（execution api）未收口；WF-01~09 基线已入库（898ea68），无阻塞前置。

【任务】真源：docs/increments/2026-10-19-WBS-工作流域任务分解.md + docs/increments/2026-10-19-WBS-任务池汇总.md §5.1（WF-26~29 及修订项）。
1. A 组草稿快照：WF-10（workflow_draft_snapshot 模型 + UniqueConstraint(definition_id,snapshot_digest) + create_all）→ WF-11（create_from_draft 幂等）→ WF-12（POST /definitions/{id}/snapshot + GET /snapshots/{snapshot_id}，prefix=/api/v1/rebuild/trial）。
2. B 组 TRIAL 八能力：WF-13 TrialValidator → WF-14 TrialRunner 主流程(L) → WF-15 单节点 / WF-16 从指定节点 / WF-17 测试变量覆盖 / WF-18 依赖模拟 / WF-19 Dry Run / WF-20 SQL 预检查（六者仅依赖 WF-14）→ WF-22 输出聚合 → WF-21 promote(L)。
3. WF-23：补 rebuild/execution/api.py（POST /runs、GET /runs/{id}、POST /runs/{id}/cancel）。
4. 暴露层与语义修订：WF-26（trial/api.py 三端点暴露）、WF-27（SKIPPED 独立终态替换 FAILED+WARN 模拟）、WF-28（workflow_version_id 语义统一）、WF-29（task_id 语义统一）。
5. C 组：WF-24 E2E 集成测试（test_trial_e2e.py；修订：移除 "404 acceptable" 绕过）→ WF-25 收尾（修订：修正 WBS 风险#3；大盘 #2/#12/#14/#26 → ✅）。

【文件域】
- datara-backend/rebuild/workflow/、rebuild/trial/、rebuild/execution/
- datara-backend/rebuild/api/app.py（trial router 挂载 + create_all）
- datara-backend/tests/rebuild/test_workflow_domain.py、test_trial_e2e.py 等
- docs/increments/（证据）

【验收】新增 pytest 全绿；全量 pytest tests/rebuild -q 不新增失败（基线 865P/1s/0F）；promote 幂等、digest 一致、SKIPPED 终态断言；证据落盘 docs/increments/evidence/。

【边界】""" + BOUNDARY_CLAUDE

BODY_T55R = """S152 T55r | RUNTIME 调度执行域 P0：调度四字段 + fencing（RT-05 暂缓除外）

【根因】S108 五域深挖 RUNTIME 域 P0：RT-01~04 调度四字段缺失（P0-1）、RT-06 failover 仅有进程内注册表（P0-3）。RT-05 EVENT 已 S109 裁定暂缓（设计契约缺口），本单不含。

【任务】真源：docs/increments/2026-10-19-WBS-任务池汇总.md §6.2。
1. RT-01 misfire_policy：WfSchedule 字段+逻辑，验收锚 FIRE_ONCE/SKIP/FIRE_ALL_LIMITED。
2. RT-02 concurrency_policy：ALLOW/FORBID/QUEUE 三策略。
3. RT-03 max_running_instances：并发上限强制。
4. RT-04 timezone：时区感知调度。
5. RT-06 failover 跨进程 fencing 原语：分布式锁/lease；技术选型如需裁定可先回报再动手。

【文件域】
- datara-backend/rebuild/（调度/执行相关模块）
- datara-backend/tests/rebuild/
- docs/increments/（证据）

【验收】四字段+逻辑 pytest 全绿（含验收锚）；fencing 原语可测试；全量 pytest tests/rebuild -q 不新增失败（基线 865P/1s/0F）；证据落盘。

【边界】""" + BOUNDARY_TRAE

BODY_T56R = """S152 T56r | RBAC 安全线三 P0（RBAC-08 已 S109 暂缓不含）

【根因】S108 五域深挖 RBAC 域 P0：RBAC-D1 EXECUTE_SQL 权限枚举缺失（全角色 403）、RBAC-D2 metrics 域 6 端点无项目级校验、RBAC-D3 rb 域 4 端点（含 DDL confirm）无项目级校验。

【任务】真源：docs/increments/2026-10-19-WBS-任务池汇总.md §6.3。
1. RBAC-01：Permission 枚举补 EXECUTE_SQL + 真实装配路径测试（修复全角色 403）。
2. RBAC-02：metrics 6 端点项目级授权，跨项目访问拒绝。
3. RBAC-03：rb 域 4 端点项目级授权（含 DDL confirm），跨项目访问拒绝。

【文件域】
- datara-backend/rebuild/（auth/rbac/metrics/rb 相关模块）
- datara-backend/tests/rebuild/
- docs/increments/（证据）

【验收】三组 pytest 全绿（含跨项目 403 断言、EXECUTE_SQL 放行断言）；全量 pytest tests/rebuild -q 不新增失败；证据落盘。

【边界】""" + BOUNDARY_TRAE

BODY_T57R = """S152 T57r | DEPLOY 域 P0：cancel 终态命名对齐（DEP-01）

【根因】S108 五域深挖 DEPLOY 域 P0：cancel 终态 CANCELED 与设计正本不一致，需全链路对齐 CANCELLED + 补 CANCEL_FAILED。

【任务】真源：docs/increments/2026-10-19-WBS-任务池汇总.md §6.5。
1. 全链路 cancel 终态 CANCELED→CANCELLED（枚举/状态机/repository/api/前端契约层凡出现处）。
2. 补 CANCEL_FAILED 终态及迁移路径。
3. 相关测试断言同步更新。

【文件域】
- datara-backend/rebuild/（execution/workflow 相关）
- datara-backend/tests/rebuild/
- datara-web/src/（契约层如涉及，最小改动）
- docs/increments/（证据）

【验收】全链路双 L 大写断言全绿（grep 无残留 CANCELED）；全量 pytest tests/rebuild -q 不新增失败；证据落盘。

【边界】""" + BOUNDARY_TRAE

BODY_T58R = """S152 T58r | 治理域 P0 两项（GOV-03~05 P1 另批派发，本单不含）

【根因】S108 五域深挖 GOV 域 P0：GOV-01 数据质量域运行时能力缺失（仅 ORM 表，测试断言已移除）、GOV-02 数据标准域 importer/导入端点缺失。

【任务】真源：docs/increments/2026-10-19-WBS-任务池汇总.md §6.1。
1. GOV-01：质量规则 CRUD + 执行 + 结果查询端点（I21 补齐），恢复对应测试断言。
2. GOV-02：标准导入 HTTP 路由 + 解析 + 入库（I22）。

【文件域】
- datara-backend/rebuild/governance/（质量域/标准域）
- datara-backend/rebuild/api/app.py（如需挂载）
- datara-backend/tests/rebuild/
- docs/increments/（证据）

【验收】CRUD+执行+结果查询 pytest 全绿；导入链路端到端测试全绿；全量 pytest tests/rebuild -q 不新增失败；证据落盘。

【边界】""" + BOUNDARY_TRAE


def main():
    msgs = read_mail(MB)
    marked = 0
    for m in msgs:
        if m.get("id") in DONE_IDS and m.get("status") != "done":
            m["status"] = "done"
            m["ack_ts"] = now()
            marked += 1
    appended = [
        envelope("Claude", "g1-mailbox-compact", BODY_G1, "TASK"),
        envelope("Claude", "C21r-workflow-wf10-29", BODY_C21R, "TASK"),
        envelope("Trae", "T55r-runtime-p0", BODY_T55R, "TASK"),
        envelope("Trae", "T56r-rbac-p0", BODY_T56R, "TASK"),
        envelope("Trae", "T57r-dep-p0", BODY_T57R, "TASK"),
        envelope("Trae", "T58r-gov-p0", BODY_T58R, "TASK"),
    ]
    out = msgs + appended
    tmp = MB + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(m, ensure_ascii=False) for m in out) + "\n")
    os.replace(tmp, MB)
    print(f"marked done={marked}; appended TASK=6 (G1/C21r -> Claude, T55r/T56r/T57r/T58r -> Trae); total lines={len(out)}")


if __name__ == "__main__":
    main()
