# Codex 契约评审回执：C1 / C2 / C4

日期：2026-10-17（Asia/Shanghai）  
基线：canonical main `e526396515a5d98222be886314a0ef3117f1fce8`（handoff #46）  
范围：A2 v2.1 源码复核、#37 ①②③正式裁定、R8 三组件锚点表 24 项复核。本文是评审证据，不代替标准 v4、监督线 R8 v2 发布令或用户裁定。

## C1 — A2 v2.1 复核冻结

**总裁定：FAIL，暂不可冻结。** 秒换算和 relation 来源已修正，但选择器语义、日期选择器/多区间、`checkInterval` UI 默认事实、超时语义仍有缺口；另有 `parameterPassing` 与标准 v3 S3 不对齐。A2 §7.1–§7.9 应在修订这些项并完成标准治理后再会签。

| 子项 | 裁定 | 核验结论与建议修订 |
|---|---|---|
| F1 `failure_waiting_seconds` | PASS | A2 §7.3 当前保留秒字段并明示 DS 源分钟 ×60、正整数、禁止舍入、溢出检查。DS `DependentParameters.java:66-69` 标分钟，`DependentExecute.java:371-380` 以 `Duration.ofMinutes` 消费。 |
| F2 双层 `relation` | PASS（A2）/ FAIL（标准 v3 锚点需纠正） | A2 §7.3/§7.5/§7.8 将 `Dependence.relation` 归组间、`DependentTaskModel.relation` 归组内，正确。DS 锚点 `DependentParameters.java:57-70`、`DependentTaskModel.java:29-31`。标准 v3 S4 原来源锚点仍反转组间/组内归属；此处由标准 owner 在获批的 v4 治理中改正，不由 Codex 静默修改。 |
| D1 `dependResult` | PASS（Datara 扩展） | A2 §7.2 正确称为 Datara 扩展，不得声称 DS 执行等价。DS `DependentItem.java:28-35` 有字段，但 `DependentExecute.java:392-416` 判定不读取 `getDependResult()`。标准 v3 来源注释建议补足此限制。 |
| D2 选择器 sentinel | FAIL | A2 §7.1 将缺省 task code 表述成“整工作流成功”，与 workflow-instance sentinel 混淆。应明确 workflow sentinel `0`=工作流实例终态；task sentinel `-1`=全部任务成功检查；具体正 task code=单任务。锚点：UI `use-dependent.ts:72-80,232-245,332-341,394-400`，`Constants.java:183-184`；分支 `DependentExecute.java:149-154,168-230,240-279`。 |
| D3 `parameterPassing` | PASS（A2 单体语义）/ FAIL（标准 v3 S3 对齐） | A2 §7.6 正确作为独立运行时 VarPool OUT 透传，缺省 false，不等价于模板变量。DS `DependentItem.java:34-35`、`DependentExecute.java:287-295,394-414`、`DependentTaskTracker.java:107-118,216-230`、`DependentUtils.java:163-178`。但标准 v3 S3 仍写作观察项并倾向变量引用替代；不能宣称整个契约与标准 v3 对齐，需提请标准 owner 修订/裁定。 |
| D4 `dateValue` / cycle / intervals | FAIL | A2 §7.4 认定 dateValue 为权威输入是对的，但缺少真实 UI 枚举、默认和切换行为，以及多区间 reducer。应登记 cycle=`day/hour/week/month`（新建默认 day）；dateValue 默认 today，切换 cycle 时清空；各 cycle 的选项需按 UI `use-dependent.ts:83-206,452-487` 列全。DS `DependentUtils.java:71-152` 返回区间列表；`DependentExecute.java:124-127,137-160` 顺序检查，缺候选 WAITING，首个非 SUCCESS 即停止；需冻结“多区间必须全 SUCCESS”合成规则。A2 §3.1 仍含 `begin_offset/end_offset`，§7.4 又将其定为扩展，必须明确两套输入能否并存及冲突处理。 |
| D5 `checkInterval` 默认值 | FAIL（A2 事实陈述待更正） | A2 §7.3 说“UI 表单亦无默认值”不准确：DS UI 新建 model 默认 `checkInterval: 10`，见 `use-dependent.ts:45-53`；序列化见 `format-data.ts:657`。后端 DTO `DependentParameters.java:47-49,61-65` 可空，仅正数校验；当前源码树执行路径没有消费 getter。建议写：“UI 默认 10 秒；后端 DTO 无默认且当前执行路径未消费；Datara 可明确选择自己的 runtime 行为，但不能称 DS 后端默认。” |
| D6 timeout | FAIL | A2 §7.9 未厘清 task timeout 起算、策略组合及终态。DS 表单 timeout 缺省 30 分钟、初始策略 WARN，可多选 WARN+FAILED 序列化为 `WARNFAILED`：`use-dependent-timeout.ts:49-107`、`fields/use-dependent.ts:551`、`format-data.ts:478-484,521-523,551-559`。task timeout 与 system max-runtime 两个事件需分开；事件公式 `TaskTimeoutLifecycleEvent.java:48-58`，调度 `TaskStartLifecycleEventHandler.java:70-85`。WARN 只告警，FAILED kill，最终 KILL 非 FAILURE：`TaskTimeoutLifecycleEventHandler.java:67-98`、`AbstractTaskStateAction.java:180-194`。不能臆定同时超时优先级。failure waiting 是另一机制，起点基于 workflow scheduleTime 或 now（`DependentTaskTracker.java:72-100,123-128`），且表单互斥。应拆为失败等待、依赖 task timeout、系统 max-runtime 三项，补齐行为后再冻结。 |

### 标准 v3 对标状态（C1）

- 已对齐：秒字段及分钟×60 换算；双层 relation 语义（但标准 v3 的来源锚点需更正）；`dependResult` 明确为 Datara 扩展；`parameterPassing` 在 A2 中独立建模。
- 不对齐/待修：标准 v3 S3 `:52` 对 `parameterPassing` 的观察项表述与 A2 §7.6 冲突；selector sentinel 说明有歧义；D4 枚举/默认/reducer/offset 双输入未闭合；D5 UI 10 秒默认陈述错误；D6 timeout 语义不完整；标准 v3 S4 `:67` 及 R4 清单 `:101` 的 relation 来源锚点倒置。
- 处置：A2 仍为 pending acceptance；Codex 不改标准正文。标准 v4 属监督线 owner，按 §5 提案/批准/版本升级治理。

## C2 — #37 ①②③正式 PASS|FAIL

**① R2：FAIL（canonical main 未集成 GREEN）。** 分支级 FE contract wiring 和测试通过记录存在，但实现提交 `0824069` 不是 canonical main `e526396` 的祖先；main 缺少 `datara-web/src/services/rebuild/variableApi.ts` 和 rebuild variables router。目标 R2 API 无真实后端联调、无 UI E2E；目标端点 envelope 因端点不存在也未真实验证。证据：`docs/increments/evidence/R2/trae-r2-green-20261017.txt` §2–§6；`rebuild/api/app.py` 当前路由树；handoff #33/#34。结论只能记作 branch-level FE contract evidence，不能签 integrated GREEN。

**② R7：FAIL（canonical main 仍 RED）。** 分支实现提交 `e0a21ff` 不是 main 的祖先；main `metricsApi.ts` 六方法仍为 `notWired`/抛 `R7_METRICS_NOT_WIRED`，对应测试仍断言拒绝未接线请求，验证视图仍标 RED；main 无六个 `/api/v1/rebuild/metrics/*` 端点。现有 governance metrics/quality/lineage 路由不是六方法替代。证据：`docs/increments/evidence/R7/trae-r7-green-20261017.txt` §3–§8；当前 `metricsApi.ts`、契约测试和 `MetricsValidationView.vue`。未有真实 BE integration 或 View E2E。

**③ A2：FAIL（未冻结）。** C1 所列 D2/D4/D5/D6 FAIL 与标准 v3 S3 对齐差异尚未修订/会签。F1/F2/D1/D3 当前契约内容可 PASS，但不足以使 A2 整体冻结。

**标准 v3 对标状态（C2）**：R2/R7 当前主线状态与 v3 的 GREEN 接线目标不符，均需先集成实现、补齐 BE/API 契约证据与规定的 A1-A7 验收证据；A2 维持 RED/pending acceptance。不得以文档、分支测试或 heartbeat 代替集成和验收。

## C4 — R8 三组件对照表 24 个源码锚点复核

复核范围：`docs/increments/2026-10-17-R8批次三组件源码锚点对照表.md`，Vanna/OpenMetadata/DataHub 各 8 项。仅评审，不编辑监督线拥有的对照表，也不代监督线发布 v2。

| 范围 | # | 结论 | 复核点/修订锚点 |
|---|---:|---|---|
| Vanna | 1 | PASS | `legacy/base/base.py:93-168` 是 RAG 生成 SQL；配置初始化另见 `:77-82`。生成不等于执行。 |
| Vanna | 2 | PASS（收窄措辞） | `legacy/base/base.py:238-260` 的 `is_sql_valid` 仅以 sqlparse 检查是否出现 SELECT，不是完整语法、安全或权限验证。 |
| Vanna | 3 | PASS | `legacy/base/base.py:419-486` 抽象训练接口；持久化实现由 integration 提供。 |
| Vanna | 4 | FAIL | `add_sql_to_prompt` 存在但 `get_sql_prompt` 未调用；实际 DDL→documentation→response guidance，再追加相似问答 user/assistant messages。修正锚点/描述至 `legacy/base/base.py:535-658`。 |
| Vanna | 5 | PASS | `integrations/chromadb/agent_memory.py:42-158` 持久客户端、collection、embedding 配置。 |
| Vanna | 6 | PASS（边界注记） | `integrations/openai/llm.py:27-98` 非流式请求中 async 方法同步调用客户端；stream 在 `:108+`。 |
| Vanna | 7 | FAIL | Flask `chat_websocket` 返回 501，占位不可用；Flask 有 SSE/poll。锚点 `servers/flask/routes.py:94-102`。不能写三通道同构。 |
| Vanna | 8 | PASS | FastAPI 注册 SSE、WebSocket、poll：`servers/fastapi/routes.py:17-183`。 |
| OM | 1 | PASS | `TableResource.java:98-114` `/v1/tables` 与字段选择。 |
| OM | 2 | PASS | `DatabaseSchemaResource.java:77-88` `/v1/databaseSchemas`；说明含 tables/views/procedures。 |
| OM | 3 | PASS | `LineageResource.java:92-115`；可补具体 GET/POST 路径。 |
| OM | 4 | PARTIAL | `LineageUtil.java:39-128` 证实 ThreadLocal defer/drain/clear；durable retry 另引 `EntityRepository.java:6181-6193` / RetryQueue-worker，不能将 outbox 实现全归于 LineageUtil。 |
| OM | 5 | PASS | `LineageUtil.java:130-154` domain upstream/downstream。 |
| OM | 6 | PASS（锚点精确化） | Python lineage 实现 `lineage.py:50-74`。 |
| OM | 7 | PARTIAL | Python search API 见 `search.py:137-146`；default index 需另引 `:238-243`。 |
| OM | 8 | PARTIAL | `SearchResource.java:103-162` endpoint 成立；注释描述 `table_search_index`，实际 `@DefaultValue` 是 `table`（`:160-162`），须显式记录不一致。 |
| DH | 1 | PASS | `DatasetProperties.pdl:7-14`。 |
| DH | 2 | PASS | `UpstreamLineage.pdl:2-9`。 |
| DH | 3 | PASS | `UpstreamLineage.pdl:11-26`，`upstreams`/`fineGrainedLineages`/`DownstreamOf`。 |
| DH | 4 | PASS（可补字段锚） | `SchemaMetadata.pdl:11-14` aspect；若描述字段内容，补字段定义行。 |
| DH | 5 | PASS | `Container.pdl:8-11`。 |
| DH | 6 | PASS | `Container.pdl:14-25` `IsPartOf`/searchable。 |
| DH | 7 | PASS | `TagProperties.pdl:6-9`。 |
| DH | 8 | PASS（收窄） | `LineageService.java:45-60` 只证明新增 upstream 必须存在且为 dataset；不是通用 URN/全图边界校验。 |

### C4 工具映射、通道及 O7

- `search_schema`：PARTIAL。OM Table/Schema/REST Search/SDK 是元数据 API；Vanna RAG 相似问答/DDL 是上下文检索参考，不替代 schema catalog；DH aspect 是结构模型。
- `validate_sql`：PARTIAL。Vanna 只检 SELECT，不替代 Datara 语法、安全、权限校验。
- `run_sql`：FAIL。`generate_sql` 是生成。改引 `VannaBase.run_sql`（`legacy/base/base.py:1673+`）、`legacy/adapter.py:32-64,117-129` 或 `/api/v0/run_sql`。
- `get_lineage`：PASS。OM lineage REST 与 DH lineage aspect/校验可作为查询和建模参考。
- `get_workflow`、`validate_workflow`、`inspect_workflow_run`、`get_task_metrics`：PASS，须注明是 Datara 原生能力，非外部组件工具。
- 通道：Vanna Flask SSE/poll 可用，WS 501；FastAPI 三通道齐备，不同构。OM Python SDK 属客户端适配模式。
- OM vs DH 建议：可保留“OM 主参照、DH aspect/fine-grained lineage 补充”作为待裁定提案；将旧的“lineage write reliability：OM retry vs DH validation”拆成“索引失败恢复”与“URN/节点校验”两个维度。
- O7：补记 legacy Flask v0 `/api/v0/generate_sql`（`legacy/flask/__init__.py:307`）、`run_sql`（`:499`）、`get_training_data`（`:742`）、`train`（`:817`）。准确结论：legacy Flask 有这些 v0 接口；当前 v2 Flask/FastAPI routes 注册聊天端点，未注册这些直连接口。不可泛称旧 API 未证实。

**标准 v3 对标状态（C4）**：本审查是源码研读输入，按 O7 要求对每项限定证据范围；本身不升级 R8 GREEN。OM/DH 选型仍为用户/会签决策，监督线负责将意见并入 R8 对照表 v2 并发布。
