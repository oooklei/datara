// @vitest-environment happy-dom
/**
 * B4 组件设计器挂载用例（happy-dom）：
 * - 编辑模式：加载草稿 + 版本列表（B5），白名单违规行内红标（打字即校验）
 * - 实时预览：F0 FieldRenderer 吃声明数据（select 候选来自声明 options）
 * - 保存：携带当前 draftRev 与编辑器 spec（乐观锁 B2）
 * - 新建模式：无 :type 参数 → 创建表单
 * - D3 发布治理：6003 闸门逐项面板（err.data.items）/ 发布摘要 / 下线确认流 / 升级链路
 * vue-router / componentApi / services 以模块 mock 注入；el-* 组件桩掉消噪音（与 FieldRenderer 用例同法）。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { ElMessageBox } from 'element-plus'

const routeState = vi.hoisted(() => ({ params: { type: 'comp_demo' as string | undefined } }))
const pushSpy = vi.hoisted(() => vi.fn())
const replaceSpy = vi.hoisted(() => vi.fn())
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: routeState.params }),
  useRouter: () => ({ push: pushSpy, replace: replaceSpy }),
}))

const getDraftSpy = vi.hoisted(() => vi.fn())
const listVersionsSpy = vi.hoisted(() => vi.fn())
const getCompSpy = vi.hoisted(() => vi.fn())
const saveDraftSpy = vi.hoisted(() => vi.fn())
const publishCompSpy = vi.hoisted(() => vi.fn())
const offlineCompSpy = vi.hoisted(() => vi.fn())
const rollbackCompSpy = vi.hoisted(() => vi.fn())
const impactedSpy = vi.hoisted(() => vi.fn())
const graphGetSpy = vi.hoisted(() => vi.fn())
const graphSaveSpy = vi.hoisted(() => vi.fn())
const wfPublishSpy = vi.hoisted(() => vi.fn())
const wfOfflineSpy = vi.hoisted(() => vi.fn())
vi.mock('../../../services/componentApi', () => ({
  getComponentDraft: getDraftSpy,
  listComponentVersions: listVersionsSpy,
  getComponent: getCompSpy,
  saveComponentDraft: saveDraftSpy,
  freezeComponentVersion: vi.fn(),
  createComponentDraft: vi.fn(),
  publishComponentVersion: publishCompSpy,
  offlineComponent: offlineCompSpy,
  rollbackComponent: rollbackCompSpy,
  getImpactedWorkflows: impactedSpy,
  getComponentRegistry: vi.fn(),
}))
vi.mock('../../../services', () => ({
  apiMode: 'real',
  isMock: false,
  graphService: { get: graphGetSpy, save: graphSaveSpy },
  offlineWorkflow: wfOfflineSpy,
  publishWorkflow: wfPublishSpy,
}))

import ComponentDesignView from '../ComponentDesignView.vue'

const DRAFT = {
  type: 'comp_demo', name: '演示组件', category: null, profile: 'dag', scope: 'user',
  executionModel: 'dag-engine', executor: null, executable: true, state: 'draft',
  publishedVersion: null, draftRev: 3, draftVersion: 2, description: null, tags: [],
  spec: {
    icon: '⚙', color: '#4C7CF0', summary: '测试声明',
    ports: { inputs: [{ name: 'in', type: 'dataset' }], outputs: [{ name: 'out', type: 'dataset' }] },
    fields: [
      { key: 'mode', label: '模式', uiType: 'select', required: true, desc: '选择模式', options: [{ label: '并行', value: 'parallel' }, { label: '串行', value: 'serial' }] },
      { key: 'dirty', label: '脏字段 =>', uiType: 'text', desc: '' },
    ],
    dropPolicy: { autoName: '演示_{n}', snapToGrid: true, prefillFromUpstream: [], maxInstances: 0 },
  },
  specHash: 'a'.repeat(64), updatedAt: '2026-09-26 10:00:00',
}
const VERSIONS = {
  type: 'comp_demo', publishedVersion: null,
  items: [
    { version: 2, state: 'draft', specHash: 'b'.repeat(64), remark: '初始草稿', publishedBy: null, publishedAt: null, createdAt: '2026-09-26 10:00:00' },
    { version: 1, state: 'frozen', specHash: 'c'.repeat(64), remark: '冻结 v1 后自动开启', publishedBy: null, publishedAt: null, createdAt: '2026-09-26 09:00:00' },
  ],
}

const stubs = {
  /* emits 声明与真实 ElButton 对齐（EP2 声明了 click emit）：不声明时 @click 落入
     attrs，既被 $emit('click') 调用又被原生 fallthrough 各调一次 —— onOffline 一次
     点击执行两次（其 toggling 守卫在 await confirm 之后，挡不住同 tick 重入） */
  ElButton: { emits: ['click'], template: '<button @click="$emit(\'click\')"><slot /></button>' },
  ElInput: { template: '<input />', props: ['modelValue'] },
  ElSelect: { template: '<div class="stub-select"><slot /></div>', props: ['modelValue'] },
  ElOption: { template: '<div />' },
  ElCascader: { template: '<div />' },
  ElTabs: { template: '<div class="stub-tabs"><slot /></div>' },
  ElTabPane: { template: '<div class="stub-pane"><slot /></div>' },
  ElAlert: { template: '<div class="stub-alert"><slot /></div>', props: ['title'] },
  /* D3 发布治理引入表格：未 stub 时 el-table 被当原生元素，Vue 会无参调用
     scoped slot（{ row } 解构崩），必须桩为组件并吞掉列内容 */
  ElTable: { props: ['data'], template: '<div class="stub-table"><slot /></div>' },
  ElTableColumn: { template: '<div class="stub-col"></div>' },
}

function mountView() {
  setActivePinia(createPinia())
  return mount(ComponentDesignView, { global: { components: stubs, directives: { loading: {} } } })
}

/** setupState 经 proxyRefs 包装，ref 取值可能是裸值也可能是 Ref——两种都兼容 */
function unwrap<T>(v: unknown): T {
  return (v && typeof v === 'object' && 'value' in (v as Record<string, unknown>)
    ? (v as { value: T }).value
    : v) as T
}

beforeEach(() => {
  vi.clearAllMocks()
  routeState.params.type = 'comp_demo'
  /* structuredClone 隔离：保存用例回写 d.draftRev 会改写共享对象，污染后续用例
     （6003 断言 draftRev=3 却收到 4）；DRAFT 纯数据可安全深拷贝 */
  getDraftSpy.mockResolvedValue(structuredClone(DRAFT))
  listVersionsSpy.mockResolvedValue(VERSIONS)
})

describe('ComponentDesignView（M1 B4 设计器）', () => {
  it('编辑模式：加载草稿与版本列表，白名单违规行内红标', async () => {
    const w = mountView()
    await flushPromises()
    expect(getDraftSpy).toHaveBeenCalledWith('comp_demo')
    expect(w.text()).toContain('演示组件')
    expect(w.text()).toContain('comp_demo')
    // 版本列表：v2 草稿 + v1 冻结（B5）
    expect(w.text()).toContain('冻结')
    expect(w.text()).toContain('草稿')
    // 白名单违规：fields[1].label 含「=>」→ 行内红标 + 违规说明
    expect(w.findAll('.frow.bad').length).toBe(1)
    expect(w.text()).toContain('含代码片段「=>」')
    // 编辑区 Tabs 挂载
    expect(w.find('.stub-tabs').exists()).toBe(true)
  })

  it('实时预览：声明字段渲染（select 候选来自 options，依赖上下文控件略）', async () => {
    const w = mountView()
    await flushPromises()
    const preview = w.find('.preview')
    expect(preview.exists()).toBe(true)
    const optionVals = preview.findAll('option').map((o) => o.element as HTMLOptionElement)
    expect(optionVals.some((o) => o.value === 'parallel')).toBe(true)
    expect(optionVals.some((o) => o.value === 'serial')).toBe(true)
    // 必填星标 + 字段名来自声明
    expect(preview.text()).toContain('模式')
    expect(preview.find('.pv-label i').exists()).toBe(true)
  })

  it('保存：携带当前 draftRev 与编辑器 spec；成功后 rev 前进', async () => {
    saveDraftSpy.mockResolvedValue({ draftRev: 4, specHash: 'd'.repeat(64), savedAt: '2026-09-26 11:00:00' })
    const w = mountView()
    await flushPromises()
    const saveBtn = w.findAll('button').find((b) => b.text() === '保存')
    expect(saveBtn).toBeTruthy()
    await saveBtn!.trigger('click')
    await flushPromises()
    expect(saveDraftSpy).toHaveBeenCalledTimes(1)
    const [type, body] = saveDraftSpy.mock.calls[0] as [string, { draftRev: number; spec: Record<string, unknown> }]
    expect(type).toBe('comp_demo')
    expect(body.draftRev).toBe(3)
    expect(body.spec).toBeTruthy()
    expect(w.text()).toContain('rev 4')
  })

  it('新建模式：无 :type → 创建表单（身份字段 + 创建草稿按钮）', async () => {
    routeState.params.type = undefined
    const w = mountView()
    await flushPromises()
    expect(getDraftSpy).not.toHaveBeenCalled()
    expect(w.text()).toContain('新建组件草稿')
    expect(w.text()).toContain('创建草稿')
    expect(w.find('.preview').exists()).toBe(false)
  })
})

/* ================= D3 发布治理（闸门面板 / 发布摘要 / 下线 / 升级链路） ================= */

/** D3 用例追加桩：ElSelect 走原生 select（可赋值触发 update:modelValue）；表格桩沿用基础 stubs */
const D3_STUBS = {
  ...stubs,
  ElSelect: {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<select class="stub-select" @change="$emit(\'update:modelValue\', Number($event.target.value))"><slot /></select>',
  },
  ElOption: { props: ['value', 'label'], template: '<option :value="value">{{ label }}</option>' },
}

function mountViewD3() {
  setActivePinia(createPinia())
  return mount(ComponentDesignView, { global: { components: D3_STUBS, directives: { loading: {} } } })
}

async function choosePublishTarget(w: Awaited<ReturnType<typeof mountViewD3>>): Promise<void> {
  const sel = w.find('.stub-select')
  ;(sel.element as HTMLSelectElement).value = '1'
  await sel.trigger('change')
  const pubBtn = w.findAll('button').find((b) => b.text() === '发布')
  await pubBtn!.trigger('click')
  await flushPromises()
}

describe('ComponentDesignView 发布治理（D3）', () => {
  it('发布闸门未过（6003）→ err.data.items 逐项渲染面板，通过/未过分色', async () => {
    publishCompSpy.mockRejectedValueOnce(Object.assign(new Error('发布闸门未通过'), {
      code: 6003,
      data: { items: [
        { gate: 'pure_data', ok: false, msg: '图标含函数片段' },
        { gate: 'contract', ok: false, msg: 'executor 未绑定' },
        { gate: 'hash_consistency', ok: true, msg: '通过' },
      ] },
    }))
    const w = mountViewD3()
    await flushPromises()
    await choosePublishTarget(w)
    expect(publishCompSpy).toHaveBeenCalledWith('comp_demo', { version: 1, draftRev: 3, remark: undefined })
    expect(w.findAll('.gate-row')).toHaveLength(3)
    expect(w.findAll('.gate-row.bad')).toHaveLength(2)
    expect(w.text()).toContain('纯数据')
    expect(w.text()).toContain('执行契约')
    expect(w.text()).toContain('图标含函数片段')
    expect(w.text()).toContain('1/3 通过')
    expect(w.find('.pub-ok').exists()).toBe(false)
  })

  it('发布成功 → 渲染摘要并重拉草稿', async () => {
    publishCompSpy.mockResolvedValueOnce({
      type: 'comp_demo', publishedVersion: 1, specHash: 'e'.repeat(64),
      supersededVersion: null, publishedAt: '2026-09-27 10:00:00',
    })
    const w = mountViewD3()
    await flushPromises()
    await choosePublishTarget(w)
    expect(w.find('.pub-ok').exists()).toBe(true)
    expect(w.text()).toContain('已发布 v1')
    expect(getDraftSpy).toHaveBeenCalledTimes(2) // 初始 + 发布后 reload
  })

  it('下线组件：确认后调 offlineComponent 并重拉草稿', async () => {
    getDraftSpy.mockResolvedValue({ ...DRAFT, state: 'published', publishedVersion: 1 })
    const confirmSpy = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as never)
    offlineCompSpy.mockResolvedValue({ type: 'comp_demo', state: 'offline', publishedVersion: 1 })
    const w = mountViewD3()
    await flushPromises()
    const btn = w.findAll('button').find((b) => b.text() === '下线组件')
    expect(btn).toBeTruthy()
    await btn!.trigger('click')
    await flushPromises()
    expect(confirmSpy).toHaveBeenCalled()
    expect(offlineCompSpy).toHaveBeenCalledWith('comp_demo')
    expect(getDraftSpy).toHaveBeenCalledTimes(2)
  })

  it('升级链路（upgradeOne）：online 先下线 → patch 引用版本 → save → 重新上线；已对齐节点不动', async () => {
    graphGetSpy.mockResolvedValue({
      id: 'wf_a', name: '流A', version: 4, meta: { profile: 'dag' }, edges: [],
      nodes: [
        { id: 'n1', type: 'comp_demo', position: { x: 0, y: 0 }, data: { componentRef: { type: 'comp_demo', version: 1 } } },
        { id: 'n2', type: 'comp_demo', position: { x: 1, y: 1 }, data: { componentRef: { type: 'comp_demo', version: 3 } } },
        { id: 'n3', type: 'other', position: { x: 2, y: 2 }, data: {} },
      ],
    })
    graphSaveSpy.mockResolvedValue({ version: 5 })
    wfOfflineSpy.mockResolvedValue({ release_state: 'offline' })
    wfPublishSpy.mockResolvedValue({ release_state: 'online' })
    const w = mountViewD3()
    await flushPromises()
    const setup = (w.vm.$ as unknown as { setupState: Record<string, unknown> }).setupState
    const upgradeOne = setup.upgradeOne as (row: unknown, pv: number) => Promise<{ ok: boolean; msg: string }>
    const r = await upgradeOne(
      { id: 'wf_a', name: '流A', code: 11, version: 4, releaseState: 'online', refVersions: [1, 3], behind: true, aligned: false },
      3,
    )
    expect(r.ok).toBe(true)
    expect(wfOfflineSpy).toHaveBeenCalledWith('wf_a')
    expect(graphSaveSpy).toHaveBeenCalledTimes(1)
    expect(graphSaveSpy.mock.calls[0][1]).toContain('comp_demo') // save remark 携带组件 type
    const saved = graphSaveSpy.mock.calls[0][0] as { nodes: { data: { componentRef?: { version: number } } }[] }
    expect(saved.nodes[0].data.componentRef?.version).toBe(3) // v1 → v3 升级
    expect(saved.nodes[1].data.componentRef?.version).toBe(3) // 已对齐不动
    expect(saved.nodes[2].data.componentRef).toBeUndefined() // 非 ref 节点不碰
    expect(wfPublishSpy).toHaveBeenCalledWith('wf_a')
  })

  /* 回归用例（审计发现）：此前 loadImpacted 调用的 getImpactedWorkflows 漏 import，
     ReferenceError 被 loadImpacted 的 catch 吞掉仅弹 toast，而 D3 用例无一触发
     release tab → 该分支从未执行，264 用例全绿仍漏检。此处直接驱动该函数，
     spy 未被调用即失败（import 缺失时调用点在到达 mock 前就抛错）。 */
  it('影响面加载（loadImpacted）：调 getImpactedWorkflows 并回填 items/meta', async () => {
    getDraftSpy.mockResolvedValue({ ...DRAFT, state: 'published', publishedVersion: 3 })
    impactedSpy.mockResolvedValue({
      type: 'comp_demo', publishedVersion: 3, state: 'published',
      items: [
        { id: 'wf_a', code: 11, name: '流A', version: 4, releaseState: 'online', refVersions: [1], behind: true, aligned: false },
        { id: 'wf_b', code: 12, name: '流B', version: 2, releaseState: 'offline', refVersions: [3], behind: false, aligned: true },
      ],
    })
    const w = mountViewD3()
    await flushPromises()
    const setup = (w.vm.$ as unknown as { setupState: Record<string, unknown> }).setupState
    await (setup.loadImpacted as () => Promise<void>)()
    expect(impactedSpy).toHaveBeenCalledWith('comp_demo')
    expect(unwrap<unknown[]>(setup.impacted)).toHaveLength(2)
    expect(unwrap<{ publishedVersion: number | null; state: string }>(setup.impactedMeta))
      .toEqual({ publishedVersion: 3, state: 'published' })
  })
})

/* ================= R2：409(6002) 且内置组件 → 引导至基线化工作台 ================= */

describe('ComponentDesignView builtin 引导（R2）', () => {
  beforeEach(() => {
    /* 内置组件走基线化治理链（无 M1 草稿行）：draft 必 409(6002)；版本列表空态；
       详情端点（GET /components/{type}）仅服务内置目录快照——成功即内置（与用户组件 404 天然互斥） */
    routeState.params.type = 'sql'
    getDraftSpy.mockRejectedValue(Object.assign(new Error('无进行中的草稿，请新建草稿版本'), { code: 6002 }))
    listVersionsSpy.mockResolvedValue({ items: [] })
    getCompSpy.mockResolvedValue({ type: 'sql', label: 'SQL 转换' })
  })

  it('409(6002) + 内置组件 → 显示基线化引导而非报错', async () => {
    const w = mountView()
    await flushPromises()
    expect(getDraftSpy).toHaveBeenCalledWith('sql')
    expect(getCompSpy).toHaveBeenCalledWith('sql')
    expect(w.text()).toContain('内置组件')
    expect(w.text()).toContain('基线化工作台')
    expect(w.text()).not.toContain('草稿加载失败')
    const setup = (w.vm.$ as unknown as { setupState: Record<string, unknown> }).setupState
    expect(unwrap<{ type: string }>(setup.builtinGuide)).toEqual({ type: 'sql' })
  })

  it('409(6002) 但详情失败（如用户组件异常无草稿）→ 维持原报错展示', async () => {
    getCompSpy.mockRejectedValue(new Error('组件不存在: sql'))
    const w = mountView()
    await flushPromises()
    expect(w.text()).not.toContain('基线化工作台')
    const setup = (w.vm.$ as unknown as { setupState: Record<string, unknown> }).setupState
    /* 引导未置位 + 报错信息已赋值（error alert title 绑定 loadErr；stub 不渲染 title，故以状态断言） */
    expect(unwrap<unknown>(setup.builtinGuide)).toBeNull()
    expect(unwrap<string>(setup.loadErr)).toContain('无进行中的草稿')
  })
})
