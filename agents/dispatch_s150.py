#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dispatch_s150.py — S150 四项裁定落地派单（监督线程序化写信箱，参照 dispatch_s149.py）

用户裁定（2026-10-20）：
1. Codex 掉线期间 T46r/T47r/T48r 三单转派 Trae；
2. P0-4 R4-SYNC 重派（推翻 53990fb 旧终裁"不派发"）——与 T46r SYNC 域同源，并入 T46r 单；
3. FE-01/02/05/06 暂缓（用户要审前端方案），不派单，仅 STATE.md 留痕。

动作：追加 3 条 TASK to=Trae。串行序：先在飞 s149 单（11 失败修复）→ T46r → T47r → T48r。
"""
import json
import os
import uuid
from datetime import datetime

MB = os.path.join("docs", "handoff", "mailbox.jsonl")

BOUNDARY = "【边界】.git 只读，改工作区后心跳回报，由监督线代提交；禁 push、禁 aoci_*。串行提示：先完成在飞单 s149（11 失败修复），再按 T46r→T47r→T48r 顺序执行，每单交付后心跳回报等验收。"


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
        "id": f"s150-{uuid.uuid4().hex[:6]}",
        "ts": now(),
        "from": "监督员",
        "to": to,
        "type": mtype,
        "ref": ref,
        "body": body,
        "status": "pending",
    }


BODY_T46R = """S150 T46r | SYNC 新域收口 + P0-4 R4-SYNC 重派接线（RED→GREEN）

【根因】两处同源缺口：①SYNC 契约已提交 898ea68 但收口未完成——缺陷 D1（缺 sync_adapter.py 接入共享执行层）、D2（统计 8 项计数无落库路径）、D3（血缘回写无写入路径）、D7（产出未提交，SYNC-06 核心已起草未跟踪、SYNC-01/02/03/05 已实现未提交）；②P0-4 R4-SYNC 接线（RED→GREEN）原终裁不派发（53990fb），2026-10-20 用户裁定推翻重派，并入本单。

【任务】
1. 真源：docs/increments/2026-10-19-WBS-SYNC新域任务分解.md（SYNC-01~09），完成剩余项（含 SYNC-09 统计与血缘落库 D2/D3 修复）。
2. 出 sync_adapter.py 接入共享执行层（D1）；核查补齐未提交产出（D7）。
3. R4-SYNC 接线 RED→GREEN：test_r4_sync_contract_pending / test_r4_sync_domain 契约解禁转绿，syncComponentApi 前后端接线。

【文件域】
- datara-backend/rebuild/sync/、datara-backend/rebuild/api/app.py（如需挂载）
- datara-backend/tests/rebuild/test_r4_sync_*.py 等对应用例
- datara-web/src/services/rebuild/syncComponentApi.ts、views/rebuild/validation/sync-form/（契约层最小改动）
- docs/increments/（证据，落 docs/increments/evidence/SYNC/）

【验收】对应用例全绿（含 xfail 解禁）；全量 pytest tests/rebuild -q 不新增失败（以当时基线为准）；证据落盘。

""" + BOUNDARY

BODY_T47R = """S150 T47r | 流表域 STREAM 剩余 8 项收口

【根因】STREAM 已完成 04/05/07/08，剩余缺口：STREAM-01（app.py 未挂载 stream router + create_all 缺 5 表）、STREAM-03（缺 8×8 全矩阵测试）、STREAM-06（streamApi.ts 全 RED I8_STREAM_NOT_WIRED）、STREAM-09（engine.py _pipeline_once 只写 Redis）、STREAM-10（StreamValidationView.vue RED 骨架）、STREAM-11（alert.py 缺失）、STREAM-12（验收）。

【任务】真源：docs/increments/2026-10-19-WBS-流表域任务分解.md，按关键路径完成 STREAM-01→STREAM-06→STREAM-09→STREAM-10→STREAM-11→STREAM-03→STREAM-12（含 app.py 挂载 + engine 上报 + alert）。

【文件域】
- datara-backend/rebuild/stream/、datara-backend/rebuild/api/app.py（挂载）
- datara-backend/tests/rebuild/test_stream_*.py
- datara-web/src/services/rebuild/streamApi.ts、views/stream/（契约层最小改动）
- docs/increments/（证据，落 docs/increments/evidence/）

【验收】pytest+vitest 对应用例全绿；观摩页 12 指标；全量 pytest tests/rebuild -q 不新增失败；证据落盘。

""" + BOUNDARY

BODY_T48R = """S150 T48r | 运行实例域 EXEC 收口（含 2 个 P0 缺陷）

【根因】EXEC 建表+三态+attempt 隔离+旧线融合未收口，含 P0 缺陷：M-EXEC-07（repository.py record_result_stat 不区分 instance_type，TRIAL 统计污染）、N-EXEC-05b（execution 六表未注册 lifespan）。

【任务】真源：docs/increments/2026-10-19-WBS-运行实例域任务分解.md，完成 EXEC-01~11 + M-EXEC-07（TRIAL/FORMAL 统计隔离）+ N-EXEC-05b + N-EXEC-07s（细节以 WBS 文档为准）。

【文件域】
- datara-backend/rebuild/execution/
- datara-backend/tests/rebuild/test_execution_*.py
- docs/increments/（证据，落 docs/increments/evidence/EXEC/）

【验收】pytest 全绿；三态状态机+时间戳契约；TRIAL/FORMAL 统计隔离断言；全量 pytest tests/rebuild -q 不新增失败；证据落盘。

""" + BOUNDARY


def main():
    msgs = read_mail(MB)
    appended = [
        envelope("Trae", "T46r-sync+p0-4-r4-sync", BODY_T46R, "TASK"),
        envelope("Trae", "T47r-stream", BODY_T47R, "TASK"),
        envelope("Trae", "T48r-exec", BODY_T48R, "TASK"),
    ]
    out = msgs + appended
    tmp = MB + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(m, ensure_ascii=False) for m in out) + "\n")
    os.replace(tmp, MB)
    print(f"appended TASK=3 (T46r/T47r/T48r -> Trae); total lines={len(out)}")


if __name__ == "__main__":
    main()
