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
vi.mock('../../../../services/componentApi', () => ({
  getComponentDraft: getDraftSpy,
  listComponentVersions: listVersionsSpy,
  saveComponentDraft: saveDraftSpy,
  freezeComponentVersion: freezeSpy,
  publishComponentVersion: publishSpy,
  createPageDraft: createPageDraftSpy,
}))

/* 子组件桩：容器 testid 由宿主承担，这里只验证宿主给画布的 props（preview 透传） */
vi.mock('../canvas/PageCanvas.vue', () => ({
  default: {
    name: 'PageCanvasStub',
    props: { page: { type: Object, required: true }, selectedId: { type: String, default: undefined }, preview: { type: Object, default: undefined } },
    emits: ['add', 'select', 'move', 'resize', 'canvasSize'],
    template: '<div class="stub-canvas" :data-preview="preview ? \'on\' : \'off\'" :data-count="page.widgets.length" />',
  },
}))
vi.mock('../palette/PagePalette.vue', () => ({ default: { name: 'PagePaletteStub', template: '<aside class="stub-palette" />' } }))
vi.mock('../inspector/PageInspector.vue', () => ({
  default: {
    name: 'PageInspectorStub',
    props: ['page', 'selectedId', 'catalog'],
    emits: ['updateWidget', 'updateCanvas'],
    template: '<aside class="stub-inspector" />',
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
  it('路由表：/meta/components/page-designer/:type? 条目（懒加载 + title 页面设计器）', () => {
    const r = routes.find((x) => x.path === '/meta/components/page-designer/:type?')
    expect(r).toBeTruthy()
    expect(r?.meta?.title).toBe('页面设计器')
    expect(typeof r?.component).toBe('function')
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
    for (const id of ['undo', 'redo', 'copy', 'paste', 'delete', 'align-left', 'align-top', 'zoom', 'refresh', 'save', 'preview', 'publish']) {
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
