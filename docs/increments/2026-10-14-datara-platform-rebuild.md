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

状态：IN_PROGRESS / I18 local dry-run API present; I19-I23 reader/mapper local substeps PARTIAL; remote integration gate PENDING。用户于 2026-10-14 明确批准方案 A。S9 影响分析见 `R3-S9-开始前影响分析.md`；v2 additive schema/migration、I18 七张源表映射/关系图/隔离目标快照/项目授权 API 与 disabled-by-default importer contract 已实现。I19-I23 各 reader/mapper 的本地子步骤及回归见本节后续子批记录，最高均为 `LOCAL_SUBSTEP_PASS / INTEGRATION_GATE_PENDING`。2026-10-15 用户明确批准 MySQL root 仅只读 `datara_meta`；I22 实时 schema 与数量证据、I18-I23 reader allowlist 一致性审计已记录，I21 reader 已依据真实 schema 修复，I22 reader+mapper 完成本地测试。经端口纠正，healthy `datara-rebuild-api` 在容器内 `:8001` 正运行 rebuild API，含 I18 dry-run，但没有本批 I22 mapping-preview；容器挂载的是旧 staging source，当前 worktree 本批代码尚未部署。I22 项目级只读 preview 已在本地实现，远端部署/控件闭环仍 pending。任何 source runtime 仍须固定 allowlist/READ ONLY transaction，不得复用指向 `ec_retail` 的 `REBUILD_MYSQL_SRC_URL` 或输出 root 凭据；不得向目标库导入业务数据，用户另行批准目标写入前不得开启/调用 importer。正式增量只有在 192.168.1.9 前端控件、后端/日志、中间件/资源、真实源/目标 parity 等约法门禁通过后才可 PASS。

2026-10-15 更新：已在用户 root 仅读授权下从 `192.168.1.9/datara-mysql-meta` 读取 I22 七张 `t_std_*` 表的 live `information_schema` 与聚合计数；证据 `evidence/R3/s9-i22-live-schema-20261015.md`。授权仅解锁固定表范围的只读源调查，不允许把 root 凭据配置进服务、不允许目标导入。当前继续按 I22 reader → I22 pure mapper 分批实现；每批按对应影响分析、测试、证据和独立提交完成。API runtime source dry-run、完整 importer/parity 及浏览器控件/日志/资源整体验收仍是独立门禁，R3-S9 仍不能标 PASS。

实现细化：S9 使用 additive revision `r3_0002_legacy_governance_carryforward`，不得修改已登记的 `r3_0001_governance_catalog` 及其 checksum。承接字段以设计 §5.2 的显式列/关系为准；标签定义单独成实体；模型 security/build/owner、指标的派生属性及原始维度、旧 I19 security metadata 均保留为普通业务字段，不引入遮罩/敏感值处理功能。当前代码分支采用 29 张新增承接表（较初始 28 张清单新增旧标签定义实体），迁移前需在文档、revision manifest 和测试中保持同数；如实现需要再扩表，须先更新本计划、设计与台账。

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
3. 按设计 §5.2 扩展规范化 ORM：I18 domain/layer/engine/model/field/relation/version；I19 asset extension/tagging/unresolved tag reference；I20 metric profile/dimension/version；I21 rule definition/task/task-rule/run legacy details/exception/report/alarm policy；I22 standard element/code-set/code-value/naming/mapping/approval/check report；I23 identity mapping。复用现有 asset、tag、quality_rule/run、standard、semantic_metric，不造平行主实体；无法解析的对象键不得创建虚构资产。
4. 新增 additive migration 与 repository/service/API；将每个源行通过 `(source_system, source_table, source_id)` 映射到目标 ID，子表/关系按明确外键顺序导入。对 I21 当前零行表仍须建模并测试空表迁移/后续 API 契约；“当前无数据”不等于忽略业务能力。
   - 项目归属映射必须由有权操作人显式选择目标 `project_id` 并纳入 dry-run；旧源记录没有可证明的项目成员关系时禁止推断。层、域、引擎、资产、标签、指标、标准等引用必须由来源身份映射表解析；未解析引用进入 dry-run 阻断清单，不以同名猜测、自动置空或隐式建关联放行。已实现 I18 七张表的纯映射：字典/模型/字段/版本均保留源身份与业务时间；关系的 src/tgt 模型必须身份解析，字段数组须为等长非空字符串 JSON 列表，并展开为目标关系字段子项。新模型目标自增 ID 尚未生成时用 source identity 符号引用；只有引用身份确在本批源清单中，图校验才允许继续。业务域旧关系明确为 `t_dw_model.biz_domain -> t_biz_domain.name`，故映射器把旧域主键 ID 作为主身份、唯一域名作为显式关系别名；这不是展示名猜测。图校验验证同批父模型存在，并检查关系两侧字段是否在本批字段中；指向已存在目标模型时，dry-run 必须先读取其字段快照后才能验证。此映射仍不读库、不写库。
5. 本地运行定向、全量 pytest，Ruff、compileall、Vue 类型检查和 migration offline/dry-run；检查旧库只读脚本、schema guard 和禁止旧 `api.*`/`common.*` 隐式依赖。更新 R3-S9 本机证据。I18 源 reader 已实现：固定七表/列 allowlist、keyset 分页、总量上限超限即失败；连接仅允许 `REBUILD_LEGACY_META_URL` 指向精确 `datara_meta`，并在只读事务内读取。用户已明确批准本次可使用 root，但必须保持同一 allowlist、只读事务、项目授权先行及无源端 DDL/DML；不得复用指向其他 schema 的 `REBUILD_MYSQL_SRC_URL`。dry-run API 拒绝非 `datara_rebuild_i0` 的目标库；此前该源 reader 未连接 1.9。

#### I22 标准治理实体 reader 与 mapper 增量（2026-10-15）

- 影响分析与现场 schema 绑定：`R3-S9-开始前影响分析.md` 的“I22 live schema gate 解锁与实施影响分析”；权威现场证据 `evidence/R3/s9-i22-live-schema-20261015.md`。只认 7 张表/实测列，不采用设计稿中的虚构列。
- 子批次 A reader：按 7 表精确 allowlist 新增固定列 reader、稳定分页/digest/captured_at、单表/总量限额、缺表缺列拒绝、source/target schema 防混读、只读事务和 SQL listener tests；先 RED。独立提交前跑 I22 与 I18-I23 reader tests、全后端 pytest、Ruff、compileall、diff-check，记录本机证据。无 API/远端部署/前端更改。
- A 当前结果：TDD RED→GREEN；I22 专项 7 passed，I18-I22 reader regression 32 passed，全后端 716 passed（64.38s），Ruff/compileall 通过。证据 `evidence/R3/s9-i22-reader-local-20261015.txt`。本批只证明本地 reader 合同，不是远程 API 或整体验收。
- 子批次 B mapper：以 A 的快照为唯一数据输入，基于现存规范化模型映射 element/code set/value/naming rule/mapping/approval/check report；显式 source identities 解析关联，源值/IDs/时间原样留痕，未知枚举、孤儿或重复关联 fail closed；先 RED，再定向和全量验证、证据及独立提交。不得执行源 SQL/审批动作，不新增用户未批准的目标导入。
- B 当前结果：TDD RED→GREEN；I22 reader+mapper 15 passed，全后端 724 passed（71.64s，含最终回归），Ruff/compileall/diff-check 通过。证据 `evidence/R3/s9-i22-mapper-local-20261015.txt`。实测 approval#1 的 `biz_type=code,biz_id=2` 找不到源码表#2，按阻断保留，未自动跳过或替换。

#### I22 项目级 read-only mapping-preview API 子批

最新状态（2026-10-15）：I22 mapping-preview 隔离 API 与页面已在 1.9 完成受控部署和控件级验证；结果为 `PREVIEW_CONTROL_PASS / PARITY_PENDING / IMPORT_NOT_AUTHORIZED`，不改变 S9/R3 整体 `IN_PROGRESS` 状态。详情见本节后续验收条目及执行台账。

- 开工前影响分析：见 `R3-S9-开始前影响分析.md`“I22 project-scoped read-only mapping preview API 开工影响分析”。实施前已检查本地 I22 mapper、标准规范化 ORM、I18 项目授权 API，以及 1.9 rebuild 容器实际 OpenAPI；范围与验收边界以该影响分析为准。
- 步骤：先为 target SELECT snapshot、source identity/fingerprint 计划服务和 API 项目权限/隔离 schema/源端只读/响应无 payload契约写 RED；实现后跑 I22 定向、I18-I23 治理回归、全后端 pytest、Ruff、compileall、diff-check。任何目标模型语义无法无损表示或未解决关联都保持 blocked，不产生隐式 create/import。随后更新隔离页面显示真实预置项目、行数/分类/关系/阻断及摘要，并通过受保护 runner 完成 1.9 控件闭环与日志/资源检查。
- 2026-10-15 子批运行验收：本地全后端 `pytest tests -q` 728 passed，Ruff/compileall/diff-check 通过；I22 页面静态契约 3 passed、Playwright runner `node --check` 通过。browser-use 对现有标签绑定/AX 读取超时后，按 fallback 技能对 `http://192.168.1.9:18091/rebuild-validation-r3-s9-i22.html` 实际操作 11/11 PASS（run `R3S9I22-20261014215054-01b8e2`）。远端 `datara-rebuild-api` 仅更新隔离 staging 所需文件，先备份 3 个原文件并 SHA-256 对照，import preflight 成功后只重启该容器；正确 `:8001` OpenAPI 包含 I22 preview 与原 I18 dry-run，容器 healthy；web 静态页 200。实时源七域共 3 行（code 1、code_value 1、approval 1，其余 0），UI 显示 2 个新增身份候选、0 个目标身份匹配、1 个 `unresolved_reference` 阻断；无 payload；响应明确 `parity_verified=false`、`import_enabled=false`，I18 import flag 为 false，API access log 为 200。相关依赖 `datara-web` up、`datara-rebuild-api` healthy、source/target 共用的 `mysql-meta` healthy；target schema 精确为 `datara_rebuild_i0`，source 为用户批准的 `datara_meta`/root 只读配置。报告/截图和部署备份位置见执行台账。本结果只关闭 mapping-preview API/UI 子批，不构成 I22 内容 parity、目标导入批准或 S9/R3 PASS。
- 运行事实：2026-10-15 远端 `datara-rebuild-api` 容器内 `:8001` OpenAPI 确认是 rebuild app，含 I18 dry-run、无 I22 preview；运行代码通过 mount 来自旧 staging source。部署时需仅更新隔离 source mount 中本批涉及的新 Backend 文件并执行健康/OpenAPI验证，不替换正式 `datara-api`，不动目标数据。当前本批 endpoint 尚未远端运行验证。
- 安全边界：仅允许项目级 source/target 只读预览。源数据继续使用用户已批准的 `datara_meta` 固定 allowlist + READ ONLY 事务；不回显 payload/root 配置，不改源表；审批 orphan 仍阻断，I18 已批准的 skip 不外推。禁止添加/启用任何目标导入 API 或写入动作。Local tests pass 不等于 S9/R3 PASS。

#### I18-I23 live schema allowlist preflight

在实现下一条 importer/API 链路前，逐域核对所有 I18-I23 reader 固定 allowlist 中的表列是否匹配 `datara_meta` 当前 live schema。先按 `R3-S9-开始前影响分析.md` 相应小节做只读 preflight；仅从 information_schema 取字段/索引/FK metadata，并对 allowlist 表做聚合 COUNT；I23 严禁选择 `user_pwd` 或账户行值。若出现 drift，停下为该 reader 做独立影响分析/修复/测试；无 drift 时记录证据与更新计划/台账后再开始下一编码子批。无 API runtime secret、无部署、无目标导入。

Preflight 发现 I21 reader 三组缺失列（详见 `evidence/R3/s9-live-reader-schema-audit-20261015.md`）。先执行影响分析中的 I21 live-contract 修正子批，之后才可继续 reader/API/importer 复核。I21 六表零行仍不豁免空快照 reader 的 live schema 合同。

I21 修正子批已完成：固定 reader 列已按 live schema 对齐；mapper 用 `source_schema_missing_columns` 备注旧源物理上不存在的字段，不假造原值/时间。I21 reader+mapper 22 passed，全后端 725 passed，Ruff/compileall 通过；证据 `evidence/R3/s9-i21-live-schema-reader-fix-20261015.txt`。仍未配置 runtime source URL/API、部署或导入。
- 验收：A/B 均仅达到 `LOCAL_SUBSTEP_PASS / INTEGRATION_GATE_PENDING`。本次 root CLI schema 查询不等于 Backend runtime dry-run；完整 I18-I23 importer/parity、目标备份/恢复、并发/故障注入、service log/middleware/resource 以及 browser-use→必要时 Playwright 控件闭环继续按计划单独完成。

#### I23 身份映射只读预览 API 与隔离验证页

- 状态：已获授权，实施中；授权不包括身份导入、用户/角色修改、密码访问或正式前端解冻。
- 用户批准：只读 `datara_meta.t_user(id,user_name,user_role,state,create_time,update_time)`；endpoint-only `legacy:i23:preview` 短期 capability；AOCI 仅 acknowledge observe fingerprints。继续排除 `user_pwd`，源端 READ ONLY、target SELECT-only。
- 前序 I22 影响：共享 `governance/api.py`、`api/app.py`、source allowlist/reader 和隔离部署合同；必须保持 I18 importer flag=false，并回归 I22 现有静态页/API。I23 是全局身份边界，不使用项目级 `EDIT_DEFINITION`/普通 DEV token。
- 实施步骤：先 RED 覆盖 scoped token 仅 I23 endpoint 可用、通用 API 拒绝 capability、验证 key 只能签发固定 15 分钟 scope；再实现 I23 endpoint 的 allowlist reader、target identity/user 只读查询、显式映射选择和阻断摘要；增加独立静态验证页和 protected Playwright runner；本地全量测试/ruff/compileall/diff-check；在 1.9 做哈希备份、限量 source/target 审核、只更新隔离容器与 18091 页面，并验证前端控件/API/backend log/MySQL readonly 与 target no-write；更新证据、状态/台账后单独提交。
- 冻结边界：不改正式 Vue/menu、通用权限矩阵、admin/DEV token 权限、DB schema、source data 或 target data；不得在页面或证据记录验证 key/token/口令；任何超出 I23 scope 的 API/数据访问拒绝。
- 验收语义：preview/control loop 通过只能记 `I23_PREVIEW_CONTROL_PASS / IDENTITY_PARITY_PENDING / IMPORT_NOT_AUTHORIZED`，不能提升 S9/R3 为 PASS，也不证明逐字段 parity。
6. 在参考产品风格隔离验证页增加可操作业务场景和稳定 fixture，预置目标项目/数据/表单并呈现行数、快照摘要、计划分类、导入顺序和阻断原因；执行控件级 UI 流程并验证后端 API 结果。使用 192.168.1.9 的非冲突端口部署；页面不得持有统一验证 key，仅由受保护 runner 注入受限短期 token。
7. 远端先只读重采样，再目标快照、dry-run 冲突清单；这些证据仅用于评审，确认 dry-run 的新增/更新/跳过/冲突数与拟定范围一致后，仍须另获用户对目标业务数据写入的明确批准才能执行导入。逐批记录前后时间戳、进程退出码、容器日志、DB 对账查询和恢复点。root 只允许用于 `REBUILD_LEGACY_META_URL` 精确指向 `datara_meta` 的固定 allowlist 仅读，不注入 root 凭据到 Backend。
   - I18 离线 dry-run 契约已要求调用方提供与目标 project 匹配的只读快照（采集时间、摘要、source identity→target ID、业务语义指纹、模型字段集合及项目范围唯一键占用者）。目标快照 repository 已按项目筛选 target ORM，仅用 SELECT 装配这组信息，并重建旧映射语义计算指纹；SQLite 集成测试断言无 DML。当前尚未在 MySQL/192.168.1.9 上运行，也未接 API。计划只分类 create/unchanged/conflict/blocked，冲突不自动更新；有问题的父模型阻断子字段/关系，不能据此授权写入。
8. 按源表逐一对账总数、有效/拒绝/重复计数、来源 ID 覆盖、字段摘要、父子/多对多/血缘关系、版本/审批链、孤儿数量和 `created_at/updated_at/generated_at`；要求未解释差异为 0，所有拒绝行有显式可复现原因。
9. 重新运行目标端重复导入验证无重复且统计 skipped/idempotent；核对 API/UI 展示、数据库行和日志时间；完成异常注入（重复键、非法 FK、中途失败恢复、并发同批请求）及批次级回滚演练。
10. 更新本计划、R3 状态和台账；只有本地检查、参考产品控件流、远端容器/中间件/数据库、日志和数据 parity 四联证据齐全才关闭 S9。R3 的其他未完成子项仍须单独完成后才可转 PASS。

### 文件与验收基线

- 预期后端范围：`datara-backend/rebuild/governance/models.py`、迁移版本文件、repository/service/API、迁移执行器（若需扩展）及 `datara-backend/tests/rebuild/` 对应回归测试；禁止改旧 `datara-backend/api/*` 和旧库模型作为运行真源。
- 验证页/runner/evidence：项目隔离页及其独立契约测试；实测证据存放 `docs/increments/evidence/R3/`，包括 schema snapshot/hash、dry-run、导入批次、逐表逐关系 parity、UI runner JSON/截图、容器/依赖健康和错误日志窗口。
- 必须满足：重复导入后目标无重复；经批准源记录 100% 有目标或显式拒绝原因；所有可解析父子/关联关系 100% 对应；未解释孤儿/数据差异为 0；新增记录 DB 时间戳非空；Ruff/compileall/pytest 全绿；页面所有关键控件闭环；远端服务健康且错误窗口为 0。
- 此增量只形成实施计划，不得把源表当前 0 行作为省略 schema/API/空集行为测试的理由；I23 credential compatibility 若尚未核实，保存账号身份/权限关系并输出重置路径，不输出凭据值。

### 2026-10-15 S9 durable checkpoint/importer 状态覆盖更新

- 本地新增通用 batch/item checkpoint repository 与 I18 service-only importer：同批次幂等键/payload 漂移保护，逐实体事务内写目标行与 checkpoint，失败项留存 class-only 错误并可显式恢复；`conflict` 不自动重试；批准的孤儿版本行持久记录 `skipped` 原因。要求 project `EDIT_DEFINITION`；MySQL target guard 精确限定 `datara_rebuild_i0`，只允许 `:memory:` SQLite 用于本地集成测试；MySQL advisory lock 与本地串行避免同键并发重复执行。
- 当前未增加可触发真实导入的 API route，亦未连接远端、调用 source reader 或写入目标数据。任何面向验证页的导入动作须另经项目权限与明确确认契约，且本轮用户裁定不等同于实际导入批准。
- 本地证据：新增 checkpoint/importer tests 7 passed，全后端 `pytest tests -q` 633 passed，Ruff、compileall、diff-check 通过。仅属内存 SQLite/本机逻辑验证，不能替代 192.168.1.9 服务、MySQL、中间件、资源、日志和浏览器四联门禁。
- 状态保持：R3-S9/R3 为 IN_PROGRESS/PARTIAL；I19-I23 映射与导入、完整 parity、目标备份/恢复、并发及回滚演练、写入确认和 API/页面控件闭环仍未完成。实际导入前必须由人工审阅最新 44-create/1-skip dry-run 及恢复计划并单独批准；不得以此轮“继续推进”解释成数据写入授权。
- 2026-10-15 后续本地批次增加 I18 replay integrity：target ID/provenance/映射字段/关系字段 child rows 在 imported/unchanged 重放时校验；外部漂移生成 terminal conflict，不自动修复或覆盖。修复 `交易`→`交易域` approved alias 经 checkpoint 无法向模型/关系传播 target ID 的缺陷。定向 9 passed、全后端 638 passed、Ruff/compileall/diff-check 通过；此批仍仅本地内存 SQLite，远端状态与导入批准不变。
- 下一本地批次：实施默认关闭的 I18 import API + fresh source/target digest 和显式确认短语契约，仅 mock 验证未来 enabled 调用；不新增验证页按钮/不改 compose 环境、不启用、不部署、不执行目标数据写入。用户的实际目标导入授权和远端快照/parity/恢复门禁仍独立。
- 2026-10-15 API contract 状态覆盖：实现默认关闭 API gate、正数持久 operator+项目编辑授权、精确 target/digest/确认短语和 ready plan 校验；target digest 现在是内容寻址，采集时间独立留痕。`pytest tests -q` 643 passed，Ruff/compileall/diff-check 通过。代码仅在隔离 worktree；运行配置未设为 true、未部署且无目标数据写入。I19-I23 映射及完整远端门禁仍未完成。

### 2026-10-15：I19 只读快照 reader 增量计划

- 前序影响分析：见 `R3-S9-开始前影响分析.md`“I19 元数据与标签只读快照 reader 开工影响分析”；以上一提交 `b78899b` 为基线。
- 本增量只覆盖旧 I19 三表 `t_meta_table_ext`、`t_meta_tag`、`t_meta_tagging` 的固定列白名单、独立只读 snapshot reader、稳定内容摘要及本地只读/分页/上限测试；不改 I18 API、mapper/importer、schema/migration、旧后端、任何前端、compose 或远端运行资源。
- 字段依据限定为旧 ORM 本地声明；S8 只读盘点曾证明三表当时各为 0 行，但本轮不重连旧库，故不能声称已复核当前远端列结构/数据。真实 reader 必须在列不匹配时失败关闭。
- 实施顺序：RED 用例（完整字段/缺列/空集/非空/只读/页序/行数上限/稳定摘要）→ 增加独立 `LegacyI19SourceSnapshot` 与 reader（复用隔离 schema/只读事务约束，不扩大 I18 snapshot 合同）→ 运行定向与全后端 pytest、Ruff、compileall、diff-check → 更新证据、影响分析、计划及台账 → 独立提交。
- 后续显式保留映射前置条件：旧 `ds_id` 到项目内目标 asset 的精确身份表、标签定义与归一化 tag 双实体的父子身份、tagging target key 的资产/字段解析规则；本批不猜测、不清空/改写 unresolved 引用，不声称 I19 mapper/parity 完成。
- 运行状态仍禁止访问源/目标 MySQL、部署、启用导入旗标、实际业务数据写入或浏览器门禁。本地结果只构成 reader 逻辑证据；后续启用源 reader/API 或导入，仍受完整 I18-I23 parity、目标快照/恢复/并发/回滚、远端验证及独立目标写入批准约束。
- 实现闭环：新增 `LegacyI19SourceSnapshot`、I19 fixed-column allowlist 与 `LegacyI19SourceReader`；不改变 I18 snapshot/API/error contract。定向 I19 reader 7 passed，I18+I19 reader regression 11 passed，最终全后端 `pytest tests -q` 650 passed in 61.34s，Ruff/compileall/diff-check 通过；真实远端 source schema 仍未验证。证据：`evidence/R3/s9-i19-source-reader-local-20261015.txt`。
- 状态：本地 reader 合同完成；I19 mapper/API/importer/parity 以及 I20-I23 未完成。无远端部署、旧库连接或目标业务写入。依约法四条，本步骤仅为 `LOCAL_SUBSTEP_PASS / INTEGRATION_GATE_PENDING`，browser-use 控件、后台日志、中间件/资源联验未通过/未执行，不能计正式增量 PASS。

### 2026-10-15：I22 源 schema 证据门与实施顺序调整

- 设计依据已补至重建设计 §13.15：I18-I23 完整承接决策不变；迁移字段映射必须绑定当前只读 schema 证据，历史主题设计稿或 dated inventory 不单独构成 source contract。
- 核查发现：`remote-schema-inventory.txt` 捕获于 `2026-10-14T17:55:28+08:00`，现存字段与 `I22-数据标准管理设计.md` 有具体差异，且当前隔离工作树没有旧 Std ORM/API。差异及范围记录见 `R3-S9-开始前影响分析.md`“I22 旧标准表 schema 证据差异复核”。
- 阻断项：I22 不开始字段 mapper/source allowlist/parity/import，直至通过批准的数据库只读途径取得当前 7 张 `t_std_*` 表的 schema identity、列/类型/nullability/default、PK/unique/FK/index 与采集时间摘要。未把 DB root 凭据放入应用，也未推断 OS root 授权。
- 无关工作仍可推进：I19 标签与资产关系的纯本地映射研究、I20 指标/版本和 I21 质量行映射可依据其自身旧 ORM 字段契约分批开发；每批均须独立影响分析、定向/全后端与静态验证。所有本地子步骤仍需保留 `LOCAL_SUBSTEP_PASS / INTEGRATION_GATE_PENDING`，只有 192.168.1.9 browser-use + API/日志 + middleware/resources 的约法闭环通过后才能关闭对应正式增量。

### 2026-10-15：I20 指标源只读快照 reader 增量计划

- 前序影响分析：见 `R3-S9-开始前影响分析.md`“I20 指标只读快照 reader 开工影响分析”；基线为 `23cc06f`。
- 限定文件/合同：在 governance source reader 增加 `t_indicator`、`t_indicator_version` 固定列白名单和独立 I20 snapshot/read API；本地增加 SQLite-only fixture 测试。不能改变 I18/I19 reader/API合同与错误文本。
- 映射语义边界：本批只作固定列原样快照，不解释 `dims`、`snapshot_json` 或 base metric 身份，不解析 JSON、不转换业务时间、不写目标侧。
- 验收步骤：TDD RED→实现→I18/I19/I20 定向测试→全后端 pytest→Ruff/compileall/diff-check→更新证据/影响分析/本计划/台账→独立提交。完全本地测试仍不构成正式增量 PASS。
- 运行安全：不连 `datara_meta`/target MySQL，不部署、不修改容器/中间件/正式前端、不新增可触发导入的 API/UI。I20 正式端到端验收仍需 192.168.1.9 的前端控件、后端 API/日志及中间件/资源闭环；缺少环境/数据证据时保持 pending。
- 本地结果：I20 定向 7 passed，I18-I20 三套 reader regression 18 passed；全后端 `pytest tests -q` 657 passed in 67.09s；Ruff、compileall、`git diff --check` 通过。证据 `evidence/R3/s9-i20-source-reader-local-20261015.txt`。这是 reader 子步，不代表 mapper/API/import/parity 或正式增量 PASS。

### 2026-10-15：I21 六表质量治理源快照 reader 增量计划

- 前序影响分析：见 `R3-S9-开始前影响分析.md`“I21 质量治理只读快照 reader 开工影响分析”；基线提交 `af0cb61`。
- 范围：六张 I21 表的 fixed-column allowlist + 独立 read-only snapshot reader + SQLite 本地契约测试；列依据仅为保留旧 QC ORM。旧 QC router/engine 已退役，本批绝不恢复执行/调度功能。
- 映射边界：JSON 配置/统计/报告保持原样，不解释 SQL、质量语义、状态或关系，不连接数据源，不写目标实体。
- 步骤：TDD RED→实现→I18-I21 reader 回归→全后端 pytest→Ruff/compileall/diff-check→更新本地证据/影响分析/计划/台账→独立提交。schema 差异一律 fail closed。
- 运行/验收安全：不连接旧库或目标库，不部署/改服务或前端，不做 API/UI/日志/中间件/资源验证。本地通过不等同正式增量 PASS；I21 后续 mapper/parity 和 192.168.1.9 控件闭环仍 pending。
- 本地结果：I21 reader 7 passed；I18-I21 readers 25 passed；全后端 `pytest tests -q` 664 passed in 67.78s；`ruff check rebuild tests/rebuild` 和 `python -m compileall -q rebuild` 通过。证据 `evidence/R3/s9-i21-source-reader-local-20261015.txt`。只完成源 reader 子步，integration gate pending。

### 2026-10-15：I20 指标纯映射增量计划

- 开工前影响分析：见 `R3-S9-开始前影响分析.md`“I20 指标 source-to-target 纯映射开工影响分析”。此前 reader commits：I20 `af0cb61`、I21 `ce4fa69`。
- 输出契约：snapshot → metric/profile atomic bundle + individual version rows; preserve `dims` as exact legacy free text (no delimiter inference) and preserve version JSON without reconstruction. Resolve base metric only through explicit source identity maps; unknown status/reference/duplicate/orphan becomes a blocker.
- 本批无 schema migration、ORM/API/importer/UI 或 DB write；后续 importer 必须支持 bundle 原子 checkpoint 和 pending identity 解析，本批不提前宣称可导入。
- 步骤：TDD RED→纯 mapper→mapping + I18-I21 reader回归→全后端 tests + Ruff/compileall/diff-check→项目证据/台账→独立 commit。
- 验收范围仅本地逻辑；实时 MySQL schema、browser 控件、API/log/middleware/resources 及数据导入均为 pending。
- 本地实测：I20 mapper 11 passed；I18-I21 readers + I20 mapper 36 passed；全后端 `pytest tests -q` 675 passed in 70.63s；Ruff、compileall、diff-check 通过。证据 `evidence/R3/s9-i20-mapper-local-20261015.txt`。仅纯映射合同，未接 importer/API/数据库。

### 2026-10-15：I21 质量治理纯映射增量计划

- 开工前影响分析：见 `R3-S9-开始前影响分析.md`“I21 质量历史 source-to-target 纯映射开工影响分析”；前序 reader 基线 `ce4fa69`。
- 输出契约：从六表 snapshot 生成 normalized rule/task/task-rule/run legacy details/exception/report/alarm records；强制 project ID；关联通过同批 source identity 或现有显式 target ID 解析；无法解析即阻断。规则 level/status 与 SQL 原文保留；JSON 作为 JSON value 稳定编码，不解释/执行。
- 旧 QC router/engine 维持退役状态；不生成虚假 asset/canonical quality rule，不将历史 run 伪装成新执行。
- 步骤：TDD RED→纯 mapping bundle→I18-I21 readers + I20 mapping regression→全后端测试/静态检查→evidence/ledger/plan→独立提交。目标 schema 不改。
- 验收仅本地逻辑；源 schema、真实关联/parity、importer/API、browser、运行资源和业务数据写入皆 pending。
- 实测结果：I21 mapper 14 passed；I18-I21 reader + I20/I21 mapper regression 72 passed；当前全后端 `pytest tests -q` 689 passed in 66.31s；Ruff、compileall、`git diff --check` 通过。规格审阅发现 run/exception 非空 `task_id` 还需解析目标任务，修复并复核通过；独立代码质量审阅未返回，不能记为通过；之后加固无效显式 target ID、date-only 时间戳和超大 numeric 边界。详见 `evidence/R3/s9-i21-mapper-local-20261015.txt`。
- 映射细节：run/exception 的非空 `task_id` 必须命中同批任务或显式 target/pending identity，同时 `legacy_task_id` 保持源 ID；目标日期列仅接受 datetime 或可解析的无时区 ISO 值，带 offset 阻断；report/alarm 使用调用方 target IDs。结果仍是 `LOCAL_SUBSTEP_PASS / INTEGRATION_GATE_PENDING`，没有 importer、实时 schema/parity、API/UI/远端运行资源或数据写入验收。

### 2026-10-15：I19 元数据扩展/标签纯映射增量计划

- 前序影响分析：见 `R3-S9-开始前影响分析.md`“I19 元数据扩展与标签纯映射开工影响分析”；reader 基线 `23cc06f`。
- 输出契约：三表 snapshot 纯 map；extension 只关联操作者显式给定且 project-scoped 的 Asset，不推造资产；旧 Tag 映射 normalized tag + legacy definition bundle；tagging 保持原 target type/key，只有 exact project-scoped target asset map 才填 resolved asset，其余原键留存且 resolved_asset_id 为空。
- TDD：覆盖空/完整/多行、tag 双实体、顺序/身份、显式重复映射、跨项目、未知 target type、悬空资产键/tag、重复键、源 JSON/日期/长度/target project；任何不可表示/引用缺失均 issue+block。
- 步骤：先 RED→纯 mapper/context/bundle→I18-I21 reader 与 I20/I21 mapper regression→全后端 `pytest tests -q`、Ruff/compileall/diff-check→项目内证据与台账→独立 commit。
- 无 importer/API/ORM/migration/数据库连接、实际导入、部署、页面/远端控件或 browser/log/middleware/resources；该子步骤最高只可为 `LOCAL_SUBSTEP_PASS / INTEGRATION_GATE_PENDING`，正式 I19 parity 与 S9 仍待完整门禁。
- 实测：I19 mapper 11 passed；I18-I21 reader + I19-I21 mapper 回归 83 passed；全后端 `pytest tests -q` 700 passed in 73.02s；Ruff、compileall 通过。规格审阅在提交前仍未回报，不记 PASS。证据：`evidence/R3/s9-i19-mapper-local-20261015.txt`。

### 2026-10-15：I23 用户身份最小只读快照 reader 增量计划

- 基线：I19 mapper 已提交 `150edd0`；I22 保持 schema evidence gate，不将历史 inventory 当作当前 schema。
- 只实现 `t_user` 六列 allowlist (`id/user_name/user_role/state/create_time/update_time`) 及只读 snapshot reader；明确排除 `user_pwd`，不得读取用户行或凭据。旧 ORM 为来源字段证据，新身份 `Role` 为后续角色映射目标。
- 不在本批实现 mapper/importer/口令重置、成员关系、API/UI、DDL、数据库连接或部署；绝不从用户/所有者猜项目成员。
- 执行次序：测试 RED→实现 reader→I18-I23 reader regression/全后端 pytest/Ruff/compileall/diff-check→写证据并更新影响分析、计划、台账→独立提交。
- 结果最高为 `LOCAL_SUBSTEP_PASS / INTEGRATION_GATE_PENDING`；真实源 schema/data、identity mapper/importer、项目成员关系、密码 reset、1.9 控件、运行日志/中间件/资源均须后续门禁，不得宣称 I23/R3 完成。
- 实测：I23 reader 4 passed；I18/I19/I20/I21/I23 reader regression 29 passed；全后端 704 passed in 66.28s；Ruff、compileall 通过。SQL listener 确认 SELECT/PRAGMA only，未选择 `user_pwd`。详见 `evidence/R3/s9-i23-reader-local-20261015.txt`。

### 2026-10-15：I23 显式用户身份关联纯映射增量计划

- 目标仅将 I23 源用户身份关联到调用方显式指定、已存在的新用户；校验用户名/Role/状态精确一致后映射至 `LegacyIdentityMappingRecord`。旧/new 静态 Role 当前枚举一致；未知值、目标不存在/跨引用重复、属性不匹配均阻断。
- 不创建或更新用户、不读或迁移 `user_pwd`、不推断项目成员、不改认证/重置流程、不部署/调 API/DB/UI。
- 顺序：RED tests→纯 mapper→I23 与治理 readers/mappers regression→全后端 pytest/Ruff/compileall/diff-check→记录证据→本增量单独提交。
- 只可记 `LOCAL_SUBSTEP_PASS / INTEGRATION_GATE_PENDING`，不等于用户迁移、身份 parity 或 R3 关闭。
- 实测：I23 mapper + reader 9 passed；全后端 709 passed in 68.62s；Ruff、compileall、backend diff-check 通过。证据 `evidence/R3/s9-i23-mapper-local-20261015.txt`。

### 2026-10-15：I23 项目外身份预览 API 开工前权限与数据边界核查

- 前序影响：刚完成并部署的 I22 mapping-preview 使用 project `EDIT_DEFINITION`，查询仅限该项目；I23 的 `LegacyIdentityMappingRecord` 是全局用户身份关联，不能复用项目权限或将项目编辑权限扩大为全局账号查询。
- 现有合同：I23 mapper 要求调用方显式提供 source-user→已存在 target-user 的选择，并精确核对 username/role/status；source allowlist 列为 `id,user_name,user_role,state,create_time,update_time`，明确排除 `user_pwd`；目标实体含 `rebuild_user` 与 `rebuild_governance_legacy_identity_mapping`。
- 阻断：当前验证 token 是 `Role.DEV`，只有 `EDIT_DEFINITION/RUN_INSTANCE/VIEW_ALL`，不含 `MANAGE_USER`；提升共用 token 到 admin 或让 project editor 查询全局用户都违反最小权限。既有 I23 reader 的 schema/count 检查不等同于用户批准读取 `t_user` 业务行；本批尚未读取用户行。
- 后续仅在用户明确裁定后再实施：推荐固定 source `datara_meta.t_user` 六列、READ ONLY transaction；target 只 project-independent SELECT；接口限定短期 `legacy:i23:preview` 只读能力且不能复用全局 admin/导入权限；前端逐项显式选择已有 target ID，展示匹配/缺失/属性差异，不创建/更新用户、不访问密码、不猜成员关系。必须先确定来源行读取批准和 browser-use/Playwright 如何取得不扩大通用权限的测试能力；其后再依次 RED→GREEN、API+页面、1.9 控件/日志/数据库资源验证和独立提交。
- 当前状态：`BLOCKED_PENDING_POLICY_APPROVAL`，未改代码、未部署、未查询 `t_user` 行、未写 target。此处阻断不影响已完成的 I22 read-only preview 子批；R3-S9/R3 仍 IN_PROGRESS/PARTIAL。
