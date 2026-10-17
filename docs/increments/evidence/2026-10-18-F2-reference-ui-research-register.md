# F2 融合立项预研登记：参考组件 UI 与 Datara 前端边界

> 状态：只读预研登记，不是融合立项批准、后端契约冻结或页面验收。日期：2026-10-18。范围：DBX、Apache DolphinScheduler/DataX、Vanna。未修改业务页面。

## 1. 依据和边界

- 权威重建设计正本 `docs/increments/2026-10-14-datara-platform-rebuild-design.md` §1.2 明确正式前端在 Backend 冻结前不改；§1.3 要求独立验证页面以被测产品的真实交互、表单、默认值、校验、步骤及反馈为准，不得以 Datara 旧正式前端为参考，也不得做成 API 按钮面板。§1.2 的 D-1 豁免仅指菜单分组和 `/std/*` 路由展示元信息，不覆盖正式页面业务功能。
- 执行状态附录 `docs/increments/2026-10-14-datara-platform-rebuild-design-执行附录.md` §1.2 复述同一豁免边界，§1.3 规定“能力—来源—源码/契约—参考页面/用户流程—新 Backend 适配—可验证场景”对照，并要求验证页调用新 Backend API。
- 当前 checkout 未发现名为《核心业务功能实现规范与验收标准》的 v4 独立文件；因此本登记不声称逐字核验了该标准 v4 的 §1.2。以上边界以本地存在的权威设计正本及执行状态附录为准；如 v4 §1.2 另有经批准差异，需由权威持有人补充其路径/版本后复核。
- `D:\dbx-main`、`D:\dolphinscheduler-dev\dolphinscheduler-dev`、`D:\vanna-main` 可读取，但在各目录根部未发现 `.git` 元数据，无法核验分支、commit 或 tag。下面的源码锚点均为本机快照路径；不将其表述为已锁定上游版本。未发现独立 `D:\DataX` 源码检出；DataX 部分只依据 DolphinScheduler DataX 任务集成源码和文档，不能代表 DataX 原生 UI。

## 2. 组件证据和差异矩阵

| 组件 | 可核实的交互工作流、字段/默认/校验/反馈 | 对应后端职责边界 | 与 Datara 的融合建议、优先级 | 缺失证据/精读项 |
|---|---|---|---|---|
| **DBX SQL IDE** | 中文查询编辑器文档描述：选连接/数据库/Schema → 编写并检查 SQL → 选择选中语句/当前语句/全文及执行目标 → 查看多结果或计划 → 保存 SQL 库/文件。快捷键、停止执行、执行状态、错误和多语句进度均有说明。历史保留选项为 200/1000（默认）/5000/10000/不限；多结果可切换横向标签/列表并固定结果。参数形式含 `?`、`:name`、`${name}`、`#{name}`、`@name`，类型有字符串/数字/布尔/NULL/原始 SQL。源码 `SqlEditorWorkspace.vue`、`QueryResultSurface.vue`、`stores/queryStore.ts`、`composables/useSqlExecution.ts`、`components/grid/DataGrid.vue` 证明编辑器、结果面、执行状态和网格是可复用交互域；文档还说明对象树含 DB/Schema/表/视图/字段，且表名引用可定位对象。 | Datara Backend 管理项目范围数据源/凭据引用、可用数据库元数据、对象探查、SQL 执行与异步取消、审计/历史/SQL 资产、结果分页和导出，以及统一变量解析/校验。DBX 的本地桌面状态和驱动实现不能直接充当 Datara 服务端契约；驱动特性须按 Datara 后端实际支持能力声明。 | **P1**：将“连接上下文—多 Schema 查询—执行范围—结果网格/历史/SQL 资产”作为独立模块；SQL 资产保存应与运行记录、变量解析上下文可追溯关联。优先照搬交互语义和安全提示，不复制桌面容器架构。正式前端继续冻结；独立验证页也必须有可编辑 SQL、连接/Schema 选择、执行范围和真实结果/错误反馈，不能退化成仅点 API 的面板。 | 本地 DBX 文档和代码足以证明通用查询闭环，但尚不足以证明所有数据库驱动的跨 Schema、视图/过程/函数/触发器编辑能力一致。DBX 对结构化 Table/Index 与文本对象的 CRUD、各驱动默认 Schema、只读权限、DDL 风险确认需另做逐驱动矩阵和对象编辑工作流精读；当前不能宣称“所有对象编辑”已被 UI 证据完整覆盖。版本/分支未锁定。 |
| **Apache DolphinScheduler 工作流 / DataX 节点** | DS 中文 DataX 指南描述：创建工作流 → DAG 画布拖入 DataX 节点 → 配置 → 查看运行结果。`dolphinscheduler-ui/src/views/projects/task/components/node/tasks/use-datax.ts` 给出通用初始值：`taskType=DATAX`、`flag=YES`、重试间隔 1、重试 0、workerGroup `default`、timeout 30、`customConfig=false`、source/target type `MYSQL`、`timeoutNotifyStrategy=[WARN]`。`fields/use-datax.ts` 具体表单含 source/target datasource、SQL、JSON 模板、资源、target table、前/后置 SQL、batch size、字节/行限速、xms/xmx、channel、自定义参数；非自定义模式显示数据源/SQL等字段，自定义模式切换到 JSON 和资源。SQL 必填；自定义 JSON 可为空仅当资源列表恰有一个 `.json` 文件，否则必需且必须是有效 JSON；空对象 `{}` 同样需恰有一个 JSON 资源。目标表必填，batchSize 最小 0；默认 byte 限速 0（无限）、record 限速 1000、xms/xmx 1、channel 1。文档称执行结果可查看；依赖等待的通用反馈时序尚未由本次 DataX 精读覆盖。 | DolphinScheduler 负责 DAG 生命周期、任务参数序列化、worker/环境选择、重试/超时/资源与运行状态；DataX worker 经 `DATAX_LAUNCHER` 执行 DataX JSON。Datara 后端须拥有自己的 DAG/任务契约、数据源资源权限、reader/writer 参数校验与映射、运行/重试/日志/指标，不依赖 DS 数据库或 worker。DataX JSON 作为插件配置需有受控扩展边界，不能默认当作可信任任意执行文本。 | **P1**：复刻关键操作顺序和表单语义：DAG 放置节点 → source/destination → 字段探查/SQL 或 JSON 配置 → 参数/资源校验 → 试运行/运行 → 进度/结果/错误。Datara 可把同步映射、列预览和 checkpoint 纳入本系统契约；不得只搬 DS 表单而不绑定 Datara API，也不得把 DataX 原生 JSON 的灵活性误称为 Datara 后端能力。 | 当前证据是 DS UI schema 与使用指南，未运行 DS 页面，也未对所有 DataX reader/writer 插件 schema、默认值、列映射探查/错误反馈做穷尽核验。独立 DataX 源码/UI 未在指定路径找到；此处不能把 DS 的 DataX 集成表单说成 DataX 自身 UI。正式 Datara DAG 页面参考 DS 真实操作流程，但后端执行语义仍需按 Datara 自有运行模型契约化。 |
| **Vanna** | `D:\vanna-main\README.md` 描述预置 `<vanna-chat>`：自然语言提问，经 SSE 流式返回进度、SQL（默认只给 admin 展示）、数据表、图表、自然语言总结。可嵌入现有 Vue/React/HTML 页面，认证复用 cookies/JWT。`frontends/webcomponent/src/components/vanna-chat.ts` 有真实聊天交互：空白输入或 disabled 时不发送；输入清空、进入 working 状态、逐块渲染流式组件；失败时显示错误状态和错误消息；属性默认 `theme=light`、`disabled=false`、`showProgress=true`、`allowMinimize=true`、SSE `/api/vanna/v2/chat_sse`，另有 websocket/poll endpoint。README 的服务端流程含用户身份 resolver、user-aware tools、权限组和 row-level security。源码在发送异常时写浏览器 console（包含 message/错误细节调用痕迹），故不应未经隐私审查照搬日志行为。 | Datara Backend 是 AI Agent 与权限/项目/数据源/变量/审计的权威宿主：用户身份、可用工具清单、工具参数 schema、查询权限、SQL 执行授权、确认门、审计与流式事件都在后端执行；Vanna 提供工具调用/流式 UI 参考，不获得绕开 Datara RBAC、项目 scope 或变量契约的通路。 | **P1（AI 浮动助手）**：借鉴聊天输入→流式任务状态→结构化结果卡片→SQL/数据预览→反馈的顺序；纳入 Datara 全局浮动助手，不新增一级菜单。把 SQL 建议与 SQL 执行分成可审查动作；写操作需走 Datara DDL/危险操作确认流程。变量应通过 Datara 统一解析服务传递。 | Vanna 快照含 Web Component 源码，能核对核心输入/输出和默认属性；但本次未运行组件、未精读其服务端所有工具权限中间件、历史/反馈持久化和不同事件失败恢复，也未核验版本。具体建议器/训练管理页面不应由当前聊天组件证据推导。 |

## 3. 融合差异优先级与处理方向

1. **P0 边界：前端解冻条件。** 当前只准研究登记；D-1 仅豁免导航/路由展示属性。任何 Datara 正式业务页面、mock/API 交互或菜单以外的页面行为改动仍需等 Backend 契约冻结及后续融合阶段，不由本登记授权。
2. **P1 后端可执行契约：** 先让 Datara 自己具备项目/数据源权限、变量解析、作业/SQL 的可审计执行、异步状态、错误反馈、结果/日志和资源引用，再把参考 UI 的关键表单步骤映射到其 API。每个字段需有后端 schema、默认来源、校验错误形状和状态转换；前端单独校验只是即时提示，不能成为安全边界。
3. **P1 组件主参考：** SQL IDE 以 DBX 作为编辑、跨 Schema 查询和结果工作区参照；DAG/DataX 以 DolphinScheduler 的画布与 DataX 节点配置参照；AI 以 Vanna 的自然语言到结构化结果流参照。融合保留 Datara 全局变量、项目 scope、运行审计和后端主权。
4. **P2 证据补足：** 固定上游仓库 commit/tag；精读 DBX 对象编辑及逐驱动能力，DS DataX 完整表单/默认值/字段交互与运行反馈，Vanna 后端权限/工具合同及组件失败恢复；补充真实页面的控件路径或截图/自动化证据。未完成前，相应功能标为“源码/文档初步映射，UI 复核待办”。

## 4. 当前结论

现有证据足以建立三个模块的交互骨架映射，但不够据此直接批准正式前端融合或宣称目标功能验收通过。DBX 和 Vanna 的参考 UI 不应被当作可直接嵌入的 Datara 页面；DolphinScheduler 的 DataX 节点是 DS 对 DataX 的集成形态，不等同 DataX 独立产品 UI。建议先完成 P2 中版本固定与缺口精读，再由后端契约冻结结果形成正式融合立项条目。本登记没有对 Datara 代码、页面或用户数据作改动。

## 5. 来源锚点

- Datara 权威设计：`docs/increments/2026-10-14-datara-platform-rebuild-design.md` §1.2–§1.3。
- Datara 执行状态边界：`docs/increments/2026-10-14-datara-platform-rebuild-design-执行附录.md` §1.2–§1.3。
- Datara 标准 v2 反馈处理与待研读事项（仅作过程证据，不替代标准 v4）：`docs/increments/evidence/2026-10-17-standard-v2-feedback-disposition.md`，位于当前嵌套 main 工作副本；本登记没有将其作为 v4 权威条文。
- DBX 用户交互：`D:\dbx-main\docs\content\docs\query-editor.cn.mdx`；真实 UI 代码 `D:\dbx-main\apps\desktop\src\components\layout\SqlEditorWorkspace.vue`、`QueryResultSurface.vue`、`D:\dbx-main\apps\desktop\src\components\grid\DataGrid.vue`、`D:\dbx-main\apps\desktop\src\stores\queryStore.ts`、`D:\dbx-main\apps\desktop\src\composables\useSqlExecution.ts`。
- DolphinScheduler DataX 用户文档：`D:\dolphinscheduler-dev\dolphinscheduler-dev\docs\docs\zh\guide\task\datax.md`；实际表单及缺省：`D:\dolphinscheduler-dev\dolphinscheduler-dev\dolphinscheduler-ui\src\views\projects\task\components\node\tasks\use-datax.ts`、`...\fields\use-datax.ts`。
- Vanna 用户/集成说明：`D:\vanna-main\README.md`；Web Component：`D:\vanna-main\frontends\webcomponent\src\components\vanna-chat.ts`、`...\services\api-client.ts`。
