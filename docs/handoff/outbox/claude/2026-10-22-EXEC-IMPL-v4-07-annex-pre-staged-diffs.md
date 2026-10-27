# IMPL-v4-07 · 附件：4 件授权外冻结基线的**预置 diff**（未落盘，候授权）

- **票据**：IMPL-v4-07｜**席**：Execution（claude / EXEC-2）
- **水位**：`v3-0054-lease-until-narrative-realignment`
- **状态**：⛔ **未应用**。以下 4 件不在票面 `paths` 内，本席**不擅自落盘**；候 Ops 裁定（A/B）后即时执行。
- **用途**：把「授权 → 落地」压到一步，避免裁定后重新取证。

---

## 文件 1 · `datara-newweb/src/router/__tests__/routes.contract.test.ts`

**位置**：L34-44（`routes 正式产品路由基线` 断言）

```diff
     expect(routes.map((r) => r.path)).toEqual([
       '/login',
       '/',
       '/dag',
       '/dep/ssh',
+      // 14.4 批 A（IMPL-v4-07）：质量规则 / 检查任务两页
+      '/qc/rule',
+      '/qc/task',
       '/sec/perm',
       '/p/:projectId',
       '/p/:projectId/:seg',
     ])
```

**同处建议**（可选，非必需）：新增一条具名绑定断言，与 `/sec/perm` 条同构：

```ts
  it('/qc/rule 与 /qc/task 绑定质量两视图且具名（IMPL-v4-07：14.4 批 A）', () => {
    const rule = routes.find((r) => r.path === '/qc/rule')
    const task = routes.find((r) => r.path === '/qc/task')
    expect(rule?.name).toBe('qc-rule')
    expect(task?.name).toBe('qc-task')
    expect(rule?.component).toBe(QualityRuleView)
    expect(task?.component).toBe(QualityTaskView)
  })
```

（需在该测试文件头部补 `import QualityRuleView from '../../views/qc/QualityRuleView.vue'` 与 `QualityTaskView` 同形。）

---

## 文件 2 · `datara-newweb/src/navigation/__tests__/menu.contract.test.ts`

**位置**：L98-115（E 组断言）

```diff
-  it('E 组 数据治理：8 formal 已实证路径 + 5 质量项 future（0.8 §3 L102-103 / §4 #3-#7）', () => {
+  it('E 组 数据治理：10 formal 已实证路径 + 3 质量项 future（0.8 §3 L102-103 / §4 #3-#7；IMPL-v4-07 将 qc-rule/qc-task 转 formal）', () => {
     const g = allGroups.find((x) => x.id === 'governance')!
     expect(g.label).toBe('数据治理')
     const formal = g.items.filter((i) => i.disposition === 'formal')
     const future = g.items.filter((i) => i.disposition === 'future')
     expect(formal.map((i) => i.path)).toEqual([
       '/meta/lineage',
       '/meta/map',
       '/meta/catalog',
       '/meta/tag',
       '/std/element',
       '/ind/list',
       '/ind/board',
       '/ind/consistency',
+      '/qc/rule',
+      '/qc/task',
     ])
-    expect(future.map((i) => i.id)).toEqual(['qc-rule', 'qc-task', 'qc-exception', 'qc-report', 'qc-alarm'])
+    expect(future.map((i) => i.id)).toEqual(['qc-exception', 'qc-report', 'qc-alarm'])
     for (const i of future) expect(i.batch).toBe('inc14')
   })
```

---

## 文件 3 · `datara-newweb/src/navigation/__tests__/menuAudit.contract.test.ts`

**无需改动**。该文件 L66-77 是**对拍逻辑**（`cfg.disposition === e.disposition`），它红是因为**台账源**（文件 4）未同步。文件 4 改后本件自动转绿。

> 修正监督报告 E-1 表格中的一项：本件属**对拍器**，非断言常量，**不需改写**。

---

## 文件 4 · `datara-newweb/src/navigation/menuAudit.ts`（**台账源**）

**位置**：L47-62（`no:3` / `no:4` 两条）

```diff
   {
     no: 3,
     legacyLabel: '质量规则',
     legacyPath: '/qc/rule',
-    disposition: 'future',
+    disposition: 'formal',
     target: 'E 数据治理组',
     targetItemId: 'qc-rule',
-    note: '去除演示标识；批次、路由、权限齐备才显示（0.8 L117）',
+    note: '去除演示标识；批次、路由、权限齐备才显示（0.8 L117）；IMPL-v4-07 转 formal（路由与契约已落位）',
   },
   {
     no: 4,
     legacyLabel: '检查任务',
     legacyPath: '/qc/task',
-    disposition: 'future',
+    disposition: 'formal',
     target: 'E 数据治理组',
     targetItemId: 'qc-task',
-    note: '同 #3 口径（0.8 L118）',
+    note: '同 #3 口径（0.8 L118）；IMPL-v4-07 转 formal',
   },
```

**连带核对项**：`AUDIT_COUNTS`（grouped/embedded/deleted 计数）若把 #3/#4 计入 `future` 分组，须同步；核对结论——`MENU_AUDIT_18` 的 `grouped` 过滤条件是 `disposition === 'formal' || disposition === 'future'`，**两者并集**，故 #3/#4 由 future 转 formal **不改变 grouped 计数**（仍为 10）。✅ `AUDIT_COUNTS` 无需改。

---

## 落地后动作

1. 复跑全量 `vitest run` → 预期 **0 failed**（当前 3 failed）。
2. 复跑 `npx vue-tsc -b` / `npx tsc --noEmit -p tsconfig.node.json` → 预期 EXIT 0。
3. 回报监督并提交 EVIDENCE_READY。

## 授权请求（重申）

- **A（建议）**：Task 修订票面 `paths`，追加上述 **3 件**（`routes.contract.test.ts` / `menu.contract.test.ts` / `menuAudit.ts`），注明「冻结基线同步」。
- **B**：Ops 直接授权一次性扩界（同上 3 件）。
- **C**：不改，基线 3 红遗留至 1.9 面（风险：验收 ⑥ 判 REWORK）。
