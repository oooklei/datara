## AOCI 已停止并物理删除（2026-10-29 用户裁定升级）

`.aoci/` 目录已完整删除（原含 archive/20261020T095235Z 归档、baseline.json、config.json 及 governance/drafts 子目录，约 200+ 文件）。所有开发、监管、实施线均不得提及、加载或恢复 AOCI；不存在任何隔离维护会话的恢复窗口。

认知与检索统一使用最小任务包、权威设计定位、`rg`/LSP 和源码绑定验证。

## 域规范（仍生效约束；原设计文档已归档 docs/archive/2026-10-20/，实现冲突时以本节为准）

> 2026-10-29 用户裁定：原「组件声明」「同步编排」两节约束随 datara 自研编排画布下线而失效，已删除。海豚只取其**编排可视化（DAG 画布）+ 运行后台底座**，门户外壳/身份/数据源/审计由 datara 与 dbx 承担（见 `docs/designs/2026-10-29-dbx-unified-target-design.md` §十）。

- **重建验证环境**：本机=代码检测/静态/类型/逻辑稽核，192.168.1.9=部署/容器/中间件/联调/browser-use E2E；前端验证入口固定 `http://192.168.1.9:8090/`（唯一前端入口，禁止多套并行部署；Web 容器内监听 80、API 代理契约不变）；部署/E2E 验收证据必须出自 1.9 隔离工作目录；页面不设登录表单，验证 key 换短时 token 注入且 key 禁入静态产物/URL/浏览器持久存储；与权威设计冲突→暂停候批刷新契约；Agent worktree 仅代码隔离，不作文档/状态权威。

## Active handoff

活跃运行控制只读 `D:\super-develop\runtime\datara-live\control\authority-carrier-registry.json` 中标为 `ACTIVE` 的载体；入口为 `governance-state.json`、`role-contracts.json` 与 `queues/snapshot.json`。当前为 `RUNNING / epoch 3`（2026-10-22 12:28 用户授权重启）。lifecycle 切换、纪元创建与派单开放仅由流程依用户明确指令执行；未持用户明确指令时，所有角色不得派单、实施、测试、验收、裁定或写共享状态。只有流程可按水位增量写入 `docs/handoff/STATE.md`、`mailbox.jsonl` 和队列投影；其他角色使用本角色最小队列卡，禁止用完整台账或归档冷启动。旧运行材料已移入 `docs/handoff/archive/2026-10-22-v2-final`，只作追溯。

**权威序（2026-10-30 用户裁定收敛）**：用户最新裁定 > `docs/designs/2026-10-29-dbx-unified-target-design.md`（**唯一实施权威**；冲突时同日线子设计 phase-1-backend / ide-integration / variable-completion 以 unified-target 为准）> `docs/agents/协作规程.md` > 其余文档。旧权威序三件（2026-10-19 v3 真源 / 2026-10-17 验收 v4 / 2026-10-20 WBS）及 increments 旧线全量、docs 根部旧设计已于 2026-10-30 归档至 `docs/increments/archive/2026-10-30-authority-consolidation/` 与 `docs/archive/2026-10-30-authority-consolidation/`，只作考古，不得作为现行依据恢复约束。归档区（docs/archive/、docs/increments/archive/、docs/handoff/archive/）只作考古。细目见 `docs/README.md` §1。

## Agent skills

## 源码真源与发布前合并（2026-11-01 用户裁定）

Datara、DBX、海豚的源码真源、双向同步位置及发版门禁见 `docs/agents/source-truth.md`。所有修改先落在对应真源；其他分支或工作区的发布内容必须先合并回真源。远程构建前运行 `python scripts/release_source.py preflight`，并把本机 Datara 源码快照同步到 192.168.1.9 隔离发布目录；发布后把 1.9 的 DBX 与海豚源码快照同步回本机。镜像、容器、构建产物及 `.source-mirrors/` 均不是源码真源。

本系统运行容器名称最多 12 个字符；名称映射、DNS 兼容别名及远端核验记录见 `docs/agents/container-names.md`。改名须同步修改 Compose/发布配置并验证服务间访问，不能只改 Docker 当前显示名。

### Issue tracker

Issues 存放在 GitHub Issues（oooklei/datara），所有操作通过 gh CLI 完成。See `docs/agents/issue-tracker.md`.

### Triage labels

使用五个默认规范 triage labels：needs-triage、needs-info、ready-for-agent、ready-for-human、wontfix。See `docs/agents/triage-labels.md`.

### Domain docs

Single-context 布局：repo 根目录 GLOSSARY.md 与 docs/adr/。See `docs/agents/domain.md`.
