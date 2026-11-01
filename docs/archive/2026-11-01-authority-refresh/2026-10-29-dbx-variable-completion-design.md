---
design_type: feature
created_at: 2026-10-29
---

# dbx SQL 编辑器 datara 变量补全与语法融合 —— 设计

## Intent Contract

**intent**：修复 dbx SQL 编辑器（`/ide`）中输入 `$` 无法带出 datara 变量管理变量名的缺陷；在保留 datara 既有 `${scope.name}` 引用口径的前提下，与 dbx 原生占位符语法及各数据库变量体系（MySQL `@`/`@@` 等）无冲突地融合，并让补全候选展示变量现值、类型与脱敏信息。

**constraints**：

* dbx 镜像**固定版本，禁止升级**；不重编 dbx Rust 二进制，仅对前端 dist 打补丁，1.9 原地构建、验证后同步本机备查。

* datara 变量引用语法**统一为** **`${scope.name}`**，与资源管理页 [CodeEditor.vue](file:///d:/需求/数据治理工具/Datara/datara-newweb/src/components/CodeEditor.vue)、`VAR_REF_RE` 及后端 `checkReference` 解析口径保持一致，用户不换习惯。

* dbx 原生占位符能力（`?` / `:name` / `#{name}` / `@set` / sqlserver `@name`）在非 datara 变量场景下**不得被破坏**；`@@` 前缀语法归属各数据库系统变量，datara 变量**不使用** **`@@`**。

* 敏感变量现值**脱敏展示**，不得在补全候选中泄露明文。

* datara 变量在 IDE 内只读注入，不在 dbx 内实现变量编辑。

**success\_criteria**：

* dbx SQL 编辑器内输入 `$`（或 `${`、`${env.`）即弹出 datara 变量补全，候选含变量名、现值、类型，敏感变量显示 `***`。

* 接受补全后落库文本为 `${scope.name}`，且 dbx **不再**把它识别为 shell 占位参数、不弹参数填写对话框。

* `${env.db_host}` 等引用可正常执行，由 datara 侧完成变量替换。

* MySQL `@@system_var` / `@@global.x` 系统变量在 dbx 内**不受影响**，仍可正常书写与补全。

* dbx 原生非 datara 占位符（`?`/`:name`/`#{name}`/`@set`）行为与打补丁前一致。

**risk\_level**：medium（纯前端 dist 补丁，可回滚；不涉及鉴权面与数据模型变更）

## Verification Contract

```
verify_steps:
  - check: dbx 补丁源码中补全源的 label 口径含 `${` 前缀，且 from 指向 `$`
  - check: dbx 执行编排层（tryExecute/tryExplain/prepareMultiExecute）对命中已注册 datara 外部变量的 `${...}` 优先替换、不弹参数对话框
  - check: dbx 原生占位符语法开关行为未变（`?`/`:name`/`#{name}`/`@set`/sqlserver `@name`）
  - check: 1.9 原地 `pnpm build` 成功，dist 产物含补丁代码（grep 关键字段）
  - check: 部署后 8090/ide 与本地 dist 的 index.html 与 chunk 清单一致
  - check: browser-use E2E 在 192.168.1.9:8090/p/<project>/ide 输入 `$` 弹出补全、接受后文本为 `${scope.name}`、无参数对话框
  - check: E2E 敏感变量现值显示为 `***`，普通变量显示现值与类型
  - check: E2E 书写 MySQL `@@global.max_connections` 不触发 datara 变量补全、不弹参数对话框
  - check: 宿主变量下发链路（`datara:variables` → `datara:variables-ack`）在实测中确有数据到达编辑器
```

## Governance Contract

```
approval_gates:
  - 采用 `${scope.name}` 统一语法并让 dbx 参数解析豁免 datara 变量 —— 需人工批准
  - 补全候选展示现值/类型/敏感脱敏 —— 需人工批准
  - dbx 前端 dist 补丁与 1.9 原地构建 —— 需人工批准
rollback: 还原 dbx 前端补丁文件至打补丁前快照，重新 `pnpm build` 覆盖 dist；datara 侧无改动则无需回滚
ownership: 用户裁定语法路线与展示口径；本 agent 负责设计、补丁实施与 1.9 验证证据
```

## Scope

| 维度  | 内容                                                              |
| --- | --------------------------------------------------------------- |
| In  | 修复 dbx 外部变量补全源的候选标签口径，使 `$` 前缀可匹配                               |
| In  | 执行编排层（`tryExecute`/`tryExplain`/`prepareMultiExecute`）优先用外部变量注册表解析占位符     |
| In  | 补全候选展示变量现值、类型与敏感脱敏                                              |
| In  | 1.9 原地构建 dbx dist、部署验证、同步产物到本机备查                                |
| In  | 新增/更新 dbx 前端契约测试（补全源 + 参数豁免）                                    |
| Out | 不重编 dbx Rust 二进制，不升级 dbx 版本                                     |
| Out | 不改动 datara 侧 `VAR_REF_RE`、后端 `checkReference` 与资源管理页语法          |
| Out | 不让 datara 变量使用 `@@` 前缀                                          |
| Out | 不破坏 dbx 原生占位符语法（`?`/`:name`/`#{name}`/`@set`/sqlserver `@name`） |
| Out | 不在 dbx 内实现变量编辑或变量管理界面                                           |

## Decisions

**D1 —— 引用语法统一为** **`${scope.name}`，不换前缀。**
datara 侧 `VAR_REF_RE`、资源管理页补全、后端 `checkReference`/`previewResolution` 已全部是 `${scope.name}`。改用其他前缀会造成两套语法并存、用户需记两种写法，收益为负。因此采纳方案 A（融合），而非方案 B（换 `{{}}` 前缀）。

**D2 —— 补全候选标签必须包含** **`${`** **前缀，这是** **`$`** **不出补全的根因。**
CodeMirror `sortOptions()` 以候选源 `from..to` 区间的文档文本作为模糊匹配 pattern，与每个候选的 `label` 做子序列匹配。当前 dbx 侧 `from` 指向 `$`、`label` 为 `scope.name`（不含 `$`），pattern `$` 在 label 中找不到该字符，全部候选被过滤，故无补全弹出。资源管理页 [CodeEditor.vue](file:///d:/需求/数据治理工具/Datara/datara-newweb/src/components/CodeEditor.vue) 的 label 为 `${scope.name}`（含 `${}`），故正常。**修复即把 dbx 候选 label 口径对齐资源管理页**，`apply` 已是完整 `${scope.name}`，无需改动。

**D3 —— 在 dbx 执行编排层用外部变量注册表优先解析占位符，避免** **`SqlParameterDialog`** **拦截。**
dbx `shell` 占位语法 `${name}` 默认开启，且参数名正则显式允许点号，`${env.db_host}` 会被判定为 shell 参数并在执行时弹参数填写对话框，拦截 datara 变量。

**实施机制（落地后修订）**：不改共享解析器 `sqlParameters.ts`。原因是 `readSqlBracedParameterAt` 同时被 `sqlStatementRanges.ts` 与 `executableStatementRangeCache.ts` 用于 mybatis 语句切分判定，在其内部加豁免会波及语句范围识别。

改在编排层 `composables/useSqlExecution.ts`：dbx 本已存在 `tryExternalSqlParameters(sql, connection)`（`useSqlExecution.ts:358`）——它用与原生一致的 `extractSqlParameterDescriptors` 抽取全部占位符，逐个到 datara 外部变量注册表 `lookupExternalVariable(scope.name)` 取值；**全部命中则直接替换并执行，任一未命中返回 `null` 交回原生参数对话框**。

该方法此前只在 `tryExecute` 中接入（`useSqlExecution.ts:262`），`tryExplain` 与 `prepareMultiExecute` 遗漏，导致 EXPLAIN 与多库执行仍弹参数框。本轮在 `tryExplain`、`prepareMultiExecute` 两处补入同样的编排（顺序：外部变量解析 → 原生参数对话框 → 原样执行）。

行为等价于「命中已注册 datara 变量则豁免」：命中即被外部值替换、不弹框；未命中仍走原生 shell 参数流程，原生能力不受损。

**D4 ——** **`@@`** **不作为 datara 变量语法，且与 datara 变量无冲突（结论）。**
`@@` 是 dbx 内置 SQL Server 系统变量（`@@ERROR`/`@@ROWCOUNT` 等）的命名空间，也是 MySQL 系统变量（`@@global.x`/`@@session.x`）前缀，**不是** dbx 的用户变量机制，与 datara 变量管理没有可融合关系。经核证：dbx 参数解析对 `@` 存在相邻 `@` 守卫，`@@x` 不会被当作参数；dbx 系统变量常量表仅作补全候选，且解析路径显式跳过 `@@` 前缀。**结论：`@@`** **保留给各数据库系统变量，datara 变量不与之共用前缀，MySQL** **`@@`** **变量可安全使用。**

**D5 —— 补全候选展示现值 + 类型 + 脱敏。**
候选详情展示变量当前值（超长截断）与值类型；敏感变量一律显示 `***`，不在补全候选中泄露明文。与右侧变量现值面板口径一致。

## Surface

| 层        | 文件                                                             | 变更性质                              |
| -------- | -------------------------------------------------------------- | --------------------------------- |
| dbx 前端   | `apps/desktop/src/lib/sql/externalVariableCompletion.ts`       | 修改候选标签口径、补全候选详情（现值/类型/脱敏）         |
| dbx 前端   | `apps/desktop/src/lib/sql/externalVariables.ts`                | 条目接口补 `valueType`（与宿主下发结构对齐）       |
| dbx 前端   | `apps/desktop/src/composables/useSqlExecution.ts`              | `tryExplain`/`prepareMultiExecute` 补入外部变量优先解析 |
| dbx 前端   | 对应契约测试                                                         | 新增/更新补全源与参数豁免用例                   |
| dbx 构建   | `/lei/apps/dbx` → `dist`（1.9 原地）                               | 重新构建前端产物                          |
| 本机备查     | `deploy/dbx/dist-2026-10-29`、`deploy/dbx/src-patch-2026-10-29`  | 同步产物与补丁源码                         |
| datara 侧 | 无                                                              | 语法与后端解析口径不变                       |

## Risks & Open Questions

* **R1（次要风险）宿主变量下发链路未在实测中端到端确证**：`DbxIdeView.vue` 的 `refreshVariables` + `datara:bridge-ready` 补发双通道与 `dbxVariableBridge.ts` 的 Proxy 克隆规避均已就位，dist 产物亦含桥代码；但「实测 `$` 无补全」与「label 口径缺陷」两个因素可同时存在。补丁落地后若仍无补全，需按此链路继续排查（`datara:variables` 是否携带非空 `entries`、`allowedOrigins` 是否与 iframe 实际 origin 一致）。

* **R2 豁免判定的时机**：参数解析发生在执行前，要求 datara 变量注册表在 SQL 执行前已完成注入。若存在「先执行、后注入」的路径，豁免会短暂失效；需在实施时确认注入先于执行。

* **R3 变量现值刷新延迟**：现值来自宿主下发的快照，若变量在 IDE 打开期间被修改，候选详情可能滞后；可接受（与右侧面板刷新节奏一致），如需强一致再引入按次拉取。

* **R4 语法冲突的长期边界**：`${scope.name}` 与 dbx `shell` 语法结构相同，当前以「命中已注册变量则豁免」收敛。若未来 datara 变量名与用户自定义 shell 参数名重名，以 datara 变量优先；此为既定取舍。

