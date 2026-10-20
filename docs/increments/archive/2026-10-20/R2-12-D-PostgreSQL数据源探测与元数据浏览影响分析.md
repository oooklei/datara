# R2-12-D：PostgreSQL 数据源探测与元数据浏览影响分析

日期：2026-10-15（Asia/Shanghai）  
状态：CONTROL_PASS（2026-10-15；代码、本地门禁、远端联合控件、资源清理与文档均已完成）  

## 前序增量影响复核

- R2-12-A `61d09e1`、B `06f8bb0`、C `6f6b4cd` 均已分别完成；C 全量后端测试 773 passed，Ruff/compileall/diff check 与 R2-12-C 真实控件证据通过。C 是 MySQL project/datasource-scoped 有界 pool，probe 与 metadata browse 共用 MySQL connector。
- C 引入的 `DatasourceEngineRegistry` 目前构造 `mysql+pymysql` URL 并拒绝非 MySQL；`MySQLMetadataCatalog` 以 MySQL `information_schema` 只读查询实现 schema→table/view→column；`probe_datasource` 也仅支持 MySQL。PostgreSQL profile 类型虽可保存，但 capability set 为空，不得误报可探测或可浏览。
- D 应保持 C 的项目隔离、pool key/fingerprint/invalidate/shutdown 生命周期和既有 MySQL 响应兼容；按 dialect 映射增加 PostgreSQL adapter，不复制第二套 datasource CRUD，也不让 PostgreSQL 路径绕开 pool registry。
- R2-12-D 不涉及 SQL/DLL 执行、SYNC、旧 source/meta/dw 数据库、正式 Vue 融合或持久 metadata snapshot。工作流、IDE、治理消费者复用 connector 仍分别留在其消费者增量。
- AOCI 全库 Maintain 仍为 `blocked/NOT ALIGNED`（112 missing、112 unbaselined、13 stale，且 MCP 与 scope CLI 对 observe pending 数视图不一致）；此治理事实独立记录，不伪报通过或借 D 改 Index/Safe Scope。

## 目标与范围

在现有 project-scoped datasource API 与 DBX 风格 metadata browser 上增加 PostgreSQL runtime probe 和只读 schema/table/view/column 探查。MySQL 行为、字段与分页协议保持兼容；按 `(project_id,datasource_id)` 隔离池。新增验证 fixture 只允许 SELECT/目录读取。

建议驱动采用 Psycopg 3 binary distribution，并由 SQLAlchemy `postgresql+psycopg` dialect 建立 URL；其安装方式不依赖容器内编译工具链，具体 Python/平台兼容在部署预检确认。官方参考：[SQLAlchemy PostgreSQL dialect](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html)、[Psycopg installation](https://www.psycopg.org/psycopg3/docs/basic/install.html)。

不纳入：PostgreSQL 写查询/DDL、SYNC 执行、数据库角色自动创建、外部 DB 密码迁移、分布式跨 worker pool、元数据周期采集与持久快照。

## 主要影响与边界

- Backend：能力 registry、连接 URL/dialect factory、pool connector、probe、catalog interface/API error mapping、requirements/container image、tests。经 C 的实现复核，connector 暴露 SQLAlchemy pool 的 DBAPI raw connection，MySQL catalog 已使用带 keyset/lookahead 的参数化 SQL；D 沿用 dialect-specific `information_schema`/PostgreSQL catalog adapter，而不是另取 SQLAlchemy Inspector connection，以保留同一池归还/rollback 生命周期、只读事务和受控分页。
- 隔离验证页：在 R2-12-B 页面复用同一对象树控件，新增 datasource type 切换；MySQL 与 PostgreSQL 同一契约测试，分别验证 schema 列表、表/视图、列类型/nullability/PK/comment。页面仍是测试入口，不注册正式菜单，不改正式 Vue。
- Runtime：部署前必须只读预检 192.168.1.9 的 PostgreSQL fixture 可用性、磁盘/内存余量、容器网络、当前 backend 镜像构建方式和 wheel 获取渠道；使用本批命名临时容器、无 host port、tmpfs 数据目录及仅 SELECT/CONNECT/USAGE 的测试角色。若 1.9 缺镜像/资源，先记录阻塞并按环境实际可用方案准备 fixture，不得改用本机数据库冒充远程验收。已完成的只读预检：PostgreSQL 16/14 镜像已缓存，`/lei` 可用 214 GiB、主机可用内存约 21 GiB、`datara_default` 有 13 个成员，backend Python 3.11.17；现存 `ds-postgres` 仅确认健康，不连接/复用/修改。见 `evidence/R2/r2-12-d-preflight-20261015.txt`。
- 重要部署隔离：`datara-backend:latest` 同时被 API/master/worker/alert/logger 使用。新增依赖通过 `Dockerfile.r2-12-d` 从已运行的 base image 派生，并用 `docker-compose.r2-12-d.yml` 构建候选 tag；部署仅重建 `datara-rebuild-api`，不得覆盖 shared latest 或重启其他进程。
- Read-only：数据库端角色权限是主要防线，catalog API 只读 transaction 是第二层；验证写入被数据库拒绝。连接串、用户名/密码不得进入浏览器、日志或证据。
- Capacity：共用 C 已定义的 profile pool limits；单 profile 最多 2+2 connections，profile registry 最多 32。MySQL 与 PostgreSQL 在各自 profile 上隔离，不因 driver 不同共用 Engine。

## 细化步骤与门禁

1. 预检 Python 版本、SQLAlchemy 版本、build/runtime requirements、容器 Dockerfile与锁定策略、1.9 磁盘/内存和 PostgreSQL 镜像/wheel 网络可达性；记录只读证据，不创建远端容器，不修改运行资源。
2. TDD RED：先为 dialect URL/driver 缺失、PostgreSQL pool profile isolation/invalidate/shutdown、只读 probe、catalog API schema/object/columns/error 和 MySQL compatibility 写测试。
3. 安装与契约：在 backend runtime 加 psycopg extra，明确 PostgreSQL capabilities；保持 MySQL capabilities 与既有响应不变。确认不支持的 kind 明确拒绝。
4. 实现通用 catalog protocol 与 MySQL/PostgreSQL adapter；复用 C pool registry，连接/profile 变更统一失效；每次浏览使用独立只读事务并保证异常 rollback/归还连接。
5. 构建独立验证页改动：复用对象树，预制两个真实 profile（fixture），从 PostgreSQL/MySQL type picker 分别操作；同域控件在一轮浏览器 run 中覆盖切换、展开 schema、table/view、列属性、跨项目拒绝及 SQL 写入拒绝。
6. 本地验收：定向 TDD 红绿、全量 backend pytest、Ruff、compileall、diff check；使用 tmpfs PostgreSQL container fixture 进行 adapter integration，但它不能替代 1.9 远程验证。
7. 远端实施：仅在步骤 1 资源与备份复核通过后部署；容器不映射 host port，使用最小权限测试角色；验证容器/API/browser/UI、后端日志、profile 计数及 fixture 删除，证据 JSON+PNG 配对并保留所有失败记录。
8. browser-use 优先；一次限时重试仍阻塞则使用 Playwright 驱动同一真实验证页控件。记录短期 token 发放来源与清理，不将 token/key/DSN 写入证据。
9. 收口时一次同步设计/计划/台账、运行一次 AOCI Maintain 并准确标状态、复核影响面和资源回收，独立提交 D。远程验证未收口前不得开下一个增量。

## 验收标准

- 新建/更新 PostgreSQL profile 后探测可连接；MySQL 原接口回归不变；无 driver 时启动/错误应明确而非伪造空目录。
- 两个 schema 的 table/view/column metadata 正确，数据库角色无法写；另一个 project 访问被拒绝；更新/删除 profile 后对应旧 Engine 被失效。
- 同一真实页面完成 MySQL 与 PostgreSQL 的用户控件操作；backend tests、日志与 runtime/fixture 清理证据对应；JSON+PNG+remote-final 齐全。
- 本批只完成 PostgreSQL datasource probe/catalog 支持，不提升 R2-12 总体完成，不声称 SQL/SYNC/治理消费者已接入。

## 实施与验收结果（2026-10-15）

- PostgreSQL runtime 使用 Psycopg 3 + `postgresql+psycopg`，复用 C 的 project/datasource pool registry；catalog 使用绑定参数的 PostgreSQL 只读目录查询。首轮远端 502 已定位为 Psycopg 参数绑定时 LIKE 文本内字面 `%` 与占位符语法冲突，先加回归测试观察 RED，再将字面模式改为 `%%`。之后另一轮仍出现通用 502，但当时无安全异常分类日志，无法确认其独立根因；不作推测。safe browse diagnostics 后续仅记异常类型/SQLSTATE，不记异常消息或连接信息；新鲜 fixture 下 PG-only 与最终联合轮次均通过。
- 最终验证按计划在同一隔离页面联合覆盖 MySQL 兼容行为与 PostgreSQL 新增行为。最终 run `r2-12-d-20261015164635` 为 PASS，6 个可见控件断言、11 个 API 响应（含预期跨项目 404），无浏览器错误或失败请求；配套 JSON、PNG 及 browser-entry/remote-final 记录在 `evidence/R2/`。
- browser-use 的页面绑定/导航/AX 获取分别经历 30 秒超时和一次 60 秒有界重试超时；明确记为 browser-use transport BLOCKED。Playwright 按 fallback 驱动同一 `18091` 页面并完成所有真实控件操作，因此不是 API-only 验收。
- 两轮 schema 浏览 502 及 PostgreSQL-only 中间 run 均保留 JSON+PNG。最终 PG/MySQL reader 权限、API 日志、profile 删除、临时 fixture 标签/网络/端口和清理结果见 `r2-12-d-remote-final-20261015.txt`。两个临时 DB fixture 均位于 `datara_default`、tmpfs、无宿主端口，完成后按精确标签核验移除；持续运行的 PostgreSQL/旧 MySQL 服务未复用或修改。
- 最终本地后端 `pytest tests -q`: 796 passed；Ruff、compileall、`git diff --check` 通过。candidate image 仅部署 `datara-rebuild-api`，其余共享容器保持原镜像/运行状态。
- 子批状态：`R2-12-D_CONTROL_PASS`。R2-12 只表示 datasource CRUD/probe/catalog/pool 基础能力完成；SQL/SYNC/IDE/治理消费者仍待各自增量，不扩大本次范围。
