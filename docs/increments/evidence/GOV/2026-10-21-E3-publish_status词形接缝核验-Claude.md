# E3 `get_workflow.publish_status` 词形接缝核验（契约冻结 2 值 vs 工作流域枚举 5 值）

- **性质**：Claude 实施线对 s345【三】④「E3 publish_status 词形保真确认（输出超 DRAFT/PUBLISHED 冻结词形即修透传或按 N-A 联动裁词形，处置先报备后动工）」做独立只读核验
- **日期**：2026-10-21
- **触发**：`s345-gov-c-ruling-e34-auth-20261021`【三】E3/E4 裁 B 补课清单第 ④ 项
- **边界**：只读静态实证；**零业务代码改动**；`.git` 只读未 push；未调用 `aoci_*`；未触碰他线在飞件

---

## 一、结论（四条）

1. **s345④ 的前提「或按 N-A 联动裁词形」已不成立**：N-A 发布流词形**已裁定并闭合**——`DRAFT | PUBLISHED`，**三源一致**（见 §二）。故修复只剩「修透传」一路，无「随 N-A 再裁」余地。
2. **词形接缝真实存在**：契约冻结 **2 值**，而工作流域 §3.1 设计 + 实现枚举为 **5 值**（`DRAFT/PUBLISHED/RUNNING/DISABLED/ARCHIVED`），E3 实现是**裸透传**（见 §三/§四）。
3. **当前潜伏，但按域设计必然触发**：全库无任何代码写入 `RUNNING/DISABLED/ARCHIVED`（`VALID_VERSION_STATUSES` 定义后**零使用**）；但工作流域 §3.1/C20 设计明列五态与 `publish_record.action = PUBLISH/OFFLINE/DISABLE/ARCHIVE`（见 §五）。
4. **前端今日无消费方**：`datara-newweb/src/` 全域 `publish_status` 零出现 ⇒ 无当日 FE 破损，风险集中于 **AI 八工具契约面**（§7.4 + Codex 验收断言）。

---

## 二、契约侧：冻结词形 `DRAFT | PUBLISHED`（三源一致）

| 源 | 原文 | 位置 |
|---|---|---|
| R8-A 契约 §7.4 | `publish_status: 'DRAFT'\|'PUBLISHED'`（**N-A 联动**） | `docs/increments/archive/2026-10-20/2026-10-17-R8-A八工具契约.md:193` |
| R8-A 契约 §7.5 联动条款 | 「词形与 N-A 发布流契约同批裁定，若 N-A 裁定变化则本字段随批调整（再冻结范围仅此字段）」 | 同上 `:197` |
| **N-A 裁定（权威）** | 「### 3.1 N-A（P1）工作流发布流 — 裁定：纳入 R4 冻结面，词形冻结 / **状态词形**：`publish_status: 'DRAFT' \| 'PUBLISHED'`（与 R8-A 契约 `get_workflow.publish_status` 一致，联动闭合）」 | `docs/increments/archive/2026-10-20/2026-10-17-P1契约冻结宣言.md:35-37` |
| 同上（闭合声明） | 「`get_workflow.publish_status` 词形随 N-A 同批定稿（本宣言 §3 已定 `DRAFT\|PUBLISHED`，联动闭合）」；「N-A/N-C 联动字段已随本宣言闭合，R8-A 契约 §8 注记中的开放条件解除」 | 同上 `:31`、`:102` |
| Codex 验收断言 | 「DRAFT/PUBLISHED、node/edge count、updated_at、latest_run 可选」+「**publish_status 必须与 N-A 冻结词形一致**」 | `docs/increments/evidence/R8/2026-10-17-Codex-P1-3-acceptance-assertions.md:31` |

⇒ **冻结词形 = `DRAFT | PUBLISHED`（2 值），且 N-A 联动条款已闭合，无「再裁」余地。**

---

## 三、域侧：工作流域 §3.1 枚举 5 值

`docs/increments/2026-10-20-增量0-0.5-六模型核对表.md:45`（在版，非归档）：

```
| status | String(16) | NOT NULL, default "PUBLISHED" | DRAFT / PUBLISHED / RUNNING / DISABLED / ARCHIVED |
```

`rebuild/workflow/repository.py:65`：

```python
VALID_VERSION_STATUSES = ("DRAFT", "PUBLISHED", "RUNNING", "DISABLED", "ARCHIVED")
```

`rebuild/workflow/models.py:13-14` 与 `:59` 同列五态（`status: Mapped[str] = mapped_column(String(16), nullable=False, default="PUBLISHED")`）。

归档设计草案（C20，`docs/handoff/archive/mailbox-2026-10-20-compact.jsonl:295`）进一步定义 `workflow_publish_record.action = PUBLISH / OFFLINE / DISABLE / ARCHIVE` —— 即**发布记录已设计 OFFLINE/DISABLE/ARCHIVE 三类动作**，对应版本态必然出现 `DISABLED` / `ARCHIVED`。

⇒ **域枚举 5 值 ⊋ 契约冻结 2 值**，超集部分 = `RUNNING` / `DISABLED` / `ARCHIVED`。

---

## 四、E3 实现：裸透传，无词形校验

`datara-backend/rebuild/ai_tools.py:295`（worktree 现态）：

```python
"publish_status": version_record.status if version_record else "DRAFT",
```

- 直取 `WorkflowVersionRecord.status` **原值**；
- 无白名单、无映射、无校验；
- 兜底分支硬编码 `"DRAFT"`（属冻结词形）。

⇒ **E3 是「域 5 态 → 契约 2 词形」的漏斗，且漏斗无任何过滤。**

---

## 五、可达性：当前潜伏，按设计必然触发

### 5.1 当前不可达（实测）

```
$ grep -rn "RUNNING\|DISABLED\|ARCHIVED" datara-backend/rebuild/workflow/*.py
models.py:13-14, :59          （仅 docstring / 注释）
repository.py:65              （仅 VALID_VERSION_STATUSES 定义）
```

`VALID_VERSION_STATUSES` **定义后零引用**（全库唯一出现即其定义行）。版本态的实际写入/读取仅：

- `repository.py:305  status="PUBLISHED"`（`publish()` 建 PUBLISHED 行）
- `models.py:60       default="PUBLISHED"`
- `repository.py:435  if row.status != "DRAFT":`（读判）

⇒ 现存版本行状态**只可能是 `DRAFT` 或 `PUBLISHED`** ⇒ E3 当前**不会**输出非冻结词形。**潜伏，非当日破损。**

### 5.2 按设计必然触发

- 工作流域 §3.1 五态为**在版设计**（§三）；
- C20 设计草案已为 `publish_record.action` 定义 `OFFLINE/DISABLE/ARCHIVE` 三类动作（§三）；
- `ai_tools.py:295` 无过滤（§四）。

⇒ **域一旦实现 DISABLED/ARCHIVED 写入，E3 立即输出非冻结词形**，违反 §7.4 + Codex 验收断言。触发条件明确、无二次巧合。

---

## 六、对 s345④ 的前提更正

s345【三】④ 原文给的两条出路：

> 「输出超 DRAFT/PUBLISHED 冻结词形即修透传**或按 N-A 联动裁词形**，处置先报备后动工」

**更正**：N-A 词形**已裁定并闭合**（§二，三源一致），「按 N-A 联动裁词形」**已无对象**——联动条款本身已声明开放条件解除。故出路收敛为**单一路径：修透传（或域侧收窄）**。

---

## 七、修复方向（供补课清单④定案，非本线动作）

| 选项 | 动作 | 评价 |
|---|---|---|
| **A1（推荐）** | **域侧收窄**：`workflow_version.status` 仅承载 `DRAFT`/`PUBLISHED`；`RUNNING`/`DISABLED`/`ARCHIVED` 移入独立生命周期字段（如 `lifecycle_state`），`publish_record.action` 四值保留为审计语义 | **从源头消除超集**；E3 透传天然保真；契约与域各得其所 |
| A2 | **E3 侧映射**：透传前将 5 态映射到冻结 2 词形（如 `RUNNING/DISABLED/ARCHIVED → ?`） | 信息有损、映射任意（3→2 不可逆），需新增契约语义，**不推荐** |
| A3 | **E3 侧收窄**：非 `DRAFT/PUBLISHED` 版本不予 `get_workflow` 可取（返回 NOT_FOUND 或另立字段） | 可行但改变可取语义，需与 §7.4 返回契约同批修订 |
| — | ~~按 N-A 联动裁词形~~ | **不可用**：N-A 已闭合（§二/§六） |

**建议**：补课清单④ 优先核 **A1 是否已在工作流域在版设计/在飞票中排产**；若未排产，则 ④ 的最小安全实现为 **A3**（E3 侧收窄 + 明确非冻结态的可取语义），并**同步报备**使 §7.4 返回契约与实现一致。

---

## 八、红线自查

| 红线 | 状态 |
|---|---|
| `.git` 只读 | ✅ 仅 `grep`/`sed`；未 `add`/`commit`/`push` |
| 禁 `aoci_*` | ✅ 零调用 |
| 禁 push | ✅ |
| 零业务代码改动 | ✅ 纯只读实证 + 文档 |
| 未触碰他线在飞件 | ✅ `ai_tools.py`/`workflow/models.py`/`repository.py` **仅读**（属四件原子单元红线件，本线仅读不改） |
| 证据成对 | ✅ 本件 + 信件 `outbox/claude/cl-done-e3-publish-status-verify.json` |
| 不静默覆盖失败证据 | ✅ 本件为新增 |
| 不摘他线票 | ✅ 仅核验补课清单④，未认领 E3/E4 补课票本体 |

---

| 版本 | 日期 | 作者 |
|---|---|---|
| v1 | 2026-10-21 | Claude 实施线（s345④ E3 publish_status 词形接缝独立核验） |
