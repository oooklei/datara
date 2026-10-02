# 组件页面设计器（设计态 + 测试运行态）设计文档

- 日期：2026-10-03
- 状态：待审定
- 方案：A（新建页面设计器内核，复用 DAG 工作台布局骨架，页面组件注册进现有组件治理链）
- 关联：M1 B4 组件声明编辑器（`ComponentDesignView.vue`，保留不废弃）、治理设计 §12/§18.2

---

## 1. 背景与根因

此前实现的 `/meta/components/design/:type?` 是治理文档定义的「组件**声明**编辑器」（编辑 spec 的端口/表单字段/dropPolicy），并非用户要求的低代码**页面**设计器。且原始需求中 aoci 索引、模板系统、样式自定义、三页整合从未进入任何设计文档——这是上次"没细化、没按要求完成"的根因。本次以本文档为唯一验收基准。

## 2. 目标与非目标

**目标（P1）**
1. 三区域布局页面设计器：左组件库 Palette / 中可拖宽高画布（默认 GraphWorkbench Inspector 视口规格，居中、阴影）/ 右属性面板。
2. 设计态数据源绑定：系统全部资源（设计态元数据 + 运行态变量），适配性下拉优先、手动输入兜底，placeholder 即默认值。
3. 测试（运行态）预览：真实数据抽样 ≤100 条，所见即所得验证布局与绑定。
4. 发布即刷新引用：发布后服务端自动批量升级所有引用图的 componentRef 版本。
5. 编辑工具条（含**刷新**）：撤销/重做/复制/删除/对齐/缩放/保存/预览/发布/刷新，图标规格与 DAG 工作台一致。
6. 模板系统：每个可拖拽组件带初始化模板；新建组件页提供页面级模板。
7. 样式系统：现代高级感设计令牌；支持自定义插图/背景图/背景填充/色彩/圆角/边框/阴影。
8. aoci 索引：Datara 仓库初始化 AOCI，组件设计器全部代码与组件生命周期操作纳入索引管理。

**目标（P2）**
9. 组件目录 + 基线化工作台 + 页面设计器（+ M1 声明编辑器）整合为单一入口页，参照 DAG 工作流整合方式。
10. 补齐 DAG 工作台遗漏的「刷新」按钮（当年已要求、实现遗漏）。

**非目标**
- 不做节点连线的流程编排（页面设计器无边概念）。
- 不引入第三方低代码引擎（tmagic/lowcode-engine 等）。
- 不做多人协同编辑。
- 不改变既有 M1 声明编辑器的治理语义。

## 3. 总体架构

```
datara-web/src/views/meta/pageDesigner/
  PageDesignerView.vue        # 三区域布局壳（面板拖宽逻辑复用 GraphWorkbench 模式）
  palette/PagePalette.vue     # 左：页面组件库（分组/搜索/模板拖出）
  canvas/PageCanvas.vue       # 中：绝对定位画布（居中视口卡片、阴影、宽高拖拽、缩放）
  canvas/WidgetRenderer.vue   # 画布 widget 递归渲染（设计态骨架 + 运行态真实数据）
  inspector/PageInspector.vue # 右：属性面板（布局/样式/数据绑定 三段）
  designerModel.ts            # PageDSL 类型 + 归一化 + 校验（纯数据红线镜像）
  bindingCatalog.ts           # 资源目录加载 + 适配性候选推导 + placeholder 默认值
  templates.ts                # 每个 widget 的初始化模板 + 页面级模板
datara-backend/api/page_designer.py   # 资源目录 / 预览 / 页面组件草稿扩展
```

- **治理链复用**：页面组件注册进 `t_component`，`execution_model` 新增第 5 值 **`page`**（`executable=false`，闸门走页面分支）；草稿/冻结/发布/下线/回滚端点复用 `component_design.py`，新增页面 DSL 校验分支与 `refresh-refs` 端点。
- **spec 载体**：`t_component_version.spec_json` 内新增 `page` 根节点：`{ canvas, widgets[], name/icon/color }`；`validateSpecPureData` 扩展 page 分支（红线 2 镜像：仅声明式绑定，禁止脚本/表达式白名单外内容）。
- **画布内核**：不用 VueFlow；绝对定位 + 拖拽移动/缩放手柄，配置数据即 PageDSL，渲染层 `WidgetRenderer` 设计态与预览态共用（单一渲染链，避免双实现漂移）。

## 4. PageDSL 数据模型

```ts
interface PageDSL {
  version: 1
  name: string; icon: string; color: string
  canvas: {
    width: number   // 默认 288（=GraphWorkbench Inspector 默认宽）
    height: number  // 默认 520
    background: BackgroundStyle
  }
  widgets: WidgetNode[]
}
interface WidgetNode {
  id: string; kind: WidgetKind
  rect: { x: number; y: number; w: number; h: number }
  props: Record<string, unknown>          // 模板给默认值
  style: ComponentStyle                   // 4.1 样式系统
  bindings: Record<string, BindingRef>    // 槽名 → 绑定（如 table.data / text.value）
  children?: WidgetNode[]                 // 容器类
}
interface BindingRef {
  kind: 'metadata' | 'variable' | 'query' | 'static'
  path?: string        // metadata: ds/db/table.field；variable: wf 变量/系统变量路径
  query?: string       // query: 只读 SELECT（预览与运行均 LIMIT 100）
  fallback: string     // 手动输入兜底值 = placeholder，缺省必填
}
```

**画布默认尺寸**：宽 288 / 高 520，居中、阴影卡片区隔左右面板；宽拖拽 140–520（同 DAG 面板约束）、高拖拽 320–1200；交互与 DAG 一致（拖拽实时更新 + 持久化 `datara.pd.canvas`）。

## 5. 左侧 Palette：页面组件库（业内低代码常用组件）

| 分组 | 组件（每个均带初始化模板） |
|---|---|
| 布局容器 | 栅格行、卡片、标签页、折叠面板、分隔线、间距 |
| 基础元素 | 文本、标题、富文本、图片/插图、图标、按钮、徽标、链接 |
| 表单输入 | 输入框、数字、选择器、日期、日期范围、开关、滑块、单选、复选、级联、文本域、上传 |
| 数据展示 | 表格、列表、描述列表、统计数值、进度条、时间线、树 |
| 图表 | 柱状图、折线图、饼图、面积图、仪表盘、散点图 |
| 绑定元素 | 元数据字段标签、变量标签、查询结果集、系统状态徽标 |

交互：分组置顶/搜索/拖入画布（同 DAG Palette 手感）；拖入即套用该组件初始化模板（props/style 给可用默认值）。

## 6. 右侧属性面板与数据源绑定

- 面板三段：**布局**（位置尺寸/对齐/层级）、**样式**（见 §7）、**数据绑定**（按 widget kind 声明 bindable 槽位，无槽位的纯装饰组件只显示布局+样式）。
- **适配性选择**：绑定槽按类型给候选下拉——
  - 数据集槽（表格/列表/图表/查询结果集）→ 候选：数据源→库→表/视图、已保存查询；
  - 标量槽（文本值/统计数值/图片 URL/状态徽标）→ 候选：元数据字段、工作流变量、系统变量、时间参数。
- **手动输入兜底**：候选无法覆盖时切手动输入；**所有手动输入项 placeholder 即默认值**——用户未输入时提交 placeholder 值（`fallback` 必填，校验兜底）。
- 资源目录 API：`GET /page-designer/resources`（树：设计态=数据源/库表字段/工作流/字典/组件清单；运行态=工作流变量/系统变量/时间参数）。

## 7. 样式系统（现代高级感）

- 设计令牌（CSS 变量）：中性灰阶面板 + 单一主色点缀、12px 圆角、柔和双层阴影、字号层级（12/13/14/16/20）、间距 4 基数；与现有 AntD5 主题对齐。
- `ComponentStyle`：填充色/渐变、背景图（含插图库引用）、圆角、边框、阴影、透明度、字体字号字色。
- 自定义项：插图、背景图、背景填充、色彩均可引用装饰图资源（插图选择器）。

## 8. 测试（运行态）预览

- `POST /page-designer/preview`：入参绑定集合 → 服务端逐绑定执行（只读校验：非 SELECT 拒绝；超时；**硬编码 LIMIT 100**）→ 返回 `{columns, rows, truncated, widgetErrors}`。
- 画布切换「预览态」：有绑定组件渲染真实数据，无绑定组件渲染模板样例数据；组件级错误以角标提示不阻塞整页。
- 预览数据不落库、不留痕（只读连接）。

## 9. 发布与引用刷新（发布即刷新）

1. 冻结→发布复用现有闸门链；page 分支闸门 = 纯数据校验 + page DSL 结构校验 + 绑定资源存在性（闸门第 8 项引用完整性延伸）。
2. 发布成功后服务端自动执行 `POST /components/{type}/refresh-refs`：扫描全部图文档中 `componentRef.type` 匹配项 → 批量升级 `componentRef.version` 至新发布版本（乐观锁、幂等）→ 返回刷新清单。
3. 前端发布成功 toast「已刷新 N 个图引用」；替代现有手动逐个 `upgradeOne`（M1 声明组件同样受益）。

## 10. 编辑工具条（含刷新）

`撤销 重做 | 复制 粘贴 删除 | 左对齐 上对齐 等距分布 | 缩放 下拉 | 刷新 | 保存 预览 发布`
- **刷新**：重载画布文档与资源目录（DAG 工作台当年要求、实现遗漏，P2 在 DAG 工作台补齐同款按钮）。
- 图标/快捷键规格与 GraphWorkbench 工具条一致。

## 11. 模板系统

- `templates.ts`：每个 palette 组件一个初始化模板（默认 props/style/示例数据/推荐绑定槽）；新建页面组件时提供页面级模板（空白 / 数据看板 / 表单页 / 列表页）。
- 模板纯数据、随 DSL 版本演进；发布闸门校验模板引用的资源存在。

## 12. aoci 索引管理

- 初始化：`aoci init`（骨架+治理配置+AGENTS.md）→ `scope` 纳入组件设计器目录 → `scan` → `index`（header+entries）。
- 索引覆盖：`pageDesigner/**`、复用件（GraphWorkbench 布局/FieldRenderer）、`page_designer.py`、`component_design.py`、`models.py` 相关表、前后端测试。
- 组件生命周期（增/删/改/查/引用/发布）在对应 Entry 的 F/R/A/S 中显式标注；任务收尾按 AGENTS.md 契约执行 `aoci_maintain` → `aoci_update_entry` 闭环。
- 依赖说明：批量生成索引内容需配置 AI 端点（`aoci ai`）或走 MCP 模型闭环；不可用时记录 `aoci_report` 不猜测。

## 13. 整合与单一入口（P2）

- `/meta/components` 单一入口页 = Tab 容器：**组件目录 | 基线化工作台 | 页面设计器 | 声明编辑器**，参照 DAG 工作流多 Tab 整合方式；`?tab=` 深链定位；与 DAG 工作台、血缘分析入口风格一致。
- 组件目录行内「设计」直达页面设计器深链；基线化链路不受影响。

## 14. 错误处理

- 绑定资源不存在/失效：属性面板行内标红，运行回退 `fallback`；预览组件级错误角标。
- 预览失败/超时：组件级错误提示，不阻塞整页预览。
- 发布闸门失败：违规项行内定位（同 M1 体验）。
- 画布渲染异常：widget 级 ErrorBoundary 兜底卡片，不拖垮设计器。

## 15. 测试策略

- **vitest**：面板拖宽/画布拖尺寸持久化、palette 渲染与拖入套模板、绑定候选推导与 placeholder 默认值落值、工具条（含刷新）、发布后自动 refresh-refs 调用、DSL 归一化与校验。
- **pytest**：page 草稿 CRUD/乐观锁、page DSL 校验分支、preview 只读拦截 + LIMIT 100、publish 闸门 page 分支、refresh-refs 批量升级幂等、execution_model=page 契约。
- 本地 vitest+pytest 全绿 → 部署 1.9 实测（既有工作流）。

## 16. 分期计划

| 期 | 内容 |
|---|---|
| P1 | §3–§12：设计器内核、组件库+模板、绑定、预览、发布刷新、工具条（含刷新）、aoci 初始化与索引 |
| P2 | §13 三页整合单一入口、DAG 工作台补「刷新」按钮、aoci 全量条目打磨 |

## 17. 风险

- aoci 索引批量生成依赖 AI 端点配置；不可用时降级为 MCP 模型闭环或 `aoci_report` 记录。
- 288px 窄画布上复杂组件预览的缩放适配（提供 zoom 适配开关）。
- `execution_model` Literal 扩展需同步前后端白名单与闸门契约，防存量口径漂移。
