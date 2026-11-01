# 用户要求事项完成情况总账（2026-10-31 → 2026-11-01）

> 生成时间：2026-11-01
> 汇总对象：用户在 2026-10-31 至 2026-11-01 期间提出的任务、功能、缺陷 / BUG、优化完善要求。
> **需求真源**：① trae 会话存档 `icube-ai-agent-storage-input-history`（100 条原始输入，含 `conversation_selection` 批注裁定）+ `paste-files/` 截图；② **Git 提交记录 159 个**（10-31 00:45 ~ 11-01 13:30，`git log --all`）；③ 各 agent 交接卡（`docs/handoff/outbox/codex/` 等）。
> **判定依据**：以**代码改动**为准（每个诉求都落到具体 commit 与文件），运行证据为 2026-11-01 对 192.168.1.9 的容器 / 镜像 / 接口 / 产物核查。

## 核查修订说明

本次仅完成重点事项的源码与历史文档静态核查，未重新核验 1.9 的当前状态，也未逐项复核全账。下文原有“已完成”、测试通过、部署和运行信息均为原账的历史主张，并非本次验收结论；不能由提交记录、静态源码或历史运行记录单独推断当前已部署或已验收。特别修正如下：

- **C11 权限矩阵**：统一 ACL 有实现，但 DBX、SSH 和编排仍存在旧权限表或回退路径；SSH、编排调用还存在固定角色的情况。`AclService.grant` 更新已有行时可覆盖 owner 行用于识别的字段，实际调用可达性及影响仍待验证。不能认定统一权限已闭环。
- **C19/C20 告警**：前端消息中心请求 `/api/v1/alerts`，现行 rebuild 路由未发现相应挂载；编排告警记录是不同契约。既有历史测试不等于消息中心或三通道当前真实验收通过。
- **C31/C34**：前者原账自述镜像仍有待核验项，后者是回滚规避，均不能归为完整收口。
- **C37/U24 仿真**：`infra/fixtures/business/ecom_sim_20261030/README.md` 记载项目 33、14 张表、8 个夹具变量、三条 DAG 实例 18/19/20 成功及浏览器截图；这是历史记录，不是本次实时验证。质量规则仍只有结构校验，不能据此宣称行级质量验收完成。原账“未执行 seed”的结论与该记录冲突，重新执行前须先核实当前状态，避免破坏既有数据。
- **U13**：现行权威 §十一明确采用改指向且不提前创建 GLOSSARY；不得按原账建议补建。
- **U22/U23**：SQL 已保存脚本的双入口仅局部同源，上传脚本仍有独立资源存储；Python/Shell 选取时复制正文，不证明运行期引用。按现行权威落实库/schema 粒度双入口同源，SQL 节点接入和具体运行语义须先核对接口与调用链，不能预设必须不可变版本或双向同步。
- **U11/U12**：画布网关已取消不等于可无差别删除 orchestration 路由；自建列表和操作可能仍有消费者，须逐路追踪后处理。
- **U19**：源码真源文档记录已有 2026-11-01 发布快照回同步；该记录是否覆盖现运行版本仍待核验，原账“一直未回同步”不能直接采信。

本次未取得 1.9 集成租约、未运行测试或实施发布；后续源码修复与验证须遵循协作规程及源码真源约束。其余条目仍需逐项核查，不能因为未在上述列出而视为确认完成。

## 一、判定口径

| 判定 | 含义 |
|---|---|
| 已完成 | 代码已落地 + 已部署到 1.9（或明确不需部署）+ 至少一层运行证据（单测 / 接口 / 产物 / 容器） |
| 未完成·待验收 | 代码与部署已就绪，缺浏览器级 E2E 或真实运行证据 |
| 未完成·未开始 | 无实现或仅有只读核查 |
| 未完成·回滚规避 | 已通过回滚消除现象，根因未修 |

关键区分：**「代码完成」≠「已部署」≠「已验收」**。

---

## 二、已完成清单（对照代码改动）

### A. 架构裁定类

| # | 用户诉求 | 为什么改（动因） | 代码证据 | 判定 |
|---|---|---|---|---|
| C01 | 前端验证入口唯一固定 `http://192.168.1.9:8090/`，禁止 18091/18092 多套并行（原话「不要多套，不方便集成」） | 多套并行部署导致集成与验证混乱 | `1d1e814a`（set 8090 as the single frontend entry）、`88d58b0b`、`252d8329`、`c758db43`、`bac7d6c4`、`24422dc5`、`a9ec387f`、`6d776f77`、`c2d8e893`（notify codex of 8090-only entry） | 已完成（1.9 `dt-web`=`8090:80`，实测 8090=200） |
| C02 | 容器名 ≤12 字符 | 长名导致 DNS/别名问题 | `f8ed6a6c`（establish source truth and short container names） | 已完成（`dt-web` 6、`dt-rebuild` 9、`dbx` 3、`ds-*` 8） |
| C03 | 源码真源 + 发布前合并 + 镜像闸门 | 多工作区产出无法确认发布内容 | `f8ed6a6c`、`fd150c37`（consolidate current authority）；`scripts/release_source.py preflight/image-gate`、`deploy/image-policy.json`、`pull_policy: never` | 已完成 |
| C04 | 编排网关取消，画布改 **iframe 同源直连海豚** | 网关代理链路不稳定、握手死循环 | `edbd2487`（embed cookie + nginx 注入 `X-Datara-Embed-Token`）、`693bd36a`（pin apiBaseUrl to page origin）、`740d7dc5`（ds embed canvas route contract）、`83b47b92`（preserve public port in DS redirect）、`8c2c615f`（stop embed session handshake feedback loop）、`0443e6f1`（wsl nginx 注入） | 已完成（契约测试 3/3） |

### B. DBX IDE 嵌入 / 鉴权 / 加载体验（本周期最大改动块）

| # | 用户诉求 | 为什么改 | 代码证据 | 判定 |
|---|---|---|---|---|
| C05 | DBX IDE 白屏 / 403，项目成员打不开 | 会话与权限判定错误 | `5311c816`（unified embedded session contract）、`3ca6d2b8`（route dbx ide bootstrap through embed contract）、`6d72f37a`（gate orchestration embed through unified session）、`ee40ccb5`（accept post embed session contract）、`51b48ffe`（bootstrap IDE from HttpOnly session and proxy API）、`ed982b7f`（allow project members to open dbx ide）、`9b4cc2e9`（enforce gateway-only auth on 0.6.29）、`8890a0cf`（guard internal connection params by token and peer）、`b2e6affa`（fetch internal connection params from guarded endpoint）、`b64f212a`（guard proxy/identity layers against raw user-db drivers）、`d3024ed4`（cover post embed session contract） | 已完成（`test_dbx_ide_proxy.py` 21 passed；1.9 无会话 401 `IDE session required`） |
| C06 | DBX 网关稳定性：liveness 心跳阻塞、启动备份失败、上游超时拖垮 | SSE 阻塞事件循环 / 非关键路径失败拖垮启动 | `5be50ac3`（isolate dbx liveness sse from gateway）、`cac4ed27`（close dbx liveness heartbeat after event）、`55dd92a8`（make dbx liveness optional no-op）、`24df2b5b`（proxy dbx liveness and startup backup）、`af2d310a`（make dbx startup backup optional）、`bee8b2d7`（allow dbx startup backup route）、`0ed94539`（fail fast on dbx gateway upstream）、`b2275de5`（keep transient dbx retries with shorter timeout） | 已完成 |
| C07 | DBX IDE 首次加载慢 / 白屏 / 连接列表重复请求 | 连接目录每次全量拉取 + 无加载反馈 | `63b70253`（add dbx connection catalog cache）、`f3a3cdbe`（serve dbx ide connection list from catalog cache）、`e0260664`（test cache behaviors）、`1d1464d5`（add dbx ide loading mask and keepalive cache）、`e7ea4747`（keep loading mask until connection tree request completes）、`633b4920`（wait for DBX connection tree ready message）、`1f493480`（avoid blocking IDE bootstrap on SSH prompt SSE）、`d4b0b188`（use frame load for DBX readiness）、`4592f85c`（clarify worker resources and retry DBX loading）、`b6001d45`（keep same-project navigation responsive after IDE）、`660fa236`（test menu changes do not reload document）、`57fd5563` / `aa4c163e`（浏览器就绪判据：先等连接列表、再校验，避免误判白屏） | 已完成（镜像 `datara-newweb:codex-main-20261101-idefix` 上线） |
| C08 | IDE 内同项目导航卡死 | 路由切换未等 iframe 就绪 | `b6001d45` | 已完成 |

### C. 权限 / 身份 / 成员

| # | 用户诉求 | 为什么改 | 代码证据 | 判定 |
|---|---|---|---|---|
| C09 | 平台角色接口 500（`AttributeError`）、角色授权流未闭环 | 仓储缺方法、前端无中文标签 | `e7b049b5`（fix update platform user roles）、`32260953`（expose platform RBAC labels and catalog）、`35c631a6`（show Chinese RBAC labels in user admin）、`b1938f36`（platform RBAC rollout plan）、`0de77d0b`（close platform user role authorization flow） | 已完成（39 passed；1.9 PATCH 两次 200、`revoked_tokens=0`） |
| C10 | 项目成员添加 404 / 错误不可读 | 前端丢弃错误码 | `af2ead91`（expose member errors and retry component catalog）：`memberApi.ts` 开 `preserveEnvelopeCode` + 4041/4042/4091 中文映射 | 已完成（产物含「该用户已经是项目成员」） |
| C11 | 权限矩阵 / 身份资源治理设计（含 4 条批注裁定） | 界面语义与后端行为不一致、资源边界不闭合 | `b1938f36`、`fd150c37`；设计 `docs/archive/2026-11-01-authority-refresh/2026-10-31-platform-rbac-model.md` §权限矩阵、`2026-11-01-identity-resource-governance-design.md` §7.4「分享授资格不授权限」；代码 `datara-backend/rebuild/acl/{api,backfill,models,service}.py` + `tests/rebuild/test_acl_policy_and_share_matrix.py` | 已完成（统一 ACL 已实现） |
| C12 | 身份 / 权限验证留痕 | 需证明平台级优先、owner 边界、分享生效 | `d4e8b69b`、`51daa1d4`、`fad8cf84`、`fd3599b3`、`c3ad46ce`、`a310b5a2`、`1ce7d229`、`e5664060`、`2dc80789`、`222e6016`、`f6eaa560`、`472340c6` | 已完成 |

### D. 前端风格 / 令牌 / 导航

| # | 用户诉求 | 为什么改 | 代码证据 | 判定 |
|---|---|---|---|---|
| C13 | 前端集成 dbx/海豚后全页面风格漂移评估与治理 | 设计令牌未收口、监控面板硬编码色值 | `621aab97`（close frontend design tokens, drop trial, add DS patch）、`ac653fae`（close theme token and monitor contract gaps）、`5d116c0a`（theme log panel via `--log-bg/--log-fg` tokens） | 已完成 |
| C14 | 部署运维子导航收口：隐藏全局 `/task-group` 快捷入口、恢复「SSH 试运行节点」入口 | 与任务中心任务组重复、SSH 入口误删 | `6edadfbf`（remove task group link from deployment nav）、`45e184e1`（retain SSH nodes for script trials）、`fbf88d76`（align SSH trial page with resource layout） | 已完成（20 passed） |
| C15 | SSH 节点页与 Worker 分组页布局不一致 | 页面结构未对齐 | `fbf88d76` 统一 `.pg/.pg-head/.toolbar/.panel/.tbl/.err-box` | 已完成（16 passed、vue-tsc 通过） |
| C16 | 嵌入系统顶部「刷新」控件 | 重载 iframe 保留项目上下文 | `0a17478d`（add embedded page refresh controls）：`DbxIdeView.vue` `data-ide-refresh`、`TaskCenterView.vue` `data-tc-embed-refresh` | 已完成（契约 37 passed，已部署） |

### E. 任务中心 / 告警 / 定时

| # | 用户诉求 | 为什么改 | 代码证据 | 判定 |
|---|---|---|---|---|
| C17 | 模板中心 tab 删除、归档；告警与 SLA 参考旧前端适配现架构 | 旧 tab 与新架构不符 | `0347bf8f`（add workflow schedules and project alarms）：「模板中心」页面在 `datara-newweb/src` 仅剩测试文件 | 已完成（页面已删） |
| C18 | 工作流定时 tab（归集行尾定时操作） | 海豚有、datara 无 | `0347bf8f` | 已完成（33 passed） |
| C19 | 告警桥接 + owner 访问强制 + 顶栏预警消息中心 | 告警未接入、无统一入口 | `0df65514`（bridge alarms and enforce owner access）、`0eeb3664`（restore topbar alert message center）、`7ad07df0`（orchestration governance regression） | 已完成（`test_orchestration_governance_api.py` + `test_orchestration_alarm_api.py` 32 passed；数据源缺口见 U09） |
| C20 | 告警三通道验收（站内 / 邮件 / Webhook） | 需真实验证 | `0df65514` | 已完成（短信待实施，见 U10） |

### F. 部署运维 / 资源 / 脚本

| # | 用户诉求 | 为什么改 | 代码证据 | 判定 |
|---|---|---|---|---|
| C21 | 删除「运行依赖文件」菜单 + 页面 `OrchestrationResourceFileView` | 该视图与海豚资源中心重复 | `063e7c41`（remove orchestration resource file view）、`f08b3923`（clean up resource file view references） | 已完成（产物内 grep 该路由标识 = 0） |
| C22 | 编排脚本同步到海豚资源中心 + 节点资源下拉按扩展名收敛 + 选中回填正文（仅 Python/Shell） | 节点选不到脚本 | `6b1da2ee`（sync saved scripts to dolphinscheduler resource center）、`2639c9bb`（python/shell 节点资源下拉按扩展名收敛并支持选中脚本回填正文）、`7ac075ed`（patchfiles 登记）、`4c805c59`（资源正文回填补丁改用编排网关 full_name 查询键） | 已完成（**限 Python/Shell，且为「复制正文」而非运行期引用**，见 U23） |
| C23 | 环境上下文贯穿（DBX / 编排 / DAG 主机共享项目环境、确定性默认） | 各处环境选择不一致 | `0eec004b`（share project environment across DBX and DAG hosts）、`2a76c692`（default project environment context deterministically） | 已完成（33 passed） |

### G. 客户观摩 / 品牌

| # | 用户诉求 | 为什么改 | 代码证据 | 判定 |
|---|---|---|---|---|
| C24 | 客户观摩入口 + 隐藏实现品牌（禁词） | 泄漏底层产品名 | `1db647ef`（publish customer viewing entry and hide implementation branding）、`abe817b5`（cover embedded branding replacement contract）、`embeddedBranding.ts` `sanitizeEmbeddedBranding` | 已完成（8090 禁词命中 0） |
| C25 | **去掉 IDE 里截图红框的功能**（DBX 欢迎页「AI 编程助手集成」推广卡） | dbx 属外链独立产品，嵌入态不应重复推广其 MCP 入口 | `embeddedBranding.ts` `hideEmbeddedMcpPromoCard`（以 `@dbx-app/mcp-server` 文本为锚点隐藏 `rounded-lg border` 容器）+ `DbxIdeView.vue` L110/L157-158 接线 + `abe817b5` 契约测试；DBX 侧源 `D:\dbx-main\apps\desktop\src\components\layout\WelcomeScreen.vue` L140-154 | 已完成 |

### H. 治理 / 缺陷修复 / 回归

| # | 用户诉求 | 为什么改 | 代码证据 | 判定 |
|---|---|---|---|---|
| C26 | 项目删除治理级联（标签/质量/标准/指标/报告/告警 + 审计保留 + 跨项目 409） | 删项目残留孤儿数据 | `08564949`（cascade-delete governance rows with project）、`c28c2709`（v0005 project fk cascade migration）、`e38c2c8c`（return conflict for cross-project deletion references）、`b5e52054`（回归期望对齐 `r3_0005_governance_project_fk_cascade`） | 已完成（17 passed） |
| C27 | 血缘字段重复实例 / ZK 线程关闭 / Kafka 生产者调用 | 运行时缺陷 | `327d0c11`（dedupe repeated runtime field instances）、`03d9f087`（guard repeated-instance dedupe）、`e92c30db`（graceful zk thread shutdown）、`197ff34d`（use KafkaProducer.flush instead of nonexistent poll） | 已完成 |
| C28 | 工作流 `tt` 保存报「请求参数[{0}]无效」 | SHELL 节点引用失效资源 | `721800bf`、`41ec966b`、`b114a347`、`b30bb95f` | 已完成（清空两节点 `resourceList`；重部署后 `PUT .../workflow-definition/188346193457664` 200 / code=0 / 版本 3→4） |
| C29 | 回归基线 | 全量回归 | 后端 pytest 1537 passed / 8 skipped；前端 922 passed；`vue-tsc` 通过（`1ce7d229`、`e5664060`、`2dc80789` 等） | 已完成 |
| C30 | 1.9 运行时清理（`datara-newweb-fe`、`datara-newweb-dag-vis-01`、整套 `datara-pkgtest`） | 旧容器/镜像残留 | `fbdf8fc8`（record 1.9 datara runtime cleanup） | 已完成 |

### I. 发布治理 / 镜像 / 仓库

| # | 用户诉求 | 为什么改 | 代码证据 | 判定 |
|---|---|---|---|---|
| C31 | 镜像升级闸门落实（锁定 digest、本地镜像 ID 校验） | 镜像被未留痕重建导致事故 | `214eb075`（lock updated DBX image digest）、`8a00a750`（validate local image IDs without invalid compose digests）、`1b8f8c69` | 已完成（**部分 FAIL**：`dt-api/dt-worker` 仍 `latest`，见 U21） |
| C32 | 21 个已合并分支归档 | 仓库分支混乱 | `5083743b`、`cf0502a0`、`ad090e4b`、`f690432b`、`e259f892` | 已完成（33 个 `archive/*` tag） |
| C33 | 海豚模块编译验证 + mysql 驱动 | 需确认补丁可编译 | `b24bfa19`、`28e43639`、`a2223cac` | 已完成（驱动仍为临时挂载，见 U16） |
| C34 | 事故处置：DBX 被未留痕重建导致「数据安全升级」+ SQL IDE 超时 | 回滚并锁定镜像 | 备份 `docker-compose.yml.bak-20261101112754`、`dbx-data-pre-rollback-20261101112754.tgz`；当前运行 `dbx:codex-main-20261101-1240` | 已完成（回滚规避） |

### J. 仿真业务数据

| # | 用户诉求 | 为什么改 | 代码证据 | 判定 |
|---|---|---|---|---|
| C35 | 电商仿真变量导入并幂等 | 仿真 fixture 需可重复导入 | `808298a8`（record ecommerce simulation variable import） | 已完成（首次 4 `saved`、复跑 4 `unchanged`，带 `simulation-fixture:ECOM_SIM_20261030`） |
| C36 | 仿真矩阵状态回填（12 行，标注降级/待验证） | 需标注验收态 | `7f799069`（backfill ecommerce simulation matrix status）、`05831f4b` | 已完成（`docs/research/2026-10-30-customer-meeting-simulation-matrix.md`） |
| C37 | **仿真业务数据落进 1.9**（源库 + 三条 `[ECOM-SIM-20261030]` 工作流 + 实例） | 用户裁定「必须做」 | `7f799069`、`808298a8`；核查：源库 `ecom_sim_20261030`（dt-db-src，14 张表）存在；datara 库仅 1 项目（id=33）；`workflow_definition` 5 条（38/39/40）；海豚 `t_ds_workflow_definition` 0 行 | **未完成**（见 U24） |

### K. 交接文档

| # | 说明 | 证据 |
|---|---|---|
| C38 | 全部交接卡 / 部署记录 / 设计文档入库 | `3aef0e11`（2026-10-31 integration deployment handoff）及 10-31~11-01 共 44 个 `docs:` commit，逐条对应上文某项的部署留痕，例如：`88e1711e`/`f5ddd83a`（DBX IDE 403）、`418f72a9`/`a4ae6699`（embed session 部署）、`b1f95142`/`63065072`（直连网关迁移规格）、`37e2d4a6`（告警中心部署）、`f3fa62ad`（客户 8090 部署）、`bf0492c8`/`121653c8`（环境上下文）、`4e8dfa52`（SSH 布局）、`48569c75`（告警 owner 收口）、`dc7eb00e`（DBX owner 套件）、`3a3b6bb0`（DBX 补丁编译） |

---

## 三、未完成清单（含初步阻塞原因）

| # | 事项 | 状态 | 初步阻塞原因 | 下一步 / 指针 |
|---|---|---|---|---|
| U01 | 组件栏空白（编排画布左侧组件面板） | 待验收 | 代码已修（`Palette.vue` 首载失败回显 + 重试、`af2ead91`），1.9 `components/spec` 返回 401 而非 404，路由存在。缺**画布内浏览器证据**：直接访问 `/p/33/dag` 只到工作流列表，需先进具体画布；且需 admin 短时 token 注入 | 在 8090 打开具体工作流画布，取 `/api/v1/rebuild/components/spec` 实际返回 |
| U02 | 成员添加 404 的浏览器端到端回验 | 待验收 | 代码与产物已就绪（`af2ead91`），缺登录态浏览器 E2E | 用 admin 短时 token 打开项目成员页，覆盖添加/重复添加/不存在用户三种错误回显 |
| U03 | c5：1.9 全量复验（逐页按钮体系、双主题、海豚 SQL/DataX 保存运行、变量、调度） | 未开始 | 需 browser-use 逐页执行，依赖登录态注入；`DATARA_PUBLIC_BASE_URL` 仍为 18091（U04） | 先修 U04，再按页面清单分批取证 |
| U04 | `DATARA_PUBLIC_BASE_URL` 仍为 `http://192.168.1.9:18091` | 未开始 | 属 1.9 容器环境变量（实测 `dt-rebuild printenv`），需随后端发版修改 | 改为 8090 后重建 `dt-rebuild` |
| U05 | zhangsan 本人凭据场景 E2E | 未开始 | **无 zhangsan 私有凭据**，按规则未擅自重置密码 | 需用户提供临时凭据或管理员重置 |
| U06 | C12 SSH 真实试运行（Python/Shell/SQL 三类） | 待验收 | 1.9 现有 `node-1.9`、`node-bad` 均 `allowTrial=false`，`trial-candidates` 返回空 | 需管理员授权一个安全节点并置 `allowTrial=true` |
| U07 | C9/C10 剩余 5 行矩阵验证（跨 Schema 同步、实时流/Open API、跨工作流依赖、三类脚本运行计数、血缘/每日影响分析） | 未开始 | 需海豚线运行 ID、真实 SQL/脚本结果 | 按矩阵行逐项运行并回填 |
| U08 | 质量行级执行能力（C10） | 未开始 | 当前运行器只做结构校验、统计 0 行；**未擅自补造行级执行** | 需先裁定行级执行口径 |
| U09 | 预警消息中心真实数据 | 未开始 | 后端未提供告警查询路由：实测 8090 `/api/v1/alerts` 返回 **404** | 后端接入告警查询 + 权限裁剪 |
| U10 | 短信告警通道 | 未开始 | 供应商接口未确定 | 待供应商选型 |
| U11 | 权威设计 §十一 冲突 1：编排网关残留 | 待逐路核查 | 历史核查发现挂载和注释残留；画布网关取消不意味着所有 orchestration 域 API 均可移除 | 按现行权威 §6.2 追踪消费者，区分保留接口与真正残留，再处理并补回归 |
| U12 | 权威设计 §十一 冲突 2：旧注释 | 未开始 | `ProjectTaskGroupView.vue` L124、`OrchestrationResourceView.vue` L147/L210/L220 仍写「经编排网关代理海豚」 | 改为 iframe 同源直连表述 |
| U13 | 权威设计 §十一 冲突 6：术语权威指向 | 已修正指向 | `docs/agents/domain.md` 已指向现行权威设计 §二/§八/§九；根目录 `GLOSSARY.md` 不存在 | 不提前创建 GLOSSARY；仅在确有跨文件术语漂移时再评估 |
| U14 | 权威设计 §十一 冲突 7：旧发布模板未归档 | 未开始 | `release/datara-1.9.0/infra/docker-compose.yml` 仍是旧五模块模板 | 归档并指向现役 compose |
| U15 | 8090 画布浏览器级逐页验收（画布渲染、三条定义可见、节点表单数据源下拉非空） | 未开始 | 现有证据止于 HTTP + 网关 API + 海豚侧真实执行三层，缺浏览器渲染层 | browser-use 打开 `/p/33/dag` |
| U16 | 海豚 mysql 驱动正式打包 | 未开始 | 当前为 worker 容器**单文件挂载** `mysql-connector-j-8.0.33.jar` 的临时做法 | 驱动打进 worker 镜像 |
| U17 | 旧栈 / 旧镜像残留清理 | 未开始 | 1.9 仍有 `dt-oldweb`、`dt-api/dt-worker/dt-master/dt-logger/dt-alert`（`datara-backend:latest`）、`dt-db-src`、`dt-db-meta`、`ds-postgres` 及多枚历史镜像标签，用途未明确故保留 | 用户确认用途后清理 |
| U18 | 旧调用链清理 | 未开始 | `datasourceApi.ts` 旧 service 消费者仍挂在已退役 `WorkflowGraphWorkbench`；旧「运行时节点」路由与后端能力待清理 | 按权威设计 §一 残留清单处理 |
| U19 | 1.9 DBX / 海豚源码快照回同步本机真源 | 未开始 | 按 `docs/agents/source-truth.md` 发布后应回同步，当前无回同步记录 | 执行 `release_source.py` 回同步并留证 |
| U20 | `tt` 页面内手工保存回测 | 待验收 | 现有证据为脚本直连海豚 API 的 200，非页面点击；且 DS 版本号每次保存递增 | 单次页面点击回测并留 Network 证据 |
| U21 | dbx 运行镜像与最新改造一致性复核（原 c4c） | 待核验 | 当前运行 `dbx:codex-main-20261101-1240`（10:18 构建），与 11-01 后续改造对应关系未登记；`dt-api/dt-worker` 仍 `latest`，`dt-alert/dt-master/dt-logger/ds-alert` 仅显示镜像 ID | 核对镜像内容与 `deploy/image-policy.json` 白名单 |
| U22 | SQL 节点无法从已保存 SQL 文件列表选取（Python/Shell 已支持） | 未开始 | 海豚 UI 补丁 `deploy/dolphinscheduler/3.4.3/datara-ui-script-resource.patch` 只改 `use-shell.ts`，`use-sql.ts` 未纳入（`patch#L174-L179`）；后端 `GET /ide-scripts`（`rebuild/resources/api.py#L537-L554`）已能投影 dbx SQL 库但**未接入 DAG 节点** | 把 `visible_ide_scripts` 投影接入 SQL 节点资源下拉 |
| U23 | SQL / Python / Shell 文件「两个入口、一个真源」未收敛 | 未开始 | ① SQL：dbx saved-SQL 库（`resources/api.py#L590-L657`）与 datara `resources(kind='sql')`（`models.py#L26-L61`）两份，`ResourceManagementView.vue#L144-L167` 仅前端拼列表，无统一主键/双向同步；② Python/Shell：datara `resources` 为真源，海豚侧单向派生副本（`script_sync.py#L108-L149`，只写不回读）；③ 节点「选取」是把正文**复制**进 `rawScript`（`patch#L189-L195`），非运行期引用 | 先裁定真源归属，再实现运行期引用或双向同步 |
| U24 | 电商仿真业务数据落地与验收 | 历史运行有记录；当前待复核 | 早期核查曾记录目标工作流缺失；`infra/fixtures/business/ecom_sim_20261030/README.md` 后续记载项目 33、14 张表、变量及三条 DAG 实例成功。历史记录不能证明当前状态或行级质量验收 | 先在合规租约下核实现状和证据，再决定是否需要补种及运行验证，避免盲目重复 seed |

---

## 四、阻塞原因归类

| 主题 | 涉及项 | 说明 |
|---|---|---|
| 浏览器级验收缺登录态/凭据 | U01、U02、U03、U05、U15、U20 | 页面不设登录表单、token 需短时注入；zhangsan 私有凭据始终未提供 |
| 后端能力缺口 | U08、U09、U10 | `/api/v1/alerts` 实测 404；质量只做结构校验；短信通道未选型 |
| 编排网关取消后的代码/文档残留 | U11、U12 | 权威设计已裁定取消，代码挂载与注释仍在 |
| 配置与文档一致性 | U04、U14、U16 | `18091` 环境变量、旧发布模板、驱动挂载临时方案；U13 术语权威指向已修正 |
| 外部环境限制 | U06、U19 | 无授权 SSH 试运行节点；远端源码回同步未执行 |
| 环境残留 | U17、U18、U21 | 旧栈容器/镜像、退役 service、镜像白名单待核对 |
| 脚本/文件真源与 DAG 节点引用 | U22、U23 | SQL 节点未接入资源下拉；多入口多副本 + 「复制正文」而非运行期引用 |
| 仿真数据落地 | U24 | 用户裁定「必须做」；已有历史运行记录，当前状态与验收待复核 |

---

## 五、建议收口顺序

1. U04（改 8090 环境变量）→ U15 / U01 / U02（同一批浏览器取证，复用注入脚本）
2. U11 / U12（编排网关代码与注释残留，纯代码可立即做）
3. U09（`/api/v1/alerts`）→ 预警中心才算真正可用
4. U06（授权 SSH 节点）→ U03 / U07 批量复验
5. U24（先核实 1.9 当前数据及历史证据，再决定是否补种）→ U23（按现行权威核对真源及库/schema 归属）→ U22（SQL 节点接入资源选择）
6. U13 / U14 / U16 / U17 / U18（一致性与残留清理，低风险）
7. U05 / U08 / U10（依赖外部输入或需先裁定口径）

---

## 六、备注

- 本账以 **Git 提交 159 个**（10-31 00:45 ~ 11-01 13:30）为骨架反推动因，再与 trae 会话存档 100 条原始输入、47 张交接卡、4 份关键设计文档交叉验证。
- **覆盖率自检**：159 个 commit 中 **130 个**被点名为证据（脚本比对 hash）；剩余 **29 个全部是 `docs:` 交接 / 部署留痕类提交**，归入 C38，**非 docs 类的未归属提交为 0**。
- 运行时控制面 `D:\super-develop\runtime\datara-live\*` 最后写入为 2026-10-24，已冻结，未作为活证据使用。
- 本账所有 1.9 实时结论均来自 2026-11-01 对 `root@192.168.1.9` 的容器、镜像、接口与前端产物核查。
