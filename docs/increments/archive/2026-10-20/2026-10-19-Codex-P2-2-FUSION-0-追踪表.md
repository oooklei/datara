# P2-2-FUSION-0：P1-7 融合追踪表与 A5 待决项

- 日期：2026-10-19；监督线派单 #d8604539 / STATE S39。
- 基线：领单后的 HEAD `72d4e72`（仅 STATE 心跳提交）；`datara-web/` 工作树干净。领单时 `datara-backend/` 已有未跟踪 `.dockerignore`、`rebuild/rb/`、`rebuild_e2e_r2.db`，属并行工作，不纳入/不覆盖。
- 输入：P1-7 研读 `docs/increments/2026-10-19-P1-7-DBX融合研读-Claude线.md`（`7c61093`）；融合方案 `docs/increments/2026-10-19-Codex-P2-2-DBX-SQLIDE融合实施方案.md`（`4aa901f`）；A5 v1.0 冻结合同 `docs/increments/2026-10-18-A5-SQL-IDE后端契约-v1.0-冻结候选.md`；R5-A 草案 `docs/increments/2026-10-18-P2-2-R5-A-SQL-IDE后端设计草案.md`。
- 判定：纳入 R5-A / 吸收（UI）/ 纳入 R5-B / 范围外 / 待裁或待证。证据等级：**C**=冻结契约/用户裁定；**S**=Datara 静态源码或设计；**R**=P1-7 所锚 DBX/原版源码研读；**U**=缺目标环境生产运行证据。C/S/R 不证明生产能力。

## 1. F 融合点（13 项）

| 项 | 来源锚 | Datara 对应点 | 阶段 0 决策 | 证据/缺口 |
|---|---|---|---|---|
| F1 连接池分级 | P1-7 §2 F1 L54 | P2-2 §3/§5 datasource/connection 适配；A5 #1–#9 使用 datasource/capability | **纳入 R5-A**：分级池语义，Datara 自有实现 | R+S；池容量、回收、driver 行为 U |
| F2 驱动运行时进程治理 | §2 F2 L55 | P2-2 §2/§6：IDE 消费已批准 datasource，不含启动/重启子系统 | **范围外（本阶段）**；Agent/JDBC/插件运行时如为必需，另立运行时任务 | R+S；目标 driver cohort U |
| F3 多语句批执行 | §2 F3 L56 | A5 §3 #9、§4：auto、全批预检、只读顺序执行、partial_failure | **纳入 R5-A**，严格按 A5，不假设事务原子性 | C+R；逐方言与只读账号 U |
| F4 结果集分页 | §2 F4 L57 | A5 #12 固定 history/resultSet 快照分页；§5 导出 | **纳入 R5-A（适配）**：分页读同一快照，禁止静默重跑 SQL | C+R；容量/driver 实测 U |
| F5 语句边界切分 | §2 F5 L58 | A5 #9、§4：变量解析后切分完整语句并全批预检 | **纳入 R5-A**；选区不能产生半条执行单元 | C+R；多方言边界 U |
| F6 语义补全 | §2 F6 L59 | A5 #1–#8 元数据/lint；编辑器补全为 UI | **吸收（UI）**：服从 Datara metadata 与 R2 变量权威，不新增 API | C+S+R；生产元数据 U |
| F7 SQL 格式化 | §2 F7 L60 | Ctrl+Shift+F，A5 无格式化 API | **吸收（UI）**：列入前端验收 | R+S；UI/方言验收待 Phase 3 |
| F8 类型化错误 | §2 F8 L61 | A5 §2.1 稳定 HTTP/domain envelope，各方法定义错误语义 | **纳入 R5-A**：不透传 driver 原始异常 | C+R；driver 错误映射 U |
| F9 对象 DDL 双轨编辑 | §2 F9 L62 | A5 #18 shared getDefinition 只读；#21–#25 R5-B policy/impact/confirm/执行/审计 | **拆分**：定义读取 R5-A；写编辑纳入 R5-B 人工闸 | C+R；逐 driver/object 能力 U |
| F10 跨 Schema 执行 | §2 F10 L63 | A5 #1–#7 ObjectRef、#9 执行上下文 | **纳入 R5-A**：显式路径/default-schema 规则，不做全局 SQL 改写 | C+R；跨 Schema 权限/执行 U |
| F11 数据编辑闭环 | §2 F11 L64 | DBX DataGrid/DML；R5-A 禁止目标库 DML，R5-B 范围是 DDL | **范围外**：不扩入本轮 R5-A 或 P2-3 DDL 写闭环 | C+R；未来需另立裁定 |
| F12 历史与资产 | §2 F12 L65 | A5 #13–#17 history/script、#20 dataset；项目 ACL/revision/保留规则 | **纳入 R5-A**：以 Datara 平台资产为真源 | C+R；ACL/CAS/清理实证 U |
| F13 数据导出 | §2 F13 L66 | A5 §1/§5：查询快照和授权 ObjectRef 表导出，CSV/JSON/XLSX | **纳入 R5-A（合同扩展）**：只读限额，不接受任意 SQL | C+R；容量/下载 ACL/清理 U |

## 2. C 冲突（7 项）

| 项 | 来源锚 | Datara 对应点 | 阶段 0 决策 | 证据/缺口 |
|---|---|---|---|---|
| C1 编辑器内核 | P1-7 §3 C1 L74 | Datara Monaco；方案 §3 C1 | **待架构门**：吸收 DBX 编辑语义；本单不授权换内核 | S+R；前端架构决定非 A5 后端项 |
| C2 执行粒度 | §3 C2 L75 | A5 #9/§4 已冻结完整语句、全批只读预检 | **纳入 R5-A**：按 A5 收敛 | C+R；方言样例 U |
| C3 对象枚举 | §3 C3 L76 | A5 #1–#7/#18 的 Datara 九类合同子集；event routine 排除 | **纳入 R5-A 九类**，不自动扩至 DBX 13 类 | C+S+R；driver/object capability U |
| C4 连接模型 | §3 C4 L77 | P2-2 §2/§6 与 A5 datasource/capability 边界 | **纳入 R5-A 语义、Datara 自实现**；进程治理不隐含纳入 | C+S+R；driver cohort/生命周期 U |
| C5 凭证 | §3 C5 L78 | A5 §1/§4 凭据不得进入 SQL/history/普通日志/事件/导出；遵循 R2/Datara 安全权威 | **纳入安全边界**，不复制 DBX SecretCodec 实现 | C+R；Datara 存储/轮换的实现证据待查 |
| C6 生命周期 | §3 C6 L79 | A5 #9–#12/#19、§4 task/SSE/cookie/cursor/恢复 | **纳入 R5-A**：DBX 语义经 Datara taskId/SSE 适配 | C+R；取消回收/断线恢复 U |
| C7 编辑器交互 | §3 C7 L80 | datara-web IDE；页面受分阶段方案 §1.2 冻结 | **吸收（UI）**：逐项评估，不复制整套或改页面 | S+R；Phase 3 切片待立项 |

## 3. 原版 SQLIDE 吸收项（8 项）

| 项 | 来源锚 | Datara 对应点 | 阶段 0 决策 | 证据/缺口 |
|---|---|---|---|---|
| A1 悬浮表/视图生成 SQL | P1-7 §4 A1 L88 | A5 #3/#18 对象信息/只读定义；草稿为 UI | **吸收（UI）**：仅生成草稿，禁止自动执行 | C+S+R；正式 UI 权限提示待验 |
| A2 结果 Tab 回显 SQL/复制 | §4 A2 L89 | A5 #12/#13 结果引用与历史 | **吸收（UI）**：关联原 SQL/语句索引，复制不改数据 | C+R；现页面映射待验 |
| A3 快捷键 | §4 A3 L90 | Ctrl+Enter→#9；Ctrl+S→#16；格式化为 UI | **吸收（UI）**：仍受权限、只读门、revision CAS | C+R；键位冲突待 UI 验收 |
| A4 结果漂移提示 | §4 A4 L91 | A5 #12 固定不可变结果快照 | **吸收（UI）**：不得虚称数据库快照隔离 | C+R；UI 提示未验 |
| A5 服务端重放分页 | §4 A5 L92 | A5 #12 同快照分页 | **吸收并适配**：“重放”不等于重执行 SQL | C+R；TTL/容量 U |
| A6 变量分色/补全 | §4 A6 L93 | R2 变量权威；A5 #9/§4 snapshot、安全边界 | **吸收（UI）**：变量服从 R2，不泄漏解析值 | C+R；端到端 U |
| A7 失败即停/警告/取消 | §4 A7 L94 | A5 §4 终态、cancelExecution 与 driver 确认 | **吸收并按 A5**：不复用旧 `api/ide.py` 执行语义 | C+R；事件/回收 U |
| A8 独立数据源中心 | §4 A8 L95 | Datara 既有中心；A5 消费授权 datasourceId | **保留并集成入口**：不在 IDE 复制数据源真源 | C+S+R；导航待 UI 验收 |

## 4. A5 冻结核对与待决/待证清单

A5 v1.0 已冻结生效（契约头部、§7）。R5-A 草案 §9/§11 是冻结前议程，不能整体继续标为“未裁”；冻结合同升版须遵标准 v4 A6 双线会签。

| 旧议题锚 | 状态 | 当前合同与后续动作 |
|---|---|---|
| §9.1 参数/分页/幂等；§11.1 capability envelope/ObjectRef | **已裁定** | A5 §2.2、§3 #1–#20 定义 envelope、完整 ObjectRef、方法参数、分页和幂等；按合同接线。 |
| §9.2 task/SSE/cancel/结果引用 | **合同已定，生产待证** | A5 #9–#12/#19、§4 定义状态机、cookie、cursor、恢复。目标 driver 的并发、取消终止和断线恢复仍须集成证据。 |
| §9.3 语句/批执行/只读 | **已裁定，逐方言待证** | A5 §4 冻结全批预检、只读、顺序执行和 partial_failure；对应 parser/driver 行为须实测。 |
| §9.4 一期 driver profile/Agent/JDBC/插件 | **待定范围/待证** | A5 §2.2/§6 要求未实测 operation 为 unknown，但未指定一期 driver cohort 和 operation/ObjectKind 矩阵；owner 须先定范围并逐项验收。 |
| §9.5 AST 方言、routine 调用、只读账号 | **原则已定，profile 细节待决/待证** | A5 §4 要求真实只读权限+AST/driver 门，不能安全分类则 fail-closed；每个方言的函数/过程调用和无法提供只读账号时的拒绝策略须明确并实测。 |
| §9.6 快照/导出/TTL | **主体已裁定，部署限额待证** | A5 #12/#20、§5 冻结分页、保留期、CSV/JSON/XLSX 和导出路径；部署容量、行/字节限额、下载 ACL/清理证据待补。 |
| §9.7 history/script 生命周期 | **已裁定** | A5 #13–#17、§5 冻结项目共享、revision CAS、软删除、保留和审计。 |
| §9.8 手动 IDE run_id | **待决** | 草案 §7.1/§9.8 要求不伪造 workflow 关联；A5 定义 taskId/historyId/sessionId，未见独立 IDE run_id 裁定。owner 决定是否需要及其与 workflow run_id 隔离规则。 |
| §9.9 对象/定义读取 | **边界已更新，能力待证** | A5 §1、#5/#18 明确 R5-A 可按 capability 只读取定义，R5-B 复用 shared reader；旧草案“R5-A 不返回源码”已由冻结合同取代。event routine 排除；逐 driver/object 能力矩阵待验。 |
| §9.10 错误码/HTTP | **已裁定** | A5 §2.1 与方法表定义稳定错误；driver 映射和安全性仍需实现验证。 |
| 方案 §3 C1 编辑器内核 | **非 A5 待决项** | DBX 交互语义按 D9 优先；是否替换 Monaco 是 Phase 3 前端架构裁定，不在本单决定。 |

### 核对结论

- 已逐项映射 28 项；P1-7 静态源码研读和 UI 锚不等于 Datara 运行证据。A5 v1.0 为当前后端合同权威。
- 需要 owner 明确的范围事项：一期 driver cohort、手动 IDE run_id 策略；若替换 Monaco，先走前端架构门。driver capability、只读执行、SSE/取消、分页导出和保留策略须按 A5 生产矩阵提供真实证据，缺证维持 unknown/未 GREEN。
- 本轮仅文档；未运行测试、未改 A5/契约/代码/页面、未触及并行后端未跟踪产物、未调用 aoci_*、未 push。
