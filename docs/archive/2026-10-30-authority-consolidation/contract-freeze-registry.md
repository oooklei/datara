# 契约冻结登记簿

> 用途：G 组门禁验收（FE-13 ~ FE-19）逐门消费的契约冻结登记表。
> 条目格式：契约名 = 冻结提交号 + 测试文件 + 状态。
> 规则：每门验收时，FE 侧动作 = 验收执行 + 冻结令登记（提交号）；「前置依赖」列登记的后端/用户解阻事件不属 FE 实施范围，仅作派发门禁。
> 禁止在解阻前判定门通过。

---

## 一、登记簿条目格式

| 字段 | 说明 |
|---|---|
| 契约名 | 契约标识（如 R2-Variable / R5-A-SqlIde / I8-Stream） |
| 冻结提交号 | 后端契约冻结的 git commit short hash |
| 测试文件 | vitest 契约测试文件路径 |
| 方法数 | 契约方法清单长度 |
| 状态 | FROZEN / GREEN-WIRED / RED-PENDING / BLOCKED |
| 冻结日期 | 契约冻结日期 |
| 验收任务 | 对应 FE-13 ~ FE-19 任务号 |
| 备注 | 关键锚点（如 A5 fc2979e、分页 1..500 等） |

---

## 二、契约条目登记

### 2.1 底座契约

| 契约名 | 冻结提交号 | 测试文件 | 方法数 | 状态 | 冻结日期 | 验收任务 | 备注 |
|---|---|---|---|---|---|---|---|
| adapterKit | 0b1a4be（FE 提交；无后端契约） | `datara-newweb/src/services/rebuild/__tests__/adapterKit.test.ts` | N/A（共享原语） | GREEN | 2026-10-17 | FE-01/FE-02 | §2.1 命名映射 / §2.2 id 归一 / §2.3 包络三态 / §2.4 ContractApiError；测试 passed 52/52（192.168.1.9，§6.2） |

### 2.2 R2 变量契约

| 契约名 | 冻结提交号 | 测试文件 | 方法数 | 状态 | 冻结日期 | 验收任务 | 备注 |
|---|---|---|---|---|---|---|---|
| R2-Variable | 2d805f2 | `datara-newweb/src/services/rebuild/__tests__/variableApi.contract.test.ts` | 6 | GREEN-WIRED | 2026-10-17 | FE-16 | 七级优先级链 run>task>workflow>project>global>env>builtin；`VARIABLE_SCOPE_PRIORITY` 冻结；后端接线提交 2d805f2（rebuild/variables/api.py 6 端点）；测试 passed 17/17（192.168.1.9，§6.2） |

### 2.3 R4 依赖契约

| 契约名 | 冻结提交号 | 测试文件 | 方法数 | 状态 | 冻结日期 | 验收任务 | 备注 |
|---|---|---|---|---|---|---|---|
| R4-Dependency | 70b2e62 | `datara-newweb/src/services/rebuild/__tests__/dependencyApi.contract.test.ts` | 5 | GREEN-WIRED | 2026-10-17 | FE-15 | upstreamTaskCode string→int 哨兵转换；DEP_* 错误码透出；后端接线提交 70b2e62（rebuild/dependency/api.py 5 端点）；测试 passed 12/12（192.168.1.9，§6.2） |

### 2.4 R4 资源契约

| 契约名 | 冻结提交号 | 测试文件 | 方法数 | 状态 | 冻结日期 | 验收任务 | 备注 |
|---|---|---|---|---|---|---|---|
| R4-Resource | 51c88c3 | `datara-newweb/src/services/rebuild/__tests__/resourceApi.contract.test.ts` | 5 | GREEN-WIRED | 2026-10-17 | FE-15 | multipart 不手工设 Content-Type；RES_* 错误码透出；后端接线提交 51c88c3（rebuild/resources/api.py 5 端点）；测试 passed 12/12（192.168.1.9，§6.2） |

### 2.5 R4 同步契约

| 契约名 | 冻结提交号 | 测试文件 | 方法数 | 状态 | 冻结日期 | 验收任务 | 备注 |
|---|---|---|---|---|---|---|---|
| R4-Sync | f14fc5d | `datara-newweb/src/services/rebuild/__tests__/syncComponentApi.contract.test.ts` | 5 | GREEN-WIRED | 2026-10-17 | FE-13 | SYNC 契约解禁后验收；xfail 门禁处置核对；后端接线提交 f14fc5d（SYNC 域融合产出与 R4-SYNC 契约解禁）；测试 passed 5/5（192.168.1.9，§6.2） |

### 2.6 R5-A SQL IDE 只读契约

| 契约名 | 冻结提交号 | 测试文件 | 方法数 | 状态 | 冻结日期 | 验收任务 | 备注 |
|---|---|---|---|---|---|---|---|
| R5-A-SqlIde | fc2979e | `datara-newweb/src/services/rebuild/__tests__/sqlIdeApi.contract.test.ts` | 17 | FROZEN | 2026-10-14 | FE-13 | A5 fc2979e 冻结；分页 1..500 勘误锚定 `sqlIdeApi.ts:409`；`R5A_CONTRACT_METHODS` 17 方法冻结；fc2979e 为**后端契约文档**提交（`docs(sql-ide): draft A5 backend contract v1.0`，2026-10-18），非代码接线提交，保留原值未改写；测试 passed 9/9（192.168.1.9，§6.2） |

### 2.7 R5-B DDL 契约

| 契约名 | 冻结提交号 | 测试文件 | 方法数 | 状态 | 冻结日期 | 验收任务 | 备注 |
|---|---|---|---|---|---|---|---|
| R5-B-SqlIdeDdl | 0bbe08d | `datara-newweb/src/services/rebuild/__tests__/sqlIdeDdlApi.contract.test.ts` | 5 | RED-PENDING | — | FE-13 | RED 哨兵 `R5B_BACKEND_NOT_WIRED`；后端接线提交 0bbe08d（sqlIdeDdlApi 波2 五方法与契约 11 用例转通）；状态未上翻（见 §6.4）；测试 passed 11/11（192.168.1.9，§6.2） |

### 2.8 I7 调度契约

| 契约名 | 冻结提交号 | 测试文件 | 方法数 | 状态 | 冻结日期 | 验收任务 | 备注 |
|---|---|---|---|---|---|---|---|
| I7-Schedule | d7560e2 | `datara-newweb/src/services/rebuild/__tests__/scheduleApi.contract.test.ts` | 5 | RED-PENDING | — | FE-15 | RED 哨兵 `R6_SCHEDULER_NOT_WIRED`；后端接线提交 d7560e2（9-01 rebuild 调度端点补建）；状态未上翻（见 §6.4）；测试 passed 6/6（192.168.1.9，§6.2） |

### 2.9 R7 统计契约

| 契约名 | 冻结提交号 | 测试文件 | 方法数 | 状态 | 冻结日期 | 验收任务 | 备注 |
|---|---|---|---|---|---|---|---|
| R7-Metrics | 60cfa50 | `datara-newweb/src/services/rebuild/__tests__/metricsApi.contract.test.ts` | 6 | GREEN-WIRED | 2026-10-17 | FE-18 | MetricValue 透传不加工；runId wireIdToString 归一；后端接线提交 60cfa50（rebuild/metrics/api.py 6 端点）；测试 passed 15/15（192.168.1.9，§6.2） |

### 2.10 I8 流契约

| 契约名 | 冻结提交号 | 测试文件 | 方法数 | 状态 | 冻结日期 | 验收任务 | 备注 |
|---|---|---|---|---|---|---|---|
| I8-Stream | 826743d | `datara-newweb/src/services/rebuild/__tests__/streamApi.contract.test.ts` | 6 | GREEN-WIRED | 2026-10-19 | FE-13 | R8-STREAM 新域建模交付后验收；流表五张模型；后端接线提交 826743d（R8-STREAM 流表新域四模型+状态机）；测试 passed 1/1（另 `streamApiSurface.contract.test.ts` 2/2，192.168.1.9，§6.2） |

### 2.11 R8-A AI 工具契约

| 契约名 | 冻结提交号 | 测试文件 | 方法数 | 状态 | 冻结日期 | 验收任务 | 备注 |
|---|---|---|---|---|---|---|---|
| R8-A-AiTools | cd43668 | `datara-newweb/src/services/rebuild/__tests__/aiToolsApi.contract.test.ts` | 9 | RED-PENDING | — | FE-13 | RED 哨兵 `R8A_BACKEND_NOT_WIRED`；mock Agent 验证面 GREEN；后端接线提交 cd43668（AI 八工具接线 ai_tools+ai_bridge）；状态未上翻（见 §6.4）；测试 passed 19/19（192.168.1.9，§6.2） |

### 2.12 M2 批（2026-10-26，工作树未提交；对应 `datara-newweb/src/services/rebuild/CONTRACT_REGISTRY.md` §1 #28/#33/#34/#35）

| 契约名 | 冻结提交号 | 测试文件 | 方法数 | 状态 | 冻结日期 | 验收任务 | 备注 |
|---|---|---|---|---|---|---|---|
| M2a modelApi 数仓建模域 | 待监督线代提交（工作区未提交） | `datara-newweb/src/services/rebuild/__tests__/modelApi.contract.test.ts`（3）+ `views/__tests__/{modelListView,dwModelDesign,dwModelVersion,dwModelLineage,dwModelEr}.contract.test.ts`（9） | 22 | GREEN | 2026-10-26 | 门1 | A6-1~A6-22（M2a 扩登 8→22）；5 视图 `/model/list|design|version|lineage|er` |
| M2b API 管理面（视图 + 网关端点 G） | 待监督线代提交（工作区未提交） | `views/__tests__/{apiManagementView,apiKeyManagementView}.contract.test.ts`（3）+ `datara-backend/tests/rebuild/test_openapi_gateway_api.py`（8） | 12（#26）+1（网关） | GREEN | 2026-10-26 | 门1 | `/open/api`+`/open/key`；受控 facade only，禁任意 URL 代理；fail-closed 5041 |
| M2c 质量批 B 三视图 + run 端点 | 待监督线代提交（工作区未提交） | `views/__tests__/{qualityRuleView,qualityTaskView,qualityReadOnlyView}.contract.test.ts`（10） | 视图契约（消费 #22） | GREEN | 2026-10-26 | 门1 | `/qc/rule|task|exception|report|alarm`；structural 红线四字段恒 0 |
| M2d D-08 ADR 映射表 + D-09 upload 版本化迁移销账 | 待监督线代提交（工作区未提交） | `datara-backend/tests/rebuild/test_component_spec_upload_migration.py` | 后端域件 | GREEN | 2026-10-26 | 门1 | `rebuild/component_spec/migrations.py` + `v0002_component_catalog_upload.py` + `scripts/seed_rebuild_component_catalog.py` |

> **M2 批状态口径**：§二 本批条目状态按「工作树实测全绿」记 GREEN；「冻结提交号」按 §三.1 应为后端接线提交，M2 批工作树尚未提交，故按「待监督线代提交」口径登记（不因登记而倒填冻结日期）。前端契约层实态以 `CONTRACT_REGISTRY.md` §1 为权威（GREEN 35 / RED 0，冻结方法合计 215）。

---

## 三、冻结令登记规则

1. **FROZEN**：契约已冻结（后端提交号已登记），FE 侧验收通过，全条目 = 提交号 + 测试 passed。
2. **GREEN-WIRED**：FE 侧已接线，vitest 全绿，等待后端冻结令登记。
3. **RED-PENDING**：FE 侧契约为 RED 态（哨兵拒绝），等待后端接线后转 GREEN-WIRED。
4. **BLOCKED**：前置依赖未满足（后端建模/用户操作），禁止判定门通过。

---

## 四、逐门验收指引

| 门 | 验收任务 | 消费的契约条目 | 前置解阻事件 | FE 侧关键动作 |
|---|---|---|---|---|
| 门 1 API 契约冻结 | FE-13 | 全部 11 契约 | SYNC 解禁 / 工作流域建模 / R8-STREAM 建模 | 契约冻结登记簿全条目 = 提交号 + 测试 passed；三新域契约逐域复核 |
| 门 2 数据模型冻结 | FE-14 | — | 工作流域六模型建表 | 建表清单与 app.py 建表核对表登记；FE types 与表结构类型契约 vitest 全绿 |
| 门 3 节点协议冻结 | FE-15 | R4-Dependency / I7-Schedule | 节点配置协议建模冻结 | 30 子项逐项验收矩阵登记（每子项 = 测试用例 + passed） |
| 门 4 变量协议冻结 | FE-16 | R2-Variable | 变量域逐级验收收口 + FE-05 完成 | 七级优先级链逐级验收；入口全覆盖核对表登记 |
| 门 5 执行状态冻结 | FE-17 | I7-Schedule | 工作流域建模交付 + 1.9 授权 | 八能力逐项验收登记；CANCELLED/CANCEL_FAILED 终态实测 |
| 门 6 统计协议冻结 | FE-18 | R7-Metrics | 回写链路 1.9 实测环境 | 回写链路 Playwright 全链路；10 字段核对表登记 |
| 门 7 时间戳规范冻结 | FE-19 | — | 新表建表（随门 2） | 新表时间戳契约实测证据登记（每表 = 时间列清单 + NULL 检查 passed） |

---

## 五、变更日志

| 日期 | 变更 | 操作人 |
|---|---|---|
| 2026-10-19 | 初始登记簿模板建立（c27-fe-gates 任务） | Claude 实施线 |
| 2026-10-23 | dq2-T006 冻结登记补登：§2.1–§2.11 共 10 条空「冻结提交号」补入后端契约接线提交（adapterKit 为 FE 提交）；新增 §六 口径与偏差说明（192.168.1.9 实执行 28 files / 285 tests passed / EXIT=0）；**状态未上翻**（无条目标 FROZEN） | DEV 席 |
| 2026-10-23 | dq2-T006-R1 返工：① §2.1–§2.11「测试文件」列按 **R-07** 更正为 `datara-newweb` 实际路径（11/11）；② 各条目「备注」列**逐条绑定** passed 计数（adapterKit 52 / R2 17 / R4-dep 12 / R4-res 12 / R4-Sync 5 / R5-A 9 / R5-B 11 / I7 6 / R7 15 / I8 1+2 / R8-A 19）；③ §6.3 偏差标记已消除；口径 **R-06**、状态 **R-08** 未变 | DEV 席 |
| 2026-10-26 | M2 批登记（M3 统一核验 + 契约登记表收口）：新增 §2.12（M2a modelApi 22 方法 / M2b API 管理面 + 网关端点 G / M2c 质量批 B 三视图 + run 端点 / M2d D-08+D-09 迁移销账 四行）；状态按「工作树实测全绿」记 GREEN，「冻结提交号」按 §三.1 口径记「待监督线代提交」；前端契约层实态以 `CONTRACT_REGISTRY.md` §1 为权威（GREEN 35 / RED 0，冻结方法合计 215） | DEV 席 |

---

## 六、口径与偏差说明（2026-10-23 DEV 席补登）

> 本节由 dq2-T006 补登产生，用于向 Q-GATE 披露口径冲突与账实偏差；不改变 §二 既有状态判定，不构成门通过结论。

### 6.1 冻结提交号口径

- 本节补登的「冻结提交号」取 **后端契约接线提交**（`datara-backend/rebuild/**` 中实现该契约的 git commit short hash），依据 §三.1「FROZEN = 后端提交号已登记」。
- **例外 1**：`R5-A-SqlIde` 原登记 `fc2979e` 为**后端契约文档**提交（`docs(sql-ide): draft A5 backend contract v1.0`，2026-10-18），非代码接线提交；保留原值，未改写。
- **例外 2**：`adapterKit` 为 FE 共享原语，无后端契约，取 FE 提交 `0b1a4be`（FE-02 登记口径）。
- 并存三种口径（后端文档冻结件 / FE 提交 / 后端接线提交），本登记簿按 §三.1 采用**后端接线提交**口径。
- **回滚条件**：若 Q-GATE 裁定改用其他口径，本节 10 条提交号整体回滚为 `—` 并改按新口径重填。

### 6.2 测试 passed 记录（192.168.1.9 实执行）

- 环境：`192.168.1.9:/lei/datara-newweb-iso/datara-newweb`，Node v22.14.0，vitest 5.0.5，租约 SELF_SERVICE（无审批）。
- 命令：`npx vitest run src/services/rebuild/__tests__`
- 结果：`Test Files 28 passed (28)` / `Tests 285 passed (285)` / EXIT=0。
- 契约文件逐项（tests passed）：variableApi 17、dependencyApi 12、resourceApi 12、syncComponentApi 5、sqlIdeApi 9、sqlIdeDdlApi 11、scheduleApi 6、metricsApi 15、streamApi 1（另有 streamApiSurface 2）、aiToolsApi 19、adapterKit 52（共享原语，含于 28 files；192.168.1.9 单跑实测 `adapterKit.test.ts` 52 passed）。
- §二 各条目「备注」列已**逐条绑定**本条对应 passed 计数（不再仅集中披露）。

### 6.3 测试路径偏差（已按 R-07 更正）

- §二 各表「测试文件」列原沿用模板期登记的 `datara-web/...` 路径；权威设计 v3 §2.5 / L105 已裁定 `datara-web` 冻结不动、`datara-newweb` 为正式产品前端。
- 实测：192.168.1.9 上 `datara-web` 四处副本（`/lei/datara`、`/lei/datara-i11-work`、`/lei/datara-i13-work`、`/lei/tmp/datara-codex-test`）均无 `src/views/rebuild/validation/` 目录 → 原声明路径在 1.9 不可执行；契约测试实际位于 `datara-newweb/src/services/rebuild/__tests__/`（可执行，见 §6.2）。
- **处置（dq2-T006-R1，2026-10-23）**：依 Q-GATE 裁定 **R-07**，§2.1–§2.11 全部「测试文件」列已更正为 `datara-newweb/src/services/rebuild/__tests__/<file>` 实际可执行路径（11/11 条）；本节偏差**已消除**。
- **回滚条件**：若裁定 §二 路径以 `datara-web` 为权威且不可改，则 §6.2 证据仅作参考，门 1 测试 passed 记录判为未成立，§二 路径回滚为原 `datara-web/...` 值。

### 6.4 状态口径与账实偏差（未上翻，待裁定）

- 本节补登**未上翻任何状态**：`GREEN-WIRED` 与 `RED-PENDING` 均按原登记保留，**无条目标 `FROZEN`**（依 dispatch anchor §四 硬约束）。
- 已知账实偏差（供 Q-GATE 裁定，本席未自行改写）：
  - `datara-newweb/src/services/rebuild/CONTRACT_REGISTRY.md` §1 记 `sqlIdeDdlApi` GREEN(5/11)、`aiToolsApi` GREEN(9/19)、`scheduleApi` RED(5/6)；
  - 192.168.1.9 实执行三者契约测试文件均通过（11 / 19 / 6 tests passed，见 §6.2）。
- **冻结日期未回填**（依 dispatch anchor §四 边界「不因登记而倒填冻结日期」）；故已补登提交号的条目其「冻结日期」列仍为 `—` 或模板原值，二者不作为冻结生效判据。
