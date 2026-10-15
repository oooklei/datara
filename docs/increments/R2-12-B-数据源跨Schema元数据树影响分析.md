# R2-12-B：项目数据源跨 Schema 元数据树影响分析

日期：2026-10-15（Asia/Shanghai）  
状态：R2-12-B_CONTROL_PASS（本子批闭环；R2-12 总体仍 IN_PROGRESS）

## 前序增量影响复核

- R2-12-A 已独立提交 `61d09e1`，结果为 `R2-12-A_CONTROL_PASS`。项目数据源 CRUD、project isolation、只读 probe、updated_at 与页面闭环已运行；最终 `rebuild_project_datasource` 行数为 0，表结构已持久存在。
- R2-12-A 的 schema 仅包含项目/连接配置及时间戳；其 API 不暴露 schema/object tree，也不保存元数据快照。B 应复用 `ProjectDatasourceRepository.get(project_id, datasource_id)` 与统一 datasource service 的连接校验边界，新增只读浏览服务，不改 CRUD 表结构、不把浏览结果写入治理元数据表。
- 认证/授权：项目隔离和 viewer 跨项目拒绝已有控件证据。新 browse endpoints 应先验证 token 与 project membership，再实例化连接器；沿用 datasource view 的 `VIEW_ALL` 许可，不新增权限点、不提升验证 runner 身份。所有 driver/对象失败返回稳定错误码，响应和日志不回显连接串/密码。
- 部署影响：1.9 的隔离 MySQL fixture 已清理，非临时 datasource 行数为 0。下一批必须重新检查 API/Web、DB、源代码挂载、容器资源、目标测试 schema 与备份；不可假设 R2-12-A fixture 仍在。
- 工作树边界：继续在 `D:\需求\数据治理工具\Datara\.worktrees\r3-s9` / `codex/r3-s9` 开发；不触碰当前主工作区 R4 未提交内容、`.aoci/baseline.json`、无关嵌套 `datara-backend/datara-backend/`、旧系统后端或正式 Vue/menu。

## 现状与设计差距

- `DataSourceDraft` 当前宣告 MySQL/PostgreSQL 均有 `query`、`metadata`、`cross_schema` 能力，但 `probe_datasource()` 运行期目前只实现 PyMySQL；`requirements.txt` 未包含 PostgreSQL driver。不可将未实现的 PostgreSQL capability 展示为可用能力。
- R2 总体计划要求 schema/table/column 跨 schema 探查，并服务于 SQL IDE 对象树、同步映射和元数据采集；R2-12-A 没有实现这些能力。B 的目标是建立可复用的只读目录 API 和前端 schema tree，以真实控件验证跨 schema 浏览。
- 为控制改动面并确保有可重复的 1.9 运行资源，本子批的实现范围限定为 MySQL：在 capability response 中仅将已实现能力作为 active；PostgreSQL 标为 planned/unsupported，不能被连接表单或 SQL IDE 误选。PostgreSQL driver、隔离实例与控件验证另列后续子批，不伪造支持。

## 范围与非目标

目标：

1. 从已登记的项目 datasource profile 读取 catalog/schema/object/column 元数据；不得接受前端任意连接串、host 或凭据。
2. 支持 catalog/schema 导航，按 schema 精确列出 table/view；提供 columns、type、nullable、primary-key、comment 等经驱动确认的必要元数据，使用分页/上限保护。
3. 以 schema-qualified identity 表示同名跨 schema 对象；所有 API 返回对象的 project/datasource/schema/type/name 身份，避免仅以裸表名覆盖。
4. MySQL adapter 使用 SQLAlchemy Inspector 或受参数绑定的信息架构查询，只读连接、有限 connect/read timeout、只允许 metadata 查询；异常时 rollback/close。数据库标识符不可作为未转义 SQL 拼接。
5. 建立按 DBX 对象浏览器交互模式设计的独立 `rebuild-validation-r2-12-b.html`，提供预置项目/数据源选择、可展开 schema/object tree、对象过滤、字段面板、跨 schema 同名对象核对、错误/空态；不引用旧 Datara 正式 Vue 页面，不加正式菜单/路由。
6. 完整验证跨项目/未授权 datasource/无 token 拒绝、空 schema、同名表区分、分页上限、未知对象类型、超时与连接释放，并确认日志无 credential 内容。

明确不包含：DDL 修改/发布、对象定义编辑、SQL execution/result sets、持久化 metadata snapshots、PostgreSQL runtime support、连接池调优、同步任务执行、正式前端融合。

## 细化步骤与门禁

1. 先查 `datara-rebuild-api`/Web mounts、API schema/time stamps、DB backup、容器/中间件/资源和可用的 MySQL 镜像；仅用本批新建且可审计清理的隔离 fixture，或 1.9 明确批准的隔离测试 schema。禁止把 `datara-mysql-src/meta/dw` 当 fixture。
2. 将 datasource capability 合同收敛为 truthful matrix：MySQL active，PostgreSQL unavailable/planned。增加测试覆盖 capabilities 与真实 adapter/driver 的一致性；如果需要支持 PostgreSQL，必须另建有 driver 和隔离运行资源的子批，不在本批暗中增加依赖。
3. RED：增加 metadata service/API tests，覆盖 project/datasource membership、schema-qualified names、同名对象、列类型、过滤/分页边界、unsupported datasource、失败关连接及只读权限。
4. 实现目录 DTO/adapter/service/repository boundaries；路由先执行 token 与 `VIEW_ALL`/项目范围校验，再从已保存 profile 加载凭据并创建只读 connector；不在应用日志写 DSN 或 SQL 参数。
5. 先完成本地全后端测试、Ruff、compileall、静态页合同和 runner 语法检查。
6. 设计隔离测试数据：至少两个 schema，各建一个相同表名、一个 view、含不同字段类型的表，并保证只读测试用户只能读此 fixture。若 1.9 没有可用镜像且不能在不下载镜像的情况下搭建，记录阻塞，不临时改用旧数据源。
7. 将静态页部署到原指定 `18091` 路径；仅重启新 rebuild API。browser-use 先操作同一页面，明确失败后按 fallback 技能一次限时重试，仍阻塞则 Playwright 在同 URL 验证真实控件。同步检查 API logs、DB 元数据/时间戳、Web/依赖健康及资源。
8. 删除临时 DB fixture 和新增测试 records；归档 browser/control JSON、截图、服务日志摘要、资源、schema/read-only 证据；回写主计划/台账并拆分提交。本子批不得把 R2-12 总体标 PASS。

## 验收标准

- 按控件展开至少两个 schema；两个 schema 内同名对象不混淆；字段面板准确显示 fixture 类型/可空/主键。
- project isolation/role/token 负例状态符合合同；对象浏览对无权用户不发生数据库连接。
- MySQL 只读 metadata adapter 对成功/异常均关闭连接；测试用户无 DDL/DML 权限。
- 本地全量 `pytest tests -q`、受影响 Ruff、compileall、静态页面 runner 检查通过。
- 1.9 API/Web/DB/middleware/资源和日志证据通过，测试数据清理后 fixture 按计划移除。
- PostgreSQL runtime、连接池、SYNC 接入仍列为待办；不因目录浏览子批 PASS 推论 R2-12 或 R4 完成。

## 风险与选择

- 正确显示支持矩阵可能显露 PostgreSQL 是合同预告而非可运行能力；既然用户要求新 Backend 重新实现且不要求兼容旧代码，本批优先准确标注“未实现”，不保持虚假兼容声明。
- MySQL `INFORMATION_SCHEMA` 对对象类型/权限的可见性受账号授权影响。API 必须返回“不可见/无权限”稳定状态，不可把权限不足解释为空 schema。
- 广泛 schema 列表可能较大；必须限频/分页并设最大 schema/object/column 数，默认加载不拉取列明细，用户展开对象后再取列。

## AOCI 治理检查说明

2026-10-15 在 R2-12-A 文件稳定后至 R2-12-B 影响分析/台账更新期间，累计四次调用 `aoci_maintain`。维护均以 `stopped/blocked` 返回：未产生候选或索引写入；报告全仓 Code cognition drift（112 missing、112 unbaselined；125 targets）及 12 个 observed pending review，且提示需先人工检查 scope。只读 `scope status` 另显示 5 项观察变化待核对、4 项 inventory 人工检查；本轮没有 ack、改 scope 或写 Entry。AOCI 全局索引仍不宣称 alignment，但此阻塞不涉及 R2-12-B 的源代码语义或外部权限；该增量有独立影响分析、局部源码/测试证据，故允许按 source-bound 范围继续开发，不改 AOCI managed assets。

## 实施与验收收口（2026-10-15 Asia/Shanghai）

- 实现：MySQL `information_schema` 只读目录 adapter/API，按已保存项目 datasource profile 读取 schema、table/view 与 columns；项目和 datasource 范围在创建连接前校验。PostgreSQL 从 active capability 移除；未实现连接池、SQL/DDL、metadata 快照及 SYNC 执行。
- 独立控件页按 DBX 对象浏览器方式提供 schema → object → columns 导航，显示同名对象的 schema-qualified identity、table/view 类型及列类型/可空/主键/comment。未改正式 Vue、路由或菜单。
- 本地最终：`pytest tests -q` 764 passed；改动 Python Ruff、compileall、验证页脚本语法与 `git diff --check` 通过。远端运行验证报告见 `evidence/R2/r2-12-b-20261015135851.json` 和配对截图 `.png`；浏览器入口/工具桥结果见 `evidence/R2/r2-12-b-browser-entry-20261015.txt`，部署、服务日志、资源与清理见 `evidence/R2/r2-12-b-remote-final-20261015.txt`。
- browser-use 页面绑定/控制尝试按约定受限重试后仍超时，登记为 `BLOCKED_TOOL_BRIDGE`；随后对同一 `http://192.168.1.9:18091/rebuild-validation-r2-12-b.html` 使用 Playwright 完成真实控件→真实 API→临时隔离 MySQL 的通过闭环，不以 API-only 代替 UI。
- 临时容器 `datara-r2-12b-mysql-fixture` 使用 `--rm`、tmpfs、无 host port；测试用户仅有 fixture schema 的 `SELECT, SHOW VIEW`。运行后容器已移除，新增 datasource profile 行数为 0；旧 source/meta/dw 库未访问或修改。服务源码/Web 变更前备份与校验记录已归入 remote-final。
- 控件断言覆盖两个 schema 下同名 `orders` 区分、`analytics.orders_view` 类型、两套不同字段类型/nullable/PK/comment、跨项目访问 404。最终 run `r2-12-b-20261015135851` PASS；较早失败/部分 JSON 与截图均保留，不覆盖为最终通过。
- 当前结论仅为 `R2-12-B_CONTROL_PASS`。R2-12 总体继续 `IN_PROGRESS`：连接池、PostgreSQL 驱动/隔离验证、与 SYNC/SQL IDE/治理采集共享 datasource service 尚未完成。AOCI 全局治理仍 dirty/stale、严格 Challenge 部分通过，不宣称 AOCI aligned；不阻断本子批 source-bound 结果。
