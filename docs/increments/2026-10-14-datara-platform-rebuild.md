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
| R2-01 治理域 | IN_PROGRESS | 本轮已将五域真源、采集/解析/质量责任与迁移原则写入设计 §5；仍需完成 I18-I23 表/API/菜单/消费者映射和逐域验收证据。 |
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
