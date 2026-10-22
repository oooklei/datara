## AOCI 开发期全线暂停（2026-10-22 用户裁定）

当前开发阶段，所有监管席与实施线均不得加载、调用或维护 AOCI；不得执行 AOCI MCP、CLI、overview、refresh、maintain 或索引更新。保留 `.aoci/`、`aoci*.txt` 等资产，不做人工删除。

认知与检索统一使用最小任务包、权威设计定位、`rg`/LSP 和源码绑定验证。候选版本代码冻结后，才允许新建一个隔离维护会话，临时恢复 AOCI，执行一次全量对齐、校验和版本快照；完成后再次停用。

本裁定优先于历史文档中的 AOCI 要求。

## 域规范（仍生效约束；原设计文档已归档 docs/archive/2026-10-20/，实现冲突时以本节为准）

- **组件声明**：spec 纯 JSON 禁函数/脚本/回调（动态行为走 conditions/behaviors/extensions）；behaviors 动作、pick 字段（table/column/cron/sshHost）、hiddenInputs（runId/nodeId/workflowId/tenantId，执行器禁回写）、refreshOptions.remote 端点（仅 datasource.tree/datasource.topics/runtime.nodes，禁 URL）四白名单；已发版不可变，消费方 componentRef:{type,version} 固定；type 全局唯一；表单八段 DSL（inputs/outputs/params/conditions/constraints/exclusions/refs/exports）；变量解析链 节点参数>工作流变量>环境组>全局；生命周期三态 unbaseline→baselining→baselined，用户认可版本=治理基础；发布闸门 run_publish_gates() 杜绝可声明不可执行；FieldSchema.showIf/onChange/text 函数字段逐组件消灭。
- **同步编排**：设计态禁运行态组件——sync(C17)/file_sync(C24) 标 runtimeOnly:true，palette/画布/W1 校验/保存闸门全排除；端点合一 endpoint_select(C37) 三模式 src_base/tgt_base/file_sync（替代 src_select/tgt_select）；拖边即引用——inputs 由边自动派生 nodeId:port 具名引用，field_map_union 按 :sourceRef/:targetRef port 语义识别，废除顺序索引；运行态 engine.py 检测 endpoint_select 物化 sys_exec_* 执行节点并按 baseMode 分拣；palette 数据同步组 7 项（src_base_orch/tgt_base_orch/file_sync_orch/endpoint_select/field_map/field_map_union/condition_set）。
- **重建验证环境**：本机=代码检测/静态/类型/逻辑稽核，192.168.1.9=部署/容器/中间件/联调/browser-use E2E；前端验证入口固定 `http://192.168.1.9:18091/`（禁 8090；18090 被并行验证栈占用；Web 容器内监听 80、API 代理契约不变）；部署/E2E 验收证据必须出自 1.9 隔离工作目录；页面不设登录表单，验证 key 换短时 token 注入且 key 禁入静态产物/URL/浏览器持久存储；与权威设计冲突→暂停候批刷新契约；Agent worktree 仅代码隔离，不作文档/状态权威。

## Active handoff

活跃运行控制只读 `D:\super-develop\runtime\datara-live\control\authority-carrier-registry.json` 中标为 `ACTIVE` 的载体；入口为 `governance-state.json`、`role-contracts.json` 与 `queues/snapshot.json`。当前为 `RUNNING / epoch 3`（2026-10-22 12:28 用户授权重启）。lifecycle 切换、纪元创建与派单开放仅由 Flow 依用户明确指令执行；未持用户明确指令时，所有角色不得派单、实施、测试、验收、裁定或写共享状态。只有流程控制 Flow 可按水位增量写入 `docs/handoff/STATE.md`、`mailbox.jsonl` 和队列投影；其他角色使用本角色最小队列卡，禁止用完整台账或归档冷启动。旧运行材料已移入 `docs/handoff/archive/2026-10-22-v2-final`，只作追溯。

**权威序**：用户最新裁定 > `docs/increments/2026-10-19-纠偏重构前端权威设计.md`（唯一需求真源 v3）> `docs/increments/2026-10-17-核心业务功能实现规范与验收标准.md`（验收 v4）> `docs/increments/2026-10-20-单线多增量WBS开发计划.md`（WBS）> `docs/agents/协作规程.md` > 其余文档；归档区（docs/archive/、docs/increments/archive/、docs/handoff/archive/）只作考古。细目见 `docs/README.md` §1。

## Agent skills

### Issue tracker

Issues 存放在 GitHub Issues（oooklei/datara），所有操作通过 gh CLI 完成。See `docs/agents/issue-tracker.md`.

### Triage labels

使用五个默认规范 triage labels：needs-triage、needs-info、ready-for-agent、ready-for-human、wontfix。See `docs/agents/triage-labels.md`.

### Domain docs

Single-context 布局：repo 根目录 GLOSSARY.md 与 docs/adr/。See `docs/agents/domain.md`.
