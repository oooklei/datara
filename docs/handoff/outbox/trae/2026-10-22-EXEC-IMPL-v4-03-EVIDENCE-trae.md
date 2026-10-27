# EVIDENCE_READY — IMPL-v4-03（trae 载体）

- **票据**：IMPL-v4-03 · C 组测试基建：datara-newweb/e2e + playwright.config.ts + datara-l12-e2e
- **域/优先级**：VALIDATION / P2 / 依赖 DEC-v4-D02（v3-0006 已裁定）
- **指派锚**：`v3-0017-dispatch-assigned-impl-v4-03`（fl-dispatch-impl-v4-03.json）
- **载体**：trae（Execution）；**实施性质**：D02 唯一文件修改 + 四路径静态稽核（本机零远测）
- **日期**：2026-10-22

## 1. 实施（唯一代码变更）

`datara-newweb/tsconfig.node.json` 按 **DEC-v4-D02** 裁定扩展 include：

```json
"include":["vite.config.ts","vitest.config.ts","playwright.config.ts","e2e/**/*.ts"]
```

- tsconfig.app.json（dom 工程）未动（裁定明示不动）。
- 该文件为票据四路径中唯一"已跟踪未修改"项，其余三路径均为未跟踪新料（见 §4 git 盘点）。

## 2. 静态验收核验（全部本机执行，零环境触达）

| # | 命令（cwd=datara-newweb） | 结果 | 判定 |
|---|---|---|---|
| 1 | `npx tsc --noEmit -p tsconfig.node.json` | exit=0，零诊断 | **GREEN（验收原文项）** |
| 2 | `npx tsc -p tsconfig.node.json --listFilesOnly` | 含 `playwright.config.ts`、`e2e/llm-models.spec.ts` 两文件 | D02 include 正向生效证据 |
| 3 | `npx playwright test --list`（collect-only，无 webServer，不触 1.9） | exit=0，**7 tests in 1 file**（§5E.1 六件套闭环 01–07 全部可收集） | 套件可运行前提成立 |
| 4 | NO_SECRET 扫描（password/secret/token/api_key 字面量，票内全部路径） | 零命中 | PASS |

注 1：spec 内 `sk-datara-e2e-primary-9911` 系注释明示的本地伪 key（仅入库密文、不出网），非凭据；鉴权一律 `E2E_PASS` 运行时注入，值禁入静态产物/URL/证据（红线 8 / S6）。
注 2：`playwright test --list` 仅解析配置与收集用例标题，不启动浏览器、不发起任何网络请求，属静态校验范畴。

## 3. 四路径逐项稽核结论

| 路径 | 状态 | 结论 |
|---|---|---|
| `datara-newweb/e2e/llm-models.spec.ts` | 新料（未跟踪） | 完整可审：鉴权 fixture（login 换 token + addInitScript 注入 + route 层 Bearer 补写）、路由承载前置闸（R1 窗口 skip 语义，R2 票承接 routes.ts）、六件套闭环 7 用例、证据成对落档（PNG + evidence json，afterAll 落盘）。与 llmApi 契约、后端 409/4092 口径一致（含 D04 修正后的注释串口径） |
| `datara-newweb/playwright.config.ts` | 新料（未跟踪） | 完整可审：testDir=./e2e、`workers:1`+`fullyParallel:false`（共享可变表防污染）、`retries:0`（RED/GREEN 证据不覆盖）、baseURL 走 `E2E_BASE`（缺省 `http://192.168.1.9:18091`，禁 8090 口径一致）、无 webServer（复用 1.9 部署栈） |
| `datara-newweb/tsconfig.node.json` | **本票唯一修改** | D02 已落，见 §1；验收命令 GREEN |
| `datara-l12-e2e/`（8 文件） | 新料（未跟踪） | 既有 L12-02 环境侧工装完整：l12-02.e2e.mjs（F1–F5 全段）、probe-auth/probe-flow、diag-*、evidence/result.json（token_len 计数、无凭据落盘）、package.json（playwright ^1.64.1）。newweb e2e 的 route 层 Bearer 补写工装即沿用于此。**零改动**，按票据纳入验收链登记 |

## 4. git 盘点（本席不 commit；集成窗 pathspec 物料）

```
 M datara-newweb/tsconfig.node.json   ← 本票唯一修改
?? datara-l12-e2e/
?? datara-newweb/e2e/
?? datara-newweb/playwright.config.ts
```

建议集成窗 pathspec：`git add -- datara-newweb/e2e datara-newweb/playwright.config.ts datara-newweb/tsconfig.node.json datara-l12-e2e`。
注意：`datara-l12-e2e/evidence/` 与 `datara-newweb/e2e/evidence/`（后者本机尚不存在，运行时生成）为运行期证据产物，是否入库请 Flow 在集成窗裁定（历史惯例：证据件随票入库归档）。

## 5. 移交 Integration（1.9 远测链）

- 验收链后续：**EVIDENCE_READY → 1.9 ENV_VERIFIED → PASS → 集成窗提交**。1.9 执行项：`npm i`（如需）+ `npx playwright install chromium`（如需）+ `npx playwright test`（需注入 `E2E_PASS`；连通性缺省走不可路由端点失败路径，无需真实 LLM 凭据；`E2E_LLM_TEST_BASE/KEY` 仅 D4 放行后注入）。
- datara-l12-e2e 为独立 harness（自带 package.json，本机未装依赖）：1.9 侧按其既有方式运行；若纳入验收链需在该目录 `npm i`，请 Integration 按租约安排。

## 6. 报 Ops/Flow 事项（非阻塞观察）

1. **composite 工程产物扩散**：node 工程 include 扩展后，`npm run build`（`vue-tsc -b`）将额外发射 `e2e/*.js/.d.ts`、`playwright.config.js/.d.ts`（与既有 `vite.config.js` 发射同类，gitignore 已覆盖旧四类、未覆盖新四类）。`.gitignore` 不在本票 paths 内，未动；请后续文档/卫生窗裁定是否补 gitignore 条目或改 emit 策略。
2. e2e 证据目录（运行时生成于 e2e/evidence/）是否随集成窗入库，见 §4 待裁定。

## 7. 状态链与边界遵守

- 本席动作：1 文件修改（tsconfig.node.json，票内路径）+ 静态核验 + 本证据件；**未跑任何远测、未触 1.9、未写 STATE/mailbox/队列投影、未 commit、未 push**（push=USER_ONLY）。
- WIP：trae=1（本票），无超领；IMPL-v4-05 READY 未指派本线、无用户领取指令，未动。
- AOCI：未加载、未调用。

—— Execution（trae），IMPL-v4-03 EVIDENCE_READY 提交，待 Acceptance 审查。
