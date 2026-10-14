# Datara 平台重建增量计划（评审修订版）

> 与《2026-10-14-datara-platform-rebuild-design.md》逐项对齐；当前序列统一为 R0-R11。每个增量遵守项目五条约法。2026-10-14 用户裁定 D-2/A：R4=SYNC，IDE=R10-A/R10-B；验证页面按该能力对应参考产品自身的前端页面、表单和用户操作流构建，旧 Datara 前端仅在 Backend 冻结后融合。测试运行环境使用统一验证 key 经 Backend auth API 预取短期 token，页面不显示登录表单、不持 key；门禁不要求人工点击登录页。

## 1. 增量总览

| 增量 | 交付重点 | 依赖 | 独立门禁 |
|---|---|---|---|
| R0 | 环境、测试库、证据和编号基线 | 无 | compose/时间戳/证据目录 |
| R1 | identity、project、RBAC、datasource 公共服务 | R0 | 统一验证 key 换短期 token、权限/连通性验证页 |
| R2 | 测试数据、schema 探查、metadata/data_asset 基线 | R0/R1 | 192.168.1.9 MySQL 对账 |
| R3 | DAG 执行、SQL/Python/Shell/依赖/调度、实例指标 | R1/R2 | 隔离页 + API + Master/Worker 日志 |
| R4 | SYNC 三类编排（源表基准/目标表基准/文件同步）、探查映射、全量/增量执行器 | R1/R2/R3 | 三场景可运行、映射可编辑、行级指标与端到端对账 |
| R5 | lineage 解析与 data_transfer 关系 | R3/R4 | 表级/字段级 lineage 对账 |
| R6 | 治理目录、quality 规则/运行/异常、标准资产承接 | R2/R5 | 五域真源和规则运行 |
| R7 | 调度增强、重试/超时/告警、HA | R3 | misfire/并发/故障恢复 |
| R8 | Kafka 流运行时与生产观摩工作流 | R2/R3 | 长驻/停止/续位点/吞吐 |
| R9 | 任务中心、实例树、导出、版本和监控 | R3/R7 | 操作闭环和指标时间戳 |
| R10-A | SQL IDE 只读能力 | R1/R2 | 资源树/补全/执行/分页/历史/导出 |
| R10-B | SQL IDE 对象写路径 | R10-A/R1 | DDL diff/备份/发布/回滚 |
| R11 | AI 工具契约、浮动助手、全盘验收 | R1-R10 | tool schema/权限/审计/预算 |

### 1.1 IDE 试行材料的重新归属（裁定 A）

- 原 `R4-设计文档.md`、`R4-开始前影响分析.md` 以及 `evidence/R4/r4-s3-*` 记录的是旧 Datara 数据源/IDE 后端上的探索试验，不是本次新 Backend 的 R4，也不能计作 R10-A/R10-B 验收通过。
- 将上述材料作为历史输入保留；其中可复用的业务发现须逐项重新核对成熟参考系统源码/文档与冻结后的新 Backend 契约。R10-A/R10-B 必须重新实现、重新部署并在 `evidence/R10-A/`、`evidence/R10-B/` 形成新证据。隔离页路径后续改为 R10-A 标识，避免把历史 `rebuild-validation-r4.html` 与 SYNC 的 R4 混淆。
- 下一项按依赖顺序为 R4-SYNC：已新建 R3→R4 影响分析与 DolphinScheduler DataX 参考初步对照；开工前继续完成上游引擎版本/边界核验和 endpoint/mapping/checkpoint API 合同冻结。R4 验证页按 DolphinScheduler DataX 页面流程（端点选择、参数/SQL 配置、列探查、映射调整、校验/预览、提交运行及结果查看）设计，使用统一验证 key 获取的短期 token 调用新 API；不复刻 Datara 旧页面，不把页面简化为 API 按钮。

### 1.2 每增量的参考研究产物

开始相应实现前，至少建立一份项目内对照记录：产品及版本/提交、官方开发或用户文档章节、源码模块/关键类与调用链、参考产品前端路由/页面/组件/表单字段/校验与关键用户操作流、核心数据模型/API 契约、Datara 新 Backend 映射、偏离项及理由、由隔离验证页执行的同语义验收案例。隔离页必须让评审者按参考产品业务路径操作（可由预置数据降低输入成本），但调用 Datara 新 Backend；不调用旧 Datara API、不把验证页做成只有 API 按钮的技术面板。引用以可复核的来源路径/URL和版本为准；不可仅凭产品名称或旧系统页面宣称已对齐。

## 2. 批次 2 的 15 项修复任务

| 任务 | 具体步骤 | 产物与完成条件 |
|---|---|---|
| R2-01 治理域 | 补五域模型、真源和外部导入边界；登记旧 I18-I23 资产承接/迁移/废弃决策 | 设计矩阵、迁移表、API 边界 |
| R2-02 调度 | 固化触发、时区、misfire、并发、优先级、worker、重试、告警 | schedule/command/instance 契约和测试 |
| R2-03 权限 | 实现最小 token/RBAC/project_member 与数据范围检查 | identity/project API、拒权测试 |
| R2-04 DDL | 新增 draft/diff/backup/publish/rollback 状态机与审计字段 | R10-B DDL 契约、危险 SQL 拦截 |
| R2-05 变量 | 建类型/作用域/表达式/现时值/补全契约，运行日志输出解析值 | VariableService schema、正负测试 |
| R2-06 流 | 固化 Kafka、长驻 job、attempt/offset/heartbeat 生命周期 | R8 流状态图和生产观摩方案 |
| R2-07 结果集 | 冻结 taskId、cursor、分页、TTL、截断、取消、导出协议 | R10-A 结果集协议 |
| R2-08 部署 | 写清 compose 拓扑、env 配置、日志卷、health 和扩容边界 | 环境清单、compose 校验 |
| R2-09 AI | 把五个 AI 工具纳入 API 清单、权限、审计和冻结门禁；保持浮动图标不加菜单 | AI tool contract、验收项 |
| R2-10 指标 | 为延迟、吞吐、完整率、证据格式定义量化基线 | 指标表和 JSON 证据规范 |
| R2-11 SYNC | 把同步执行器纳入组件单一真源和执行链，补全/增量/断点/行计数 | worker/master/scheduler/catalog 对齐 |
| R2-12 datasource | datasource 先行覆盖 CRUD、连通、schema/table/column、连接池 | 公共前置 API 和探针 |
| R2-13 测试库 | 明确 1.9 MySQL schema 供给和 init SQL，默认时间戳真测 | 远端 schema/默认值证据 |
| R2-14 门禁 | 每后端增量建立按参考产品前端用户流程设计的隔离验证页，正式前端冻结；测试运行环境用统一验证 key 调用 R1 token API 获取受限短期 token 并注入页面上下文，不要求用户登录或暴露 key；browser-use 优先，一次有界重试仍阻塞即 Playwright 同页操作；API-only 不可替代 | key→token 签发及范围/过期测试、控件闭环与双通道/运行资源证据；R1 单独验 auth/RBAC |
| R2-15 IDE 拆分 | R10-A/R10-B 拆计划、文件、测试和发布门禁 | 两份验证单，写路径单独审批 |

## 3. 本批次执行顺序

1. 对上一批 R3/D-2 影响复核：只读确认 R0-R11 路径、D-1 豁免、Qc ORM 保留和 1.9 健康；逐项见 `R3-to-batch2-impact-20261014.md`。
2. 先完成设计/计划 15 项同源修订，更新台账并执行文档交叉检查。
3. 执行后端契约扫描：`rebuild/` 代码禁止隐式依赖旧 `api.*`/`common.*`，只有显式白名单可用；AI 工具必须存在 schema 和权限断言。
4. 本机执行 Python compile、定向 pytest、Vue 类型检查（依赖不存在时记录环境阻塞，不伪报 0 错）。
5. 将需要运行的最小验证页部署到 192.168.1.9 的非正式端口，验证 API、容器、MySQL/Redis/ZK/Kafka 和日志。
6. 完成四联证据后独立提交批次 2；没有浏览器控件级证据不得标记全绿。

### 3.1 R2-01—R2-15 状态跟踪（2026-10-14）

| 任务 | 状态 | 已有证据/未完成条件 |
|---|---|---|
| R2-01 治理域 | IN_PROGRESS | 用户已裁定 D-R3-S8=A：扩展新 Backend 规范化模型完整承接 I18-I23。实体清单/语义/迁移边界见设计 §5.2、§6；R3-S9 影响分析与实现闭环未完成，仍需逐源表/实体/关系 parity 及隔离验证页证据。 |
| R2-02 调度 | DESIGN_DEFINED | 设计矩阵有触发/时区/misfire/并发/worker 契约；需核验实现、故障/并发测试及真实运行证据。 |
| R2-03 权限 | DESIGN_DEFINED | 最小 RBAC 与范围策略已定义；需核验新 Backend 认证/API/拒权覆盖及验证页证据。 |
| R2-04 DDL | DESIGN_DEFINED | 已要求 R10-B draft/diff/backup/publish/rollback；尚未实现/验收，不允许提前开放写路径。 |
| R2-05 变量 | DESIGN_DEFINED | 类型/作用域/补全/现值/运行快照已定义；需模型、验证、日志实测。 |
| R2-06 流 | DESIGN_DEFINED | Kafka 与长驻 stream 状态机已定义；需真实生产观摩及故障恢复证据。 |
| R2-07 结果集 | DESIGN_DEFINED | taskId/cursor/TTL/截断/取消/导出已定义；需 R10-A 协议测试和 UI 证据。 |
| R2-08 部署 | DESIGN_DEFINED | 1.9 compose 拓扑、配置和日志/health 已定义；需核验 env 引用、compose 与日志聚合证据。 |
| R2-09 AI | DESIGN_DEFINED | 五工具契约/权限/审计/预算与浮动助手边界已定义；需代码 schema、拒权和冻结门禁。 |
| R2-10 指标 | IN_PROGRESS | 本轮将过时全量测试数 536 更新为实测 583，并记录 QC browser 21/21；其余性能基线需专门采样。 |
| R2-11 SYNC | DESIGN_DEFINED | 执行器链路已写入设计；需 datasource 前置、执行器实现和全量/增量/断点/行计数闭环。 |
| R2-12 datasource | DESIGN_DEFINED | CRUD/探查/连接池契约已定义；需实现与跨 schema、失败路径验证。 |
| R2-13 测试库 | PARTIAL | 1.9 运行 schema 已供测试，R3 时间戳/行数证据部分存在；需把 schema/init 与默认值证据按新 Backend 契约核实。 |
| R2-14 门禁 | IN_PROGRESS | token bootstrap 与 Playwright 同页策略已有；QC 批次 1 21/21 PASS，仍需每个后端增量依照参考产品 UI 做闭环。 |
| R2-15 IDE 拆分 | DESIGN_DEFINED | R10-A/B 已拆分；需两份独立验证单和 DDL 写路径审批边界。 |

此跟踪表是最高实证状态，不以“设计中有一行”代替代码/远端/控件验收；状态提升须附证据链接并同步更新台账。

## 4. 与旧资产的处置

旧 I18-I23 后端资产不因重建文档创建而删除：先做表/接口/菜单映射，再分别标记“承接、迁移、冻结或废弃”。`Qc*` ORM 保留，旧质量 API 源文件已按批次 1 清除；旧前端 mock 只有在正式融合增量时才清理。

## 5. 证据和时间戳

每个增量的证据路径为 `docs/increments/evidence/R{n}/`；运行表的 `created_at/updated_at/generated_at` 必须来自数据库默认或后端持久化，证据同时记录 API 返回时间、数据库行、容器日志时间和验证页操作时间。

## 6. 当前实测基线回写（2026-10-14 Asia/Shanghai）

| 项目 | 实测值 | 环境/证据 | 结论 |
|---|---:|---|---|
| Backend 全量回归（最新） | 584 passed / 60.91s | 本机 `datara-backend/tests`，含 QC 权限回归断言；前一 QC 退役基线 583/65.47s 见 `evidence/R3/batch1-postdeploy-20261014.txt` | PASS |
| 批次 2 runner 定向回归 | 4 passed / 0.12s | 本机 `datara-web/deploy/test_r3_governance_runner.py` | PASS |
| R3-3 调度契约定向测试 | 2 passed | 本机 `test_i3_schedule_contract.py` | PASS |
| Vue 类型检查 | `vue-tsc --noEmit` 0 errors | 本机 `datara-web` | PASS |
| 远端 API 健康 | `UP`；`db=true`、`redis=true`、`zk=true` | 192.168.1.9:8000 | PASS |
| 调度/依赖/补数实例 | 3 个实例均 success；3/3 任务成功 | 192.168.1.9 Master/Worker 日志与 metrics | PASS |
| QC 退役浏览器控件闭环 | 21/21 assertions；browser errors=0 | Playwright 操作同一 `192.168.1.9:18091/rebuild-validation-r3.html`；browser-use 无法绑定 tab 后按 R2-14 回退 | PASS |

以上数字为本轮实际测量值，不是目标值；目标值仍以 R2-10 的响应、延迟、完整率和吞吐门禁为准。

## 7. R3-S9：I18–I23 规范化模型扩展与隔离迁移

状态：IMPACT_ANALYSIS_COMPLETE / READY_FOR_LOCAL_IMPLEMENTATION；用户于 2026-10-14 明确批准方案 A。S9 影响分析见 `R3-S9-开始前影响分析.md`；批准范围是模型扩展、计划更新和完整承接，不代表可以跳过逐批门禁或直接改旧库。

### 开始前影响分析与边界

- 前序影响：R3-S6 已在隔离 `datara_rebuild_i0` 安装 12 张通用治理表；R3-S7 已写入可识别的验证 fixture；R3-S8 只读采样确认旧库 I18 有 45 条、I22 有 3 条，I19/I20/I21 当前为 0，I23 `t_user` 有 4 条。迁移统计必须区分 S7 fixture、历史来源行和新目标行。
- 业务影响：需要扩展治理 ORM/migration/API 和验证页，要求项目归属、稳定来源键、主子实体、版本/审批/历史关系及统一时间戳；可能影响 R5/R6/R11 的 API contract。不能在没有实体映射和回归证据时将旧资产标记为完整承接。
- 数据边界：源 `datara_meta` 只读；所有 DDL/DML 仅可作用于 `datara_rebuild_i0`。执行前生成并校验目标 schema/数据快照，记录 SHA-256、目标 schema identity 和数据库时间；导入采用批次 ID、source identity、幂等唯一键及逐记录 checkpoint。任何目标行冲突不得覆盖。
- 回滚：按 migration batch 精确回滚新增批次且未被新业务引用的记录；schema 变更只做 additive migration。恢复前后核对 schema 指纹、目标表行数和批次状态；不允许 DROP/TRUNCATE，不允许恢复旧 QC API/engine。
- 控件门禁：新验证页按 OpenMetadata/DataHub 目录与对象详情、标准/指标/质量任务的参考产品真实操作语义设计；通过新 Backend API 预置/查看/复核资产、模型版本、指标维度、标准码值审批、质量任务运行与异常报告。browser-use 优先，按 R2-14 限次回退同页 Playwright；API-only 不能替代控件闭环。正式 Vue 继续冻结。
- 停止条件：旧源快照与 R3-S8 证据不一致、目标 schema 非唯一、活动验证 fixture 无法排除、来源键冲突/归属不唯一、源只读权限失效、目标快照不可恢复、parity 有缺失或额外关系、运行服务出现 error marker、远端执行影响旧库/其他 schema。

### 细化步骤

1. 复核并冻结 R3-S8 源/目标 schema 指纹、表列/键/外键、精确行数及所有实体字段映射；补足 I18-I23 完整性矩阵和 I23 用户/角色/权限映射。只读检查，不读取/输出口令明文。
2. 本地先为新实体/API/migration contract 编写失败测试：来源组合唯一键、外键与级联策略、项目授权、统一时间戳、历史版本完整性、孤儿拦截、幂等与重试、回滚隔离及错误批次续跑。
3. 按设计 §5.2 扩展规范化 ORM：I18 domain/layer/engine/model/field/relation/version；I19 asset extension/tagging；I20 metric dimension/version；I21 quality task/task-rule/run/exception/report/alarm policy；I22 standard element/code-set/code-value/naming/mapping/approval/check report；I23 identity mapping。复用现有 asset、tag、quality_rule/run、standard、semantic_metric，不造平行主实体。
4. 新增 additive migration 与 repository/service/API；将每个源行通过 `(source_system, source_table, source_id)` 映射到目标 ID，子表/关系按明确外键顺序导入。对 I21 当前零行表仍须建模并测试空表迁移/后续 API 契约；“当前无数据”不等于忽略业务能力。
5. 本地运行定向、全量 pytest，Ruff、compileall、Vue 类型检查和 migration offline/dry-run；检查旧库只读脚本、schema guard 和禁止旧 `api.*`/`common.*` 隐式依赖。更新 R3-S9 本机证据。
6. 在参考产品风格隔离验证页增加可操作业务场景和稳定 fixture；执行控件级 UI 流程并验证后端 API 结果。使用 192.168.1.9 非冲突端口部署；页面不得持有统一验证 key，仅注入受限短期 token。
7. 远端先只读重采样，再目标快照、dry-run 冲突清单；确认 dry-run 的新增/更新/跳过/冲突数与批准范围一致后才执行导入。逐批记录前后时间戳、进程退出码、容器日志、DB 对账查询和恢复点。
8. 按源表逐一对账总数、有效/拒绝/重复计数、来源 ID 覆盖、字段摘要、父子/多对多/血缘关系、版本/审批链、孤儿数量和 `created_at/updated_at/generated_at`；要求未解释差异为 0，所有拒绝行有显式可复现原因。
9. 重新运行目标端重复导入验证无重复且统计 skipped/idempotent；核对 API/UI 展示、数据库行和日志时间；完成异常注入（重复键、非法 FK、中途失败恢复、并发同批请求）及批次级回滚演练。
10. 更新本计划、R3 状态和台账；只有本地检查、参考产品控件流、远端容器/中间件/数据库、日志和数据 parity 四联证据齐全才关闭 S9。R3 的其他未完成子项仍须单独完成后才可转 PASS。

### 文件与验收基线

- 预期后端范围：`datara-backend/rebuild/governance/models.py`、迁移版本文件、repository/service/API、迁移执行器（若需扩展）及 `datara-backend/tests/rebuild/` 对应回归测试；禁止改旧 `datara-backend/api/*` 和旧库模型作为运行真源。
- 验证页/runner/evidence：项目隔离页及其独立契约测试；实测证据存放 `docs/increments/evidence/R3/`，包括 schema snapshot/hash、dry-run、导入批次、逐表逐关系 parity、UI runner JSON/截图、容器/依赖健康和错误日志窗口。
- 必须满足：重复导入后目标无重复；经批准源记录 100% 有目标或显式拒绝原因；所有可解析父子/关联关系 100% 对应；未解释孤儿/数据差异为 0；新增记录 DB 时间戳非空；Ruff/compileall/pytest 全绿；页面所有关键控件闭环；远端服务健康且错误窗口为 0。
- 此增量只形成实施计划，不得把源表当前 0 行作为省略 schema/API/空集行为测试的理由；I23 credential compatibility 若尚未核实，保存账号身份/权限关系并输出重置路径，不输出凭据值。
