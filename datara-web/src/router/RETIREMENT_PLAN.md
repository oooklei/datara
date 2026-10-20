# FE-03 验证页路由退役方案设计

> 任务：c28-fe-xcut ｜ FE-03（X 横切）｜ 前置：六批融合全部完成（未满足，方案先行）
> 依据：WBS `docs/increments/2026-10-19-WBS-前端融合任务分解.md` FE-03 行；设计 §10 融合规则；预研 §3.2 改造点 1
> 实锚：`datara-web/src/router/routes.ts` L97-107（10 条 `/rebuild/validation/*` 路由）

---

## 一、退役策略

**策略选择：保留路由记录 + 验收深链跳转（Retired-Validation DeepLink）**

不直接删除 10 条 `/rebuild/validation/*` 路由记录，而是：

1. **路由记录保留**在 `routes.ts`，追加 `meta.retired: true` + `meta.deeplink`（正式页深链）；
2. **组件替换**为轻量 `RetiredValidationRedirect.vue`（`src/views/rebuild/validation/` 下统一壳页），`onMounted` 时 `router.replace(meta.deeplink)`，同时渲染「该验证页已退役」提示与跳转中状态；
3. **验证页组件目录**（`src/views/rebuild/validation/<10 个子目录>`）随第 6 批后清理评估（WBS FE-03 工作内容 3）——退役执行阶段再删组件文件，本方案阶段仅冻结映射。

**选型理由**：
- 满足 WBS 验收标准「验证页路由 404 或重定向深链可达」——保留路由 + 重定向深链可达；
- 保留书签/历史链接可达性（直接删路由会 404 或落兜底 Placeholder，体验断裂）；
- 与现有深链模式一致（`/dag/design/:id` → redirect `/dag` + query 先例，routes.ts L14）；
- CI 回归可逐条断言「路由可达 + 跳转正确」。

## 二、10 条路由深链映射表

| # | 验证页路由 | name | 融合来源 | 正式页深链（meta.deeplink） | 批次 |
|---|---|---|---|---|---|
| 1 | `/rebuild/validation/sql-ide-readonly` | rebuild-sql-ide-readonly | R5-A SQL IDE 只读 | `/ide` | B2（FE-07） |
| 2 | `/rebuild/validation/sql-ide-ddl` | rebuild-sql-ide-ddl | R5-B SQL IDE DDL | `/ide` | B2（FE-07） |
| 3 | `/rebuild/validation/schedule` | rebuild-schedule-validation | R6 调度运行时 | `/dag/instances` | B3（FE-08） |
| 4 | `/rebuild/validation/stream` | rebuild-stream-validation | R8 流处理观摩 | `/stream/list` | B5（FE-10） |
| 5 | `/rebuild/validation/metrics` | rebuild-metrics-validation | R7 统计质量血缘 | `/ind/board` | B6（FE-12） |
| 6 | `/rebuild/validation/sync-form` | rebuild-sync-form-validation | R4 同步组件表单 | `/sync/list` | B4（FE-09） |
| 7 | `/rebuild/validation/dependency-form` | rebuild-dependency-form-validation | R4 依赖表单 | `/dag?tab=edit` | B1（FE-06） |
| 8 | `/rebuild/validation/resource-upload` | rebuild-resource-upload-validation | R4 资源上传 | `/ds/list` | FE-21 |
| 9 | `/rebuild/validation/variable` | rebuild-variable-validation | R2 统一变量 | `/dag?tab=edit` | B1（FE-05） |
| 10 | `/rebuild/validation/ai-assistant` | rebuild-ai-assistant-validation | R8-B AI 悬浮助手 | `/` | B6（FE-11） |

**映射依据**：WBS 各批次的融合目标页（FE-05→/dag 变量页签、FE-06→/dag 编排依赖页签、FE-07→/ide、FE-08→/dag/instances、FE-09→/sync、FE-10→/stream、FE-11→顶栏 AI、FE-12→/ind）。

## 三、深链跳转组件设计

**组件路径**：`src/views/rebuild/validation/RetiredValidationRedirect.vue`（退役后统一壳页）

**行为**：
1. `onMounted` 读取 `route.meta.deeplink`；
2. `router.replace(deeplink)`（replace 避免回退到退役页）；
3. 渲染过渡态：「该验证页已融合退役，正在跳转至正式页面…」+ 深链目标展示；
4. 若 `meta.deeplink` 缺失，兜底 `router.replace('/')`。

**路由记录改写示例**（退役执行阶段）：

```ts
// 退役前（现状）
{ path: '/rebuild/validation/variable', name: 'rebuild-variable-validation',
  component: () => import('../views/rebuild/validation/variable/VariableValidationView.vue'),
  meta: { title: '统一变量验证（R2）' } },

// 退役后
{ path: '/rebuild/validation/variable', name: 'rebuild-variable-validation',
  component: () => import('../views/rebuild/validation/RetiredValidationRedirect.vue'),
  meta: { title: '统一变量验证（R2）', retired: true, deeplink: '/dag?tab=edit' } },
```

## 四、深链回归机制说明

### 4.1 回归层（vitest，CI 可跑）

**测试文件**：`src/router/__tests__/rebuild-validation-retirement.test.ts`

**断言矩阵**（退役执行阶段激活）：
1. 10 条路由记录仍在 `routes` 中（未删除）；
2. 每条 `meta.retired === true`；
3. 每条 `meta.deeplink` 指向的正式页路由在 `routes` 中存在（深链目标可达）；
4. 深链映射表与 §二 表一一对应（防漂移）；
5. 组件统一指向 `RetiredValidationRedirect.vue`（不再指向 10 个旧验证页组件）；
6. `npm run build` 无悬空 import（旧验证页组件删除后无残留引用）。

### 4.2 深链目标可达性预检（退役前即可跑）

**测试文件**：`src/router/__tests__/rebuild-validation-retirement.test.ts`（前置断言，当前即可跑）

当前即可断言：§二 表中 10 条 `meta.deeplink` 指向的正式页路由**当前已存在**于 `routes.ts`（`/ide`、`/dag/instances`、`/stream/list`、`/ind/board`、`/sync/list`、`/dag`、`/ds/list`、`/` 均已注册）。这保证退役执行时深链目标不会悬空。

### 4.3 Playwright 端到端（退役执行阶段）

**测试文件**：`e2e/rebuild-validation-retirement.spec.ts`

逐条 10 路由：
1. `page.goto('/rebuild/validation/<x>')` → 断言 URL 最终落在 `meta.deeplink`；
2. 断言无 404 白屏（兜底 Placeholder 不出现）；
3. 断言正式页关键元素渲染（如 `/ide` 的编辑器容器）。

## 五、验收标准对照（WBS FE-03）

| WBS 验收标准 | 本方案覆盖 |
|---|---|
| 验证页路由 404 或重定向深链可达（Playwright 逐条 10 路由核验） | §4.3 Playwright 逐条 + §4.2 前置断言 |
| `npm run build` 无悬空引用 | §4.1 断言 6 |
| 深链回归机制说明登记 | 本文档 §四 |

## 六、执行边界

- 本方案仅设计，**退役执行待六批收口**（前置未满足）；
- 退役执行时需同步：① 改 routes.ts 10 条记录；② 新建 `RetiredValidationRedirect.vue`；③ 删除/归档 10 个验证页组件目录；④ 更新 `rebuild-validation.test.ts` 断言；
- 文件域：`datara-web/src/router/`（本方案 + 测试）、`datara-web/src/views/rebuild/validation/`（退役执行阶段组件替换）。

---

*产出：Claude 实施线 c28-fe-xcut；日期：2026-10-19；状态=方案冻结，待六批收口执行。*
