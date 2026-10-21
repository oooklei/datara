# C-spec-01 A1 seed 独立深度核验 — 读链等价性 + F3 锚3 判据保真 + 脚本缺陷与潜伏风险

- **性质**：Claude 核验线对 s360（C-spec-01 A1 seed cl-done）做独立深度只读核验；s361 已裁 PASS 且 F3 已解锁，本件为**判据保真与潜伏风险备案**，不主张推翻 PASS
- **日期**：2026-10-22
- **触发**：s361 裁定后；监督线自身核验（s359【一】⑤）仅「实锚 185 行含 REBUILD_DB_URL/META_DB_URL 关键字」——**浅核**，故本线做深核
- **边界**：只读静态实证；**零业务代码改动**；`.git` 只读未 push；未调用 `aoci_*`；未触碰他线在飞件

---

## 一、结论（五条）

1. **读链等价性 PASS（强）**：seed 读侧条件与读链 `published_document()` **逐字等价**（非近似）——见 §二。这是 seed 最核心的正确性主张，**独立复核成立**。
2. **F3 锚3「ETag 随发布变更」结构性不可满足**（核心发现）：ETag = `sha256(body)`，而 rebuild 组件规格面**纯只读**（无 write/publish 路径），publish 链写 `datara_meta` 且**无 publish→rebuild_i0 通路** ⇒「随发布变更」当前架构下**无从发生**；s360 实证的是「随 rebuild_i0 内容变更」。见 §三。
3. **单行坏 `spec_json` 致全目录 500**：`_spec_item` 任一组件解析失败即整体 `ComponentSpecError` → HTTP 500（全目录不可用，非单件降级）；seed **全列复制无校验**，会原样传播坏行。见 §四。
4. **脚本自有输出仍印「预期 18/18/59」**（`:84` 注释 + `:169` verify 行），与 s361【二】**31 定案**矛盾——复跑输出自相矛盾。见 §五。
5. **三项潜伏风险**（当前未触发）：组件/版本拷贝条件未耦合（C2）、`_copy_row` 全列含 `id` 的 PK 覆盖（C3）、`t_component_log.action` 实际词形超出模型注释文档集（§六）。

---

## 二、读链等价性核验（PASS）

### 2.1 读链（`rebuild/component_spec/service.py:90-107`）

```python
select(Component, ComponentVersion)
  .join(ComponentVersion, and_(
      ComponentVersion.component_id == Component.id,
      ComponentVersion.version == Component.published_version,
      ComponentVersion.state == "published",
  ))
  .where(Component.state == "published")
  .order_by(Component.id)
```

### 2.2 seed 读侧（`scripts/seed_rebuild_component_catalog.py:92-107`）

```python
meta_session.query(ComponentVersion)
  .join(Component, and_(
      ComponentVersion.component_id == Component.id,
      ComponentVersion.version == Component.published_version,
  ))
  .filter(Component.id.in_(comp_ids),          # comp_ids = state=='published' 的组件
          ComponentVersion.state == "published")
```

**等价性论证**：seed 先取 `Component.state == "published"` 得 `comp_ids`，再以 `Component.id.in_(comp_ids)` + join `component_id==Component.id` 限定版本。读链以 `where(Component.state == "published")` + join 限定。两者限定集**同一**（都是「published 组件 × 其 published_version 的 published 版本行」），排序均按 id 升序。⇒ **逐字等价，非近似**。

### 2.3 其余 PASS 项

| 项 | 实证 | 判定 |
|---|---|---|
| dry-run 真只读 | `else` 分支 `rebuild_session.rollback()`（`:171`）；`add()` 未 flush；meta 侧纯 `query` | ✅ |
| 单事务 | 一次 `commit()`（`:164`），异常 `rollback()`（`:174`） | ✅ |
| 保留原 id | `_copy_row` 全列复制含 `id`（`:57-62`）；组件/版本显式携带 meta id（`:126`/`:137`）⇒ 维持 `component_version.component_id` 引用 | ✅ |
| 孤儿日志排除 | `ComponentLog.component_id.in_(comp_ids)`（`:110`）⇒ 与 s361【二】**31 定案**一致 | ✅ |
| ETag 机制在位 | `service.py:106` `sha256(body)`；`api.py:50-51` `If-None-Match` → 304 | ✅ |
| 唯一键假设 | `t_component.type` `unique=True`（`common/models.py:631`）；`t_component_version` `uk_comp_type_ver(type,version)`（`:683`）；`t_component_log` PK `id`（`:692`）——与 seed 的 `exist_c/exist_v/exist_l` 键**逐一吻合** | ✅ |
| 执行位 | `REBUILD_DB_URL` 缺失即 `return 2`（`:70-73`）；`META_DB_URL` 缺省回落 `common.config.get_settings().db_url`（`:44-50`） | ✅ |

---

## 三、F3 锚3 判据保真（核心发现）

### 3.1 事实链

| # | 事实 | 出处 |
|---|---|---|
| 1 | `etag = f'"{hashlib.sha256(body).hexdigest()}"'`——**ETag 是响应体的纯内容哈希** | `rebuild/component_spec/service.py:106` |
| 2 | rebuild 组件规格面**只有一个端点** `GET /spec`（`:29`），`service.py` 自述 "Published component specification **reader**" | `rebuild/component_spec/api.py:29`；`service.py:1` |
| 3 | 该域**无任何 write/publish 路径**（`rebuild/component_spec/` 仅 api/service/migrations/revisions 四件，无写入端点） | 目录实测 |
| 4 | publish 链写 `datara_meta`（旧平台），rebuild 读链读 `datara_rebuild_i0`——**两端点跨库** | s355【二】、s356【三】 |
| 5 | **不存在** `datara_meta → rebuild_i0` 组件数据同步机制；长期同步=**SYNC-01 候办/预研**（s359【三】派 Trae，tr-done-42 候收） | s356【三】、s359【三】 |

### 3.2 判定

⇒ **ETag 只能在 rebuild_i0 数据被变更时变化**。而「发布」（publish）写的是 `datara_meta`，**不触及 rebuild_i0** ⇒ **「ETag 随发布变更」在当前架构下无从发生**。

s360 实证的路径是：**seed 写入 rebuild_i0（内容变）→ ETag 变**。这是「**随 rebuild_i0 内容变更**」，与「随**发布**变更」**语义不同**。

### 3.3 对 s360 自述替代的评估（公平披露）

s360§一 锚3 原文已**如实自述**替代：

> 「锚3 ETag=29f9f0ec…，If-None-Match 复放 HTTP 304（缓存语义在位，**随发布变更锚以 ETag 机制在位+304 复放验证**）」

⇒ **替代披露属实，无隐瞒**。但**替代不成立**：

- 「ETag 机制在位」（ETag 头存在 + 304 复放）**不能推出**「发布致 ETag 变更」——前者是**机制存在性**，后者是**数据通路因果性**；
- 且如 §3.2，本架构下**该因果通路不存在**，故「随发布变更」非但未验证，**在 SYNC-01 落地前不可能验证**。

### 3.4 建议（不主张推翻 PASS）

F3 阻塞确已解除（items 非空 + 组件可取 + 机制在位），s361 的 PASS **结论可维持**；仅请**修正判据措辞**以免未来复验误判：

- 锚3 收口为「**ETag 随 rebuild_i0 内容变更**」（已由 seed 数据变更实证）；
- **明记**「随**发布**变更」依赖 SYNC-01 长期同步机制落地后**复验**，当前标注为**不可验证项**（受架构制约，非实施缺陷）。

---

## 四、单行坏 `spec_json` 致全目录 500

`service.py:34-38`：

```python
def _spec_item(component, version):
    try:
        spec = json.loads(version.spec_json)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ComponentSpecError(f"invalid published specification for {component.type}") from exc
```

`published_document()` 在**列表推导**中逐个调用 `_spec_item`（`:104`）⇒ **任一组件**解析失败即整体抛出 ⇒ `api.py:45-49` 捕获后返回 **HTTP 500**（`code 5001`）。

⇒ **一个坏行 → 整个组件目录不可用**（全有全无，非单件降级）。

**与 seed 的叠加风险**：seed 对 `t_component_version.spec_json` **全列复制、零校验**（`_copy_row` 不解释内容）⇒ meta 侧若存在坏 JSON，seed **原样传播**至 rebuild_i0，致 rebuild 目录**整体 500**。

**当前未触发**：s360 实测 `items_count=18` 全出 ⇒ 18 行 `spec_json` 均合法。

> **限定（自我收窄）**：`t_component_version.spec_json` 为 `LONGTEXT` **NOT NULL**（`common/models.py:672-674`，无 `nullable=True`）⇒ **NULL 路径被 schema 阻断**，触发条件收窄为**仅「非空但非法 JSON」**。
>
> **另注**：即便 meta 侧 18 行全合法，**未来 SYNC-01 增量同步**若写入坏行，同样触发本 500——故本项应随 SYNC-01 预研一并考虑（ fail-fast 隔离 vs 全有全无）。

---

## 五、脚本缺陷（C1）与潜伏风险（C2/C3）

### 5.1 C1 · 脚本自有输出仍印「预期 18/18/59」（与 s361 定案矛盾）

```
:84   # ---- 读侧：受控只读 datara_meta（预期 18/18/59） ----
:169  print(f"[verify] rebuild_i0 t_component={n_c} …（预期 18/18/59）")
```

s361【二】已定案 `t_component_log` = **31**（59 系票面拟稿估算偏差）。脚本**两处硬编码 59 未订正** ⇒ `--apply` 复跑输出自相矛盾：`[verify] … t_component_log=31（预期 18/18/59）`。

**建议**：订正为 `18/18/31`，或移除硬编码预期改为「读侧实计数」。属**无害但误导**的缺陷，修复成本一行。

### 5.2 C2 · 组件/版本拷贝条件未耦合（潜伏）

| 对象 | seed 拷贝条件 |
|---|---|
| `t_component` | `state == "published"`（**无条件**，只要 published 即拷） |
| `t_component_version` | `version == published_version AND state == "published"`（**条件**） |

⇒ 若二者**背离**（组件 `state=published` 但其 `published_version` 指向的行 `state != "published"`，或 `published_version IS NULL`），则 `t_component` 会出现**无匹配版本行的组件**；读链 **inner join 静默丢弃** ⇒ `items_count < t_component 计数` 且**无任何报错**。

**当前未触发**：s360 实测 18/18 自洽。**但 seed 自身不校验该不变量**——`[verify]` 只打印两侧计数，不打印「读链可产出 items 数」。

> **加剧因素**：`t_component_version.component_id` 与 `t_component_log.component_id` **均无 DB 级 `ForeignKey`**（`common/models.py:664`/`:693` 仅注释 "→ t_component.id"）⇒ 参照完整性**纯应用层保障**，无 DB 兜底；孤儿版本行**不会**报 FK 错，只会静默少 items。

**建议**：seed 增一行不变量断言——`len(components) == len(versions)` 且 `len(items) == len(components)`（后者可经 `published_document()` 同法算得），不等即 `abort`。

### 5.3 C3 · `_copy_row` 全列含 `id` 的 PK 覆盖（潜伏）

`_copy_row`（`:57-62`）遍历 `source.__dict__` 全列 `setattr`，**含 `id`**。`exist_c/exist_v` 按**业务键**匹配既有行后**整行覆盖（含 id）**。

⇒ 若 rebuild_i0 出现**非本脚本写入**的同 `type` 行（`id` 不同）→ `dst.id = src.id` → **主键冲突 `IntegrityError`**（当前**无该场景**：表空、脚本为唯一写者）。

> **当前不触发**：首发空表；复跑时 `id` 相同（幂等）。**但**：`--apply` 的「保留原 id」设计意味着**任何外部预置行都会被覆盖**——若未来 rebuild_i0 有其它数据来源，需先冲突检测。

### 5.4 C4 · `t_component_log.action` 实际词形超出模型注释文档集（文档漂移）

模型注释（`common/models.py:696-698`）文档化 6 个 action：`create / update_draft / freeze_version / publish / offline / rollback`。

s360 实测 action 分布含 **10** 个：`create16 / publish19 / update_draft1 / **reopen_draft5 / redraft4 / discard3 / delete16**` ⇒ **`reopen_draft` / `redraft` / `discard` / `delete` 四个词形未在模型注释文档集内**。

⇒ **契约文档漂移**（列本身为自由 `String(32)`，非枚举约束，故功能不受影响）。属治理工具**词形治理**面的好例子，建议随 §7.5/§7.4 类契约修订一并登记。

---

## 六、旁证采信（独立复核 s360【四】）

s360【四】称 validation-token「层1 capability 拒令」。独立复核 `api.py:21-27`：

```python
claims = token_service.verify(raw)
if claims.get("capability") is not None:
    raise ValueError("scoped capability is not valid for component specifications")
```

⇒ **capability token 对 `GET /spec` 被拒**，与 s360 实测层1 **吻合**，**旁证采信**。层2（`vt-exchange` HTTP 500 / `rebuild_active_token` FK 1452 `user_id=0`）属 DB-token-01/02 票面，本件不重复核。

---

## 七、红线自查

| 红线 | 状态 |
|---|---|
| `.git` 只读 | ✅ 仅 `grep`/`sed`/`awk`/`find`；未 `add`/`commit`/`push` |
| 禁 `aoci_*` | ✅ 零调用 |
| 禁 push | ✅ |
| 零业务代码改动 | ✅ 纯只读实证 + 文档 |
| 未触碰他线在飞件 | ✅ `seed_rebuild_component_catalog.py`/`rebuild/component_spec/*`/`common/models.py` **仅读**（属他线在飞交付件与四件原子单元邻接面，仅读不改） |
| 证据成对 | ✅ 本件 + 信件 `outbox/claude/cl-done-cspec01-a1-seed-deepverify.json` |
| 不静默覆盖失败证据 | ✅ 本件为新增 |
| 不摘他线票 | ✅ C-spec-01/A1 seed 归 Claude 实施线（s358/s360 已交付、s361 已裁 PASS）；本件仅**核验**，未认领该票 |
| 不推翻已裁结论 | ✅ §3.4 明示「不主张推翻 PASS」，仅请修正判据措辞 |

---

## 八、修订记录

| 版本 | 日期 | 作者 | 说明 |
|---|---|---|---|
| v1 | 2026-10-22 | Claude 核验线 | 首版（C-spec-01 A1 seed 独立深度核验：读链等价性 + F3 锚3 判据保真 + 脚本缺陷/潜伏风险） |
