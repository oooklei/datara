# ADR-2026-10-26-01：workflow_type 枚举口径归一（NORMAL/SYNC/STREAM ↔ wf/sync/stream）

- 状态：已接受（Accepted）
- 日期：2026-10-26
- 关联差距：`docs/qa/2026-10-26-可交付差距报告.md` §4 P1 **D-08**
- 关联设计：`docs/increments/2026-10-19-纠偏重构前端权威设计.md` §5A.2（L507-509）、§5C.1 ⑥（L644）

---

## 1. 背景与问题

Datara 数据治理平台的「工作流类型」（workflow_type）在**后端权威实现**与**设计文档 / 前端展示层**之间存在两套口径，导致联调与验收时出现歧义：

| 口径 | 取值 | 出处 |
|---|---|---|
| 后端权威枚举（新规范） | `NORMAL` / `SYNC` / `STREAM` | `rebuild/workflow/repository.py`、`rebuild/component_spec/catalogue.py` |
| 设计 / 前端展示枚举（旧） | `wf` / `sync` / `stream` | `datara-newweb/src/stores/dagTabs.ts`、`datara-web/src/stores/dagTabs.ts` |
| 存量历史枚举（已废弃） | `etl` | 旧前端四分类、`datara-backend/api/lineage.py` |

三套口径并存，若不登记权威映射，则：
1. 前端拿到的 `NORMAL` 无法确定应渲染为 `wf` 还是 `sync`；
2. 存量 `ETL` 标签工作流在迁移后去向不明；
3. 测试与验收缺少唯一判定基准，容易各自臆断。

本 ADR 的目的：**登记唯一权威映射表 + ETL 降级规则 + 转换时机与边界**，消口径歧义。

---

## 2. 权威枚举定义

**唯一权威枚举（后端持久化与领域判定）= `NORMAL` / `SYNC` / `STREAM`（大写）。**

取证：

- `datara-backend/rebuild/workflow/repository.py:71`
  `WORKFLOW_TYPES = frozenset(WORKFLOW_COMPONENT_TYPES)`，其键集合即 `{NORMAL, SYNC, STREAM}`。
- `datara-backend/rebuild/workflow/models.py:38`
  `CheckConstraint("workflow_type IN ('NORMAL','SYNC','STREAM')", name="ck_workflow_definition_type")`。
- `datara-backend/rebuild/workflow/models.py:50`
  `workflow_type: Mapped[str] = mapped_column(String(16), nullable=False, default="NORMAL", server_default="NORMAL")`。
- `datara-backend/rebuild/component_spec/catalogue.py:13-25`
  `WORKFLOW_COMPONENT_TYPES = {"NORMAL": (...), "SYNC": (...), "STREAM": (...)}`。
- `datara-backend/rebuild/component_spec/catalogue.py:35-39`
  `workflow_kind(value)`：`.strip().upper()` 归一化后必须命中 `WORKFLOW_COMPONENT_TYPES`，否则返回 `None`。

**展示枚举（前端）= `wf` / `sync` / `stream`（小写，三分类）。**

取证：

- `datara-newweb/src/stores/dagTabs.ts:15`
  `export type DagProfileType = 'wf' | 'sync' | 'stream'`（已由四分类收窄为三分类，删除 `etl`）。
- `datara-newweb/src/views/TaskCenterView.vue:135-143`
  `typeOf()`：`workflowType === 'SYNC' → 'sync'`；`'STREAM' → 'stream'`；`'NORMAL' → 'wf'`；
  `TYPE_LABEL: Record<DagProfileType, string> = { wf: '工作流', sync: '同步', stream: '流' }`。
- `datara-newweb/src/components/WorkflowGraphWorkbench.vue:86`
  `props.tab.type === 'sync' ? 'SYNC' : props.tab.type === 'stream' ? 'STREAM' : 'NORMAL'`（出站反向映射）。

**历史枚举（已废弃）= `etl`。**

取证：

- `datara-web/src/stores/dagTabs.ts:11`
  `export type DagProfileType = 'wf' | 'sync' | 'etl' | 'stream'`（旧前端四分类，`etl` 为待降级项）。
- `datara-backend/api/lineage.py:78`
  `"wf": e.wf_name or ""`（旧后端血缘用 `wf` 命名，属展示层遗留）。

---

## 3. 映射表（权威）

| 后端权威枚举（存储/判定） | 前端展示枚举（UI） | 语义 | 组件类型集合（`WORKFLOW_COMPONENT_TYPES`） |
|---|---|---|---|
| `NORMAL` | `wf` | 普通 DAG 工作流 | `sql, python, shell, dependent` |
| `SYNC` | `sync` | 同步工作流 | `src_base_orch, tgt_base_orch, file_sync_orch, endpoint_select, field_map, field_map_union, condition_set` |
| `STREAM` | `stream` | 流处理工作流 | `stream_input, stream_fuse, stream_output, page_board` |
| `ETL`（历史，已废弃） | —（无独立展示） | 存量 ETL 标签工作流 | **降级映射为 `NORMAL`（即展示为 `wf`）** |

### 3.1 ETL 降级规则

- **规则**：存量 `ETL` 标签工作流**一律降级映射为普通工作流 `NORMAL`**（展示层 `wf`）。
- **依据**：用户裁定 2026-10-20「工作流分类，可以去掉 ETL 这类（实质上也是普通 DAG 工作流）」（设计 §5A.2 L507、§5C.1 ⑥ L644）。
- **落地实现**：
  - 入站降级：`datara-backend/rebuild/workflow/repository.py:239`
    `update_definition` 中 `workflow_type = "NORMAL" if workflow_type == "ETL" else workflow_type`。
  - 迁移降级：`datara-backend/rebuild/workflow/revisions/v0001_workflow_type.py:33`
    `UPDATE workflow_definition SET workflow_type='NORMAL' WHERE UPPER(TRIM(workflow_type))='ETL'`；
    `MANIFEST["legacy_mapping"] = {"ETL": "NORMAL"}`（L13）。
- **fail-closed 约束**：`v0001_workflow_type.py:15` `mixed_evidence: "fail-closed"`；当一条工作流同时命中 NORMAL/SYNC/STREAM 多类组件证据时，迁移直接 `raise RuntimeError`（L54-55），拒绝猜测。
- **不可变约束**：已发布工作流类型不可更改——`repository.py:242` `WF_WORKFLOW_TYPE_IMMUTABLE`。

---

## 4. 转换时机与边界

### 4.1 入站归一化（写入 / 迁移路径）

- **位置**：`datara-backend/rebuild/workflow/repository.py:182-186`（`create_definition`）
  `workflow_type = workflow_type.strip().upper()`；不在 `WORKFLOW_TYPES` → `WorkflowDomainError("WF_TYPE_UNKNOWN", "workflow_type must be NORMAL, SYNC, or STREAM")`。
- **边界**：入站只接受**大写** `NORMAL/SYNC/STREAM`；`ETL` 仅在 `update_definition`（L239）做降级兼容，`create_definition` 不接受 `ETL`。
- **迁移路径**：`v0001_workflow_type.py` 的 `upgrade()` 负责把历史列值收敛到权威枚举（ETL→NORMAL，其余按 `workflow_node.node_type` 证据推断 SYNC/STREAM）。

### 4.2 出站展示（读取 / 下发路径）

- **后端 → 前端**：后端只下发权威枚举（`NORMAL/SYNC/STREAM`），**不在后端做小写化**。前端 `TaskCenterView.vue:135-139` 的 `typeOf()` 负责把权威枚举映射为展示枚举。
- **前端 → 后端**：前端 `WorkflowGraphWorkbench.vue:86` 在提交/创建时把展示枚举反向映射回权威枚举（`sync→SYNC`、`stream→STREAM`、其余→`NORMAL`）。
- **边界**：展示枚举 `wf/sync/stream` **仅存在于前端展示层**，不得作为持久化值或 API 契约值；后端 `workflow_kind()`（`catalogue.py:35-39`）与 `published_document`（`service.py:116-119`）只认大写权威枚举，传入小写或未知值即报错。

### 4.3 一句话口径

> **存储与判定用大写 `NORMAL/SYNC/STREAM`；展示用小写 `wf/sync/stream`；`ETL` 是历史别名，等价于 `NORMAL`。**

---

## 5. 代码取证引用（文件:行）

| 结论 | 取证位置 |
|---|---|
| 权威枚举定义 | `datara-backend/rebuild/workflow/repository.py:71`；`rebuild/workflow/models.py:38,50` |
| 入站归一化 + 拒绝未知值 | `datara-backend/rebuild/workflow/repository.py:182-186` |
| ETL 入站降级 | `datara-backend/rebuild/workflow/repository.py:239` |
| 已发布类型不可改 | `datara-backend/rebuild/workflow/repository.py:242` |
| 迁移 ETL→NORMAL + 证据推断 + fail-closed | `datara-backend/rebuild/workflow/revisions/v0001_workflow_type.py:13,15,33,54-55` |
| 组件类型集合（三分类） | `datara-backend/rebuild/component_spec/catalogue.py:13-25` |
| 组件域归一化 | `datara-backend/rebuild/component_spec/catalogue.py:35-39` |
| 前端展示枚举（新，三分类） | `datara-newweb/src/stores/dagTabs.ts:15` |
| 前端出站映射 | `datara-newweb/src/views/TaskCenterView.vue:135-143` |
| 前端入站反向映射 | `datara-newweb/src/components/WorkflowGraphWorkbench.vue:86` |
| 旧前端四分类（含 etl） | `datara-web/src/stores/dagTabs.ts:11` |
| 旧后端 wf 命名遗留 | `datara-backend/api/lineage.py:78` |

---

## 6. 影响面

- **后端**：无需改动。权威枚举、ETL 降级、fail-closed 均已在 `repository.py` 与 `v0001_workflow_type.py` 落地。
- **前端（datara-newweb）**：无需改动。`DagProfileType` 已收窄为三分类，`typeOf()` / `TYPE_LABEL` / `WorkflowGraphWorkbench.vue` 反向映射均已就位。
- **前端（datara-web，旧）**：`DagProfileType` 仍含 `etl`，属遗留；融合后废弃，不要求改。
- **契约面**：`GET /api/v1/rebuild/components/spec` 等下发权威枚举，前端按 §4.2 映射；契约冻结注册表（`docs/contract-freeze-registry.md`）无需新增条目（本 ADR 为口径说明，非新契约）。
- **测试**：`tests/rebuild/test_workflow_migrations.py` 已覆盖 ETL 映射与混合证据 fail-closed，作为回归基准。

---

## 7. 验收方式

1. **映射正确性**：对任意后端 `workflow_type`，前端 `typeOf()` 产出唯一展示值：
   - `NORMAL → wf`、`SYNC → sync`、`STREAM → stream`。
2. **ETL 降级**：存量 `ETL` 工作流经 `v0001_workflow_type` 迁移后 `workflow_type == 'NORMAL'`；`update_definition` 传入 `ETL` 等价于 `NORMAL`。
3. **fail-closed**：构造同时含 NORMAL 与 SYNC 组件证据的工作流，迁移须抛错（`test_workflow_migrations.py` 已覆盖）。
4. **回归**：`python -m pytest tests/rebuild/test_workflow_migrations.py -q` 全绿。
5. **口径唯一性**：全局检索不得再出现把 `wf/sync/stream` 作为后端持久化值的代码路径（展示层映射除外）。
