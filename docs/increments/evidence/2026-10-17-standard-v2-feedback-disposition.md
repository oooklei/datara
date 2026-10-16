# 核心业务功能标准稿 v2 反馈处理报告

- 评审日期：2026-10-17
- 评审对象：`docs/increments/2026-10-17-核心业务功能实现规范与验收标准.md`（权威设计稿 v2）
- 直接反馈来源：并行协作 handoff 心跳 #38（质量监督员对 DBX–DS 源码研读映射的评审及标准稿 v2 联合评审请求）
- 交叉核验：DBX/DS 源码复核、R2/R5 当前实现证据、用户此前给出的核心业务要求
- 处理边界：本文件是正式评审意见和拟修订文本，不直接改写标准正文、不发布新版本，也不替代 §5 要求的提案审批与双边会签。

## 1. 总体结论

标准稿 v2 的优先级原则、后端先行、R 系列契约验证页与最终功能验证页分层、DBX 优先并融合原版 SQL IDE 优势、DS 全链路复刻、变量体系作为跨域基础等方向与用户要求一致，建议保留。当前版本仍有若干会改变运行语义或验收结论的缺口，故本轮结论为：**方向通过，规范文本有条件通过；修订并履行 §5 版本流程前，不得据此冻结 A2/A5，也不得把相关 RED/WIP 标记为 GREEN。**

本轮没有发现需要“拒绝”的反馈意见。需要调整实施阶段或范围的意见均标为“有条件采纳”，条件在相应条目中列明；这不代表降低用户定义的最终能力要求。

## 2. 逐条反馈与裁定

| 编号 | 类别 | 反馈 / 问题 | 结论 | 处理与依据 |
|---|---|---|---|---|
| F1 | 问题 | DS `failureWaitingTime` 源单位为分钟，而 A2 使用 `failure_waiting_seconds`，存在 60 倍误差风险。 | 采纳 | 在映射和标准中写明 `wire_seconds = source_minutes × 60`，只接受正整数分钟，禁止隐式舍入；校验乘法范围。`checkInterval` 单位为秒，须分开记录。来源：DS `DependentParameters.java:66-69`。 |
| F2 | 问题 | DS 的 `dependTaskList`、组间 `relation`、`checkInterval`、失败策略和等待时间属于嵌套 `Dependence`，并且组间、组内各自有 AND/OR；拍平或固定组间 AND 会丢失行为。 | 采纳 | A2/映射采用嵌套 `dependence` 对象，分别建模组间 relation 与每组 relation；覆盖 AND/AND、AND/OR、OR/AND、OR/OR。来源：`DependentParameters.java:33-78`、`DependentTaskModel.java:26-31`。 |
| G1 | 建议 | DBX–DS 映射未登记原版 SQL IDE 与 DBX 的融合议程；原版特有且兼容的界面/操作优势没有评估。 | 采纳 | 增加逐能力比较表：DBX 基线、原版 SQL IDE 现状、冲突点、裁定、复用/不复用理由及证据锚点。冲突优先 DBX；只有不改变 DBX 语义、权限、安全及项目隔离的原版优势才可吸收。 |
| G2 | 补充需求 | DBX 对象树类型粒度不清，不能判断函数、存储过程、触发器、索引等对象是否纳入覆盖。 | 采纳 | 增加 `database → schema → object → column` 层级和对象类型 × 驱动能力矩阵。DBX `ObjectSourceKind` 包含 view/materialized view/procedure/function/trigger/event/sequence/synonym/job/package/type 等，但不含 table/index；table 有独立 DDL/结构模型，index 是表结构子对象。必须分别标明 list/get-definition/editability/generator/execution/rollback 能力与驱动限制，不以单个 `list_tables` 能力代表完整对象树。 |
| G3 | 问题 | DDL 深度研读状态未同步“R5-A 必做前置”，可能绕过关键证据门。 | 部分采纳 | 采纳“必须完成 DDL 源码与设计差距研究并作为 R5-A/A5 规格决策前置”。对“对象编辑全链路是否必须在 R5-A 实现”不作无条件采纳：权威设计 §7.1、§13.6 要求定义编辑、校验、依赖、影响预览、快照、确认、执行、日志及回滚/补偿；审查发现这些不能仅凭 DBX 已有 SQL 执行器宣称等价。建议把定义读取/只读目录与写入 DDL 闭环分开设门；写路径可以分批，但不得从最终验收范围删除，分批版本需经 §5 审批。 |
| D1 | 问题 | 标准将 `dependResult` 与 DS 原生结果直接关联，可能错误声称“依赖上游失败也成立”已由 DS 实现。 | 采纳 | 明确 DS 模型虽含该字段，但核验的 `DependentExecute` 判定路径不消费它。Datara 的 `depend_result: success|failed` 按用户要求可作为 Datara 扩展验收，但必须单独定义单项极性、AND/OR 三态组合先后顺序、`NON_EXEC`/超时映射；不得标为 DS 原生等价。来源：`DependentItem.java`、`DependentExecute.java`。 |
| D2 | 问题 | workflow 成功、所有任务成功、指定任务状态是三个独立选择器；以 task code 缺省推断整工作流会混淆。 | 采纳 | 规范明确 `workflow → DEPENDENT_WORKFLOW_CODE`；`task + selector=all_tasks → DEPENDENT_ALL_TASK_CODE`；`task + selector=task + upstream_task_code → 指定任务`。禁止由缺省 task code 猜测。验收覆盖无实例、禁用/流任务、运行中/重试及自依赖首实例。 |
| D3 | 问题 | `parameterPassing` 与模板变量解析不等价；标准当前将其描述为可被变量引用替代的观察项。 | 采纳 | 将上游成功 VarPool OUT 到下游的透传作为独立行为；默认关闭，保留同名值选择规则。只有全覆盖替代方案经用户批准才可替代。R2 与 R4 的变量存储集成可后续设计，但契约必须冻结且不能据此省略 R4 验收。来源：`DependentItem.java:33-38`、`DependentExecute.java:392-414`。 |
| D4 | 问题 | DS `cycle + dateValue` 不能未经证明视作双输入运行语义，也不等价于 Datara offset/ISO 窗口。 | 采纳 | 以 `dateValue` 作为窗口计算的权威输入；`cycle` 仅作表单分组/输入合法性校验（若保留 wire 字段）。服务端按业务日期、时区及边界规则生成 `DateInterval[]`；offset/ISO 是 Datara 扩展，除非逐窗口、多区间验证，不得宣称 DS 等价。 |
| D5 | 问题 | 标准未充分区分 DS 依赖失败等待与依赖节点等待超时，二者表单互斥、默认及单位不同。 | 采纳 | 分别定义：`failureWaitingTime` 是 WAITING 策略下失败结果等待时间，源单位分钟；依赖节点 `timeoutFlag/timeout/timeoutNotifyStrategy` 是另一项“等待依赖完成”配置，默认关闭，开启时 timeout 默认 30 分钟、通知默认 WARN，可选 WARN/FAILED，并与 failure-waiting 配置互斥。写明起算点、窗口关闭行为、正数校验及默认值；`checkInterval` 默认 10 秒。 |
| D6 | 问题 | 标准将 DBX “异步执行”概括为后台提交/轮询，和源码行为不完全一致。 | 采纳 | 区分普通 `execute_query`/`execute_multi`（调用等待查询结果）、多语句进度事件、`execute_conditional_update` 的异步/超时特例，以及 `execution_id` 取消。Datara 的 taskId、SSE/轮询、分页、取消、终态与 TTL 是 Datara 后端合同，另行定义，不冒称 DBX 原生语义。 |
| V1 | 问题 | S3 “旧版已有该实现逻辑”“R2 已冻结域”夸大当前证据；解析器增量不是七命名空间服务、resolver、校验或 attempt 快照。 | 采纳 | 改为“旧版有部分兼容语法及解析行为；七级 namespace 统一契约是目标能力，落地/冻结状态以 R2 契约和证据为准”。当前纯 tokenizer 识别不等于所有文本输入位已接入、也不等于 VariableService 完成。旧语法兼容边界另列决策，不可静默破坏。 |
| V2 | 问题 | `parameterPassing` 与变量体系关系表述不一致。 | 采纳 | 按 D3 修订 S3 及通用验收项：变量解析和 VarPool OUT 运行时透传分别建模、分别验收；合并存储或快照是实现集成选择，不得抹掉透传行为。 |
| B1 | 问题 | §4 R5-A 将多个 DBX 能力合称“九能力”，但没有清晰逐项矩阵、对象树/DDL 边界及 Datara 项目隔离要求。 | 采纳 | 改为逐项证据矩阵，至少覆盖 SQL 查询、多语句、结果网格/分页、历史、SQL 资产、导出、异步/取消、跨 Schema、对象浏览/定义；另外分别登记类型化错误、驱动 × 操作能力及本地桌面存储到 project-scoped Backend 的迁移差异。对象写入流程不得用只读能力通过。 |
| B2 | 疑问 | DDL 编辑应处于 R5-A 还是拆成只读 R5-A、写入 R5-B？DBX 的对象源编辑和结构化表编辑不等于 Datara 设计要求的版本、发布、审计、回滚闭环。 | 有条件采纳 | 同意将 DDL 证据研究作为 R5-A/A5 的规格前置，并区分只读目录/定义读取与有副作用的 DDL 写操作。建议 R5-A 验证对象发现、能力矩阵允许的定义读取、表/Schema 元数据、权限/隔离、跨 Schema 查询与一般 SQL 非执行解析；不将 DBX schema-diff DependencyGraph 视为通用只读依赖 API，也不把表结构草稿输入校验视作对象 DDL 编译校验。对象依赖/影响预览、草稿、DDL 语法校验、快照、确认、发布/执行、审计及回滚/补偿归 R5-B 或独立受控批次。条件：这只是阶段划分提案，不减免 §7.1/§13.6 最终能力；需标准 owner 按 §5 形成版本修订并会签后生效。 |
| A1 | 补充需求 | #38 通知 Vanna、OpenMetadata、DataHub 三组件资料包，要求 R8 研读并决定 OM 或 DH 主参照。 | 有条件采纳 | 纳入 R8/A5 后续研究清单：按源码锚点比较 Vanna 工具调用、OM/DH 元数据模型/REST/aspect、权限和治理能力，再由证据提出主参照建议。当前不裁定 OM 或 DataHub 为主参照；资料已就位不是已研究或已验收的证据。 |
| P1 | 建议 | #38 要求修订映射 v2 并由 Trae 回传 Resolved。 | 采纳 | 映射文档由其单一 owner 修订；Codex 提供本报告、DS 源码差异与条款建议，待 v2 回传后复核 F1/F2 及新增运行语义。 |

## 3. 可直接纳入标准修订的拟议条文

以下是建议文本，作为标准稿 v3 提案材料；在 §5 审批前不直接替换权威正文。

### S3 变量体系（建议替换状态与 parameterPassing 文字）

> 所有纳入本规范范围的文本输入位均应支持统一变量契约；具体输入位清单、旧语法兼容规则、命名空间解析、类型/权限校验、补全、运行值透传和 attempt 级不可变快照分别列入 R2/R5 API 与验收矩阵。旧版实现仅作为语法和行为兼容证据，不据此宣称七级命名空间能力已完成。实现冻结及完成状态以当前契约、证据和门禁记录为准。SQL IDE 后端应复用同一变量服务和快照能力。
>
> DolphinScheduler `parameterPassing` 是独立的运行时值透传能力：默认 false；仅按契约规定在成功上游依赖满足后，将 VarPool OUT 参数传递至下游，并保留同名参数选择语义。不得以模板变量解析替代该行为。若提出全覆盖替代方案，须先提交差异、失败行为和验收证据并履行 §5 审批。

### S4 依赖对象模型与状态（建议替换相关表格行）

> DS 参数必须保留嵌套 `dependence` 模型及两级 relation：依赖组之间 relation 与每组内部 relation 独立配置，覆盖 AND/AND、AND/OR、OR/AND、OR/OR。`checkInterval` 使用秒；DS `failureWaitingTime` 使用分钟，映射至 Datara 秒字段时按 `seconds = minutes × 60` 精确转换，不舍入。失败等待与依赖节点等待超时分别建模并遵守 DS 表单互斥规则。
>
> 上游选择器无歧义区分 workflow 最终状态、所有有效非流任务成功、指定任务状态；不得用缺省 task code 推断选择器。DS 原生计算状态按 SUCCESS/WAITING/FAILED 及适用的 NON_EXEC 边界映射。`dependResult` 在 DS 参数模型中存在，但经审阅的执行路径未消费；Datara 单项成功/失败极性属扩展，必须明确极性转换、两级 AND/OR 合成顺序和 timeout/NON_EXEC 行为。
>
> 时间窗以 `dateValue` 为权威运行输入，`cycle` 仅作分组/校验信息；运行时按业务日期、时区及明确的边界规则生成一个或多个 `DateInterval`。Datara offset/ISO 字段不得未经逐例证明宣称与 DS 等价。

### §4 R4 / R5-A 验收（建议补充）

> R4 冻结前必须通过双层 relation 组合、三个上游选择器、分钟到秒换算、等待/超时互斥、DateInterval 多区间、NON_EXEC、失败极性扩展及 parameterPassing 的契约案例。以上语义未定或未有证据时，R4 保持 RED。
>
> R5-A 的 DDL 精读为只读契约冻结前置，交付对象 × 驱动能力矩阵和映射决议。R5-A 实现/验收限定于只读对象目录、能力矩阵允许的定义读取、表/Schema 元数据、跨 Schema 查询与补全、一般 SQL 的非执行解析/lint，以及拟纳入、待相应契约冻结后验收的异步/取消/结果/历史/资产/导出能力；不执行 DDL，不承担对象依赖/影响分析或对象 DDL 语法编译验证。Table/Index 作为结构化表模型（Index 是表结构子对象）；View/Function/Procedure/Trigger 等按 source-backed 对象分类。草稿、结构化 DDL 生成、对象 DDL 语法校验、依赖/影响评估、diff、快照/版本、人工确认、发布执行、审计及失败回滚/补偿归 R5-B 或经 §5 批准的等价阶段；最终能力仍须满足 §7.1/§13.6。DBX 桌面编辑能力存在，不代表 Datara 跨驱动、项目隔离的后端能力已实现；R5-A PASS 不授权对象写入。

### S2 / S5 附加验收说明（建议补充）

> R 系列契约接线页只验证后端契约、状态和证据，不得标为最终功能验证页；最终页面须在后端冻结后按目标组件真实字段、默认值、校验、交互顺序和结果反馈单独验收。R8 对 Vanna、OpenMetadata、DataHub 的研读结论须附来源锚点；主参照选择在证据形成后作为变更提案会签。

## 4. 歧义及需在版本提案中明确的具体问题

这些是待决策项，不阻止本报告完成，但在规范冻结前必须处理：

1. **DDL 阶段边界：** 对象编辑/DDL 写闭环是 R5-A 必做，还是 R5-A 先冻结只读和元数据合同、R5-B 实现写入闭环？无论如何，§7.1/§13.6 目标是否完整保留为最终验收项？本报告建议后者分阶段、保留最终要求。
2. **失败极性组合：** Datara 扩展的 `dependResult=failed` 如何转换成单项三态结果，并在 OR/AND、NON_EXEC、超时与自依赖首实例下如何合成？需提供真值表和边界案例。
3. **时间语义：** 业务日期由调度时区还是项目时区提供？DST、左闭右开边界、节假日/业务日历、跨日及多个 DateInterval 的排序/合并规则是什么？
4. **参数透传冲突：** VarPool OUT 与显式变量定义/同名局部值冲突时，采用 DS 原规则还是统一 VariableService 的优先级？需明确来源和失败策略。
5. **变量兼容：** 旧 `${...}` 与 `$[...]` 词法边界、允许的标识符字符，以及 `${date(N)}`、`${tmp.*}`、`${run.*}`、`${wf.*}` 与七级命名空间的映射/弃用方式。
6. **DBX 对象能力：** 各对象类型和各数据库驱动是否都支持定义读取、结构化编辑、DDL 执行？`ObjectSourceKind` 与驱动矩阵、 overload identity、分页及权限范围需由源码证据确认。
7. **DBX 融合裁定：** 原版 SQL IDE 中哪些操作优势可被吸收、哪些与 DBX 冲突而必须舍弃？逐项矩阵给出决策 owner 与证据。
8. **R8 主参照：** OpenMetadata 或 DataHub 哪个作为治理元数据主参照；Vanna 的工具调用方法如何与 Datara Agent 权限、审计及确认门组合？须待三组件研读后提案，不在当前无证据裁定。

## 5. 文档修订清单

| 文档/区域 | 必要修改 | Owner / 完成证据 |
|---|---|---|
| 核心业务标准 v2 → v3 提案 | 修订 S3、S4、§4 R4/R5-A，补充 S2/S5 说明和本报告第 4 节待决项；版本号、日期、变更记录齐全。 | 标准文档 owner；按 §5 提案、审批、双边会签及 heartbeat。 |
| DBX–DS 研读映射 v1 → v2 | 落 F1/F2/G1-G3；补 relation 四组合、单位、选择器、parameterPassing、日期区间、对象树/驱动矩阵、DBX 异步语义及原版 SQL IDE 融合对照。 | Trae（handoff 单一 owner）；源文件行锚和 Resolved 回执。 |
| A2 R4 依赖/资源契约 | 修 nested dependence、三 selector、failure polarity 扩展、秒/分钟、等待/超时互斥、dateValue 真值、parameterPassing；契约例和错误语义。 | A2 owner；冻结前 Codex/Trae 复核与合同证据。 |
| R5-A/R5-B 计划与验收 | 拆分只读目录/定义获取和 DDL 写路径门禁；逐项九能力/驱动矩阵；最终保留 §7.1/§13.6 写入闭环。 | R5 owner；DBX 源码差异矩阵、权限/安全验收。 |
| R8/A5 资料研究 | Vanna/OM/DH 来源锚点比较，提交主参照选择提案。 | R8 owner；三组件研读表与会签记录。 |

## 6. 后续跟进与正式回复草稿

### 跟进事项

1. Trae 按第 2、3 节修订 DBX–DS 映射 v2，并逐项回填 #38 的 Resolved 状态；Codex 复核 DS 运行语义与源码锚点。
2. 标准文档 owner 将本报告作为 v3 修订提案，依 §5 完成审批、双边会签及新版本/heartbeat；在此之前 v2 正文保持原样。
3. A2 冻结前完成第 4 节 1–5 项决策并将答案写入契约和验收例；不得通过口头默认或实现代码反向决定契约。
4. R5-A/R5-B 分阶段提案确认后，按 DBX 对象 × 驱动矩阵推进；未完成 DDL 闭环的阶段必须保持 RED，不用 routine catalog/list 能力代替对象编辑验收。
5. R8 启动三组件研读，主参照结论只在证据充分后提案；当前不把资料包已发布等同研究完成。

### 可直接发送给 handoff 对接方的回复

> 已完成标准稿 v2 联合评审。总体方向认可，但规范文本有条件通过，尚不具备 A2/A5 冻结条件。监督员 #38 的 F1（failureWaitingTime 分钟到秒换算）和 F2（嵌套 Dependence 及两级 relation）均采纳为必改；G1（原版 SQL IDE 融合议程）、G2（对象树类型粒度）采纳补齐；G3（DDL 精读作为 R5-A/A5 前置）采纳。源码复核另识别出三选择器不可混淆、`dependResult` 非 DS 已消费语义、`parameterPassing` 不可由变量解析替代、dateValue/时区/多区间语义、依赖失败等待与依赖节点等待超时需分开，以及 DBX 常规查询 await 与条件更新异步特例等 P1 修订项。DDL 写入闭环建议按只读能力与受控写入能力分阶段，但不得降低设计 §7.1/§13.6 的最终目标。详细裁定、拟议条文、歧义清单和修订 owner 见 `docs/increments/evidence/2026-10-17-standard-v2-feedback-disposition.md`。本回复是 v3 修订提案，不是静默改版；按标准 §5 完成审批、双边会签和新版本发布后生效。Vanna/OpenMetadata/DataHub 资料研究及主参照选择作为 R8 后续项，不预先宣称完成。

## 7. 后续状态校正（依据 handoff 心跳 #39–#41）

本报告起草后，共享 main 已继续推进，以下新裁定优先于本报告原“待提案”表述：

- 心跳 #41 记录用户裁定：保留 `failure_waiting_seconds` 字段名；不改为 `failure_waiting_minutes`。F1 的核心风险控制仍采纳，必须在实现和验收中明确 DS 源分钟 × 60 转为契约秒并覆盖换算测试。
- 用户批准组间 relation；标准稿 v3 已落库（main `3378175`），S4/§4 已补 `group_relation: AND|OR`、默认 AND 和相应验收项。该项由“拟修订”转为“已按裁定修订”，A2 契约需同步会签。
- 心跳 #39/#40 已登记映射 v2 和三组件研读产出；本报告中的 G1-G3 应结合映射 v2 当前内容复核，不应把已落库事项继续列为未完成。R8 的 OM/DH 主参照仍待正式裁定；当前研读建议 OM 为主参照、DH aspect 用于细粒度血缘参考。
- 本报告仍是评审记录，不取代标准稿 v3 或后续 heartbeat；A2、R5-A/R5-B 的状态需按共享 main 最新契约和实施证据重新判定。任何“已冻结/已完成”表述都须以最新 handoff、标准正文和实际证据为准。

