# Codex F2 融合立项预研：被测组件交互参考与正式页差异基线

- 日期：2026-10-17
- 状态：预研完成；不是 Phase 3 启动令，不修改正式页面，也不改变后端优先与冻结门。
- 任务来源：`docs/increments/2026-10-17-分阶段混合集成方案-设计.md` §4 Phase 3/F2、§7 F2；验收准则见 `docs/increments/2026-10-17-核心业务功能实现规范与验收标准.md` §S2。
- 范围：对 DS、DBX、DataX、Vanna 的现有交互/源码/使用资料做只读盘点，为后续功能验证页立项提供来源差异基线。OpenMetadata/DataHub 属于 R8 后续对照资料，不在本轮页面设计中扩展。

## 1. 结论

F2 的页面验收应逐组件采集并呈现五类事实：真实表单字段、默认值、校验规则、用户操作顺序、结果反馈。参考产品只能为其自身确有的能力作证；某个产品没有可核验的 UI 时，须声明页面由 Datara 自创并以该产品的配置/执行契约为后端语义来源。Datara 旧版正式前端和仅含 API 按钮的调试面板都不能替代该验收标准。

本文件属于 Phase 3 前的差异预研。当前 R 系页面是后端契约接线/可视化验证层，不等同于完整功能页验收；在 API、数据模型、节点、变量、执行状态、统计、时间戳七项协议冻结且试运行/正式运行验收通过前，不据此启动正式前端融合或改造页面。冻结期仅保留设计明示的导航豁免。

预研没有发现可以跨组件照搬的通用表单。DS 依赖节点、DBX SQL 工作台、DataX JSON 作业配置和 Vanna 对话 Agent 属于不同交互形态，后续应分别定义验证流程；它们共同受 Datara 后端权限、隔离、审计、变量、运行与恢复契约约束。

## 2. 组件交互事实与可复用边界

| 组件 | 可复核的交互事实 | 五要素/流程基线 | 不能据此推导的内容 |
|---|---|---|---|
| DolphinScheduler 依赖节点 | 依赖组间及组内均有 AND/OR；条件含依赖类型、项目、工作流、任务、周期、日期、参数传递；另有轮询、失败与 timeout 设置。UI 中关系默认 AND、类型 workflow、周期 day、日期 today、失败策略 FAILURE、轮询 10 秒、timeout 30 分钟但关闭；并非每个字段都有初始默认值。 | 添加 DEPENDENT 节点→设组间关系→添加组及条件→选择类型/项目/工作流/任务/周期/日期→配置参数传递、轮询、失败等待和 timeout。编辑页没有执行前预览；实例详情显示条件状态图标。 | UI 校验存在缺陷：轮询间隔校验不能可靠拒绝负数/非整数，timeout 策略空值校验依赖未见初始化的字段。已查执行路径未消费 `checkInterval`；因此 UI 字段默认值不得被描述成后端已实现轮询契约，服务端须独立定义并验收。权限、时区、业务日期、时间窗/DST、状态三态机、恢复/幂等和 VarPool 合并均须由 Datara 后端契约定义。 |
| DBX SQL 工作台 | 查询上下文涉及连接/database/schema；执行目标有选区、当前语句、全部 SQL；参数对话框类型含 string/number/boolean/null/raw，默认 string；结果网格支持本地过滤、数据库过滤/排序和具备可靠标识时的行编辑。对象浏览和源码查看按驱动能力展示。 | 选择/打开带上下文的查询→编写 SQL→确定执行范围→按需填写参数→执行并查看网格/错误/计划→保存 SQL 资产。连接表单默认值随 driver profile 变化，MySQL 默认不得推广至其他驱动。 | Schema 感知不等于跨 database；对象可见不等于可编辑，存储过程/函数可编辑性按驱动/对象能力。取消受驱动限制。只读/生产保护、授权、审计、密钥托管须由 Datara 后端实现。DBX 普通查询命令 await 返回与旧版 taskId+SSE 生命周期不能合并称为等价。 |
| Alibaba DataX | 本轮未发现可作为 DataX 上游核心项目通用验收标准的官方可视化作业 UI；可确认的权威形态是 JSON Job 配置和 Reader/Writer 插件契约。作业由 `job.setting`（如 channel/errorLimit）与 `job.content`（reader/writer name/parameter）组成。 | 以插件 schema/示例配置为基础创建或编辑 JSON→校验 Reader/Writer 与参数→执行 Job→呈现配置校验、运行日志/错误及结果。若 Datara 提供图形化表单，该表单是适配 DataX 配置语义的自创 UI，须逐插件声明字段和默认值来源。 | 不得把 Alibaba DataWorks 或其他产品 UI 称为 DataX UI。DataX 配置 schema 不定义 Datara 的权限、变量解析、调度、审计、状态恢复或作业生命周期接线。由于本机未发现 `D:\DataX` checkout，本项依官方 DataX 源码/插件开发资料核验，需在正式实现前记录具体版本/commit 和插件集合。 |
| Vanna | 现代 webcomponent 是聊天交互壳：输入问题、conversation 上下文、流式状态/响应与错误；模型、SQL runner 和工具由服务端 Agent/依赖注入。旧版 Flask UI 的训练数据管理能力不可默认算作现代 chat 必备交互。 | 输入自然语言问题→显示流式思考/工具状态→展示 SQL、结果/错误和可继续追问；训练上下文可按 DDL、文档、SQL、question-SQL 等类型呈现。Datara 连接选择、模型 key 配置和身份由 Datara 控制面注入。 | Vanna 工具组权限不是项目/RBAC/行列权限；`run_sql` 工具可调用注入的 SQL runner，不能视为固有只读。Datara 需将 SQL 生成与执行分段：展示 SQL/目标/只读策略并通过授权确认后，只调用 Datara 管控的只读工具；不得向 Vanna 暴露生产凭证或允许其直连数据库。 |

## 3. 关键源码与文档锚点

### 3.1 DolphinScheduler

- `D:\dolphinscheduler-dev\dolphinscheduler-ui\src\views\projects\task\components\node\fields\use-relation-custom-params.ts:36-97`：组关系字段。
- `...\fields\use-dependent.ts:317-508`：依赖类型、选择器、周期/日期、参数传递及轮询/失败配置；具体默认/校验锚为 `328-340,354-380,402-444,446-487,509-557`。
- `...\fields\use-dependent-timeout.ts:49-107`：timeout 默认和交互校验。
- `...\workflow\components\dag\use-node-status.ts:72-97`、`...\store\project\task-node.ts:132-137`：实例条件结果到状态图标的反馈。
- 后端状态回写/读取：`D:\dolphinscheduler-dev\dolphinscheduler-dev\dolphinscheduler-master\src\main\java\org\apache\dolphinscheduler\server\master\engine\executor\plugin\dependent\DependentTaskTracker.java:242-285`、`D:\dolphinscheduler-dev\dolphinscheduler-dev\dolphinscheduler-api\src\main\java\org\apache\dolphinscheduler\api\service\impl\WorkflowInstanceServiceImpl.java:322-344`。

### 3.2 DBX

- 查询编辑器/执行目标/参数：`D:\dbx-main\docs\content\docs\query-editor.cn.mdx:21-121`、`apps/desktop/src/components/editor/useQueryEditorExecution.ts:67-122`、`SqlExecutionTargetPicker.vue:6-110`、`SqlParameterDialog.vue:22-104,168-226`。
- 驱动能力与对象浏览：`docs/content/docs/databases.cn.mdx:6-73`、`docs/content/docs/object-browser.cn.mdx:6-72`、`apps/desktop/src/types/database.ts:1013`（`ObjectSourceKind`）。
- 结果网格与生产保护：`docs/content/docs/data-grid.cn.mdx:24-79`、`docs/content/docs/production-safety.cn.mdx:6-44`。
- 执行生命周期：`src-tauri/src/commands/query.rs:35-89,174-289`；Datara 旧版接口 `datara-backend/api/ide.py:384-441,477-506,538-615,692-852` 仅用于识别需融合/区别的原版能力，不作为页面验收标准。
- 凭证安全：`crates/dbx-core/src/persistence/secret_codec.rs:267-303`、`storage.rs:235,1010+`、`docs/content/docs/data-security-migration.cn.mdx:45-63,66-108,118-129`。此处仅描述 DBX 事实，不构成 Datara 密钥方案裁定。

### 3.3 DataX

- 官方源码配置模型：[`alibaba/DataX core/src/main/job/job.json`](https://github.com/alibaba/DataX/blob/master/core/src/main/job/job.json)。
- 官方插件开发/Reader-Writer 生命周期资料：[`alibaba/DataX dataxPluginDev.md`](https://github.com/alibaba/DataX/blob/master/dataxPluginDev.md)。
- 正式实现需锁定 DataX 源码 commit 和目标插件版本，不能以浮动 `master` 作为最终验收锚。

### 3.4 Vanna

- 本机权威参考源码目录：`D:\vanna-main`。聊天输入/消息流：`frontends/webcomponent/src/components/vanna-chat.ts:711-726,854-885,1059-1093,1384-1411`；API 客户端：`.../services/api-client.ts:12-32,54-56`。
- 服务端 Agent/工具：`src/vanna/core/agent/agent.py:657-827`、`src/vanna/tools/run_sql.py:18-60,63-136`、`src/vanna/core/registry.py:63-112,144-175`。
- README 初始化模式：`README.md:152-180`；现代 Agent 迁移/DI：`MIGRATION_GUIDE.md:201-242`。训练管理旧版 UI：`src/vanna/legacy/flask/__init__.py:742-852,1208-1269`，不得与现代 webcomponent 混称。
- 官方产品资料：[`Vanna Quickstart`](https://vanna.ai/docs/tutorials/quickstart-5min)、[`How to Train`](https://ask.vanna.ai/docs/train/)、[`Configure`](https://vanna.ai/docs/configure)。占位权限页只可作弱佐证，行为以本地源码/测试为准。

## 4. Datara 后端契约与页面验收分层

1. 页面记录的字段、默认、校验、步骤、反馈必须可定位到所测组件的 UI/文档/源码；每条标注来源版本、文件/行号、是组件原生事实还是 Datara 自创集成。
2. 后端仍是根本：页面表现不得代替服务端的输入校验、身份与项目隔离、能力授权、变量解析、运行状态、持久化、恢复、幂等、审计与错误契约。
3. 依赖组件是 DAG 核心节点，DolphinScheduler 作为语义和交互主要来源；为补齐业务类型的 Datara 扩展（file/table_state/external_task）需以已裁定的后端契约为准，不能把 DS UI 未覆盖部分伪称 DS 原生功能。
4. SQL IDE 复用 DBX 能力语义，driver 能力必须逐类声明；跨 Schema 与跨 database 分开验收。变量契约按 Datara 冻结标准执行，不能由 DBX/Vanna 的局部变量/参数机制替代。
5. DataX 若无适用官方 UI，Datara 可以自建面向 JSON/plugin schema 的可视化配置页，但需在设计中说明“UI 自创、DataX 配置语义复刻”，并由目标插件契约驱动表单及校验。
6. Vanna 的聊天和流式结果可作交互参考；SQL 执行、密钥、项目上下文、训练语料隔离和工具授权必须走 Datara 后端。预览/审批与执行之间必须保留 Datara 的授权门。

## 5. 后续立项输入

- 正式启动 F2 前，为每个页面指定 owner、被测组件版本、源文件清单和验收证据格式；DataX 另锁定源码 commit 与插件白名单。
- 页面逐项填写“五要素+来源锚点+Datara 后端契约链接”；无法由 UI 核验的后端能力列入 API/执行级验收，而非用模拟按钮通过。
- 本预研只提供参考基线；正式页面实现仍须等待 Phase 3 启动条件与后端冻结门通过。没有在本轮改动正式页面或业务代码。
