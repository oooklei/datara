# INC4-FE-3 证据：Palette 双 Tab（组件库/工作流）（4.2c）

- 票号：INC4-FE-3（s260 五票顺位第三票派令）
- 执行线：Trae
- 日期：2026-10-21（Asia/Shanghai）
- 交付信：docs/handoff/outbox/trae/tr-done-24.json
- 权威锚：权威设计 v3 §5A.1（L489-491 蓝本 Palette 双 Tab 照抄）/ §5A.3（L507-513 组件规格一源零私设）/ L969 布局蓝本一致性判据；验收标准 v4；WBS 增量 4

## 一、派令原文

> 【INC4-FE-3】Palette 双 Tab（组件库/工作流）

tr-ack-24 承诺范围：蓝本 datara-web/src/graph/workbench/Palette.vue 双 Tab 框架照抄 + 组件库数据一源 loadComponentSpecs 零私设（§5A.3）+ paletteVisible 契约过滤 + 宿主 TaskCenterView 空态挂载 + wf Tab 占位归 FE-4 + 测试双文件 + 三绿门；通用边界 = R6 零触碰 + metricsApi/memberApi 禁改 + 禁 aoci + .git 只读 + 测试范式沿 S252。

## 二、交付物（四件）

### 1. datara-newweb/src/components/Palette.vue（新建，194 行）

- L1-23 头注释：蓝本照抄声明（PalTab 双 Tab/.pal-tabs/.pal-tab.on/搜索框/分组折叠 folded+arrow▼/拖拽 setData('datara/node-type')+effectAllowed=copy/.p-ico/.p-name/.p-code/空态「无匹配组件」）+ §5A.3 组件规格一源零私设声明（/api/v1/rebuild/components/spec；ETag/304/last-success 回落、首载 fail-closed 全在 API 层）+ paletteVisible===false 过滤为 normalizeSpec 契约内规则（D1 闸门 §13-5 runtime-only 显式 false）非组件私设 + 缺位降级三条（ViewProfile/resolveSchema/activeTags 通道归 FE-6/7；wf Tab 内容归 FE-4；load-tasks 事件契约在位、宿主 onPickTasks 已接驳）。
- script：
  - `props = defineProps<{ defaultTab?: 'palette' | 'wf' }>()`（宿主可指定初始 Tab；任务中心空态默认「工作流」，GraphWorkbench 常规不传保持「组件」）；`defineEmits<{ 'load-tasks': [{ items: DagPickItem[] }] }>()` 无绑定声明（本票无内部触发点，FE-4 实装 onLoad 再赋 const emit）。
  - `codeOf(identity)`：identity.code 字符串探测（旧 NodeSchema.code 通道；spec visual.badge 是 {key,colorMap} 状态徽标对象非 code 字符串，不直出——badge 结构陷阱规避）。
  - `rowOf(it)`：paletteVisible===false 返回 null 集中过滤 + spec→PalRow 映射（label=identity.displayName 兜底 type / desc=description.summary / icon=color=visual 直取 / cat=description.category）。
  - onMounted：`loadComponentSpecs()` → rows 映射过滤；失败 console.warn + 空态（fail-closed 不阻断宿主渲染）；finally loaded=true。
  - `groups` computed：kw 过滤三通道（label/desc/type，trim+toLowerCase）+ 分组键=category 全路径、组名=末段（split 末元素）、空类别归「通用」+ Map 保序一级平铺（蓝本单层目录结构）。
  - `onDragStart(e,row)`：`e.dataTransfer?.setData('datara/node-type', row.type)` + `effectAllowed='copy'`（蓝本原文）。
- template：`.wb-palette[data-palette]` > `.pal-tabs`（v-for tabs，`.pal-tab.on`）> palette 分支（`.pal-search` input 内联样式 border var(--border-color,#d3d9e3)；`.pal-list` > `.pal-cat(:class={fold})` > `.pal-cat-head`（▼+组名+.cnt）@click 折叠 toggle > `.pal-items` > `.pal-item(:draggable=true :title @dragstart)` > `.p-ico(:style background)+.p-name(label + v-if row.code .p-code)`；空态 `v-if="loaded && groups.length === 0"`「无匹配组件」——防挂载瞬间闪空态）> wf 分支 `.pal-empty`（「工作流目录归 INC4-FE-4 交付（候选池接线后可用）」）。
- style scoped：旧 theme.css 全局系 + Palette.vue scoped 系合并（仅组件库分支），全量 CSS 变量 fallback 化（新前端无全局 token，fallback 即生效值）：--card→直接 #fff（沿 FE-2 tc-tabs 惯例）/ --border→var(--border-color,#e2e8f0) / --border-strong→var(--border-color,#d3d9e3) / --text-2→var(--text-secondary,#64748b) / --text-3→var(--text-3,#94a3b8) / --bg→var(--bg-secondary,#f8fafc) / --primary→var(--primary-color,#2563eb) / --radius-sm→var(--radius-sm,6px)；旧主色 rgba(22,104,220,.25)→rgba(37,99,235,.25)（#1668dc→#2563eb 换算）。
- 蓝本省略项（头注释披露，接驳批次明确）：.p-desc/.pal-item.disabled 灰置系（无 ViewProfile disabled/phase 通道，FE-6/7 接驳再补）、行级分类徽标 .p-cat（无 catLabelsOf 通道）、wf 系 scoped 样式全套（.pal-task/.pt-* 通配/.pal-bar/.pal-mini/.pal-load/.pal-all/.wf-root-*，归 FE-4）、scoped .p-code wf 变体（11px primary 系——组件库行保留 theme.css 全局 9.5px 系）。

### 2. datara-newweb/src/views/TaskCenterView.vue（三处编辑，326 → 331 行）

- 头注释 L22-25：缺位降级声明中「Palette 双 Tab 归 INC4-FE-3：空态仅提示在位」改为「INC4-FE-3 已接驳：空态渲染 `<Palette default-tab="wf">` @load-tasks="onPickTasks"（事件同名同载荷直连）；组件库一源 loadComponentSpecs（§5A.3 零私设）；wf Tab 目录内容仍归 FE-4 候选池接线」。
- import 区 L33：+ `import Palette from '../components/Palette.vue'`。
- 空态 L269-278：`.tc-empty-hint` 前插入 `<Palette default-tab="wf" @load-tasks="onPickTasks" />` + 注释更新（声明不加 .tc-newbtn——顶栏已有新建入口，避免双钮；hint 两行文案与 data-tc-empty 测试锚保留）；`.tc-empty` 样式零改动（row 方向 flex，Palette 232px+hint 并列成立）。

### 3. datara-newweb/src/components/__tests__/palette.contract.test.ts（新建，241 行，10 用例）

- 范式：`vi.hoisted` specLoad + `vi.mock('../../services/rebuild/componentSpecApi', ...)`（loadComponentSpecs/resetComponentSpecCache）；`item()` helper 构造 ComponentSpecItem 形状（仅 identity/description/visual 参与渲染映射）；beforeEach `specLoad.mockReset()` + `mockResolvedValue` 空快照；mountPalette helper。
- 十用例：①双 Tab 顺序照抄（组件/工作流）+ 缺省激活「组件」+ 搜索框在位 + FE-4 占位不存在；②defaultTab='wf' 初始激活 + `.pal-empty` 含「INC4-FE-4」+ 点击切回组件库占位消失；③分组渲染（`.pal-cat`×3：路径末段组名且不含「批处理与同步/」前缀（.pal-cat-head 文本含 ▼ 用 toContain）/空类别归「通用」/.cnt 计数/.p-ico background 内联/.p-code 文本）；④paletteVisible===false 项过滤（runtime-only 不进调色板）；⑤搜索三通道 label/desc/type 各命中一组件 + 无命中渲染「无匹配组件」；⑥折叠 toggle（.pal-cat-head click 加/去 .fold）；⑦拖拽契约（fakeDT trigger('dragstart')：setData('datara/node-type', type) + effectAllowed='copy'）；⑧加载失败 console.warn + 空态（spyOn mockImplementation 局部 + mockRestore）；⑨identity.code 非字符串（数字 123）不渲染 .p-code、字符串渲染；⑩加载前不闪空态（never-resolve promise + 不 flush 同步断言，锁定 loaded 门控）。

### 4. datara-newweb/src/views/__tests__/taskCenterView.contract.test.ts（四处编辑，359 → 366 行，20 用例不变）

- 头注释：依赖 mock 说明 + componentSpecApi（specLoad——FE-3 已接驳：空态渲染 Palette，组件规格一源不进网络层，mock 空快照即可，Palette 断言归 palette 契约测试）；「FE-3 接驳前 setupState 直调」说明更新为「既有用例仍经 setupState 直调 onPickTasks，Palette load-tasks 事件同名同载荷，DOM 入口已接通」。
- hoisted 块 + `specLoad: vi.fn()`；element-plus mock 后 + `vi.mock('../../services/rebuild/componentSpecApi', ...)`；beforeEach + `specLoad.mockReset()` + `mockResolvedValue({ items: [], etag: '"00"', source: 'network' })`。
- 既有 20 用例零改动全数通过（data-tc-empty 三处断言不受影响：Palette 挂载于 .tc-empty 内、hint 文案保留）。

## 三、验证（三绿门，2026-10-21 08:18-08:26 机器实跑，修复后终态）

| 门 | 命令 | 结果 |
| --- | --- | --- |
| 类型 | `npx vue-tsc -b` | exit 0，零错误 |
| 测试 | `npx vitest run` | 40 files / **415 passed**（FE-2 收口基线 36 files/382 passed 全数通过零退化 + 本票 palette 新文件 1 file/10 tests；余 3 files/23 tests 系 FE-2 收口后他线并入的既有用例，本次全量实跑全绿，见披露 §四.3） |
| 构建 | `npm run build` | exit 0，1633 modules，838ms（chunk>500kB 警告为存量已知项） |

首轮 build 1 failed（CSS 注释 `*/` 陷阱，自纠一处注释写法即过，见披露 §四.1）；vue-tsc/vitest 首轮即绿；三绿门串行跑（FE-2 教训沿用）。

## 四、披露

1. **CSS 注释 `*/` 陷阱再次触发（build 唯一可拦，自纠）**：Palette.vue scoped 头注释 `.pt-*/` 的 `*/` 提前终止注释，postcss 报 Unexpected '/'（Palette.vue:3:25，vite:vue style 插件）；改顿号列举（`.pal-task、.pt-* 通配、.pal-bar、.pal-load`）。FE-2 披露 §四.4 同款第二例——**`.xxx-*/` 型注释写法已列入本线禁用模式，样式注释内类名列举一律顿号**。vue-tsc/vitest 均不解析 style，唯 build 可拦，三绿门缺一不可第二次实证。
2. **`.p-code` 蓝本双定义取舍**：旧 Palette.vue scoped `.p-code`（11px primary 系，wf 行用）与 theme.css 全局 `.pal-item .p-code`（9.5px text-3 系）并存；新组件组件库行保留后者，wf 变体归 FE-4。
3. **测试计数口径**：40/415 较 FE-2 收口 36/382 净增 4 files/33 tests；本票仅 palette.contract.test.ts（1 file/10 tests）。余 3 files/23 tests 为 FE-2 收口（07:53）后其他线并入的既有用例（非本线动作），本次全量实跑全数通过、零 failed，不构成退化；验收口径 = FE-2 基线用例全数通过 + 本票新增用例全绿。
4. **badge 结构陷阱规避落地**：spec visual.badge 是 {key,colorMap} 状态徽标对象非旧 NodeSchema.code 字符串；`.p-code` 数据源定为 identity.code 字符串探测（codeOf helper），非字符串不渲染，用例⑨锁定。
5. **分组策略定稿落地**：spec description.category 为路径（如「批处理与同步/数据源」）→ 分组键=全路径、组名=末段、空类别归「通用」；一级平铺沿蓝本单层目录；用例③锁定（组名不含路径前缀断言）。
6. **defineEmits 无绑定声明**：`defineEmits<{ 'load-tasks': [{ items: DagPickItem[] }] }>()` 不赋 const（本票无内部触发点；tsconfig 无 noUnusedLocals，按求干净处理）；FE-4 实装 onLoad 时再赋 `const emit =`。
7. **空态防闪**：`v-if="loaded && groups.length === 0"` 门控（蓝本数据同步加载无此问题，新前端异步加载需防挂载瞬间闪空态）；用例⑩以 never-resolve promise 锁定。
8. **缺位降级三条（头注释逐处声明）**：ViewProfile/resolveSchema/activeTags 通道归 FE-6/7（分组改 spec category 派生；无 disabled/phase 灰置与 .p-cat 徽标通道）；wf Tab 内容归 FE-4（新建分类/搜索/目录树/勾选载入/行操作，候选池接线后可用）；load-tasks 事件契约在位（DagPickItem[] 同名同载荷，宿主 onPickTasks 已接驳，FE-4 onLoad 生效）。

## 五、纪律遵守

- .git 只读（零 commit/push）；零 aoci_* 调用（裁定 #85）；R6 冻结面零触碰；metricsApi/memberApi 收编件禁改；projectMenu.ts 七段定稿未触碰。
- 测试范式沿 S252（vi.hoisted + vi.mock）+ FE-2 mountView pinia 惯例；路由表/router/index.ts 零改动。
- 蓝本照抄保真：双 Tab 框架/搜索/分组折叠/拖拽契约（setData 键名+effectAllowed）/空态文案（「无匹配组件」原文）照抄；唯一差异 = 组件规格一源（§5A.3 loadComponentSpecs 替代 ViewProfile.palette 通道）+ CSS 变量 fallback 惯例 + 主色换算。
