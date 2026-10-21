# INC4-FE-2 证据：画布多 Tab MAX_DAG_TABS=5 + edit 态右上操作（4.2b）

- 票号：INC4-FE-2（s260 五票顺位第二票派令）
- 执行线：Trae
- 日期：2026-10-21（Asia/Shanghai）
- 交付信：docs/handoff/outbox/trae/tr-done-23.json
- 权威锚：权威设计 v3 §5A.1（L481-492 蓝本四要素表「照抄（交互机制与持久化键名一并继承）」）/ §5A.2（L494-505 三分类收窄）/ §7.3（布局蓝本一致性判据）/ §8.4（复制准入红线）；验收标准 v4；WBS 增量 4

## 一、派令原文

> 【INC4-FE-2】画布多 Tab MAX_DAG_TABS=5

tr-ack-23 承诺范围：蓝本 TaskCenterView.vue 中段画布多 Tab 逻辑照抄（openTab/onCloseTab/MAX_DAG_TABS=5 上限/.tc-dagbar 画布条）+ edit 态右上专属操作（＋新建工作流/另存为模板/视角名）；通用边界 = 三绿门 + R6 零触碰 + metricsApi/memberApi 禁改 + 禁 aoci + .git 只读 + 测试范式沿 S252。

## 二、交付物（四件）

### 1. datara-newweb/src/stores/dagTabs.ts（新建，83 行）

- L3-14 头注释：I11 用户裁定锚（同画布单实例/多 Tab 切换/关闭提示保存/上限 5）+ 蓝本照抄声明（旧蓝本 datara-web/src/stores/dagTabs.ts 照抄，交互机制与持久化键名一并继承）+ 唯一差异 = §5A.2 收窄。
- L15 `DagProfileType = 'wf' | 'sync' | 'stream'`（§5A.2 三分类：删 etl）。
- L17-25 `DagTab`（key=docId 天然唯一 / name / type / code?）；L28 `MAX_DAG_TABS = 5`；L31-36 `DagPickItem`（Palette load-tasks 载荷形状，FE-3 接驳位）。
- L38-83 store：`open()` 三态返回 `'ok'|'dup'|'full'`（dup=仅激活已有 Tab；full=≥5 拒绝不 push；open 即激活新 Tab）+ `activate()`（非法 key 不生效）+ `remove()`（splice 后 `Math.min(idx, length-1)` 落位右邻/左邻，独 Tab 关闭回空串；返回被移除 docId 供宿主清理快照）。

### 2. datara-newweb/src/views/TaskCenterView.vue（90 → 326 行改造）

- L1-28 头注释扩写：FE-2 蓝本锚 + 四项缺位基建降级声明（GraphWorkbench/Palette/listDefinitions/auth+createTemplate 逐处标注接驳批次）。
- L29-32 import：dagTabs store 四导出（MAX_DAG_TABS/useDagTabsStore/DagPickItem/DagTab/DagProfileType）。
- L52-54 `dagTabs` store 接线 + `activeTab` computed。
- L56-59 `profileOf` 视角名（`'DAG 编排'` 常量承载；ViewProfile 体系归 FE-6/7）。
- L60-65 lsGet/lsSet（try/catch 隐私模式兜底）。
- L67-96 PoolMeta 形状 + `isTaskType` 收窄守卫 + `typeOf()`（tags 同步/流 优先，seedType 兜底，默认 wf——§5A.2 删 ETL 分支，存量 etl 降级映射 wf，执行前报监督线核对候批）+ TYPE_LABEL 三项（去 etl）+ `openTab()`（默认打开与 Palette 载入共用）。
- L98-116 `onPickTasks(p:{items})`（蓝本 L141-158 照抄）：逐项 openTab，full 即 ElMessage.warning（`最多同时打开 5 个画布 Tab，后续 N 项未载入`）break；非 dup 逐项落盘 `datara.dag.last[.type]` + `datara.dag.lastType`；末尾 switchTab('edit')。本票 handler 在位接驳（Palette load-tasks 事件同名同载荷，FE-3 接驳后即活）。
- L118-129 edit 态右上专属操作：onOpenCreateWf / saveActiveAsTemplate（auth.canEdit/WfCreateDialog/ElMessageBox.prompt→createTemplate 随画布内核批次接驳，本票 ElMessage.info 提示降级）。
- L131-140 `hasSnapDraft(docId)` / `clearSnap(docId)`：dirty 信号 = 快照草稿（键名 `datara.dag.snap.{docId}` 继承）。
- L142-184 `onCloseTab(t)`（蓝本 L205-248 三选交互照抄）：激活 Tab 有草稿 → ElMessageBox.confirm 三选（confirmButtonText='保存并关闭' + distinguishCancelAndClose:true；resolve=保存并关闭、reject('cancel')=放弃修改、reject('close')=X/ESC 取消不关）；非激活 Tab 有草稿 → confirm（confirmButtonText='仍要关闭'）后关，reject 直接返回；remove 后 await nextTick 再 clearSnap（等旧实例卸载回写）。
- L186-205 onMounted 打开优先级（蓝本 L250-276 照抄）：`?doc=` 直达（openTab + last 落盘）> lastType 读对应键恢复 > 无（空态）。候选池缺失降级：openTab 落 name=docId 占位 + type=wf；「陈旧 last 清理」待 FE-4 接线后启用。
- L207-219 CanvasPlaceholder 占位组件（h 渲染 `.tc-canvas-slot` 双行文案）：承载蓝本 KeepAlive + `:key=activeTab.key` 重挂载结构，FE-6/7 内核到位后替换为 GraphWorkbench。
- L222-284 template 中段：`.tc-dagbar[data-tc-dagbar]`（v-if tabs.length）> `button.tc-dag`（`.on` 激活态/:title/:data-dag-tab/@click activate）内 `.tcd-code`（v-if code!=null，`#{{code}}`）/.tcd-name/.tcd-type（TYPE_LABEL）/`.tcd-x`（@click.stop onCloseTab——stop 防 X 触发 Tab 激活）+ `.tc-daghint`（`{{count}}/5`）；`.tc-canvas`（v-if activeTab）内 KeepAlive>CanvasPlaceholder；v-else `.tc-empty` 空态双行文案（蓝本原文）；右上三件 v-if（新建工作流常驻 edit 态 / 另存为模板 v-if activeTab / 视角名常驻 edit 态）。
- L286-325 style：`.tc-dagbar/.tc-dag/.tcd-*/.tc-daghint/.tc-canvas/.tc-canvas-slot/.tc-empty` 等蓝本照抄 + 新壳 CSS 变量 fallback 惯例。

### 3. datara-newweb/src/stores/__tests__/dagTabs.contract.test.ts（新建，127 行，12 用例）

- 范式：`beforeEach(() => setActivePinia(createPinia()))`（store 状态隔离）。
- 12 例：①MAX_DAG_TABS=5 锚；②§5A.2 收窄锁（`// @ts-expect-error §5A.2：etl 已删，四类型回潮则此行编译报错` + `const bad: DagProfileType = 'etl'`——编译期锁定）；③初始态；④open 'ok'（key=docId+isOpen+激活）；⑤open 'dup'（仅激活 count 不增）；⑥open 满 5 'full'（拒绝不 push）；⑦activate 非法 key 不生效；⑧remove 激活中段→右邻落位（Math.min(idx, len-1)=1→'d3'）；⑨remove 末位→左邻（→'d1'）；⑩remove 独 Tab→activeKey=''; ⑪remove 非激活→activeKey 不变；⑫remove 不存在→null。

### 4. datara-newweb/src/views/__tests__/taskCenterView.contract.test.ts（重写 102 → 359 行，20 用例）

- FE-1 describe 六用例语义保留（见披露 §四.1 改写说明）。
- FE-2 describe 十四用例：
  - 挂载通道：①`?doc=` 直达（last 落盘 + lastType + 画布占位渲染）；②last 恢复（lastType=sync 读 `datara.dag.last.sync`，type 兜底 wf 断言）。
  - Tab 条：③渲染断言（hint `2/5`/徽标 TYPE_LABEL/code `#7`/title/`.on` 新开即激活/点击激活 els[0]）；④KeepAlive + :key 画布跟随（切 Tab 文案跟随不销毁）。
  - Palette 载入：⑤逐项开 Tab + last 按类型落盘 + lastType + 切回 edit（replaceSpy `{query:{tab:'edit'}}`）；⑥dup 仅激活不重复落盘；⑦full 警告截断（msgWarning 1 次 + 文案含「最多同时打开 5 个」+ Tab 停留 5）。
  - 关闭三选：⑧非激活无草稿直关无确认（X @click.stop 不触发激活断言 activeKey 保持）；⑨激活有草稿 confirm 参数断言（`confirmButtonText:'保存并关闭'` + `distinguishCancelAndClose:true`）+ 关 + snap 清理；⑩reject('cancel')=关 + 清 snap；⑪reject('close')=不关 + snap 留；⑫非激活有草稿双路（resolve=关+清 / reject=不关+留，confirm 参数 `仍要关闭`）。
  - 右上：⑬降级提示（点击 msgInfo 计数）+ 另存为模板 v-if activeTab 出没；⑭edit 态三件出没（沿 FE-1 ②）。
- 范式基建：`mountView()` = `createPinia()` + `setActivePinia(pinia)` + `mount(TaskCenterView, { global: { plugins: [pinia] } })`（store 状态隔离 + 测试体可种入/读取同一实例）；`seedSnap(docId)` = localStorage 种 `datara.dag.snap.{docId}`（`{draft:{nodes:[]}}`）；`pickTasks` 经 `setupState.onPickTasks` 直调（组件未 defineExpose，Palette load-tasks 事件同名同载荷）；element-plus mock 沿 S252 vi.hoisted 五 spy + beforeEach `boxConfirm.mockReset()+mockImplementation(()=>Promise.resolve())` 恢复默认 resolve。

## 三、验证（三绿门，2026-10-21 07:48-07:53 机器实跑，修复后终态）

| 门 | 命令 | 结果 |
| --- | --- | --- |
| 类型 | `npx vue-tsc -b` | exit 0，零错误 |
| 测试 | `npx vitest run` | 36 files / **382 passed**（FE-1 基线 356 + 本票 store 12 + 视图净增 14 = 382，0 failed 0 退化） |
| 构建 | `npm run build` | exit 0，1629 modules，685ms（chunk>500kB 警告为存量已知项） |

首轮（修复前）3 failed / 382，全部系测试侧时序与断言方向问题，组件与 store 代码零改动即修复（见披露 §四.3）。

## 四、披露

1. **FE-1 测试文件重写（tr-done-22 候验收影响声明）**：taskCenterView.contract.test.ts 全文重写，FE-1 六用例语义保留、零回归，但有三处改动——①mountView 引入 pinia 插件（FE-1 原范式无 store 依赖）；②用例②「默认 edit 主视角」画布断言由 `data-tc-canvas-slot` 占位槽改为 `data-tc-empty` 空态文案「暂无打开的画布」（FE-2 后 edit 态空态语义变化，占位槽由 KeepAlive+CanvasPlaceholder 替代，FE-1 证据 §四.4 已预告移除）；③用例③「非法 ?tab= 回落」同步改空态断言。行号全面漂移。tr-done-22 验收请以「六用例语义保留」口径核（本文件 §二.4 为最终态）。
2. **CanvasPlaceholder 替代 FE-1 占位槽**：FE-1 交付的单槽 `.tc-canvas-slot` 占位（v-if tab==='edit' 常渲染）由「KeepAlive > CanvasPlaceholder(:key=activeTab.key) / v-else 空态」双态结构替代，`data-tc-canvas-slot` 属性保留在占位组件内部（测试选择器不变），结构对齐蓝本 KeepAlive 语义。
3. **首轮 3 failed 全系测试侧（自纠，组件零改动）**：①「Palette 载入」同步 it 内 DOM 断言早于 switchTab('edit') 的异步重渲染——改 async + `await flushPromises()`；②「关闭非激活有草稿」循环内 store.open 后 findAll 早于 dagbar v-if 重渲染（TypeError reading 'find'）——循环内补 flushPromises；③「Tab 条渲染」断言方向写反（open 语义=新开即激活，应 els[1].on 而非 els[0]）——修正断言方向并改点 els[0] 验证点击激活。**时序范式沉淀：凡 store 变更或 handler 触发后接 DOM 断言，必须 `await flushPromises()`；纯 store/localStorage/spy 断言可同步。**
4. **CSS 注释 `*/` 陷阱（build 拦截，自纠）**：样式注释内 `.tcd-*/` 的 `*/` 提前终止注释，后续文本被 postcss 当 CSS 解析致 `npm run build` 失败（compiler-sfc Parser.unexpected at TaskCenterView.vue:20:42）；改顿号列举（`.tcd-* 系列`）。vue-tsc/vitest 均不解析 style，唯 build 可拦——三绿门缺一不可的实证。
5. **vue-tsc 首轮 exit 1 输出未捕获**：首轮两命令并行共享终端致日志交叉，vue-tsc 错误段被挤出缓冲；修复终态单独重跑 exit 0，首轮具体错误无法回溯（终态零错误为验收口径）。**教训沉淀：输出敏感命令必须串行跑。**
6. **缺位基建降级四处（头注释逐处声明）**：画布内核 GraphWorkbench（FE-6/7，CanvasPlaceholder 占位 + dirty 信号=快照草稿）；Palette 双 Tab（FE-3，onPickTasks handler 在位）；候选池 listDefinitions（FE-4，?doc=/last 落 name=docId 占位 + wf 兜底，陈旧 last 清理待接线）；auth/WfCreateDialog/createTemplate（画布内核批次，右上行为提示降级）。
7. **存量 ETL 降级映射**：§5A.2 删 etl 分支，typeOf 对存量 etl 定义落 wf（tags 契约值「同步/流」优先判定）；执行前报监督线核对候批（本票无存量数据迁移动作）。

## 五、纪律遵守

- .git 只读（零 commit/push）；零 aoci_* 调用（裁定 #85）；R6 冻结面零触碰；metricsApi/memberApi 禁改面未触碰；projectMenu 七段定稿未触碰。
- 测试范式沿 S252（vi.hoisted + vi.mock）+ FE-1 mountView pinia 扩展；路由表/router/index.ts 零改动；无 demo/catch-all 路由新增。
- 蓝本照抄保真：交互机制（三选确认/@click.stop/KeepAlive 重挂载/打开优先级）与持久化键名（datara.dag.last[.type]/lastType/snap.{docId}）一并继承，唯一差异 = §5A.2 三分类收窄。
