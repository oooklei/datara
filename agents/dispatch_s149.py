#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dispatch_s149.py — S149 分散派单（监督线程序化写信箱，参照 dispatch_s131.py）

动作：
1. 死信清理：to=Trae 的 s129-c7c92b（T69 宿主实测）与 s129-b041b1（T67 dry_run 修复）
   已由 Trae 线 S143 交付、监督线 S145 验收并代提交 c267917，标记 done 防重复领单。
2. 附 1 条 MSG 向 Trae 说明死信处置。
3. 任务池分散派单 3 单（Codex 线 token 耗尽掉线，暂停派单）：
   - Claude：P1-6' 收尾（PoC 注入修正重跑取证 + adapter.py:217 缺陷修复单）
   - Claude：P-OPT-1 收尾（原派 Codex 改派；分层快照+裁定索引缺口盘点收尾）
   - Trae：S143 上报 11 个预先存在失败核查修复（i19/i20/i23 系列）

不派项：AOCI 传输策略（待用户裁）；P2-2 Track A 复验收口（监督线动作）；
P2-3（硬前置 P2-2 GREEN 未满足）。
"""
import json
import os
import uuid
from datetime import datetime

MB = os.path.join("docs", "handoff", "mailbox.jsonl")
DEAD_IDS = {"s129-c7c92b", "s129-b041b1"}


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
        "id": f"s149-{uuid.uuid4().hex[:6]}",
        "ts": now(),
        "from": "监督员",
        "to": to,
        "type": mtype,
        "ref": ref,
        "body": body,
        "status": "pending",
    }


def task(to, ref, body):
    return envelope(to, ref, body, "TASK")


BODY_P1_6PRIME = """S149 P1-6' 收尾 | PoC 注入修正重跑取证 + adapter.py:217 缺陷修复单

【根因】P1-6' 遗留两项收尾（STATE.md §二.2）：PoC 注入修正后 vanna_factory 未重跑取证；adapter.py:217 缺陷未出修复单。

【任务】
1. 重跑 vanna_factory PoC，取证注入修正生效，证据落盘 docs/increments/evidence/。
2. 出具 adapter.py:217 缺陷修复单（缺陷描述/影响面/修复方案/回归口径），落 docs/increments/。

【文件域】
- datara-backend（vanna_factory PoC 与 adapter.py 相关文件，仅重跑取证所需最小改动）
- docs/increments/（证据与修复单文档）

【验收】重跑证据在位且结论明确；修复单完整；若 adapter.py:217 需代码修复，先回报方案待监督线裁定再动手。

【边界】.git 只读，改工作区后心跳回报，由监督线代提交；禁 push、禁 aoci_*"""

BODY_P_OPT_1 = """S149 P-OPT-1 收尾 | STATE.md 分层快照 + 裁定索引落地缺口盘点与收尾

【根因】P-OPT-1（结构设计：STATE.md 分层快照 ≤60 行 + decisions-index.md 裁定索引 → 各线冷启动只读快照）主体已实践（archive/ 分卷体系运转中），剩余缺口未盘点收口；原派 Codex 因 token 耗尽掉线，改派 Claude 线。

【任务】
1. 盘点 P-OPT-1 落地状态：STATE.md 分层快照（≤60 行上限+滚动归档节奏）、decisions-index.md 裁定索引与主标准衔接、mailbox.jsonl done 消息定期清出机制，列剩余缺口清单。
2. 文档/索引层可零风险收尾项直接收尾；涉及基础设施代码（mailbox_loop.py 等）或信箱重写的项，列方案回报待监督线执行。

【文件域】
- docs/handoff/（STATE.md 等，盘点为主）
- docs/increments/（裁定索引、缺口清单文档）
- agents/（仅文档性改动；代码改动先回报方案）

【验收】缺口清单+处置结论一份，落 docs/increments/；引用化，禁贴全文。

【边界】.git 只读，改工作区后心跳回报，由监督线代提交；禁 push、禁 aoci_*"""

BODY_TRAE_11 = """S149 预先存在 11 失败核查修复 | i19/i20/i23 系列（S143④ 上报）

【根因】S143 全量回归 854 passed / 11 failed，11 个失败为预先存在（与 T67/T69 无关）：i19_preview_api×2（403≠200）、i20_preview_api×4（403≠200）、i23_mapping×4（mapper 错误码集缺 invalid_source_identity/incomplete_source_row 等）、i23_preview_api×1（200≠401 未鉴权）。

【任务】
1. 逐个定位 11 失败根因，先分清三类：用例预期过时 / 实现缺陷 / 环境依赖。
2. 属实现缺陷或用例过时的按最小改动修复；属环境依赖的记录阻塞回报。

【文件域】
- datara-backend/tests/rebuild/（相关测试）
- 必要时对应实现文件（最小改动）

【验收】对应用例全绿；全量 pytest tests/rebuild -q 不新增失败（基线 854P/11F → 目标 865P/0F）；证据落盘 docs/increments/evidence/。

【边界】.git 只读，改工作区后心跳回报，由监督线代提交；禁 push、禁 aoci_*"""

BODY_DEAD_NOTE = (
    "S149 信箱清理 | s129-c7c92b（T69 宿主实测）与 s129-b041b1（T67 dry_run 修复）"
    "已由你线 S143 交付并经监督线 S145 验收代提交（c267917），两条 TASK 已标 done，无需重复处理。"
    "同轮另派新单：预先存在 11 失败核查修复（见 TASK）。"
)


def main():
    msgs = read_mail(MB)
    marked = 0
    for m in msgs:
        if m.get("id") in DEAD_IDS and m.get("status") == "pending":
            m["status"] = "done"
            m["ack_ts"] = now()
            marked += 1
    appended = [
        envelope("Trae", "s129-c7c92b,s129-b041b1", BODY_DEAD_NOTE, "MSG"),
        task("Claude", "P1-6prime-finish", BODY_P1_6PRIME),
        task("Claude", "P-OPT-1-finish", BODY_P_OPT_1),
        task("Trae", "preexist-11-failures-i19-i20-i23", BODY_TRAE_11),
    ]
    out = msgs + appended
    tmp = MB + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(m, ensure_ascii=False) for m in out) + "\n")
    os.replace(tmp, MB)
    print(f"dead marked done={marked}/{len(DEAD_IDS)}; appended MSG=1 TASK=3; total lines={len(out)}")


if __name__ == "__main__":
    main()
