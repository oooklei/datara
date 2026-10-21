/**
 * INC4-FE-1/2（4.2a/4.2b）验收测试：任务中心视角页签框架 + 画布多 Tab（s260 派令）。
 *
 * FE-1 覆盖（蓝本 TaskCenterView.vue 照抄语义 + §5A.1 内容门控）：
 *  1. 四视角页签照抄渲染（顺序 + icon + label）；
 *  2. 默认 edit 主视角（FE-2 后 = 画布空态 + 右上专属操作三件）+ 非法 ?tab= 回落 edit；
 *  3. ?tab= 激活分流：runs=页签占位（内容归增量 8）、templates/alarm=框架保留；
 *  4. switchTab → router.replace 合并既有 query（保书签）。
 *
 * FE-2 覆盖（蓝本中段 L59-276 照抄 + §5A.2 三分类收窄）：
 *  - ?doc= 直达 / last 恢复（datara.dag.last* 持久化键名一并继承）；
 *  - Tab 条渲染（TYPE_LABEL 徽标 / hint n/5 / .on 激活 / 点击激活 / @click.stop 关闭钮）；
 *  - Palette 载入 onPickTasks（逐项开 Tab + last 落盘 / dup 仅激活不落盘 / full 警告截断）；
 *  - 关闭三选（激活有草稿：保存并关闭/放弃修改/X·ESC 取消；非激活：草稿确认/直关）；
 *  - KeepAlive + :key 画布区跟随 activeTab；右上专属操作降级提示（画布内核批次接驳）。
 *
 * 依赖 mock：vue-router（useRoute.query / useRouter.replace + FE-4 params.projectId）、
 * element-plus（ElMessage / ElMessageBox spy——真实弹窗不进 DOM，断言调用参数与三选 action 路径）、
 * componentSpecApi（specLoad——FE-3 已接驳：空态渲染 Palette，其组件规格一源
 * loadComponentSpecs 不进网络层，mock 空快照即可，Palette 断言归 palette 契约测试）、
 * workflowApi（poolLoad——FE-4 已接驳：TC 与真实 Palette 子组件同源候选池 API
 * 不进网络层；categories 系 RED 哨兵内联 mock，行操作不触发）。
 * 既有用例仍经 setupState 直调 onPickTasks（组件未 defineExpose；
 * Palette load-tasks 事件同名同载荷，DOM 入口已接通）。
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { replaceSpy, routeQuery, routeParams, poolLoad, msgInfo, msgWarning, boxConfirm, specLoad } = vi.hoisted(() => ({
  replaceSpy: vi.fn(() => Promise.resolve()),
  routeQuery: { value: {} as Record<string, unknown> },
  routeParams: { value: {} as Record<string, unknown> },
  poolLoad: vi.fn(),
  msgInfo: vi.fn(),
  msgWarning: vi.fn(),
  boxConfirm: vi.fn(() => Promise.resolve()),
  specLoad: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: routeQuery.value, params: routeParams.value }),
  useRouter: () => ({ replace: replaceSpy }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { info: msgInfo, warning: msgWarning, error: vi.fn(), success: vi.fn() },
  ElMessageBox: { confirm: boxConfirm },
}))

// FE-3 Palette 挂载于画布空态：其组件规格加载不进网络层（空快照即空目录）
vi.mock('../../services/rebuild/componentSpecApi', () => ({
  loadComponentSpecs: specLoad,
  resetComponentSpecCache: vi.fn(),
}))

// FE-4 TC 挂载真实 Palette 子组件：其 workflowApi 全部导入符号须在 mock 中供给
// （候选池 listWorkflowDefinitions + categories RED 哨兵系——行操作不进 DOM 不触发）
vi.mock('../../services/rebuild/workflowApi', () => ({
  listWorkflowDefinitions: poolLoad,
  deleteWorkflowDefinition: vi.fn(),
  WF_CATEGORIES_NOT_WIRED: 'WF_CATEGORIES_NOT_WIRED: rebuild/workflow categories contract not connected yet',
  workflowCategories: {
    listCategories: vi.fn(() => Promise.reject(new Error('WF_CATEGORIES_NOT_WIRED: rebuild/workflow categories contract not connected yet'))),
    createCategory: vi.fn(),
    deleteCategory: vi.fn(),
    setWfTags: vi.fn(),
  },
}))

import TaskCenterView from '../TaskCenterView.vue'
import { useDagTabsStore } from '../../stores/dagTabs'

function mountView() {
  // 每用例独立 pinia（store 状态隔离）；setActivePinia 供测试体种入/读取同一实例
  const pinia = createPinia()
  setActivePinia(pinia)
  return mount(TaskCenterView, { global: { plugins: [pinia] } })
}

/** 种入画布快照草稿（本票 dirty 信号 = hasSnapDraft；FE-6/7 接驳 graphStore 后改种 store） */
function seedSnap(docId: string) {
  localStorage.setItem(`datara.dag.snap.${docId}`, JSON.stringify({ draft: { nodes: [] } }))
}

/** FE-3 Palette 接驳前的 onPickTasks 触发通道（setupState 直调，载荷 = Palette load-tasks 事件同名同载荷） */
function pickTasks(
  w: ReturnType<typeof mountView>,
  items: { id: string; name: string; type: 'wf' | 'sync' | 'stream' }[],
) {
  ;(w.vm.$ as unknown as { setupState: { onPickTasks: (p: { items: typeof items }) => void } })
    .setupState.onPickTasks({ items })
}

beforeEach(() => {
  routeQuery.value = {}
  routeParams.value = {}
  poolLoad.mockReset()
  poolLoad.mockResolvedValue([])
  replaceSpy.mockClear()
  msgInfo.mockClear()
  msgWarning.mockClear()
  boxConfirm.mockReset()
  boxConfirm.mockImplementation(() => Promise.resolve())
  specLoad.mockReset()
  specLoad.mockResolvedValue({ items: [], etag: '"00"', source: 'network' })
  localStorage.clear()
})

/** 蓝本 tabs 数组原文（顺序 + icon + label） */
const BLUEPRINT_TABS = [
  { k: 'edit', label: '任务编排', icon: '⑃' },
  { k: 'templates', label: '模板中心', icon: '▦' },
  { k: 'runs', label: '运行监控', icon: '▶' },
  { k: 'alarm', label: '告警与SLA', icon: '🖂' },
]

describe('INC4-FE-1 任务中心顶部视角页签框架（/dag，s260 派令）', () => {
  it('四视角页签照抄渲染：顺序 + icon + label 与蓝本一致，页签条单实例', () => {
    const w = mountView()
    expect(w.find('[data-tc-tabs]').exists()).toBe(true)
    const els = w.findAll('[data-tc-tabs] .tc-tab')
    expect(els).toHaveLength(BLUEPRINT_TABS.length)
    BLUEPRINT_TABS.forEach((t, i) => {
      expect(els[i].attributes('data-tab')).toBe(t.k)
      expect(els[i].text()).toBe(`${t.icon}${t.label}`)
    })
  })

  it('默认 edit 主视角：edit 页签 .on 态 + 画布空态（Palette 载入前）+ 右上专属操作三件', () => {
    const w = mountView()
    expect(w.find('[data-tab="edit"]').classes()).toContain('on')
    expect(w.find('[data-tc-empty]').exists()).toBe(true)
    expect(w.find('[data-tc-empty]').text()).toContain('暂无打开的画布')
    expect(w.find('[data-testid="new-workflow"]').exists()).toBe(true)
    expect(w.find('.tc-view').text()).toBe('DAG 编排')
    expect(w.find('.tc-save-template').exists()).toBe(false) // 无激活 Tab 不渲染
    expect(w.find('[data-tc-dagbar]').exists()).toBe(false) // 无 Tab 不渲染 Tab 条
  })

  it('非法 ?tab= 回落 edit（蓝本初始化语义照抄）+ 画布空态', () => {
    routeQuery.value = { tab: 'nope' }
    const w = mountView()
    expect(w.find('[data-tab="edit"]').classes()).toContain('on')
    expect(w.find('[data-tc-empty]').exists()).toBe(true)
  })

  it('?tab=runs：runs 页签激活 + 占位注记渲染（内容归增量 8），画布区与 Tab 条不渲染', () => {
    routeQuery.value = { tab: 'runs' }
    const w = mountView()
    expect(w.find('[data-tab="runs"]').classes()).toContain('on')
    expect(w.find('[data-tab="edit"]').classes()).not.toContain('on')
    expect(w.find('[data-tc-runs-slot]').exists()).toBe(true)
    expect(w.find('[data-tc-runs-slot]').text()).toContain('增量 8')
    expect(w.find('[data-tc-canvas-slot]').exists()).toBe(false)
    expect(w.find('[data-tc-dagbar]').exists()).toBe(false)
  })

  it('?tab=templates / ?tab=alarm：页签激活态正确，框架保留且 body 不渲染占位内容', () => {
    for (const k of ['templates', 'alarm']) {
      routeQuery.value = { tab: k }
      const w = mountView()
      expect(w.find(`[data-tab="${k}"]`).classes()).toContain('on')
      expect(w.find('[data-tc-canvas-slot]').exists()).toBe(false)
      expect(w.find('[data-tc-runs-slot]').exists()).toBe(false)
      expect(w.find('[data-tc-body]').text()).toBe('')
    }
  })

  it('点击页签 → switchTab → router.replace 合并既有 query（保书签，蓝本语义）', async () => {
    routeQuery.value = { tab: 'edit', foo: 'bar' }
    const w = mountView()
    await w.find('[data-tab="runs"]').trigger('click')
    expect(replaceSpy).toHaveBeenCalledTimes(1)
    expect(replaceSpy).toHaveBeenCalledWith({ query: { tab: 'runs', foo: 'bar' } })
    // 本地激活态即时切换（不等路由响应）
    expect(w.find('[data-tab="runs"]').classes()).toContain('on')
  })
})

describe('INC4-FE-2 画布多 Tab（MAX_DAG_TABS=5，蓝本照抄 + §5A.2 收窄）', () => {
  it('?doc= 直达：开 Tab（name=docId 占位）+ last 落盘 + 画布占位渲染', async () => {
    routeQuery.value = { doc: 'd9' }
    const w = mountView()
    await flushPromises()
    const s = useDagTabsStore()
    expect(s.count).toBe(1)
    expect(s.activeTab).toMatchObject({ docId: 'd9', name: 'd9', type: 'wf' })
    expect(w.find('[data-tc-canvas-slot]').text()).toContain('画布：d9')
    // 直达也更新「上次打开」落盘（推导类型 wf → 主键 datara.dag.last）
    expect(localStorage.getItem('datara.dag.last')).toBe('d9')
    expect(localStorage.getItem('datara.dag.lastType')).toBe('wf')
  })

  it('last 恢复：无 ?doc= 时按 lastType 读对应键开 Tab（候选池 FE-4 接线前 name=docId 占位、type 兜底 wf）', async () => {
    localStorage.setItem('datara.dag.lastType', 'sync')
    localStorage.setItem('datara.dag.last.sync', 'd7')
    mountView()
    await flushPromises()
    const s = useDagTabsStore()
    expect(s.count).toBe(1)
    expect(s.activeTab?.docId).toBe('d7')
    expect(s.activeTab?.name).toBe('d7')
    // 元数据接线前 typeOf 无 tags 可查 → wf 兜底（头注释降级声明，FE-4 后升真）
    expect(s.activeTab?.type).toBe('wf')
  })

  it('Tab 条渲染：徽标 TYPE_LABEL / code #n / hint n/5 / .on 激活态 / 点击激活', async () => {
    const w = mountView()
    const s = useDagTabsStore()
    s.open({ docId: 'd1', name: '任务一', type: 'wf' })
    s.open({ docId: 'd2', name: '同步二', type: 'sync', code: 7 })
    await flushPromises()
    expect(w.find('[data-tc-dagbar]').exists()).toBe(true)
    const els = w.findAll('[data-tc-dagbar] .tc-dag')
    expect(els).toHaveLength(2)
    expect(w.find('.tc-daghint').text()).toBe('2/5')
    // open 语义 = 新开即激活 → 后开的 d2 为 .on
    expect(els[1].classes()).toContain('on')
    expect(els[0].classes()).not.toContain('on')
    expect(els[0].find('.tcd-type').text()).toBe('工作流')
    expect(els[1].find('.tcd-type').text()).toBe('同步')
    expect(els[1].find('.tcd-code').text()).toBe('#7')
    expect(els[1].attributes('title')).toBe('同步二')
    await els[0].trigger('click')
    expect(s.activeKey).toBe('d1')
    expect(w.findAll('[data-tc-dagbar] .tc-dag')[0].classes()).toContain('on')
  })

  it('KeepAlive + :key 画布区跟随 activeTab 渲染（蓝本切 Tab 不销毁结构占位）', async () => {
    const w = mountView()
    const s = useDagTabsStore()
    s.open({ docId: 'd1', name: '任务一', type: 'wf' })
    s.open({ docId: 'd2', name: '任务二', type: 'stream' })
    await flushPromises()
    expect(w.find('[data-tc-canvas]').exists()).toBe(true)
    expect(w.find('[data-tc-canvas-slot]').text()).toContain('画布：任务二')
    s.activate('d1')
    await flushPromises()
    expect(w.find('[data-tc-canvas-slot]').text()).toContain('画布：任务一')
  })

  it('Palette 载入（onPickTasks）：逐项开 Tab + last 按类型落盘 + lastType 落盘 + 切回 edit', async () => {
    routeQuery.value = { tab: 'templates' }
    const w = mountView()
    pickTasks(w, [
      { id: 'a1', name: 'A', type: 'sync' },
      { id: 'a2', name: 'B', type: 'stream' },
    ])
    await flushPromises() // switchTab('edit') 触发的 tab.value 重渲染是异步的，DOM 断言前必须等
    const s = useDagTabsStore()
    expect(s.count).toBe(2)
    expect(s.activeTab?.docId).toBe('a2')
    expect(localStorage.getItem('datara.dag.last.sync')).toBe('a1')
    expect(localStorage.getItem('datara.dag.last.stream')).toBe('a2')
    expect(localStorage.getItem('datara.dag.lastType')).toBe('stream')
    expect(w.find('[data-tab="edit"]').classes()).toContain('on')
    expect(replaceSpy).toHaveBeenCalledWith({ query: { tab: 'edit' } })
  })

  it('Palette 载入去重：重复项仅激活已有 Tab，last 不重复落盘（dup 不写）', () => {
    const w = mountView()
    const s = useDagTabsStore()
    s.open({ docId: 'a1', name: 'A', type: 'wf' })
    pickTasks(w, [{ id: 'a1', name: 'A', type: 'wf' }])
    expect(s.count).toBe(1)
    expect(s.activeKey).toBe('a1')
    expect(localStorage.getItem('datara.dag.last')).toBeNull()
  })

  it('Palette 载入超限：full 警告 + 后续项截断，Tab 停留 5 个', () => {
    const w = mountView()
    const s = useDagTabsStore()
    for (let i = 1; i <= 5; i++) s.open({ docId: `x${i}`, name: `t${i}`, type: 'wf' })
    pickTasks(w, [
      { id: 'y1', name: 'Y', type: 'wf' },
      { id: 'y2', name: 'Z', type: 'wf' },
    ])
    expect(s.count).toBe(5)
    expect(s.isOpen('y1')).toBe(false)
    expect(msgWarning).toHaveBeenCalledTimes(1)
    expect(String(msgWarning.mock.calls[0][0])).toContain('最多同时打开 5 个画布 Tab')
  })

  it('关闭非激活 Tab（无草稿）：直关无确认，X @click.stop 不触发 Tab 激活', async () => {
    const w = mountView()
    const s = useDagTabsStore()
    for (const id of ['d1', 'd2', 'd3']) s.open({ docId: id, name: id, type: 'wf' })
    s.activate('d1')
    await flushPromises()
    await w.findAll('[data-tc-dagbar] .tc-dag')[1].find('.tcd-x').trigger('click')
    await flushPromises()
    expect(boxConfirm).not.toHaveBeenCalled()
    expect(s.count).toBe(2)
    // 无 stop 会先激活 d2 再关闭 → 落位 d3；有 stop 则 activeKey 保持 d1
    expect(s.activeKey).toBe('d1')
  })

  it('关闭激活 Tab（有草稿）· 确认「保存并关闭」：关闭 + snap 清理（保存接驳 FE-6/7，本票同放弃收尾）', async () => {
    const w = mountView()
    const s = useDagTabsStore()
    s.open({ docId: 'd1', name: '一', type: 'wf' })
    seedSnap('d1')
    await flushPromises()
    await w.find('.tcd-x').trigger('click')
    await flushPromises()
    expect(boxConfirm).toHaveBeenCalledWith(
      '当前画布有未保存的修改，关闭前要保存吗？',
      '关闭画布',
      expect.objectContaining({ confirmButtonText: '保存并关闭', distinguishCancelAndClose: true }),
    )
    expect(s.count).toBe(0)
    expect(localStorage.getItem('datara.dag.snap.d1')).toBeNull()
  })

  it("关闭激活 Tab（有草稿）· reject('cancel')「放弃修改」：关闭 + snap 清理", async () => {
    const w = mountView()
    const s = useDagTabsStore()
    s.open({ docId: 'd1', name: '一', type: 'wf' })
    seedSnap('d1')
    boxConfirm.mockRejectedValueOnce('cancel')
    await flushPromises()
    await w.find('.tcd-x').trigger('click')
    await flushPromises()
    expect(s.count).toBe(0)
    expect(localStorage.getItem('datara.dag.snap.d1')).toBeNull()
  })

  it("关闭激活 Tab（有草稿）· reject('close')（X/ESC 取消）：不关闭 + snap 保留", async () => {
    const w = mountView()
    const s = useDagTabsStore()
    s.open({ docId: 'd1', name: '一', type: 'wf' })
    seedSnap('d1')
    boxConfirm.mockRejectedValueOnce('close')
    await flushPromises()
    await w.find('.tcd-x').trigger('click')
    await flushPromises()
    expect(s.count).toBe(1)
    expect(s.activeKey).toBe('d1')
    expect(localStorage.getItem('datara.dag.snap.d1')).not.toBeNull()
  })

  it('关闭非激活有草稿 Tab：确认「仍要关闭」resolve → 关 + 清 snap；reject → 不关 + snap 留', async () => {
    for (const confirmed of [true, false]) {
      const w = mountView()
      const s = useDagTabsStore()
      s.open({ docId: 'd1', name: '一', type: 'wf' })
      s.open({ docId: 'd2', name: '二', type: 'sync' })
      s.activate('d1')
      seedSnap('d2')
      await flushPromises() // store 变更后 dagbar v-if 重渲染是异步的，findAll 前必须等
      if (!confirmed) boxConfirm.mockRejectedValueOnce('cancel')
      await w.findAll('[data-tc-dagbar] .tc-dag')[1].find('.tcd-x').trigger('click')
      await flushPromises()
      expect(boxConfirm).toHaveBeenCalledWith(
        expect.stringContaining('未保存的修改草稿'),
        '关闭画布',
        expect.objectContaining({ confirmButtonText: '仍要关闭' }),
      )
      if (confirmed) {
        expect(s.count).toBe(1)
        expect(localStorage.getItem('datara.dag.snap.d2')).toBeNull()
      } else {
        expect(s.count).toBe(2)
        expect(localStorage.getItem('datara.dag.snap.d2')).not.toBeNull()
      }
    }
  })

  it('右上专属操作降级：新建工作流 / 另存为模板（仅激活 Tab 在位）点击均提示接驳', async () => {
    const w = mountView()
    expect(w.find('.tc-save-template').exists()).toBe(false)
    await w.find('[data-testid="new-workflow"]').trigger('click')
    expect(msgInfo).toHaveBeenCalledTimes(1)
    useDagTabsStore().open({ docId: 'd1', name: '一', type: 'wf' })
    await flushPromises()
    expect(w.find('.tc-save-template').exists()).toBe(true)
    await w.find('.tc-save-template').trigger('click')
    expect(msgInfo).toHaveBeenCalledTimes(2)
  })

  it('右上专属操作仅 edit 态在位（templates/runs/alarm 不渲染）', () => {
    for (const k of ['templates', 'runs', 'alarm']) {
      routeQuery.value = { tab: k }
      const w = mountView()
      expect(w.find('[data-testid="new-workflow"]').exists()).toBe(false)
      expect(w.find('.tc-save-template').exists()).toBe(false)
      expect(w.find('.tc-view').exists()).toBe(false)
    }
  })
})

describe('INC4-FE-4 候选池接线（projectId 承接 route.params + 池查真名/类型）', () => {
  const ROW = { id: 42, name: '客户画像', tags: ['同步'], code: 3 }

  it('?doc= 直达查池真名：Tab name/tags 类型推导/code 直通 + last 按类型落盘', async () => {
    routeParams.value = { projectId: '7' }
    routeQuery.value = { doc: '42' }
    poolLoad.mockResolvedValue([ROW])
    mountView()
    await flushPromises()
    expect(poolLoad).toHaveBeenCalledWith(7)
    const s = useDagTabsStore()
    expect(s.count).toBe(1)
    expect(s.activeTab).toMatchObject({ docId: '42', name: '客户画像', type: 'sync', code: 3 })
    expect(localStorage.getItem('datara.dag.last.sync')).toBe('42')
    expect(localStorage.getItem('datara.dag.lastType')).toBe('sync')
  })

  it('last 恢复查池真名：last.sync 命中池 → 真名 + tags 类型（FE-2 占位名升真）', async () => {
    routeParams.value = { projectId: '7' }
    localStorage.setItem('datara.dag.lastType', 'sync')
    localStorage.setItem('datara.dag.last.sync', '42')
    poolLoad.mockResolvedValue([ROW])
    mountView()
    await flushPromises()
    const s = useDagTabsStore()
    expect(s.count).toBe(1)
    expect(s.activeTab).toMatchObject({ docId: '42', name: '客户画像', type: 'sync', code: 3 })
  })

  it('陈旧 last 清理：池非空且目标已删 → last 双键清落盘 + 不开 Tab（蓝本 L272-274）', async () => {
    routeParams.value = { projectId: '7' }
    localStorage.setItem('datara.dag.lastType', 'sync')
    localStorage.setItem('datara.dag.last.sync', '99')
    poolLoad.mockResolvedValue([ROW])
    mountView()
    await flushPromises()
    expect(useDagTabsStore().count).toBe(0)
    expect(localStorage.getItem('datara.dag.last.sync')).toBe('')
    expect(localStorage.getItem('datara.dag.lastType')).toBe('')
  })

  it('池不可用保底：候选池拉取失败 → last 占位打开（name=docId / type wf 兜底）', async () => {
    routeParams.value = { projectId: '7' }
    localStorage.setItem('datara.dag.last', 'd7')
    poolLoad.mockRejectedValue(new Error('backend not ready'))
    mountView()
    await flushPromises()
    const s = useDagTabsStore()
    expect(s.count).toBe(1)
    expect(s.activeTab).toMatchObject({ docId: 'd7', name: 'd7', type: 'wf' })
  })

  it('onPickTasks 池命中：item 自带名/类型被池真名覆盖（PoolMeta 直通 openTab）', async () => {
    routeParams.value = { projectId: '7' }
    poolLoad.mockResolvedValue([{ id: 42, name: '客户画像', tags: ['流'], code: 3 }])
    const w = mountView()
    await flushPromises() // onMounted loadDefPool → defPool 就绪后再 pick
    pickTasks(w, [{ id: '42', name: 'Palette 行占位名', type: 'stream' }])
    await flushPromises()
    const s = useDagTabsStore()
    expect(s.count).toBe(1)
    expect(s.activeTab).toMatchObject({ docId: '42', name: '客户画像', type: 'stream', code: 3 })
    expect(localStorage.getItem('datara.dag.last.stream')).toBe('42')
    expect(localStorage.getItem('datara.dag.lastType')).toBe('stream')
  })
})
