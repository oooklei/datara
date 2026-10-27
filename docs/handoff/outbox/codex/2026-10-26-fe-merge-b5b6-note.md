# 字条：阶段 0 快照已落地 → 续作 B5/B6（致 Codex）

| 项 | 值 |
|---|---|
| 时间 | 2026-10-26（用户侧写于 D 盘主检出） |
| 收件 | Codex（worktree `C:\Users\Administrator\.codex\worktrees\c63c\Datara`，分支 `codex/datara-target-completion`） |
| 关联 | 权威交接单 `docs/handoff/2026-10-26-前端融合纳入-交接-codex.md`（§3 冲突 D / §4 B1~B6 / §5 优化 / §8 回执），本字条是它的续作补充，不替代 |
| 回执 | 每票完成照 §8 写八字段回执 JSON 至本目录；证据续写 `.codex-evidence/FE-MERGE-B5/`、`FE-MERGE-B6/` |

---

## 0. 快照落地（你离线期间由用户侧完成，勿重做）

| 动作 | 落点 |
|---|---|
| c63c 三回合工作树**整树提交** | `71ed3540` @ `codex/datara-target-completion`，tag **`snapshot/fe-merge-c63c-20261026`**（54 文件，+7494/−953；含冲突 D 合并版、B1~B4、quality / feMergeB3Assets 测试） |
| 证据链备份 | `D:\需求\数据治理工具\Datara\docs\evidence\2026-10-26-c63c-snapshot\`（374 文件 = codex-evidence 全量 + backend 证据） |
| D 盘 main r6 快照提交 | `7c14ae31` @ main（B1 三件套 `styles/theme.css` + `main.ts` + `tsconfig.node.json`；SshNode r6；`system/llm-models/` 两页；COPY_LEDGER #16/#17/#18） |
| 实测基线 | c63c：vitest **96 文件 / 816 用例全绿**、`vue-tsc -b` EXIT=0（2026-10-26 独立复跑，非采信日志） |

> `.codex-evidence/` 保持 untracked（既有约定），已有 D 盘完整副本，worktree 即使被清理也不丢。

---

## 1. 续作 B5（冲突件并集，交接单 §4）

### 1a. 三组文件**直接从 D 盘工作区抄入 c63c**（均为用户已批裁定，勿重新发明）

| D 盘源文件 | 内容 | 配套测试同步抄 |
|---|---|---|
| `datara-newweb/src/services/rebuild/streamApi.ts` | ruling fix #2：`I8_PERMISSION_MATRIX` 九键（用户已批「勿回退」） | `src/services/rebuild/__tests__/streamApi.contract.test.ts` |
| `datara-newweb/src/services/rebuild/syncComponentApi.ts` | C4 并集（约 48 行增量） | `src/services/rebuild/__tests__/syncComponentApi.contract.test.ts` |
| `datara-newweb/src/views/resources/ResourceManagementView.vue` | ruling fix #4：默认 `kind='sql'`（约 L45） | `src/views/__tests__/resourceManagementView.contract.test.ts`（L20/L29/L60） |

### 1b. IdeView / LoginView r6 版在 D 盘 `stash@{2}`（已验证含 `PILL_CLASS` 与令牌注释）

- 取法（**只读提取，严禁 pop / drop**）：`git show 'stash@{2}:datara-newweb/src/views/ide/IdeView.vue'`、`git show 'stash@{2}:datara-newweb/src/views/LoginView.vue'`（stash 为全 worktree 共享 ref，c63c 内可直接取）
- 并集口径（交接单 B5）：stash 版（r6 令牌化 + `.pill` 全局去重）为体、融合 T5 变量三要求为补；落地后 ide 契约测试不回退（交接单口径 13 例）、`loginView.contract.test.ts` 5 例不回退
- `routes.ts`（C1/C2 路由归一）同在 stash@{2}，按方案并入

---

## 2. 续作 B6（测试资产入库，交接单 §4）

D 盘现成，抄入 c63c 后入库：`playwright.config.ts`、`e2e/`、`deploy/DEPLOY-1.9.md`；`.gitignore` 增补 `playwright-report/`、`playwright.config.js`、`playwright.config.d.ts`（编译产物不入库）。
注：`tsconfig.node.json` 已含 `playwright.config.ts` + `e2e/**/*.ts` include（随 `7c14ae31` 入库），B6 落地即闭环。

---

## 3. 收编预裁定（阶段 2 用，先记不用）

c63c → main 收编时的 3 个预期冲突：

1. `main.ts`：main 侧多 2 行令牌注释 —— **任取**（零功能差）
2. `SshNodeManagementView.vue`：c63c 版多 `credVisible` 显隐复位（模态打开时） —— **取 c63c**
3. `LlmModelFormDialog.vue`：c63c 版多 longcat provider（对齐后端 T1 `cc9f92f5`） —— **取 c63c**

废弃件：D 盘根级 `src/views/ResourceManagementView.vue`（136 行重复件，归一裁定 `views/resources/` 为正本）收编时删除。

---

## 4. 纪律（不变，重申）

1. 三层 stash（`stash@{0}` layer3 / `@{1}` layer2 / `@{2}` 42 件冲突面）在 IdeView/LoginView 并集**验证通过前一律不 pop / 不 drop**；
2. 按文件名精确 `git add`，**严禁 `-A` / `add .`**；
3. 每批双验证：`npx vitest run` 全量（基线 816 绿不得回退）+ `npx vue-tsc -b` EXIT=0；
4. 提交格式 `feat(newweb): [F-xx] ...`；
5. `.git` 提交仍由用户侧把关，你按边界执行（完成后回执即可）。
