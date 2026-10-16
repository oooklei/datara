# Codex T-1 评审回执：DBX × 原版 SQLIDE 融合对照清单

- 评审对象：`docs/increments/2026-10-17-DBX-原版SQLIDE-融合对照清单.md`
- 对照依据：设计稿 §13.17-9（D9），任务池 §7 P1-7，handoff #52/#53；评审标准为逐项意见、D9 优先级一致性、DBX 与原版源码双侧锚点、O7 未实证披露。
- 评审结论：**FAIL（修订后复评）**。这是对“D9 全面研读与融合对照已经完成”的验收结论；不否定当前文档作为有用的第一版矩阵。

## 逐项评审意见

| 范围 | 结论 | 复核意见与需补内容 |
|---|---|---|
| C1 编辑器内核 | 认可，补锚点 | 以 DBX CodeMirror 6 为准、吸收原版语言与变量语义，符合 D9。当前 `QueryEditor.vue:L26-L49` 主要显示导入；补充实际装配入口 `useQueryEditorCodeMirror.ts:L20` 及 runtime、statement boundary、completion 实现锚点。 |
| C2 语句执行粒度 | 有条件认可 | 清单把“选中优先”作为兼容提议交 A5 裁定，未冒充冻结结论，处理合理。补明：选区执行若与 DBX 的语句边界解析/可执行范围冲突，DBX 语义优先；提议不得覆盖该规则。 |
| C3 对象枚举 | 部分认可 | DBX `ObjectSourceKind` 的 13 类枚举作为基准正确；R5-A 的 9 类收敛子集目前没有逐对象类型 × 数据库驱动支持、排除理由、阶段边界和回扩验收门槛。补全矩阵后才能说明这是分阶段收敛，而非永久降级。 |
| C4 连接模型 | 认可 | DBX 池化分级/驱动适配为目标，保留 Datara 数据源中心的信息架构，符合 D9 与不深绑原则。实施映射仍需保持 Datara 自有适配边界。 |
| C5 凭证存储 | 有条件认可 | 禁止明文并加严安全基线方向正确。但 `connection_secrets.rs:L1` 标注为 legacy 空壳，`keychain.rs` 是辅助读取，不能证明 SQLite Storage 的实际加密实现或安全等价。请补真实存储读写、密钥保护和平台边界源码锚点；未核实前仅描述为待验证方向。 |
| C6 编辑器交互 | 认可 | 以 DBX 交互语义为准并评估 Monaco 特性迁移成本符合 D9；需确保 Monaco 特性只作为候选吸收项，不能反向覆盖 DBX 语义。 |
| 原版交互吸收项 | 认可 | 快捷键、变量补全、结果 SQL 回显、页间漂移提示、服务端重放分页等有利于融合，符合用户允许吸收原版界面优势的要求。逐项仍应有可追溯处理状态与后续接线验收点。 |
| 核心能力覆盖 | 异议，需补矩阵 | 当前没有将跨 Schema 查询，以及表、视图、存储过程、函数的发现/查看/编辑/DDL 执行分别映射至后端能力、R5-A/R5-B 阶段、驱动差异和验收证据。D9 与原始业务要求明确包含这些对象与跨 Schema 查询。 |
| D9 完成度 | 异议 | 清单 §7 明列 `commands/docs.rs`、`global_search.rs`、DataGrid 提交 SQL 生成链、Agent/ExternalDriver/PluginConnection 深语义、schema/data compare 算法、原版 datasource 页面待精读；§1 数据编辑行也承认提交 SQL 生成细节待精读。因此不能验收为“全面研读完成”。 |
| O7 披露 | 认可 | 文档将待精读项保持为未知，没有把待证事实写成结论，满足诚实披露；后续修订应保留并逐项关闭这些边界。 |
| 来源可复现性 | 补充要求 | 仅写 `D:\dbx-main` 本地快照与日期，未标识快照版本/采集时间/文件清单；本轮 DBX 输入目录无法通过 Git 提交号固定。补充只读归档标识、采集时间和 manifest/hash（不修改参考源码）。 |

## 主智能体锚点复核

- DBX `apps/desktop/src/types/database.ts:L1013` 定义 13 种 `ObjectSourceKind`，支持 C3 的基线事实。
- DBX `apps/desktop/src/components/editor/useQueryEditorCodeMirror.ts:L20` 是 CodeMirror 装配入口，比仅引用 `QueryEditor.vue` 导入行更能证明实际实现位置。
- DBX `README.zh-CN.md:L229-L231` 只支持功能概述（CodeMirror 6、补全、选中 SQL 执行、格式化、历史、脚本），不替代实现锚点。
- 原版 `datara-web/src/views/ide/components/SqlEditor.vue:L4-L10,L47-L108,L509-L517` 支持 Monaco/Monarch、变量分色和选区执行事实；`IdeView.vue:L37-L43` 支持快捷键事实。
- 原版 `datara-backend/api/ide.py:L384-L441,L477-L506,L538-L615,L692-L852` 支持异步执行、取消、结果重放分页及导出事实；`common/models.py:L394-L421` 支持 IdeHistory 字段事实。
- 凭证引用应以实现链复核；已知 `connection_secrets.rs` 是 legacy 空壳注记，不能作为 SQLite Storage 实现证明。

## D9 优先级一致性

当前矩阵对 C1/C3/C4/C5/C6 的“冲突时 DBX 为准”总体一致；原版特色列为吸收候选，原则正确。C2 选中优先仅能作为待裁定兼容提案，必须明确受 DBX 语句边界规则约束。`R5-A MetaTree 9 类`、写入能力和提交 SQL 生成链仍须逐驱动/阶段标出缺口，不能以总体方向一致替代逐能力验收。

## 复评所需修订清单

1. 增加 13 类对象类型 × 数据库驱动的发现、查看、编辑/DDL 能力矩阵，标记只读/写入阶段、排除理由、回扩门槛和验收证据。
2. 显式映射跨 Schema 查询及表/视图/存储过程/函数的端到端后端职责与阶段计划。
3. 对 §7 每项待精读内容增加实现路径、源码锚点、结论、状态；关闭之前继续标为未完成。
4. 补充 DBX CodeMirror 实装与凭证存储真实实现锚点；未证实的安全能力保持 O7 未知状态。
5. 记录 DBX 参考快照的可复现标识、采集时间及 manifest/hash。
6. 维持 C2 的“兼容提议/A5 待裁定”状态，并补充 DBX 优先约束，不得擅自冻结。

复评前，结论保持 **FAIL**；本回执不替代 A5 冻结，也不变更 R5 契约。
