# FE-04 扩展（演示）组 demo 标识摘除清单

> 任务：c28-fe-xcut ｜ FE-04（X 横切）｜ 前置：随第 4/5/6 批触发
> 依据：WBS `docs/increments/2026-10-19-WBS-前端融合任务分解.md` FE-04 行；预研 §3.2 改造点 7；设计 §10 豁免注记 D-1
> 实锚：`datara-web/src/router/routes.ts`（meta.demo 路由 L44-46/58-93/111-115）；`datara-web/src/App.vue` L96-115（扩展（演示）组菜单）

---

## 一、摘除范围分析

WBS FE-04 前置依赖：第 4 批（SYNC 域项）、第 5 批（流域项）、第 6 批（统计/血缘域项）各触发对应摘除。

**逐域实锚核验**（2026-10-19 实盘）：

| 批次 | 域 | 对应路由 | 当前 demo 标识状态 | 摘除动作 |
|---|---|---|---|---|
| 第 4 批 | SYNC | `/sync/list`、`/sync/detail/:id` | **无 demo: true**（routes.ts L40-41，真实通道已成立） | 无需摘除（已真实） |
| 第 5 批 | STREAM | `/stream/list`、`/stream/detail/:id` | **有 demo: true**（routes.ts L45-46） | **摘除 meta.demo** |
| 第 6 批 | 统计/血缘 | `/meta/lineage`、`/ind/*` | **无 demo: true**（routes.ts L21/90/94-95，真实通道已成立） | 无需摘除（已真实） |

**菜单面核验**：App.vue 扩展（演示）组（L96-115）19 个菜单项中：
- 第 4/5/6 批域对应菜单项（同步任务 L75、血缘分析 L82、指标目录 L87、指标看板 L88、一致性检查 L89）**均已在真实组**，不在扩展（演示）组；
- 扩展（演示）组中的项（脚本/参数/质量/开放接口/标准/安全/部署中心/组件日志/告警管理/运维操作）**不属第 4/5/6 批融合域**，不在 FE-04 摘除范围。

**结论**：FE-04 当前实际摘除清单 = **2 条路由**（第 5 批 STREAM 域）。

## 二、摘除清单（路线 ↔ 域 ↔ 批次）

| # | 路线 | 域 | 批次 | 文件 | 状态 | 核验 |
|---|---|---|---|---|---|---|
| 1 | `/stream/list` | STREAM | 5（FE-10 触发） | `src/views/stream/StreamListView.vue` | pending | `node scripts/verify-demo-removal.mjs` |
| 2 | `/stream/detail/:id` | STREAM | 5（FE-10 触发） | `src/views/stream/StreamDetailView.vue` | pending | 同上 |

**已确认无需摘除**（登记备查）：

| 路线 | 域 | 批次 | 原因 |
|---|---|---|---|
| `/sync/list`、`/sync/detail/:id` | SYNC | 4 | 真实通道已成立，无 demo 标识 |
| `/meta/lineage`、`/ind/list`、`/ind/board`、`/ind/consistency` | 统计/血缘 | 6 | 真实通道已成立，无 demo 标识 |

## 三、摘除执行规范（待批次触发）

每摘除一项，执行以下步骤：

1. **routes.ts**：删除对应路由行的 `demo: true`（保留路由记录与 component）；
2. **App.vue 菜单**：若该路由在扩展（演示）组菜单中，移入对应真实组（当前 2 条 STREAM 路由不在扩展（演示）组菜单中，无需菜单调整）；
3. **隔离确认**：确认页面组件无 `services/mock/seed.ts` 引用（FE-01 注意点①隔离确认）；
4. **真实通道可达**：Playwright 验证对应路由端到端走真实通道；
5. **build + grep 双向核验**：`node scripts/verify-demo-removal.mjs --build`。

## 四、核验脚本

**路径**：`datara-web/scripts/verify-demo-removal.mjs`

**双向核验**：
1. **源码核验**：routes.ts / App.vue 中无残留 demo 标识；
2. **引用核验**：页面组件无 `services/mock/seed.ts` 误引用；
3. **build 核验**（`--build` 启用）：`npm run build` 无悬空引用。

**当前状态**：2 条登记项均为 `pending`（批次 5 未执行），脚本 SKIP 为预期行为。批次 5 摘除后将 status 改为 `done`，脚本即执行实际核验。

## 五、验收标准对照（WBS FE-04）

| WBS 验收标准 | 本清单覆盖 |
|---|---|
| 每批摘除后对应路由 Playwright 真实通道可达 | 待批次触发（§三 步骤 4） |
| build + grep 双向核验无 seed.ts 误引用 | §四 核验脚本 |
| 摘除清单登记（路线 ↔ 域 ↔ 批次） | §二 摘除清单 |

## 六、执行边界

- 本清单仅登记，**摘除执行待对应批次**（第 5 批 STREAM 域，前置 R8-STREAM 新域建模交付）；
- 文件域：`datara-web/src/router/routes.ts`（摘 meta.demo）、`datara-web/src/views/`（本清单 + 组件隔离确认）。

---

*产出：Claude 实施线 c28-fe-xcut；日期：2026-10-19；状态=清单冻结，待第 5 批触发执行。*
