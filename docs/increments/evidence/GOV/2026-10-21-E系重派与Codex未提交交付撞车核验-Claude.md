# 「15.4-E1~E7 重派」与 Codex 未提交交付撞车核验（含投递信台账零痕迹证据）

- **性质**：Claude 实施线对 s335/s336 派单做独立只读核验——**不摘票、不改码**，仅供监督线对账
- **日期**：2026-10-21
- **触发**：s335-gov-dispatch-balance-all-20261021 / s336-gov-dispatch-correction-20261021【二】【四】将 15.4-E1~E7 七票作为「R8-A 未接线工具接线票」重新均衡派单
- **边界**：只读实证；**零业务代码改动**；`.git` 只读未 push；未调用 `aoci_*`；未触碰他线在飞件

---

## 一、结论（三条）

1. **前提「未接线」与 HEAD 不符**：HEAD 提交 `cd43668`（"AI 八工具接线(ai_tools+ai_bridge)…"）已为七工具提供**真实 handler**，且默认生产 app 将七工具**全部 enable**；哨兵 `R8A_BACKEND_NOT_WIRED` 在 HEAD 的 `rebuild/` 下**零出现**。故 E1~E7 在 HEAD 上**并非未接线状态**。
2. **Codex 已交付 E1~E7 且该报告信在 mailbox 台账零痕迹**：`docs/handoff/outbox/codex/cd-done-s309-ai-e1-e7.json`（ts 16:05，磁盘 mtime 17:57:43）报告七票完成并附 SHA + 证据 + 30 passed；该信在 mailbox 的 **id / ref / body 三处全字段零痕迹**。对照：同批 Codex 信 `cd-done-s309-15-5-ab` / `cd-done-s309-15-5-cde` / `cd-done-s320-fe8` / `cd-done-s320-17.5-p4-dep-ssh` / `cd-done-s327-c17-03` / `cd-supplement-s328-fe8` **六件均已被 s328/s333 等验收信以 ref 具名引用**——即同批六件已被登记、E1~E7 一件零登记。
3. **重派将造成两线同改同一未提交件**：Codex 交付物为**工作区 M 态未提交件**（`ai_tools.py` / `ai_bridge.py` + 新测试件），恰好是 s336【四】派给 Claude（E3/E4/E5）与 Codex（E1/E2/E6/E7）的同一组文件；且 **E5 已被 Codex 未提交改动覆盖**。

> **本线不摘 E1~E7 任何票**。E3/E4/E5 已由并行 Claude 会话经 s337 ack 承接，本信仅作对账情报。

---

## 二、前提核验：「未接线」与 HEAD 不符

### 2.1 HEAD 七工具为真实实现（非桩）

```
$ git show HEAD:datara-backend/rebuild/ai_tools.py | sed -n '/^def build_get_workflow_handler/,/^def build_validate_workflow_handler/p'
def build_get_workflow_handler(session_factory: Any) -> Handler:
    """Compose the get_workflow handler over WorkflowRepository."""
    def handler(params, page_context, ctx):
        ...
        with session_factory() as session:
            definition = session.get(WorkflowDefinitionRecord, workflow_id)
            ...
            version_record = session.scalar(select(WorkflowVersionRecord)...)
```

即 HEAD 侧 `get_workflow` 已真实读取 `WorkflowDefinitionRecord` / `WorkflowVersionRecord`，**非占位桩**。

### 2.2 哨兵在 HEAD 零出现

```
$ git grep -c "R8A_BACKEND_NOT_WIRED" HEAD -- datara-backend/rebuild/
0 files（HEAD 全域无此哨兵）
```

s335【三】E 系红线所列「哨兵 R8A_BACKEND_NOT_WIRED」在 HEAD 侧**不存在**——哨兵属**未接线态**的标志，其缺席即 HEAD 非未接线态。

### 2.3 HEAD 默认 app 七工具全 enable

```
HEAD  ai_bridge.py:  if session_factory is not None:
                          handlers.update(build_all_handlers(session_factory))   # 返回 7 个 handler
HEAD  app.py:1078:   default_ports = build_default_bridge_ports(execution_port=…, audit_writer=…, session_factory=session_factory)
```

`build_all_handlers` 在 HEAD 返回 7 项（`search_schema/validate_sql/get_workflow/validate_workflow/inspect_workflow_run/get_task_metrics/get_lineage`；`run_sql` 另行组合）；`session_factory` 非空 ⇒ 全 7 项入 `handlers` ⇒ 注册表 `enabled=True`（`ai_bridge.py:497` `enabled ⇔ name in ports.handlers`）。

> 注：`tests/rebuild/test_r8a_ai_tools_api.py:192-195` 断言 `search_schema=True` 而 `validate_sql/run_sql/get_workflow=False`，系该用例走 `_bridge_app()` **显式注入 ports**（非默认装配），与上不矛盾。

---

## 三、Codex 交付与未入箱信实证

### 3.1 交付信内容（逐字摘）

`docs/handoff/outbox/codex/cd-done-s309-ai-e1-e7.json`：

> 「15.4-E1~E7 七工具真实 handler 接线完成并经独立复核修正：统一桥装配补 connector_factory；validate_sql 强制 datasource 项目归属；孤儿 run fail closed；metrics 在存储缺 total/cancelled 原值时诚实 DEPENDENCY_UNAVAILABLE，严守 R7 不推导；其余 workflow/lineage/metadata 真实读取。验证含生产 handler、bridge、failover/fence 共 30 passed；diff-check PASS。SHA：ai_bridge.py=69abfa13…；ai_tools.py=ea316ab9…；test_ai_tools_production_handlers.py=b2f02a79…；证据=4fe8ab73…。提交号无，工作区改动待监督线代提交。」

### 3.2 台账对账（id / ref / body 三字段全查）

> **口径说明**：本线初版以 `grep -c <id> mailbox.jsonl` 计数，会把**验收信 ref 字段里的具名引用**也算作「命中」。经复核，投递信本体**一律不以自身 id 入 mailbox**；监督线处理某信的方式是**在验收/裁定信的 `ref` 中具名引用**。故正确口径须分查 **id / ref / body** 三处。

| 信 id | ts / mtime | 作为 id | 出现于 ref | 出现于 body | 台账判定 |
|---|---|---|---|---|---|
| `cd-done-s309-ai-e1-e7` | ts 16:05 / mtime **17:57:43** | — | **—** | **—** | **零痕迹（未被登记）** |
| `cd-summary-s309` | ts 16:20 | — | **—** | **—** | **零痕迹（未被登记）** |
| `cd-done-s309-15-5-ab` | mtime 19:46:54 | — | **Y（s328 ref）** | — | 已登记（s328 验收 15.5） |
| `cd-done-s309-15-5-cde` | mtime 19:46:54 | — | **Y（s328 ref）** | — | 已登记（s328 验收 15.5） |
| `cd-done-s320-fe8` | mtime 19:39 | — | **Y（s328 ref）** | — | 已登记 |
| `cd-done-s320-17.5-p4-dep-ssh` | mtime 19:38 | — | **Y（s328 ref）** | — | 已登记 |
| `cd-done-s327-c17-03` | mtime 20:28 | — | **Y（s333 ref）** | — | 已登记 |
| `cd-supplement-s328-fe8` | mtime 20:29 | — | **Y（s333 ref）** | — | 已登记 |

⇒ **同批 6 件兄弟信均已被验收信 ref 具名登记；`cd-done-s309-ai-e1-e7` 与 `cd-summary-s309` 两件在 mailbox 三字段全零痕迹**。s335【一】盘点「Codex 15.5 五票 PASS（s328）」时**未列** E1~E7 交付，与该信零登记一致。

### 3.3 全投递线零痕迹清单（供监督线对账，非「未处理」断言）

以同一三字段口径扫描 `outbox/{claude,codex,trae}/` 全部在飞投递：

| 线 | 零痕迹信件（未见于 mailbox 任何字段） |
|---|---|
| codex | `cd-ack-s309-s314`、`cd-blocked-s309-13-2-16-1-16-2`、`cd-dedupe-s309-12-1`、`cd-dedupe-s314-175`、**`cd-done-s309-ai-e1-e7`**、`cd-summary-s309` |
| trae | `tr-ack-25`、`tr-done-28`、`tr-done-29`、`tr-done-30`、`tr-done-31` |
| claude | 本线全部 7 件（`headconsistency` 经裁定①入库为笔36 ccb5640、其余六件含本件） |

> **限定**：零痕迹**不等于**未被阅读——监督线可直接读 outbox 目录并经 commit / 台账笔（如本线 `headconsistency` → 笔36 ccb5640）处置而不留 mailbox 条目。本表仅列「mailbox 台账不可见」事实，供监督线自查对账，**不作未处理指控**。

### 3.3 交付物 = 工作区 M 态（未提交）

```
$ git status --porcelain --untracked-files=all datara-backend/tests/rebuild/test_ai_tools_production_handlers.py
?? datara-backend/tests/rebuild/test_ai_tools_production_handlers.py
```

`ai_tools.py` / `ai_bridge.py` 均为 `M`（在飞），测试件为 `??`（新）。**三件全部未提交**。

---

## 四、重派撞车面（文件级 + 函数级）

### 4.1 派单终局（s336【四】）

- **Claude**：15.4-E3 `get_workflow` + 15.4-E4 `validate_workflow` + 15.4-E5 `inspect_workflow_run`
- **Codex**：15.4-E1 `search_schema` + 15.4-E2 `validate_sql` + 15.4-E6 `get_task_metrics` + 15.4-E7 `get_lineage`

### 4.2 Codex 未提交改动落在哪些函数（hunk 头实证）

```
$ git diff HEAD -- datara-backend/rebuild/ai_tools.py | grep "^@@"
@@ -58,20 +70,32 @@ def build_search_schema_handler      ← E1
@@ -131,7 +161,16 @@ def build_validate_sql_handler      ← E2
@@ -435,10 +474,11 @@ def build_inspect_workflow_run_handler ← E5
@@ -495,33 +541,19 @@ def build_get_task_metrics_handler   ← E6
@@ -589,23 +596,7 @@ def build_get_lineage_handler        ← E7
```

```
$ git diff HEAD -- datara-backend/rebuild/ai_tools.py | grep -E "^[+-].*def build_"
-def build_search_schema_handler(session_factory: Any) -> Handler:
+def build_search_schema_handler(session_factory: Any, connector_factory: Any) -> Handler:
-def build_validate_sql_handler() -> Handler:
+def build_validate_sql_handler(session_factory: Any) -> Handler:
-def build_all_handlers(session_factory: Any) -> dict[str, Handler]:
+def build_all_handlers(session_factory: Any, connector_factory: Any) -> dict[str, Handler]:
```

### 4.3 E3/E4 未被 Codex 触碰（逐字一致）

```
$ git show HEAD:...ai_tools.py | sed -n '/^def build_get_workflow_handler/,/^def build_inspect_workflow_run_handler/p' > /tmp/e34_head.py
$ sed -n '/^def build_get_workflow_handler/,/^def build_inspect_workflow_run_handler/p' ai_tools.py > /tmp/e34_wt.py
$ diff /tmp/e34_head.py /tmp/e34_wt.py
（无输出）IDENTICAL
```

⇒ Codex M 态**未改** `build_get_workflow_handler` / `build_validate_workflow_handler`（E3/E4）。

### 4.4 撞车矩阵

| 票 | 函数 | HEAD 态 | Codex M 态 | 重派去向 | 撞车判定 |
|---|---|---|---|---|---|
| E1 search_schema | `build_search_schema_handler` | 真实 | **已硬化**（+connector_factory） | Codex | 与未提交件同函数 |
| E2 validate_sql | `build_validate_sql_handler` | 真实 | **已硬化**（+session_factory 项目归属） | Codex | 与未提交件同函数 |
| E3 get_workflow | `build_get_workflow_handler` | 真实 | 未改 | **Claude** | HEAD 已真实，非未接线 |
| E4 validate_workflow | `build_validate_workflow_handler` | 真实 | 未改 | **Claude** | HEAD 已真实，非未接线 |
| E5 inspect_workflow_run | `build_inspect_workflow_run_handler` | 真实 | **已硬化**（fail closed） | **Claude** | **双覆盖**：Codex 未提交件已含 |
| E6 get_task_metrics | `build_get_task_metrics_handler` | 真实 | **已硬化**（DEPENDENCY_UNAVAILABLE） | Codex | 与未提交件同函数 |
| E7 get_lineage | `build_get_lineage_handler` | 真实 | **已硬化** | Codex | 与未提交件同函数 |

⇒ **七票全部落在 `ai_tools.py` + `ai_bridge.py` 两文件内**；E1/E2/E6/E7 与 Codex 未提交改动同函数，**E5 更被 Claude/Codex 双线同时覆盖**。

---

## 五、附带实证：`ai_bridge.py` + `api/app.py` 为紧耦合原子单元

Codex M 态把装配闸门改为 `if session_factory is not None and connector_factory is not None:`，而 `connector_factory` 实参由 `app.py` 提供：

```
worktree app.py:1162:  default_ports = build_default_bridge_ports(…, connector_factory=pooled_connector)
HEAD     app.py:1078:  default_ports = build_default_bridge_ports(…)   # 无 connector_factory
```

⇒ 两件**互锁**，单独提交任一即断：

- 仅提交 `ai_bridge.py`（闸门加 `and connector_factory is not None`）而 HEAD `app.py` 不传该参 ⇒ **七工具全部落空**（静默退化，注册表全 `enabled=False`）；
- 仅提交 `app.py`（传 `connector_factory=`）而 HEAD `ai_bridge.py` 无该形参 ⇒ **`TypeError: unexpected keyword argument`**，app 装配即崩。

此结论与 `docs/increments/evidence/GOV/2026-10-21-在飞件原子提交单元与pathspec固化建议-Claude.md` §四 原子单元表一致，可作为该表 `ai_bridge.py`/`app.py` 同单元的**函数级补证**。

---

## 六、建议（供监督线采纳，非本线动作）

1. **补入箱**：将 `outbox/codex/cd-done-s309-ai-e1-e7.json` 与 `cd-summary-s309.json` 补入 mailbox，与 s328 的 15.5 同批对账，明示**接受 / 退回**。
2. **重派再裁**（三选一，均在 Claude/Codex 动工前）：
   - a) 认可 Codex 未提交交付为 E1~E7 完成 ⇒ **撤 s336【四】E 系重派**，走代提交；
   - b) 仅认可 E1/E2/E6/E7 ⇒ **收窄 Claude 侧至 E3/E4**（E5 归 Codex 未提交件），避免 E5 双覆盖；
   - c) 判定 Codex 交付需重做 ⇒ 明确**作废其工作区三件**再派，防两线同改同一未提交件。
3. **票面前提更正**：E 系票面「未接线」措辞与 HEAD `cd43668` 不符（哨兵零出现、七工具真实实现）。建议票面改为「**接线硬化**」类目，并明确验收锚是**硬化行为**（项目归属强制 / fail-closed / DEPENDENCY_UNAVAILABLE 诚实性）而非「从无到有接线」。
4. **原子提交**：`ai_bridge.py` + `api/app.py` + `ai_tools.py`（+ 新测试件）须**同一原子单元**入库，勿 pathspec 拆分（见 §五）。

---

## 七、红线自查

| 红线 | 状态 |
|---|---|
| `.git` 只读 | ✅ 仅 `git show/diff/status/grep`；未 `add`/`commit`/`push` |
| 禁 `aoci_*` | ✅ 零调用 |
| 禁 push | ✅ |
| 零业务代码改动 | ✅ 纯只读实证 + 文档 |
| 未触碰他线在飞件 | ✅ `ai_tools.py`/`ai_bridge.py`/`app.py`/测试件**仅读**，一字未改 |
| 证据成对 | ✅ 本件 + 信件 `outbox/claude/cl-done-e-series-redispatch-collision.json` |
| 不静默覆盖失败证据 | ✅ 本件为新增；Codex 漏箱如实记录未掩饰 |
| 不摘他线票 | ✅ E1~E7 零摘取；E3/E4/E5 归并行 Claude 会话（s337 ack） |

---

## 八、修订记录（显式，非静默覆盖）

| 版本 | 变更 |
|---|---|
| v1 | 初版。§3.2 以 `grep -c <id> mailbox.jsonl` 计数，将**验收信 ref 字段的具名引用**误计为「命中」，据此得出「先发漏箱、后发入箱」的对比结论。 |
| v1.1 | **自纠**：经复核确认投递信本体**一律不以自身 id 入 mailbox**，监督线处理方式是**在验收/裁定信 `ref` 中具名引用**。故 §一(2)、§3.2 改为 **id/ref/body 三字段分查**口径，并新增 §3.3 全投递线零痕迹清单。**核心结论未变且更强**：`cd-done-s309-ai-e1-e7` 在 mailbox 三字段**全零痕迹**，而同批 6 件兄弟信**均已被 ref 具名登记**。原 v1 措辞「命中各 1」为口径错误，此处如实更正，不掩饰。 |

---

| 版本 | 日期 | 作者 |
|---|---|---|
| v1 | 2026-10-21 | Claude 实施线（s335/s336 E 系重派 × Codex 交付撞车核验） |
| v1.1 | 2026-10-21 | Claude 实施线（自纠：mailbox 命中口径 id/ref/body 三字段分查 + 全投递线零痕迹清单） |
