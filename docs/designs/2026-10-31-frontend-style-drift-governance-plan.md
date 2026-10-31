# 前端样式漂移治理方案（按钮体系 / 脚本开发页 / 令牌闭合）

- **日期**：2026-10-31
- **状态**：待批（只读审计结论 + 修复方案；未获用户明确指令前不实施）
- **权威序**：用户最新裁定 > `docs/designs/2026-10-29-dbx-unified-target-design.md` > 本方案 > 其余文档
- **审计性质**：review-only（实测事实与审美判断分离，证据均落到文件行号）
- **验证入口**：`http://192.168.1.9:18091/`（禁 8090；18090 被并行验证栈占用）

---

## §1 背景

用户在浅色主题下实测发现两类漂移并附截图：

1. **任务组管理页**：工具栏「新建任务组 / 刷新」与表格行「共享 / 编辑 / 关闭」按钮的边框、背景、字号明显不一致；
2. **脚本开发页（/resources）**：整体布局与其他页面不同、存在英文「Upload」残留、上传控件按钮框样式漂移。

结合上轮全站审计（20+ 视图静态审查 + browser_use 双主题验证），本文档将两批发现合并为一份分级治理方案。

---

## §2 实测问题清单

### §2.1 P0-A：按钮体系分裂（同屏三种按钮语言）

**根因**：`datara-newweb/src/styles/theme.css` 只定义了 `.op-btn`（L189-192）与 `.tb-new`（L193-195）两个按钮设计类，**不存在任何裸 `<button>` 全局基线**（L107 仅加 transition）。凡未挂类的 `<button>` 均按浏览器默认渲染：ButtonFace 灰底、outset 直角边框、13.3px 字号——与设计类（6px 圆角、11.5px 字号、token 边框）同屏冲突。

| # | 位置 | 代码形态 | 实际渲染 |
|---|------|----------|----------|
| A1 | ProjectTaskGroupView.vue L66-68 | 表格行「共享/编辑/关闭」裸 button | 浏览器默认（截图证据） |
| A2 | ProjectTaskGroupView.vue L98-99、L110-112 | 弹窗 footer「取消/保存」等裸 button | 浏览器默认 |
| A3 | SshNodeManagementView.vue L39 | 行内「探测/编辑/删除」裸 button | 同上 |
| A4 | ApiKeyManagementView.vue L21、ApiManagementView.vue L16 | 行内操作裸 button | 同上 |
| A5 | system/UserManagementView.vue L99 | 「停用/重置密码」裸 button | 同上 |
| A6 | qc/QualityRuleView.vue L57 | 行内操作裸 button | 同上 |
| A7 | depops/OrchestrationResourceView.vue L61 | 行内操作裸 button | 同上 |
| A8 | 附带散装规则：OrchestrationAlarmPanel.vue L260（`button{margin-right:8px}`）、WorkflowScheduleList.vue L104、WorkflowVariablePanel.vue L142 | 组件内自定义 button 规则 | 各自为政 |

**附带发现（版本差异疑点）**：截图中「新建任务组」为实心蓝底（`.tb-new` 视觉），而当前工作区代码为 `op-btn primary` = 白底描边蓝字（theme.css L191）。两者视觉契约不同，需核对 1.9 部署包与工作区的主题版本差异。

### §2.2 P0-B：脚本开发页整体脱离设计系统

页面：`/resources` → `views/resources/ResourceManagementView.vue`（菜单项「脚本开发」，navigation/menu.ts L163）。

| # | 问题 | 位置 |
|---|------|------|
| B1 | 英文「Upload」标签 | L6 |
| B2 | `aria-label="Upload resource type"` 英文 | L7 |
| B3 | 报错 `'Upload failed'` 英文 | L96 |
| B4 | 状态列硬编码英文 `active`（应为 `.pill ok` + 中文） | L16 |
| B5 | `.upload-control` 全库无 CSS 定义 → 原生 select + file input 完全裸奔（用户所见「按钮框漂移」） | L6-L9 |
| B6 | 布局自造：`.resource-page{padding:24px}` 裸值、裸 h1（无 `.sec-head` 强调条）、裸 table（th 无灰底、无行 hover）、自造 `.list-search`；不用全局 `.pg/.pg-head/.panel/.tbl/.toolbar` | L179 |
| B7 | 行内「修改/查看版本」裸 button | L16 |
| B8 | 版本弹窗自造 `.version-dialog`（全局已有 `.dlg` 体系）；遮罩用 `color-mix` 与他页 rgba 不一致 | L180、L179 |

### §2.3 P1：主按钮语义不统一（系统性）

- `.tb-new`（实心蓝底白字，theme.css L193）与 `.op-btn.primary`（描边蓝字，L191）并存，各页面随机选用；
- 违背 uiuxpromax `primary-action` 准则：每屏应只有一个实心主 CTA，次级操作描边降级；当前无此分层规则。

### §2.4 上轮审计遗留（与本方案同批实施）

| 级别 | 问题 | 位置 |
|------|------|------|
| P0 | 组件完全硬编码色值（不响应主题切换） | SyncMappingEditor.vue L148-160、WorkflowRunMonitor.vue L349-364、StreamObservationPanel.vue L293、ScriptResourceEditor.vue L325/327、DependencyNodeEditor.vue L243 |
| P1 | `var(--x, fallback)` fallback 漂移（旧主色 `#2563eb` vs 新 `#1668dc`） | Palette.vue L477-532、WorkflowGraphWorkbench.vue L1051-1190、NodeConfigPanel.vue L409-485、VariableReferenceInput.vue L93-99、SpecBlockPanel.vue L168-227、TabsView.vue L69/71 |
| P1 | 遮罩 rgba 不统一（4 处 3 种值） | VariableManagementDialog.vue L300、ScheduleDialog.vue L412、HomeView.vue L194、DetailDrawer.vue L59-64 |
| P2 | 零散硬编码 `#dce3eb`/`#15803d`/`#eee` 等 | OrchestrationAlarmPanel.vue L258、WorkflowScheduleList.vue L102、ResourceScriptEditorDialog.vue L588、ProjectTaskGroupView.vue L376（`.form-err` fallback `#d92d20` ≠ `--danger:#e5484d`）等 |

---

## §3 优化方案（分级任务）

### §3.1 P0-A：补全局按钮基线，回收裸按钮

1. **theme.css 新增 `.mini-btn` 兜底类**（表格/弹窗行内按钮专用），视觉对齐 `.op-btn`：
   `border:1px solid var(--border-strong); background:var(--card); border-radius:var(--radius-sm); font-size:11.5px; color:var(--text-2)`；hover/active/disabled 态与 `.op-btn` 一致。
2. **同时给 `.tbl .actions button` 挂同款选择器**——一处定义，A1–A7 七个页面自动收敛，无需逐页改模板。
3. 语义修饰：主操作加 `.primary`、危险操作加 `.op-btn.danger`（已存在，theme.css L307）；A8 的散装 button 规则统一清理。
4. 弹窗 footer 按钮（A2）统一 `.mini-btn`，主提交按钮用主按钮类（见 §3.3）。

### §3.2 P0-B：脚本开发页对齐改造

1. **文案中文化**：「Upload」→「上传资源」（含 aria-label）；「Upload failed」→「上传失败」；`active` → `.pill ok` 渲染「启用」；表头「大小」标注单位（如 `大小(Byte)` 或格式化 KB/MB）。
2. **上传控件重做**：参照 OrchestrationResourceFileView.vue L17 的「`.op-btn` 按钮 + hidden file input」模式，消灭原生 file input 裸奔。
3. **结构迁移**：`.resource-page` → `.pg` + `.pg-head/.sec-head`；裸 table → `.tbl`；搜索框并入 `.tbl-toolbar`；行内按钮 → `.op-btn`；`.version-dialog` → 全局 `.dlg`；遮罩统一 `--mask-bg`。
4. 契约测试同步：`resourceManagementView.contract.test.ts` 中涉及文案/结构的选择器按改造结果更新（仅测试断言，不动契约面）。

### §3.3 P1：主按钮收敛 + 遮罩统一

1. **定规则**：每屏唯一主 CTA = 实心（建议将 `.op-btn.primary` 升级为实心、视觉对齐 `.tb-new`，一处改动全局生效；`.tb-new` 保留为工具栏「新建」快捷别名或逐步合并）；次级 = `.op-btn` 描边；危险 = `.op-btn.danger`。
2. **theme.css 新增 `--mask-bg`**（建议 `rgba(15,23,42,.45)`，深色主题另给值），替换 §2.4 所列 4 处遮罩 + ResourceManagementView 的 `color-mix`。
3. **版本差异核对**：比对 192.168.1.9:18091 部署包的 theme.css 与工作区（截图实心 vs 代码描边），确认部署线构建来源后统一。

### §3.4 P1/P2：令牌闭合收尾（上轮遗留）

1. P0 五组件硬编码色值全部替换为 CSS 变量（`--card/--border/--text-2/--primary/--danger/--success/--warn` 等）；
2. P1 六组件 fallback 值统一到新版令牌（删除旧主色 fallback 或改为正确值）；
3. P2 零散硬编码清理（含 ProjectTaskGroupView.vue L376 `.form-err` fallback 对齐 `--danger`）。

---

## §4 验证口径

| 层 | 手段 | 通过标准 |
|----|------|----------|
| 静态 | `cd datara-newweb && npx vue-tsc --noEmit` | 无类型错误 |
| 契约 | `npx vitest run src/views/__tests__/designTokenClosure.contract.test.ts`、`src/styles/__tests__/themeResponsive.contract.test.ts` 及受影响页面的 contract 测试 | 全绿 |
| 视觉 | 18091 部署入口 + browser_use 逐页复验（任务组管理、SSH 节点、API、APIKey、用户管理、质检规则、编排资源、/resources） | 同屏按钮仅两种形态（实心主 CTA + 描边次级）；无英文残留；浅色/深色双主题一致 |
| 回归 | 上轮 PASS 页面抽查（/、/dag、/dep/*） | 不因新基线类产生新漂移 |

---

## §5 实施边界

- 本方案为**文档交付**；代码修复需用户明确指令（或按 AGENTS.md 流程派单）后执行；
- 工作量估算：P0-A ≈ 2h、P0-B ≈ 1.5h、P1 ≈ 1h、P1/P2 收尾 ≈ 1.5h；
- 实施顺序：§3.1 → §3.2 → §3.3 → §3.4，每级完成后过一次 §4 验证再进入下一级；
- 所有改动限于 `datara-newweb/src`（theme.css + 上述页面/组件 + 对应契约测试），不触碰路由契约与后端接口。
