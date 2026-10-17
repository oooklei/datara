# P1-6 PoC 验收材料 · Trae 实施线侧（2026-10-17）

> 性质：P1-0 步骤 5 四项验收材料的本线侧产出（P1-6 评审=监督线）。BE 域（`ai_copilot/`、`tests/ai_copilot/`、pyproject/vendor）属 Codex 线，本线零触碰；BE 侧部分如实标注【转引】/【未实跑】，不谎称。O7 证据分级：【亲核】=Trae 主智能体实跑/实读；【转引】=他线产出仅登记路径。
> 测试真源：`datara-web/src/views/rebuild/validation/ai-assistant/aiToolsApi.contract.test.ts`（19 例）；复跑命令：`npx vitest run src/views/rebuild/validation/ai-assistant/aiToolsApi.contract.test.ts --reporter=verbose`（cwd=datara-web）。

## 材料一 A1-A7 门禁证据包（R8-B/FE 侧【亲核】）

### TDD 红绿时间线（git `--date=iso-local` 实锚）

| 步 | 提交 | 时间（+08:00） | 内容 |
|---|---|---|---|
| RED | c2841c6 | 2026-10-17 13:29:49 | `aiToolsApi.ts` 契约消费面 RED——八工具信封/注册表/错误码类型全量登记，工厂全方法拒绝 `R8A_BACKEND_NOT_WIRED`（P1-4） |
| GREEN | 3b8474c | 2026-10-17 13:34:01 | mockAgent 假 Agent 适配层（无 LLM 规则式 generate_sql + 8 工具注册表/信封/审计） |
| GREEN | f77d769 | 2026-10-17 13:34:06 | 契约测试 19 例全绿（冻结面/RED refuse/mock 全链路/错误映射/预算/审计回链） |
| 载体 | 83d16b8 | 2026-10-17 13:36:54 | R8-B 悬浮助手测试页（NL→SQL→授权确认→run_sql→结果+解释） |
| 载体 | d64afb0 | 2026-10-17 13:37:00 | 路由 `/rebuild/validation/ai-assistant` 登记 |
| 复跑 | — | 2026-10-17 19:38:54 | 注释级修订（cf260f4）后实跑：**Tests 19 passed (19)，Test Files 1 passed，Duration 388ms**（vitest v5.0.3） |

### 逐门禁状态（A1-A7，标准稿 v3 §3 口径）

| 门禁 | 状态 | 依据 |
|---|---|---|
| A1 TDD 红绿 | PASS（FE 侧） | 上表：RED（c2841c6，RED 注记+「every RED contract method refuses」用例）→ GREEN（f77d769），时间戳=git 提交实锚；复跑 19:38:54 仍绿 |
| A2 独立评审 | 待 P1-6 评审 | 本材料即评审输入；T-1 主交付物已 Codex 第 5 轮复验 PASS（24e29e0/#120）+监督收讫（#121）佐证本线评审链可信 |
| A3 证据成对 | 登记态如实声明 | FE 测试无截图面：以本文登记+可复现命令替代 JSON+PNG 成对；remote-final=本文 pathspec 提交入库即达 |
| A4 O7 诚实 | PASS | mock=假 Agent 无 LLM（隔离于 K1）如实声明；BE 侧未实跑处逐项标注；无偷懒隐瞒 |
| A5 复刻完备性 | N/A（PoC 载体） | R8-B 为 PoC 验收载体非复刻域；复刻对照=P1-7 融合对照清单（v2.3，全链闭环，规则⑥ fc0e9a9） |
| A6 契约冻结 | PASS | R8-A v1 冻结面零改动；本线唯一触达=cf260f4 注释词形（#147 裁定一，零逻辑/零枚举） |
| A7 红线 | PASS | 无 token/key 入库（K1 环境注入隔离）；mock run_sql 不触真库；结果以行数/摘要呈现不回传样本值 |

## 材料二 主权四条断言测试报告 + 跨项目隔离演示（BE 侧【转引】，本线未实跑）

- 测试真源：`datara-backend/tests/ai_copilot/test_adapter_sovereignty.py`（Codex 域未跟踪文件，本线未触碰未执行）；四条断言定义见 P1-0 步骤 2（①key 仅环境注入路径 ②generate_sql 不执行 ③上下文缺失抛 `SovereigntyContextMissing` ④记忆读写经 audit hook）。
- FE 侧镜像口径【亲核】：契约测试用例「sovereignty mirror: generate_sql without explicit user/project context throws」GREEN（复跑 19:38:54 在案）——mock 层与主权条款镜像一致。
- BE 实跑结果与跨项目隔离演示（两条 project 上下文互不可见）：**待 Codex 线随令提交，本文不代称 GREEN**。

## 材料三 成功判据演示（mock 全链路 API 证据【亲核】）

- 判据定义：自然语言→SQL→经授权执行→结果解释（P1-0 步骤 5.3；允许「录屏/API 证据」二选一，本文取 API/测试证据口径，无录屏）。
- 证据：契约测试用例「mock agent full chain without LLM (isolated from K1) > NL → generate_sql → (authorization gate) → validate_sql → run_sql → result + explanation」GREEN（复跑 19:38:54 在案）。
- UI 载体：`AiAssistantValidationView.vue` + 路由 `/rebuild/validation/ai-assistant`（d64afb0）。

## 材料四 锁版证明（锁定值【亲核】；pip freeze 快照【未实跑】如实标注）

- 锁文件：`datara-backend/requirements-ai-copilot.lock`——pip-compile `--generate-hashes` 生成（Python 3.12，`--find-links=vendor/ai_copilot/wheels`）。
- 锁定值【亲核 Grep】：`vanna[chromadb]==2.0.2`（pyproject.toml:9 / requirements-ai-copilot.in:3 / lock:2585）；`chromadb==1.5.9`（pyproject.toml:10 / .in:4 / lock:420）；精确 `==` 锁，无 `>=`/`~=` 自动升级通道。
- vendor wheel 缓存：`datara-backend/vendor/ai_copilot/`（README 注明 vanna==2.0.2 MIT）。
- **pip freeze 快照+锁文件 diff：未由本线实跑**——datara-backend 下未发现 venv 目录，BE 环境与 vendor/ 为 Codex 域在途产出（工作区未跟踪文件），待 Codex 线随令补交快照与 diff；本线未改动上述任何文件。

---

> 归属声明：本文仅登记 Trae 线 FE/R8-B 侧【亲核】证据与 BE 侧诚实缺口；BE 侧证据（A1 BE 时间线/主权四条实跑/跨项目隔离演示/pip freeze 快照）由 Codex 线按 P1-6 评审令另行落 evidence。评审口径以监督线 P1-6 为准。
