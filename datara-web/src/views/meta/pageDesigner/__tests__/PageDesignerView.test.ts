// @vitest-environment happy-dom
/**
 * Task 13 设计器页壳挂载用例（happy-dom）：
 * - 路由表：/meta/components/page-designer/:type? 条目（懒加载 + title）
 * - 编辑态：三区域容器（palette/canvas/inspector）+ 工具条按钮齐全
 * - 刷新：重载 getResources（spy +1）
 * - 预览：调 preview() 并把结果传给画布（stub PageCanvas 收 preview prop）
 * - 保存：携带 draftRev 乐观锁 + spec={page}
 * - 发布链：确认 → freeze → publish → toast「已刷新 N 个图引用」；响应无 refresh 时兜底 refreshRefs
 * - 新建态：名称 + 4 页面模板卡 → createPageDraft → router.replace 深链
 * vue-router / pageApi / componentApi 以模块 mock 注入；三个子组件与 el-* 桩掉消噪音
 * （stub + emits 对齐写法同 ComponentDesignView.test.ts）。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ElMessage, ElMessageBox } from 'element-plus'
import { routes } from '../../../../router/routes'

const routeState = vi.hoisted(() => ({ params: { type: 'page_demo' as string | undefined } }))
const pushSpy = vi.hoisted(() => vi.fn())
const replaceSpy = vi.hoisted(() => vi.fn())
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: routeState.params }),
  useRouter: () => ({ push: pushSpy, replace: replaceSpy }),
}))

const getResourcesSpy = vi.hoisted(() => vi.fn())
const previewSpy = vi.hoisted(() => vi.fn())
const refreshRefsSpy = vi.hoisted(() => vi.fn())
vi.mock('../pageApi', () => ({
  pageApi: { getResources: getResourcesSpy, preview: previewSpy, refreshRefs: refreshRefsSpy },
}))

const getDraftSpy = vi.hoisted(() => vi.fn())
const listVersionsSpy = vi.hoisted(() => vi.fn())
const saveDraftSpy = vi.hoisted(() => vi.fn())
const freezeSpy = vi.hoisted(() => vi.fn())
const publishSpy = vi.hoisted(() => vi.fn())
const createPageDraftSpy = vi.hoisted(() => vi.fn())
const createComponentDraftSpy = vi.hoisted(() => vi.fn())
const getComponentSpy = vi.hoisted(() => vi.fn())
const deleteComponentSpy = vi.hoisted(() => vi.fn())
vi.mock('../../../../services/componentApi', () => ({
  getComponentDraft: getDraftSpy,
  listComponentVersions: listVersionsSpy,
  saveComponentDraft: saveDraftSpy,
  freezeComponentVersion: freezeSpy,
  publishComponentVersion: publishSpy,
  createPageDraft: createPageDraftSpy,
  createComponentDraft: createComponentDraftSpy,
  getComponent: getComponentSpy,
  deleteComponent: deleteComponentSpy,
}))

/* 子组件桩：容器 testid 由宿主承担，这里只验证宿主给画布的 props（preview 透传） */
vi.mock('../canvas/PageCanvas.vue', () => ({
  default: {
    name: 'PageCanvasStub',
    props: {
      page: { type: Object, required: true },
      selectedId: { type: String, default: undefined },
      selectedIds: { type: Array, default: undefined },
      preview: { type: Object, default: undefined },
    },
    emits: ['add', 'select', 'move', 'resize', 'canvasSize'],
    template: '<div class="stub-canvas" :data-preview="preview ? \'on\' : \'off\'" :data-count="page.widgets.length" />',
  },
}))
vi.mock('../palette/PagePalette.vue', () => ({ default: { name: 'PagePaletteStub', template: '<aside class="stub-palette" />' } }))
vi.mock('../inspector/PageInspector.vue', () => ({
  default: {
    name: 'PageInspectorStub',
    props: ['page', 'selectedId', 'catalog'],
    emits: ['updateWidget', 'updateCanvas', 'reorder'],
    template: '<aside class="stub-inspector" />',
  },
}))
/* fields 模式子组件桩：验证宿主透传（行数/来源）与受控事件回抛 */
vi.mock('../fields/FieldsCanvas.vue', () => ({
  default: {
    name: 'FieldsCanvasStub',
    props: ['rows', 'selectedIdx'],
    emits: ['select'],
    template: '<div class="stub-fcanvas" :data-count="rows.length" />',
  },
}))
vi.mock('../fields/FieldsInspector.vue', () => ({
  default: {
    name: 'FieldsInspectorStub',
    props: ['rows', 'dropPolicy', 'selectedIdx', 'source'],
    emits: ['select', 'patchRow', 'addRow', 'removeRow', 'moveRow', 'patchDropPolicy'],
    template: '<aside class="stub-finspector" />',
  },
}))

import PageDesignerView from '../PageDesignerView.vue'

const DRAFT = {
  type: 'page_demo', name: '演示页面', category: null, profile: 'dag', scope: 'user',
  executionModel: 'page', executor: null, executable: false, state: 'draft',
  publishedVersion: null, draftRev: 3, draftVersion: 2, description: null, tags: [],
  spec: {
    page: {
      version: 1, name: '演示页面', icon: 'block', color: '#1677ff',
      canvas: { width: 288, height: 520, background: { fill: '#ffffff', size: 'cover' } },
      widgets: [
        {
          id: 'wq', kind: 'table', rect: { x: 8, y: 40, w: 264, h: 160 },
          props: { columns: [{ title: '名称', dataIndex: 'name' }], emptyText: '暂无数据' }, style: {},
          bindings: { data: { kind: 'query', datasourceId: 1, query: 'SELECT name FROM t_user', fallback: '数据集' } },
        },
      ],
    },
  },
  specHash: 'a'.repeat(64), updatedAt: '2026-10-03 10:00:00',
}
const VERSIONS = {
  type: 'page_demo', publishedVersion: null,
  items: [
    { version: 2, state: 'draft', specHash: 'b'.repeat(64), remark: '初始草稿', publishedBy: null, publishedAt: null, createdAt: '2026-10-03 10:00:00' },
    { version: 1, state: 'frozen', specHash: 'c'.repeat(64), remark: '冻结 v1', publishedBy: null, publishedAt: null, createdAt: '2026-10-02 09:00:00' },
  ],
}
const CATALOG = {
  datasources: [{ id: 1, name: '主库', type: 'postgres', db: 'pg_main' }],
  workflows: [], globalParams: [], timeParams: [], components: [],
}

const stubs = {
  /* emits 与真实 ElButton 对齐（click 声明），避免 attrs fallthrough 双触发 */
  ElButton: { emits: ['click'], template: '<button @click="$emit(\'click\')"><slot /></button>' },
  ElInput: { props: ['modelValue'], emits: ['update:modelValue'], template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />' },
  ElTag: { template: '<span class="stub-tag"><slot /></span>' },
  ElDropdown: { template: '<div class="stub-dropdown"><slot /></div>' },
  ElDropdownMenu: { template: '<div><slot /></div>' },
  ElDropdownItem: { template: '<div><slot /></div>' },
  ElAlert: { props: ['title'], template: '<div class="stub-alert">{{ title }}<slot /></div>' },
}

function mountView() {
  return mount(PageDesignerView, { global: { components: stubs, directives: { loading: {} } } })
}

const tb = (w: ReturnType<typeof mountView>, id: string) => w.find(`[data-testid="tb-${id}"]`)

beforeEach(() => {
  vi.clearAllMocks()
  routeState.params.type = 'page_demo'
  getDraftSpy.mockResolvedValue(structuredClone(DRAFT))
  listVersionsSpy.mockResolvedValue(structuredClone(VERSIONS))
  getResourcesSpy.mockResolvedValue(structuredClone(CATALOG))
})

describe('PageDesignerView（Task 13 页壳）', () => {
  it('路由表：/meta/components/page-designer/:type? redirect 落宿主设计器页签（title 组件设计器）', () => {
    const r = routes.find((x) => x.path === '/meta/components/page-designer/:type?')
    expect(r).toBeTruthy()
    expect(r?.meta?.title).toBe('组件设计器')
    expect(typeof r?.redirect).toBe('function')
    const fn = r!.redirect as (t: { params: Record<string, string> }) => { path: string; query: Record<string, string> }
    const withType = fn({ params: { type: 'page_demo' } })
    expect(withType.path).toBe('/meta/components')
    expect(withType.query).toMatchObject({ tab: 'designer', designType: 'page_demo' })
    const noType = fn({ params: {} })
    expect(noType.query).toMatchObject({ tab: 'designer' })
    expect(noType.query.designType).toBeUndefined()
  })

  it('嵌入态（ComponentHub）：designType prop 优先于 route.params；新建成功 emit designTypeChange', async () => {
    routeState.params.type = 'page_route_other' // 路由残留不应生效
    mount(PageDesignerView, {
      props: { designType: 'page_demo' },
      global: { components: stubs, directives: { loading: {} } },
    })
    await flushPromises()
    expect(getDraftSpy).toHaveBeenCalledTimes(1)
    expect(getDraftSpy).toHaveBeenCalledWith('page_demo')
    // 嵌入新建态：designType='' → emit 回调而非 router.replace
    const w2 = mount(PageDesignerView, {
      props: { designType: '' },
      global: { components: stubs, directives: { loading: {} } },
    })
    await flushPromises()
    expect(getDraftSpy).toHaveBeenCalledTimes(1) // 新建态不加载草稿
    createPageDraftSpy.mockResolvedValue({ type: 'page_new_x', draftRev: 0, draftVersion: 1 })
    await w2.find('input').setValue('宿主新页')
    const createBtn = w2.findAll('button').find((b) => b.text() === '创建')
    await createBtn!.trigger('click')
    await flushPromises()
    /* type 由客户端生成（中文 slug 为空 → page_ui_ + 时间戳36进制），emit 生成值而非响应值 */
    const emittedType = w2.emitted('designTypeChange')?.[0]?.[0] as string
    expect(emittedType).toMatch(/^page_ui_[0-9a-z]+$/)
    expect(createPageDraftSpy).toHaveBeenCalledWith(expect.objectContaining({ type: emittedType, name: '宿主新页' }))
    expect(replaceSpy).not.toHaveBeenCalled()
  })

  it('6002（有历史版本无进行中草稿）：后端已自动开修订 → 重拉一次成功加载', async () => {
    getDraftSpy.mockRejectedValueOnce(Object.assign(new Error('无进行中的草稿'), { code: 6002 }))
    const w = mountView()
    await flushPromises()
    expect(getDraftSpy).toHaveBeenCalledTimes(2)
    expect(w.find('[data-testid="pd-canvas-stage"]').exists()).toBe(true)
    expect(w.find('.stub-alert').exists()).toBe(false)
  })

  it('编辑态挂载：三区域容器 + 工具条按钮齐全 + 加载草稿/目录', async () => {
    const w = mountView()
    await flushPromises()
    expect(getDraftSpy).toHaveBeenCalledWith('page_demo')
    expect(getResourcesSpy).toHaveBeenCalledTimes(1)
    expect(w.find('[data-testid="pd-palette"]').exists()).toBe(true)
    expect(w.find('[data-testid="pd-canvas-stage"]').exists()).toBe(true)
    expect(w.find('[data-testid="pd-inspector"]').exists()).toBe(true)
    expect(w.find('.stub-canvas').exists()).toBe(true)
    for (const id of ['undo', 'redo', 'copy', 'paste', 'delete', 'align-left', 'align-top', 'dist-h', 'dist-v', 'zoom', 'refresh', 'save', 'preview', 'publish']) {
      expect(tb(w, id).exists(), `工具条按钮 tb-${id} 应存在`).toBe(true)
      expect(tb(w, id).text().length).toBeGreaterThan(0)
    }
    expect(w.text()).toContain('撤销')
    expect(w.text()).toContain('刷新')
    expect(w.text()).toContain('发布')
  })

  it('刷新：点击触发 getResources 重载（spy +1）', async () => {
    const w = mountView()
    await flushPromises()
    expect(getResourcesSpy).toHaveBeenCalledTimes(1)
    await tb(w, 'refresh').trigger('click')
    await flushPromises()
    expect(getResourcesSpy).toHaveBeenCalledTimes(2)
    expect(getDraftSpy).toHaveBeenCalledTimes(2) // 草稿同步重拉
  })

  it('预览：点击触发 preview() 并把结果传给画布（stub 收 preview prop）', async () => {
    previewSpy.mockResolvedValue({ results: { wq: { columns: ['a'], rows: [['1']], truncated: false, error: '' } }, rowCap: 100 })
    const w = mountView()
    await flushPromises()
    expect(w.find('.stub-canvas').attributes('data-preview')).toBe('off')
    await tb(w, 'preview').trigger('click')
    await flushPromises()
    expect(previewSpy).toHaveBeenCalledTimes(1)
    const [qs] = previewSpy.mock.calls[0] as [{ id: string; datasourceId: number; sql: string }[]]
    expect(qs).toHaveLength(1)
    expect(qs[0].id).toBe('wq')
    expect(qs[0].datasourceId).toBe(1)
    expect(w.find('.stub-canvas').attributes('data-preview')).toBe('on')
  })

  it('预览收集：query 绑定仅 datasourceId 无 SQL → 不进 preview（渲染模板样例数据）', async () => {
    const draft = structuredClone(DRAFT)
    // 数据源引用型绑定新形状：仅 datasourceId 无 SQL（query 字段缺省）
    const data = draft.spec.page.widgets[0].bindings.data as unknown as Record<string, unknown>
    delete data.query
    getDraftSpy.mockResolvedValue(draft)
    const w = mountView()
    await flushPromises()
    await tb(w, 'preview').trigger('click')
    await flushPromises()
    expect(previewSpy).not.toHaveBeenCalled()
    // 无查询绑定仍进入预览态（样例数据渲染）
    expect(w.find('.stub-canvas').attributes('data-preview')).toBe('on')
  })

  it('预览失败汇总：响应含 widgetErrors → 弹 warning 且仍进入预览态', async () => {
    previewSpy.mockResolvedValue({
      results: { wq: { columns: [], rows: [], truncated: false, error: '数据源 999 不存在' } },
      rowCap: 100,
      widgetErrors: [{ id: 'wq', error: '数据源 999 不存在' }],
    })
    const warnSpy = vi.spyOn(ElMessage, 'warning').mockImplementation((() => ({})) as never)
    const w = mountView()
    await flushPromises()
    await tb(w, 'preview').trigger('click')
    await flushPromises()
    expect(warnSpy).toHaveBeenCalledTimes(1)
    const toast = String(warnSpy.mock.calls[0][0])
    expect(toast).toContain('1 个组件预览失败')
    expect(toast).toContain('数据源 999 不存在')
    // 汇总提示不中断预览态
    expect(w.find('.stub-canvas').attributes('data-preview')).toBe('on')
    vi.restoreAllMocks()
  })

  it('保存：携带 draftRev 乐观锁 + spec={page}', async () => {
    saveDraftSpy.mockResolvedValue({ draftRev: 4, specHash: 'd'.repeat(64), savedAt: '2026-10-03 11:00:00' })
    const w = mountView()
    await flushPromises()
    await tb(w, 'save').trigger('click')
    await flushPromises()
    expect(saveDraftSpy).toHaveBeenCalledTimes(1)
    const [type, body] = saveDraftSpy.mock.calls[0] as [string, { draftRev: number; spec: Record<string, unknown> }]
    expect(type).toBe('page_demo')
    expect(body.draftRev).toBe(3)
    expect((body.spec.page as { name: string }).name).toBe('演示页面')
  })

  it('粘贴：缓冲为空禁用；复制后点粘贴 widgets 数 +1', async () => {
    const w = mountView()
    await flushPromises()
    // 缓冲为空 → 粘贴禁用
    expect(tb(w, 'paste').attributes('disabled')).toBeDefined()
    // 选中 wq（stub canvas emit select）→ 复制 → widgets 1→2
    w.findComponent({ name: 'PageCanvasStub' }).vm.$emit('select', 'wq')
    await flushPromises()
    await tb(w, 'copy').trigger('click')
    expect(w.find('.stub-canvas').attributes('data-count')).toBe('2')
    expect(tb(w, 'paste').attributes('disabled')).toBeUndefined()
    // 粘贴 → widgets 2→3（深拷贝缓冲 + 新 id + 12px 偏移）
    await tb(w, 'paste').trigger('click')
    expect(w.find('.stub-canvas').attributes('data-count')).toBe('3')
  })

  it('层级：inspector emit reorder → 宿主按数组序调整 widgets（top 移末尾 / down 交换）', async () => {
    const w = mountView()
    await flushPromises()
    // 复制一个 widget 使数组有 2 项（wq 在前，克隆在后）
    w.findComponent({ name: 'PageCanvasStub' }).vm.$emit('select', 'wq')
    await flushPromises()
    await tb(w, 'copy').trigger('click')
    await flushPromises()
    const idsOf = () =>
      (w.findComponent({ name: 'PageCanvasStub' }).props('page') as { widgets: { id: string }[] }).widgets.map((x) => x.id)
    expect(idsOf()).toHaveLength(2)
    // wq（首位）top → 移到末尾（靠后者上层渲染）
    w.findComponent({ name: 'PageInspectorStub' }).vm.$emit('reorder', 'wq', 'top')
    await flushPromises()
    expect(idsOf()[1]).toBe('wq')
    // wq（末位）down → 与前一位交换回首位
    w.findComponent({ name: 'PageInspectorStub' }).vm.$emit('reorder', 'wq', 'down')
    await flushPromises()
    expect(idsOf()[0]).toBe('wq')
  })

  it('发布主路径：确认 → freeze → publish → toast「已刷新 2 个图引用」', async () => {
    freezeSpy.mockResolvedValue({ frozenVersion: 2, draftVersion: 3, draftRev: 0 })
    publishSpy.mockResolvedValue({
      type: 'page_demo', publishedVersion: 1, specHash: 'e'.repeat(64),
      supersededVersion: null, publishedAt: '2026-10-03 12:00:00',
      refresh: { refreshed: 2, publishedVersion: 1, items: [] },
    })
    const confirmSpy = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as never)
    const successSpy = vi.spyOn(ElMessage, 'success').mockImplementation((() => ({})) as never)
    const errorSpy = vi.spyOn(ElMessage, 'error').mockImplementation((() => ({})) as never)
    const w = mountView()
    await flushPromises()
    await tb(w, 'publish').trigger('click')
    await flushPromises()
    expect(confirmSpy).toHaveBeenCalled()
    expect(freezeSpy).toHaveBeenCalledWith('page_demo')
    expect(publishSpy).toHaveBeenCalledWith('page_demo', { version: 2, draftRev: 0 })
    const toasts = successSpy.mock.calls.map((c) => String(c[0])).join('｜')
    expect(toasts).toContain('已刷新 2 个图引用')
    expect(errorSpy).not.toHaveBeenCalled()
    // 发布后重拉本地状态（草稿 + 版本）
    expect(getDraftSpy).toHaveBeenCalledTimes(2)
    vi.restoreAllMocks()
  })

  it('发布兜底：publish 响应无 refresh → 调 pageApi.refreshRefs', async () => {
    freezeSpy.mockResolvedValue({ frozenVersion: 2, draftVersion: 3, draftRev: 0 })
    publishSpy.mockResolvedValue({
      type: 'page_demo', publishedVersion: 1, specHash: 'e'.repeat(64),
      supersededVersion: null, publishedAt: '2026-10-03 12:00:00',
    })
    refreshRefsSpy.mockResolvedValue({ refreshed: 0, publishedVersion: 1, items: [] })
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as never)
    const successSpy = vi.spyOn(ElMessage, 'success').mockImplementation((() => ({})) as never)
    vi.spyOn(ElMessage, 'error').mockImplementation((() => ({})) as never)
    const w = mountView()
    await flushPromises()
    await tb(w, 'publish').trigger('click')
    await flushPromises()
    expect(refreshRefsSpy).toHaveBeenCalledWith('page_demo')
    const toasts = successSpy.mock.calls.map((c) => String(c[0])).join('｜')
    expect(toasts).toContain('无引用需要刷新')
    vi.restoreAllMocks()
  })
})

describe('PageDesignerView 新建态（无 :type）', () => {
  beforeEach(() => {
    routeState.params.type = undefined
    getDraftSpy.mockClear()
  })

  it('新建卡：名称输入 + 4 个页面模板卡 + 创建按钮；不加载草稿', async () => {
    const w = mountView()
    await flushPromises()
    expect(getDraftSpy).not.toHaveBeenCalled()
    expect(w.find('[data-testid="pd-canvas-stage"]').exists()).toBe(false)
    for (const name of ['空白页', '数据看板', '表单页', '列表页']) expect(w.text()).toContain(name)
    expect(w.find('input').exists()).toBe(true)
    expect(w.text()).toContain('创建')
  })

  it('创建：createPageDraft（type 以 page_ 开头 + 选定模板 page）→ router.replace 深链', async () => {
    createPageDraftSpy.mockResolvedValue({ type: 'page_x', draftRev: 0, draftVersion: 1 })
    const w = mountView()
    await flushPromises()
    await w.find('input').setValue('我的看板')
    // 选择「数据看板」模板卡（heading/statistic/statistic/chart-bar/table 共 5 widget）
    const card = w.findAll('.pd-tpl-card').find((c) => c.text().includes('数据看板'))
    expect(card).toBeTruthy()
    await card!.trigger('click')
    const createBtn = w.findAll('button').find((b) => b.text() === '创建')
    expect(createBtn).toBeTruthy()
    await createBtn!.trigger('click')
    await flushPromises()
    expect(createPageDraftSpy).toHaveBeenCalledTimes(1)
    const body = createPageDraftSpy.mock.calls[0][0] as { type: string; name: string; page: { name: string; widgets: unknown[] } }
    expect(body.name).toBe('我的看板')
    expect(body.type).toMatch(/^page_[a-z0-9_]+$/)
    expect(body.page.name).toBe('我的看板')
    expect(body.page.widgets).toHaveLength(5)
    expect(replaceSpy).toHaveBeenCalledWith(expect.stringMatching(/^\/meta\/components\/page-designer\//))
  })

  it('名称为空：不调用 createPageDraft 并提示', async () => {
    const warnSpy = vi.spyOn(ElMessage, 'warning').mockImplementation((() => ({})) as never)
    const w = mountView()
    await flushPromises()
    const createBtn = w.findAll('button').find((b) => b.text() === '创建')
    await createBtn!.trigger('click')
    await flushPromises()
    expect(createPageDraftSpy).not.toHaveBeenCalled()
    expect(warnSpy).toHaveBeenCalled()
    vi.restoreAllMocks()
  })
})

describe('PageDesignerView 多选等距分布与快捷键（I3，对齐 GraphWorkbench 规格）', () => {
  it('多选横分布：3 个选中 → tb-dist-h → 中间 widget x 等距；不足 3 个按钮禁用', async () => {
    const w = mountView()
    await flushPromises()
    // 初始仅 1 个 widget → 分布按钮禁用
    expect(tb(w, 'dist-h').attributes('disabled')).toBeDefined()
    // 直接往宿主 page 对象补 2 个 widget（布局值给定便于断言）
    const pageObj = w.findComponent({ name: 'PageCanvasStub' }).props('page') as {
      widgets: { id: string; kind: string; rect: { x: number; y: number; w: number; h: number }; props: Record<string, never>; style: Record<string, never>; bindings: Record<string, never> }[]
    }
    pageObj.widgets.push(
      { id: 'wa', kind: 'text', rect: { x: 0, y: 0, w: 40, h: 20 }, props: {}, style: {}, bindings: {} },
      { id: 'wb', kind: 'text', rect: { x: 100, y: 30, w: 40, h: 20 }, props: {}, style: {}, bindings: {} },
    )
    const stub = w.findComponent({ name: 'PageCanvasStub' })
    // 单选 wa → additive 追加 wq、wb（shift 多选，emit 载荷 (id, true)）
    stub.vm.$emit('select', 'wa')
    await flushPromises()
    stub.vm.$emit('select', 'wq', true)
    stub.vm.$emit('select', 'wb', true)
    await flushPromises()
    expect(tb(w, 'dist-h').attributes('disabled')).toBeUndefined()
    await tb(w, 'dist-h').trigger('click')
    await flushPromises()
    // 按 x 升序 [0, 8, 100] → 中间 round(0 + 100/2) = 50；首尾不动
    const xs = Object.fromEntries(pageObj.widgets.map((x) => [x.id, x.rect.x]))
    expect(xs).toEqual({ wa: 0, wq: 50, wb: 100 })
  })

  it('快捷键 Ctrl+Z 撤销：复制后 Ctrl+Z 回到 1 个 widget（撤销栈清空后按钮禁用）', async () => {
    const w = mountView()
    await flushPromises()
    expect(tb(w, 'undo').attributes('disabled')).toBeDefined()
    w.findComponent({ name: 'PageCanvasStub' }).vm.$emit('select', 'wq')
    await flushPromises()
    await tb(w, 'copy').trigger('click')
    expect(w.find('.stub-canvas').attributes('data-count')).toBe('2')
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'z', ctrlKey: true }))
    await flushPromises()
    expect(w.find('.stub-canvas').attributes('data-count')).toBe('1')
    expect(tb(w, 'undo').attributes('disabled')).toBeDefined()
  })

  it('快捷键 Delete 删除选中；焦点在 input（typing target）时不删除', async () => {
    const w = mountView()
    await flushPromises()
    w.findComponent({ name: 'PageCanvasStub' }).vm.$emit('select', 'wq')
    await flushPromises()
    // 焦点在输入元素 → 快捷键跳过（keydown 自 input 冒泡，target=input）
    const input = document.createElement('input')
    document.body.appendChild(input)
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Delete', bubbles: true }))
    await flushPromises()
    expect(w.find('.stub-canvas').attributes('data-count')).toBe('1')
    // window 派发 Delete → 删除主选中
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Delete' }))
    await flushPromises()
    expect(w.find('.stub-canvas').attributes('data-count')).toBe('0')
    input.remove()
  })

  it('快捷键 Escape：非预览态无效果；预览态退出预览', async () => {
    previewSpy.mockResolvedValue({ results: {}, rowCap: 100 })
    const w = mountView()
    await flushPromises()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(w.find('.stub-canvas').attributes('data-preview')).toBe('off')
    await tb(w, 'preview').trigger('click')
    await flushPromises()
    expect(w.find('.stub-canvas').attributes('data-preview')).toBe('on')
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(w.find('.stub-canvas').attributes('data-preview')).toBe('off')
  })
})

describe('PageDesignerView 深链自动建稿（Task 15 统一入口）', () => {
  it('草稿 6001 + 目录存在 → 取 label/desc 物化种子页建稿 → 重载草稿进入编辑态', async () => {
    routeState.params.type = 'user_demo'
    const e6001 = Object.assign(new Error('组件不存在'), { code: 6001 })
    getDraftSpy.mockRejectedValueOnce(e6001).mockResolvedValueOnce(structuredClone(DRAFT))
    /* executionModel='page' → 走 page 种子页建稿分支（声明式组件走 createComponentDraft，另有专测） */
    getComponentSpy.mockResolvedValue({ type: 'user_demo', label: '演示组件', desc: '测试用组件', executionModel: 'page' })
    createPageDraftSpy.mockResolvedValue({ type: 'user_demo', draftRev: 0, draftVersion: 1 })
    listVersionsSpy.mockResolvedValue(structuredClone(VERSIONS))
    getResourcesSpy.mockResolvedValue(structuredClone(CATALOG))
    const w = mountView()
    await flushPromises()
    expect(getComponentSpy).toHaveBeenCalledWith('user_demo')
    expect(createPageDraftSpy).toHaveBeenCalledTimes(1)
    const body = createPageDraftSpy.mock.calls[0][0] as {
      type: string; name: string
      page: { name: string; widgets: { kind: string; props: Record<string, unknown> }[] }
    }
    expect(body.type).toBe('user_demo')
    expect(body.name).toBe('演示组件')
    /* 种子页：heading = 组件名 + text = 目录描述（componentSeedPage 真实函数产出） */
    expect(body.page.name).toBe('演示组件')
    expect(body.page.widgets.map((x) => x.kind)).toEqual(['heading', 'text'])
    expect(body.page.widgets[0].props.text).toBe('演示组件')
    expect(body.page.widgets[1].props.text).toBe('测试用组件')
    /* 建稿后重载草稿 + 版本 + 目录，进入编辑态 */
    expect(getDraftSpy).toHaveBeenCalledTimes(2)
    expect(listVersionsSpy).toHaveBeenCalledWith('user_demo')
    expect(w.find('.stub-canvas').exists()).toBe(true)
  })

  it('目录也无此 type（乱路径）→ 不建稿，落加载错误态', async () => {
    routeState.params.type = '__ghost__'
    const e6001 = Object.assign(new Error('组件不存在'), { code: 6001 })
    getDraftSpy.mockRejectedValue(e6001)
    getComponentSpy.mockRejectedValue(new Error('组件不存在: __ghost__'))
    const w = mountView()
    await flushPromises()
    expect(createPageDraftSpy).not.toHaveBeenCalled()
    expect(w.find('.pd-err').exists()).toBe(true)
  })
})

describe('PageDesignerView 组件级删除（Task 15 CRUD 补齐）', () => {
  it('纯草稿组件显示删除按钮：确认 → deleteComponent → 回组件目录', async () => {
    const confirmSpy = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as never)
    deleteComponentSpy.mockResolvedValue({ type: 'page_demo', deleted: true })
    const w = mountView()
    await flushPromises()
    const btn = w.find('[data-testid="tb-comp-delete"]')
    expect(btn.exists()).toBe(true)
    await btn.trigger('click')
    await flushPromises()
    expect(confirmSpy).toHaveBeenCalled()
    expect(deleteComponentSpy).toHaveBeenCalledWith('page_demo')
    expect(pushSpy).toHaveBeenCalledWith('/meta/components')
  })

  it('builtin 草稿不显示组件级删除按钮（后端 409，按钮前置隐藏）', async () => {
    getDraftSpy.mockResolvedValue({ ...DRAFT, type: 'sql', name: 'SQL', scope: 'builtin' })
    const w = mountView()
    await flushPromises()
    expect(w.find('[data-testid="tb-comp-delete"]').exists()).toBe(false)
  })
})

describe('PageDesignerView fields 模式（组件初始化落地）', () => {
  /* 声明式组件（spec.fields 双源之一）草稿 fixture */
  const FIELDS_DRAFT = {
    type: 'op_demo', name: '演示算子', category: null, profile: 'dag', scope: 'user',
    executionModel: 'dag-engine', executor: 'sql', executable: true, state: 'draft',
    publishedVersion: null, draftRev: 1, draftVersion: 1, description: null, tags: [],
    spec: {
      fields: [
        { key: 'sql', label: 'SQL', uiType: 'text', required: true, desc: '语句' },
        { key: 'ds', label: '数据源', uiType: 'resource', required: false },
      ],
      dropPolicy: {
        snapToGrid: false, autoName: '{type}_{n}', prefillFromUpstream: ['ds'],
        autoConnect: { upstream: 'nearest', downstream: 'nearest' }, maxInstances: 0,
      },
    },
    specHash: 'a'.repeat(64), updatedAt: '2026-10-03 10:00:00',
  }
  /* 八段底稿（form.params）草稿 fixture：6002 重开的内置组件复制的就是它 */
  const BASELINE_DRAFT = {
    type: 'sql', name: 'SQL', category: null, profile: 'dag', scope: 'builtin',
    executionModel: 'dag-engine', executor: 'sql', executable: true, state: 'draft',
    publishedVersion: 1, draftRev: 1, draftVersion: 2, description: null, tags: [],
    spec: {
      form: { title: 'SQL 参数', group: '基础', params: [{ key: 'sql', label: 'SQL', uiType: 'text', required: true, visible: true }] },
      dropPolicy: { autoName: '{type}_{n}' },
      other: { keep: true },
    },
    specHash: 'a'.repeat(64), updatedAt: '2026-10-03 10:00:00',
  }

  it('spec.fields 草稿 → fields 模式渲染：FieldsCanvas 行非空 + Inspector 挂载，palette/页面专属按钮隐藏', async () => {
    routeState.params.type = 'op_demo'
    getDraftSpy.mockResolvedValue(structuredClone(FIELDS_DRAFT))
    const w = mountView()
    await flushPromises()
    expect(w.find('.stub-fcanvas').attributes('data-count')).toBe('2')
    expect(w.find('.stub-finspector').exists()).toBe(true)
    expect(w.find('.stub-canvas').exists()).toBe(false)
    expect(w.find('[data-testid="pd-palette"]').exists()).toBe(false)
    expect(w.find('[data-testid="tb-fields-tag"]').exists()).toBe(true)
    /* page 专属按钮不渲染；双模式按钮（删除/刷新/保存/发布）仍在 */
    for (const id of ['copy', 'paste', 'align-left', 'align-top', 'dist-h', 'dist-v', 'zoom', 'preview']) {
      expect(tb(w, id).exists(), `page 专属按钮 tb-${id} 应隐藏`).toBe(false)
    }
    for (const id of ['undo', 'redo', 'delete', 'refresh', 'save', 'publish']) {
      expect(tb(w, id).exists(), `双模式按钮 tb-${id} 应保留`).toBe(true)
    }
  })

  it('patchRow 编辑 + 保存：写回 spec.fields 原位 + dropPolicy 保留', async () => {
    routeState.params.type = 'op_demo'
    getDraftSpy.mockResolvedValue(structuredClone(FIELDS_DRAFT))
    saveDraftSpy.mockResolvedValue({ draftRev: 2, specHash: 'f'.repeat(64), savedAt: '2026-10-03 11:00:00' })
    const w = mountView()
    await flushPromises()
    w.findComponent({ name: 'FieldsInspectorStub' }).vm.$emit('select', 0)
    await flushPromises()
    w.findComponent({ name: 'FieldsInspectorStub' }).vm.$emit('patchRow', 0, { label: 'SQL 语句' })
    await flushPromises()
    await tb(w, 'save').trigger('click')
    await flushPromises()
    expect(saveDraftSpy).toHaveBeenCalledTimes(1)
    const body = saveDraftSpy.mock.calls[0][1] as { draftRev: number; spec: Record<string, unknown> }
    expect(body.draftRev).toBe(1)
    const rows = body.spec.fields as { key: string; label: string }[]
    expect(rows[0].label).toBe('SQL 语句')
    expect(rows[0].key).toBe('sql')
    expect(rows[1].key).toBe('ds')
    const dp = body.spec.dropPolicy as Record<string, unknown>
    expect(dp.autoName).toBe('{type}_{n}')
    expect(dp.prefillFromUpstream).toEqual(['ds'])
  })

  it('八段底稿（form.params）源：保存写回 form.params，form 其余段/其他 spec 段原样保留，不新增顶层 fields', async () => {
    routeState.params.type = 'sql'
    getDraftSpy.mockResolvedValue(structuredClone(BASELINE_DRAFT))
    saveDraftSpy.mockResolvedValue({ draftRev: 2, specHash: 'f'.repeat(64), savedAt: '2026-10-03 11:00:00' })
    const w = mountView()
    await flushPromises()
    w.findComponent({ name: 'FieldsInspectorStub' }).vm.$emit('addRow')
    await flushPromises()
    await tb(w, 'save').trigger('click')
    await flushPromises()
    const body = saveDraftSpy.mock.calls[0][1] as { spec: Record<string, unknown> }
    const form = body.spec.form as { title: string; group: string; params: Record<string, unknown>[] }
    expect(form.title).toBe('SQL 参数')
    expect(form.group).toBe('基础')
    expect(form.params).toHaveLength(2)
    expect(form.params[0]).toMatchObject({ key: 'sql', visible: true })
    expect(form.params[1]).toMatchObject({ visible: true }) // makeFieldRow 八段源补 visible
    expect(body.spec.other).toEqual({ keep: true })
    expect(body.spec.fields).toBeUndefined()
  })

  it('空声明 {}：从目录 formFields 物化初始表单（getComponent 触达，行非空）', async () => {
    routeState.params.type = 'op_blank'
    getDraftSpy.mockResolvedValue({ ...structuredClone(FIELDS_DRAFT), type: 'op_blank', spec: {} })
    getComponentSpy.mockResolvedValue({
      type: 'op_blank', label: '空白算子', desc: '', executionModel: 'dag-engine', profile: 'dag',
      formFields: [
        { key: 'srcDs', label: '源数据源', type: 'resource', required: true },
        { key: 'threshold', label: '阈值', type: 'number', defaultValue: 10 },
      ],
    })
    const w = mountView()
    await flushPromises()
    expect(getComponentSpy).toHaveBeenCalledWith('op_blank')
    expect(w.find('.stub-fcanvas').attributes('data-count')).toBe('2')
    expect(w.find('.stub-finspector').exists()).toBe(true)
  })

  it('6001 + 声明式目录组件 → createComponentDraft 物化 fields（不走 createPageDraft）', async () => {
    routeState.params.type = 'user_op'
    const e6001 = Object.assign(new Error('组件不存在'), { code: 6001 })
    getDraftSpy.mockRejectedValueOnce(e6001).mockResolvedValueOnce(structuredClone(FIELDS_DRAFT))
    getComponentSpy.mockResolvedValue({
      type: 'user_op', label: '自定义算子', desc: '目录物化', executionModel: 'dag-engine', profile: 'etl',
      formFields: [{ key: 'src', label: '源', type: 'text', required: true }],
    })
    createComponentDraftSpy.mockResolvedValue({ type: 'user_op', draftRev: 0, draftVersion: 1 })
    const w = mountView()
    await flushPromises()
    expect(createPageDraftSpy).not.toHaveBeenCalled()
    expect(createComponentDraftSpy).toHaveBeenCalledTimes(1)
    const body = createComponentDraftSpy.mock.calls[0][0] as Record<string, unknown>
    expect(body).toMatchObject({ type: 'user_op', name: '自定义算子', profile: 'etl', executionModel: 'dag-engine', executable: true })
    expect(body.spec).toEqual({ fields: [{ key: 'src', label: '源', uiType: 'text', required: true }] })
    /* 建稿后重载草稿进入编辑态 */
    expect(getDraftSpy).toHaveBeenCalledTimes(2)
    expect(w.find('.stub-fcanvas').exists()).toBe(true)
  })

  it('decl 页签编辑 + 保存：summary 写回 spec + icon/color 恒写 + 未编辑 V2 键不落 JSON', async () => {
    routeState.params.type = 'op_demo'
    getDraftSpy.mockResolvedValue(structuredClone(FIELDS_DRAFT))
    saveDraftSpy.mockResolvedValue({ draftRev: 2, specHash: 'f'.repeat(64), savedAt: '2026-10-03 11:00:00' })
    const w = mountView()
    await flushPromises()
    /* 身份页签 summary 输入（data-testid 经 attrs 透传到 el-input stub 根 input） */
    const summaryInput = w.find('input[data-testid="sf-id-summary"]')
    expect(summaryInput.exists()).toBe(true)
    await summaryInput.setValue('演示算子简介')
    await tb(w, 'save').trigger('click')
    await flushPromises()
    const body = saveDraftSpy.mock.calls[0][1] as { spec: Record<string, unknown> }
    expect(body.spec.summary).toBe('演示算子简介')
    /* 一级必有键恒写（空串也落，页面骨架依赖） */
    expect(body.spec.icon).toBe('')
    expect(body.spec.color).toBe('')
    /* 未编辑的 V2 optional 键不落 JSON（缺位键契约） */
    expect(body.spec.displayName).toBeUndefined()
    expect(body.spec.outputs).toBeUndefined()
    expect(body.spec.behaviors).toBeUndefined()
    /* fields/dropPolicy 原链路不回归 */
    expect(Array.isArray(body.spec.fields)).toBe(true)
    expect((body.spec.dropPolicy as Record<string, unknown>).autoName).toBe('{type}_{n}')
  })

  it('outputs 缺项豁免口径：dag-engine 记缺项 chip，demo-only 豁免（ExecutionModel 语义对齐）', async () => {
    /* dag-engine（真实执行）：outputs 未声明 → 徽标记缺项 */
    routeState.params.type = 'op_demo'
    getDraftSpy.mockResolvedValue(structuredClone(FIELDS_DRAFT))
    let w = mountView()
    await flushPromises()
    expect(w.find('[data-testid="scb-chip-outputs"]').exists()).toBe(true)
    w.unmount()
    /* demo-only（无任何执行实现）：无数据输出语义 → outputs 缺项豁免，chip 消失 */
    getDraftSpy.mockResolvedValue({ ...structuredClone(FIELDS_DRAFT), executionModel: 'demo-only' })
    w = mountView()
    await flushPromises()
    expect(w.find('[data-testid="scb-chip-outputs"]').exists()).toBe(false)
  })
})
