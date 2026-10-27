# Ops 分诊呈递 · IMPL-v4-02a 边界张力与附带发现（致 Ops / Flow）

- **报告席**：Execution（claude）｜**票据**：IMPL-v4-02a（P1，DELIVERY，派单 v3-0041）
- **时间**：2026-10-22｜**水位**：`v3-0045-lease-request-rt-impl-v4-03-c-group`
- **性质**：只读稽核发现 + 边界张力呈递，**不代裁、不代写共享状态**；三项均属他席职权，报 Ops 分诊
- **触发**：IMPL-v4-02a 本地段收口稽核（6 路径 + 契约对齐 + 接线）

---

## B-1（D0-D2 候裁）：02a 路径对 02b 路径的编译期依赖

- **位置**：`datara-newweb/src/components/NodeConfigPanel.vue` **L24**（**02a 路径**）
  ```ts
  import { createDatasourceContract } from '../services/rebuild/datasourceApi'
  ```
- **越界对象**：`datara-newweb/src/services/rebuild/datasourceApi.ts`（**02b 路径**，Task 增量 06 §3 / 增量 07 §3）
- **依赖性质（重要）**：
  1. **只读消费**——仅 `listDatasources()` 用于 `srcDs`/`tgtDs` 下拉数据源名；**无写路径、无权限面扩张**。
  2. **静默降级**——加载失败置 `dsFailed=true`，面板提示、**不阻断保存其余字段**（设计注释 L12-14 明示）。
  3. **依赖已可满足**——`datasourceApi.ts` 已实存（工作区未跟踪），`CONTRACT_REGISTRY.md` #16 记为 **GREEN**（11 端点 / 4 测试）。即该依赖**不以 02b 实施完成为前置**。
  4. **编译期**——TS/Vite 构建需该模块可解析；若 02b 面被回退/迁移，02a 构建面随之破。
- **呈请裁定方向（供 Decision 参考，本席不预设）**：
  - (a) **D0/D1**：认定「02a 对 02b 契约的**只读消费**」为既有既定设计的自然结果（权威设计 §5A/§5E 未禁止跨域只读引用），予以**追认**，无需扩边；
  - (b) **D2**：认定需在 pathspec/登记面显式登记该跨域引用（如 CONTRACT_REGISTRY 增补 sshNodeApi 行 + 标注 02a↔02b 只读引用）；
  - (c) 若认定须解耦，则 02b 面落地后回填——本席**不自行选路**。
- **本席已做**：**未修改** `datasourceApi.ts`；**未**在 02a 面复制/内联其逻辑（避免双源漂移）；**未**静默扩边。

## F-3（后端，02a 路径外）：`apply_ssh_node_migrations` 死码（与既有 F-2 同型）

- **位置**：`datara-backend/rebuild/sshnode/migrations.py` L16（定义）｜**全仓零调用点**
- **实测**：`grep -rn "apply_ssh_node_migrations" datara-backend/ --include=*.py` → 仅定义处 + `tests/rebuild/test_sshnode_migrations.py`（测试自用）。
- **对照**：`app.py` lifespan（L363-368）调用 `apply_component_spec_migrations` / `apply_llm_migrations` / `ensure_i1_schema` / `ensure_schedule_schema` / `ensure_model_schema` / `ensure_runtime_node_schema`；**未**调用 `apply_ssh_node_migrations`（亦未调用 `apply_runtime_node_migrations` / `apply_execution_migrations`）。
- **影响**：`rebuild_ssh_node` 表经 `Base.metadata.create_all`（`app.py` L318-400 tables 列表含 `SshNodeRecord.__table__`）创建 → **运行时无碍**；但 `rebuild_schema_migration` 台账**不登记** `v0001_ssh_node_registry`，迁移可重放性与审计链缺一环。
- **同型**：与 Ops 已分类的 **F-2**（`apply_runtime_node_migrations` / `apply_execution_migrations` 死码）**完全同型**——建议**并票处理**（Ops 已建议独立 P3/MAINTENANCE 票）。
- **处置**：后端文件、**02a 路径外**，本席**不自修**（沿用 F-2 先例：实施线未越界自修，纪律正确）。

## F-4（登记簿，02a 路径外）：CONTRACT_REGISTRY 缺 sshNodeApi 行

- **位置**：`datara-newweb/src/services/rebuild/CONTRACT_REGISTRY.md`（现 18 行）
- **缺行**：`sshNodeApi.ts`（新契约件）+ 其测试 `sshNodeApi.contract.test.ts`（3 用例）**未登记**。
- **自订纪律**：该簿头部载「新增/变更契约文件**有测试对应方可合入**」，且「门 1 API 契约验收直接消费」——缺行使 sshNode 域契约在门 1 **不可见**。
- **同批滞后**：`llmApi.ts`（node A 交付）亦未见对应新行；该簿「最近更新」停留在 2026-10-21（16.1 波2）。属**登记滞后**，非代码缺陷。
- **处置**：`CONTRACT_REGISTRY.md` **02a 路径外**，本席**不自写**；建议随 02a/02b 集成窗或独立文档窗补登（候 Ops/Flow 定归属）。

## E-1（路由请求）：02a 的 1.9 e2e 证据产出路径

- **张力**：02a acceptance 含「1.9 端到端 GREEN（sshNode 域）」，但 **02a paths 不含 `datara-newweb/e2e/`**；`e2e/` 现仅 `llm-models.spec.ts`（node A），**无 sshNode 用例**。
- **边界规则**：票面明载「02a paths 不含 `datara-newweb/e2e/`；若需新增 sshNode 用例文件，经 Ops 路由避免与 IMPL-v4-03（e2e/ 属主）路径碰撞，不静默扩边」。
- **本席已做**：**未**新增 e2e 用例件。
- **呈请**：请 Ops/Flow 就「sshNode 域 1.9 e2e 证据」产出方式定路——
  - (i) 授权在 `e2e/` 新增 `ssh-node.spec.ts`（需与 03 属主协调，或纳入 03 收口批）；
  - (ii) 或由 Integration 以既有 `llm-models.spec.ts` 同构**临时**驱动 `/dep/ssh` 冒烟（不落新件）；
  - (iii) 或降级 02a 验收为「契约测试 + 本机静态 + 人工冒烟」并**升版修订验收面**（须 Decision/用户裁定，本席不代裁）。
- **本席已提交租约请求**（`2026-10-22-EXEC-IMPL-v4-02a-lease-request.md`），business_key `IMPL-v4-02a:REMOTE_TEST:sshnode-domain`；回执前不进 1.9 执行。

---

## 附：本票进度（供 Ops/Flow 知悉，无请求动作）

- IMPL-v4-02a 本地段：**EVIDENCE_READY**（`outbox/claude/2026-10-22-EXEC-IMPL-v4-02a-EVIDENCE-claude.md`）——6/6 路径、静态三项全绿、契约 10/10、接线 5/5。
- 1.9 段：租约请求已提交，候回执。
- 边界不变式：02a/02b 路径互斥无交叠，本席**零越界**（02a paths 之外零写入）。

## 边界声明

- 本轮仅**只读稽核** + **本机静态校验** + **呈递件落盘**；**未**修改任何代码、**未**写 STATE/mailbox/队列投影、**未** commit/push、**未**加载 AOCI、**未**弹窗用户。
- 三项（B-1/F-3/F-4）与 E-1 均属他席职权（Decision 边界裁定 / Ops 归并与建票 / Flow 集成窗归属），本席**不自行处置**，报 Ops 分诊。

—— Execution（claude），IMPL-v4-02a 边界张力与附带发现，报 Ops。
