# P2-2 FUSION-1：R5-A 实施细目（Codex 子任务 A）

- 状态：实施拆解设计；不修改代码、接口契约或冻结 A5 v1.0。
- 基线：FUSION-0 追踪表 `docs/increments/2026-10-19-Codex-P2-2-FUSION-0-追踪表.md`；P1-7 研读 `docs/increments/2026-10-19-P1-7-DBX融合研读-Claude线.md`；冻结契约 `docs/increments/2026-10-18-A5-SQL-IDE后端契约-v1.0-冻结候选.md`；模块建议参考 `docs/increments/2026-10-18-P2-2-R5-A-SQL-IDE后端设计草案.md`。
- 路径声明：下表是建议的改动落点/新建模块，不表示这些文件当前已实现相应生产能力；实施前须复核基线 HEAD、现有文件和 A5 兼容性。A5 冻结方法签名、字段与安全限制优先。
- 范围：F1/F3/F4/F5/F8/F9 的 R5-A 只读部分/F10/F12/F13；F9 的 DDL 编辑/保存/确认明确不属于 R5-A。

## 1. 按融合点拆解

| 项 | 建议文件级变更点（均为提案） | A5 冻结接口映射 | 依赖/顺序 | 规模 |
|---|---|---|---|---|
| F1 连接池分级 | `datara-backend/rebuild/datasource/pool.py`、`contracts.py`、`models.py`：整理 driver profile、只读连接/池能力接口、资源生命周期与能力报告；`tests/rebuild/test_datasource_pool.py` 加入契约验证。可由 `rebuild/sql_ide/` 的依赖注入消费，不在 SQL IDE 内另造池。 | §2.2 datasource capability；§3 #1–#9 使用已授权 datasource/capability。无新增 wire method，不将 DBX `PoolKind` 直接照搬为 Datara 公共枚举。 | 先于元数据、定义读取、SQL 执行；后续需按 driver family 接入并测池回收/并发。 | L |
| F3 多语句批执行 | `datara-backend/rebuild/sql_ide/execution.py`、拟新增 `statement_batch.py` / `task_store.py`；`tests/sql_ide/` 增批预检、顺序执行、部分失败及禁止重放用例。SSE 与任务存储可按现有 A5 路由拆模块。 | §3 #9 `executeSql(request)`；#10 `cancelExecution(taskId)`；#11 `openEventStream(taskId)`；#19 `getExecutionStatus(taskId)`；§4 全批预检、只读身份、`partial_failure`、幂等及不得宣称整批原子/自动重试。 | F5 完整语句切分和变量处理之后；F1 只读 driver/session 就绪后；再接 #11/#19 事件恢复。 | L |
| F4 结果集分页 | 拟新增 `datara-backend/rebuild/sql_ide/result_store.py`、`result_page.py`；`datara-web/src/services/rebuild/sqlIdeApi.ts` 映射分页，`.../sql-ide-readonly/components/ResultGrid.vue` 仅消费快照页；后端结果分页测试。 | §3 #12 `fetchResultPage(historyId,resultSetId,offset,limit,query?)`；#11 result ref；§5 快照/导出。按 `(historyId,resultSetId)` 读同一不可变快照，不从分页路径重跑 SQL。 | 依赖 F3 结果物化与 history/resultSet 标识；分页 API 后再接 F13 查询结果导出。 | L |
| F5 语句边界切分 | `datara-web/src/views/rebuild/validation/sql-ide-readonly/components/SqlEditor.vue`（选择/光标边界的请求构造）；后端拟新增 `rebuild/sql_ide/statement_batch.py` 做最终语义校验；分别覆盖 FE 边界与后端切分测试。 | §3 #8 `lintSql(datasourceId,sql)`、#9 `executeSql(request)`；§4 变量解析后按完整语句全批预检。选区半条语句不得悄然变成独立可执行语句。 | 先于 F3；编辑器只提供候选文本，服务端对最终 SQL 执行方言解析/只读判定。 | M |
| F8 类型化错误 | `datara-backend/rebuild/sql_ide/contracts.py`（公共 envelope / domain error）、拟新增 `errors.py`（内部分类到安全域码映射）、`execution.py` 与各 service 边界映射；FE `datara-web/src/services/rebuild/sqlIdeApi.ts` 解析稳定 envelope；错误映射测试。 | §2.1 稳定 HTTP/domain envelope；§3 #1–#20 每方法定义的 400/403/404/409/unsupported/expired 等语义；#11 `errorDetail{code,category,stage,retryable}`。不得回传 driver 原始异常、连接串、密钥或敏感值。 | 应在首个 endpoint 前定义公共错误类型；各能力实现时逐条映射；driver-specific 映射需证据后启用。 | M |
| F9 DDL 双轨，仅 R5-A 读 | 拟新增 `datara-backend/rebuild/sql_ide/definition_reader.py`，调用 driver/object 专属只读 source reader；`datara-web/src/services/rebuild/sqlIdeApi.ts` 和对象元数据 UI 只增加 definition preview 消费入口（若产品确需本阶段）；测试验证权限、unsupported 与只读性。表定义独立 getter，index 仍是父表子对象元数据。 | §3 #18 `getDefinition(datasourceId,objectRef)`：`objectRef/sourceKind/definitionText/sourceVersion/capability/constraints/generatedAt`。§3 #21–#25 为 R5-B facade/policy/impact/confirm/record，仅标为后续边界，不能在本项实现写路径。 | 依赖 F1 capability 和完整 ObjectRef；仅对声明并验证支持的 driver/object 开放。R5-B 之后可消费同一个 sourceVersion。 | M |
| F10 跨 Schema 执行 | 拟新增 `rebuild/sql_ide/execution_context.py` / 方言策略适配（可合并入 `execution.py`）；`tests/sql_ide/` 针对 schema/catalog/default schema 语义及 fail-closed 覆盖。元数据 ObjectRef 由 datasource 模型统一提供。 | §3 #1–#7 含 database/schema 的完整 ObjectRef；#9 `executeSql(request)` 的 `db/catalog/schema` 执行上下文；§4 方言与只读分类。显式上下文由 driver adapter 处理，不做全局 SQL 文本替换。 | F1 建立 driver profile 后；先验证 ObjectRef /授权，再解析并应用对应方言上下文，最后进入 F3 批执行。 | L |
| F12 历史与资产 | 拟新增/整理 `rebuild/sql_ide/history_service.py`、`script_service.py`、`dataset_service.py` 与持久化 repository/migrations；FE `services/rebuild/sqlIdeApi.ts`、`views/.../HistoryDrawer.vue`、项目脚本资产 service。测试覆盖 project/user ACL、软删除、revision CAS、TTL 与 dataset 晋升。 | §3 #13 `listHistory(datasourceId)`、#14 `deleteHistory(historyId)`、#15 `listScripts()`、#16 `saveScript(input)`、#17 `deleteScript(id,expectedRevision)`、#20 `saveResultAsDataset(historyId,resultSetId,input)`；§4 任务最小状态/保留；§5 资产约束。 | F3 先产出关联 task/history；F4 的 result snapshot 完成后才能 #20；脚本 revision/CAS 可并行，但必须以 Datara 项目资产为真源。 | L |
| F13 数据导出 | 拟新增 `rebuild/sql_ide/export_service.py`、`export_store.py`、下载/取消路由；FE `services/rebuild/sqlIdeApi.ts` 显式新增 `exportResult/exportTable`，结果面板/对象目录按需提供操作。独立测快照读取、授权 ObjectRef、行/字节限额、TTL、取消与部分文件清理。 | §1、§5 独立导出合同；结果 `POST .../exports(historyId,stmtIndex,format)`；表级 `POST .../table-exports(datasourceId,ObjectRef,format,rowLimit)`；状态/下载/取消路由。#12 仅分页读取，不得隐藏导出；表导出不接受任意 SQL、不重跑 IDE 查询。 | F4 先提供稳定结果快照；表导出依赖 F1 与 ObjectRef/只读 cursor；随后实现短期 export handle、下载授权和清理。 | L |

规模口径：S=单模块/低耦合；M=跨少量模块且状态简单；L=跨层、持久化或 driver 差异显著。这里只用于排期估算，不是工时承诺。

## 2. 建议实施次序与门禁

1. **底座**：F8 公共错误/envelope、F1 driver profile 与只读池接口、F10 ObjectRef/context 约束；锁定服务依赖注入，不扩 A5 wire contract。
2. **解析及执行**：F5 完整语句边界 → F3 批预检/顺序只读执行 → #10/#11/#19 取消、事件与状态恢复；结果写入不可变 task/history/result 引用。
3. **结果与资产**：F4 快照分页 → F12 历史与脚本（revision CAS）→ #20 dataset snapshot 晋升；F13 结果导出可复用 F4 快照。
4. **定义与导出收口**：F9 #18 仅只读 getter；F13 表级导出接 driver cursor 和授权 ObjectRef，完成下载/过期/清理路径。发布顺序不代表可跳过契约各自的验收门。

## 3. 必须等待决策或实证的点

- F1：driver profile 分类、池容量/回收/并发参数均须逐类实测；不得凭 DBX 28 个 PoolKind 推出 Datara 支持矩阵。
- F3/F5/F10：多语句事务行为、语句切分、只读判定及默认 schema/catalog 注入，逐方言取证；目标库真实只读账号是第二道强制边界。未知语义必须 fail-closed，不以 SQL rewrite 猜测。
- F4/F13：快照存储容量、分页/导出行与字节上限、driver cursor 行为、下载 ACL 和清理可靠性均需实现前确定并用真实 driver 验证。不得因估计不足而默默重跑或截断冒称完整。
- F8：driver 原始异常到固定 domain code 的映射仅能由可重复错误样本建立；未映射异常只能安全归类，不暴露原文。
- F9：`getDefinition` 的可用 driver/object-kind、table DDL getter、sourceVersion/etag 稳定性须有逐项能力证据；unsupported/unknown 显式返回。任何写编辑、policy、impact、人工确认/发布均留待 R5-B 与其人工闸。
- F12：项目/用户 ACL 实际来源、脚本并发 revision 存储、软删除审计及各类保留/清理任务需对照平台现状确认；不得假定外部 DBX 文件就是平台资产真源。

以上门禁不改变 FUSION-0 的纳入决定，不预先选择待证驱动能力，也不替代冻结 A5 或监督线裁定。
