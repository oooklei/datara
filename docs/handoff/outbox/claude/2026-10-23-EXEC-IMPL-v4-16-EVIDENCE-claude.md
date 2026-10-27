# IMPL-v4-16 · EVIDENCE（本地段）· EXEC-3

- **席**：Execution EXEC-3（claude 载体）｜**票**：IMPL-v4-16（17.3 集群监控页组件段）
- **派单**：v3-0060-dispatch-assigned-impl-v4-16（票面 `fl-dispatch-impl-v4-16.json`，`assigned_to: claude (EXEC-3)`，本席承接无歧义；EXEC-1 已声明不领 EXEC-3 面票）
- **时间**：2026-10-23T02:2x+08:00｜**水位**：v3-0060
- **本机结果口径**：A5-E2 裁定后——本机仅静态校验，全部本机输出 **DIAGNOSTIC_ONLY_NOT_PASS_EVIDENCE**；组件测试执行移交 1.9 面（租约请求已先行落件，先于任何 1.9 执行）

## 1. 路径实存清单（2/2，均在票面 `paths` 内）

| 路径 | 状态 |
|---|---|
| `datara-newweb/src/views/depops/MonitorView.vue` | 新建（≈150 行，组件段，无路由/菜单改动） |
| `datara-newweb/src/views/__tests__/monitorView.contract.test.ts` | 新建（6 用例） |

**无越界路径声明**：本席本次落盘仅上述 2 件 + 本 outbox 证据件；未触 `router/routes.ts`、`navigation/menu.ts`（FE-SHELL 锁在 07）、未触 `monitorApi.ts` 与任何后端件（git status 本席足迹仅 2 个 `??` 新文件，其余工作区改动均为他席既有状态）。

## 2. 静态检查（三项 EXIT=0）

| 项 | 命令 | 结果 |
|---|---|---|
| 全量类型 | `npx vue-tsc -b` | **EXIT 0**（含新测试件类型面） |
| node 侧类型 | `npx tsc --noEmit -p tsconfig.node.json` | **EXIT 0** |
| NO_SECRET | 对 2 件交付物做凭据模式 grep（password/secret/token/api_key/AKIA/OPENSSH 等） | **0 命中** |

## 3. FE↔BE 契约对拍（验收 ①②③ 的字段面核对）

- 取数：视图仅 `createMonitorContract().fetchMonitorNodes()`（组件内单例构造），**零直连 fetch/axios**（源文件 grep 无 `fetch(`/`axios` 调用）。
- 快照面：`zkAvailable`/`generatedAt` 头部呈现（`data-zk`/`data-generated`）；节点行 10 字段与 `MonitorNode`（module/node/cpu/mem/memUsedMb/memTotalMb/disk/heartbeat/metricState/lastSeen/tags）逐项对齐，与后端 `rebuild/monitor/service.py` 输出字段一一对映（ssh 行 cpu/mem/disk 恒 null、metricState 恒 unsupported——后端冻结行为如实承接）。
- 如实性红线：null → `—`；`heartbeat=unknown` → 「未知（无法判定）」+ ZK 徽标红态；`stale` → 「过期」；`unsupported` → 「不支持」；页脚 note 固化口径（90s TTL、手动刷新不轮询）。
- 非 0 包络码：monitorApi 经 `preserveEnvelopeCode` 保码，视图 catch 后按 `加载失败（code X）：msg` 透出（用例 4 断言）。
- 三态：loading（role=status）/空（data-empty，区分「未加载」与「节点空」）/错误（role=alert，独立横幅，刷新失败保留表格不闪空）。

## 4. 组件测试清单（6 用例，候 1.9 面 GREEN）

| # | 用例 | 对应验收 |
|---|---|---|
| 1 | 混合模块三行（master/worker/ssh）+ 全字段覆盖（cpu/mem/memMb/disk/lastSeen/tags/zk/generatedAt） | ② |
| 2 | 空指标全 `—` + stale「过期」/unsupported「不支持」/heartbeat unknown「未知（无法判定）」+ ZK 不可用徽标 | ③ |
| 3 | 空态（nodes=[]）无空壳表 | ④ |
| 4 | 非 0 包络码错误横幅（code 5002 + msg）无空壳表 | ④ |
| 5 | 刷新失败保留上次快照（表格不闪空） | ④ |
| 6 | 手动刷新换新数据 + 无轮询（恰 2 次调用：挂载 1 + 手动 1） | ④/⑤ |

## 5. 1.9 段（未执行，候租约）

- 租约请求：`2026-10-23-EXEC-IMPL-v4-16-lease-request.md`（RT-IMPL-V4-16-MONITOR-COMPONENT，**先于任何 1.9 执行**）。
- 1.9 面：`vitest run src/views/__tests__/monitorView.contract.test.ts`（可并入在途 RT 队列单环境串行）。

## 6. 资源自报

- 本轮轮次数：1（领票→实施→静态校验→证据面）｜空转比自估：0（产出轮）｜子智能体实际运行数：0（未消耗配额）

—— Execution EXEC-3（claude），本地段 EVIDENCE_READY 呈递，候 Integration 租约回执。
