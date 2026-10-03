// @vitest-environment happy-dom
/**
 * Task 15 统一入口用例（组件目录）：
 * - 头部与用户组件卡所有「调用设计器」的操作统一指向 /meta/components/page-designer
 *   （:type 深链由设计器自动加载/自动建稿），入口按钮统一命名「组件设计器」；
 * - 用户组件卡删除（仅草稿语义由后端把关）：确认 → deleteComponent → 刷新清单。
 * vue-router / componentApi / baselineApi 以模块 mock 注入；el-* 桩掉消噪音。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ElMessage, ElMessageBox } from 'element-plus'

const pushSpy = vi.hoisted(() => vi.fn())
vi.mock('vue-router', () => ({ useRouter: () => ({ push: pushSpy }) }))

const listSpy = vi.hoisted(() => vi.fn())
const statsSpy = vi.hoisted(() => vi.fn())
const registrySpy = vi.hoisted(() => vi.fn())
const getCompSpy = vi.hoisted(() => vi.fn())
const deleteCompSpy = vi.hoisted(() => vi.fn())
vi.mock('../../../services/componentApi', () => ({
  listComponents: listSpy,
  getComponentStats: statsSpy,
  getComponentRegistry: registrySpy,
  getComponent: getCompSpy,
  deleteComponent: deleteCompSpy,
}))
const progressSpy = vi.hoisted(() => vi.fn())
vi.mock('../../../services/baselineApi', () => ({ progress: progressSpy }))

import ComponentCatalogView from '../ComponentCatalogView.vue'

const ROW = {
  type: 'sql_transform', label: 'SQL 转换', icon: 'edit', color: '#1677ff',
  desc: '对数据集执行 SQL', categories: ['etl'], shape: 'card', profile: 'dag',
  dagRelevant: true, executionModel: 'dag-engine', executionNote: '', code: 'C01',
  runtimeOnly: false, route: 'worker', executor: 'sql', paletteVisible: true,
  paletteGroup: 'transform', formFieldCount: 1, requiredFieldCount: 0,
  flags: {},
}
const STATS = {
  catalogHash: 'h1', generatedAt: '2026-10-03 10:00:00', source: {}, profiles: [],
  stats: { total: 1, unrouted: 0, unroutedTotal: 0, unroutedTypes: [], unroutedByProfile: {}, backendOnlyTypes: [], crossProfileDuplicateTypes: [], consistencyErrors: [] },
}
const REGISTRY = [
  { type: 'user_demo', name: '演示组件', profile: 'dag', scope: 'user', state: 'draft', publishedVersion: null, executionModel: 'dag-engine', category: null },
  { type: 'user_off', name: '已下线组件', profile: 'dag', scope: 'user', state: 'offline', publishedVersion: 1, executionModel: 'dag-engine', category: null },
  { type: 'assert', name: '数据校验', profile: 'dag', scope: 'builtin', state: 'published', publishedVersion: 1, executionModel: 'dag-engine', category: 'etl' },
]

const stubs = {
  ElButton: { emits: ['click'], template: '<button @click="$emit(\'click\')"><slot /></button>' },
  ElAlert: { props: ['title'], template: '<div class="stub-alert">{{ title }}<slot /></div>' },
  ElInput: { props: ['modelValue'], emits: ['update:modelValue'], template: '<input />' },
  ElSelect: { template: '<div class="stub-select"><slot /></div>' },
  ElOption: { template: '<div />' },
  ElCheckbox: { props: ['modelValue'], template: '<label class="stub-check"><slot /></label>' },
  ElForm: { template: '<form><slot /></form>' },
  ElFormItem: { template: '<div><slot /></div>' },
  ElTable: { template: '<div class="stub-table" />' },
  ElTableColumn: { template: '<div />' },
  ElDrawer: { props: ['modelValue'], template: '<div v-if="modelValue" class="stub-drawer"><slot /></div>' },
  ElDescriptions: { template: '<div><slot /></div>' },
  ElDescriptionsItem: { template: '<div><slot /></div>' },
}

function mountView(props?: { openDesigner?: (type?: string) => void }) {
  return mount(ComponentCatalogView, { props, global: { components: stubs, directives: { loading: {} } } })
}

beforeEach(() => {
  vi.clearAllMocks()
  listSpy.mockResolvedValue({ total: 1, catalogHash: 'h1', schemaVersion: 1, items: [structuredClone(ROW)] })
  statsSpy.mockResolvedValue(structuredClone(STATS))
  registrySpy.mockResolvedValue(structuredClone(REGISTRY))
  progressSpy.mockRejectedValue(new Error('baseline 未就位'))
})

describe('ComponentCatalogView 统一入口（Task 15）', () => {
  it('头部按钮「组件设计器」→ /meta/components/page-designer（新建态）', async () => {
    const w = mountView()
    await flushPromises()
    const head = w.find('.head-actions button')
    expect(head.exists()).toBe(true)
    expect(head.text()).toBe('组件设计器')
    await head.trigger('click')
    expect(pushSpy).toHaveBeenCalledWith('/meta/components/page-designer')
  })

  it('用户组件卡「组件设计器」→ /meta/components/page-designer/{type}（深链直改）', async () => {
    const w = mountView()
    await flushPromises()
    const cards = w.findAll('.ucard')
    expect(cards).toHaveLength(2)
    const btn = cards[0].findAll('button').find((b) => b.text() === '组件设计器')
    expect(btn, '用户组件卡应有「组件设计器」入口').toBeTruthy()
    await btn!.trigger('click')
    expect(pushSpy).toHaveBeenCalledWith('/meta/components/page-designer/user_demo')
  })

  it('草稿卡有删除入口；已下线卡不显示删除', async () => {
    const w = mountView()
    await flushPromises()
    const cards = w.findAll('.ucard')
    expect(cards[0].text()).toContain('删除')
    expect(cards[1].text()).not.toContain('删除')
  })

  it('builtin 组件不进用户组件区（registry 混入行被过滤，防系统组件误渲染删除入口）', async () => {
    const w = mountView()
    await flushPromises()
    const cards = w.findAll('.ucard')
    expect(cards).toHaveLength(2) // assert(builtin) 被过滤，仅剩 user_demo/user_off
    expect(w.find('.ugov-t').text()).toContain('· 2')
  })

  it('删除：确认 → deleteComponent → 成功提示并刷新清单', async () => {
    const confirmSpy = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as never)
    const msgSpy = vi.spyOn(ElMessage, 'success').mockImplementation((() => ({})) as never)
    deleteCompSpy.mockResolvedValue({ type: 'user_demo', deleted: true })
    const w = mountView()
    await flushPromises()
    const del = w.findAll('.ucard')[0].findAll('button').find((b) => b.text() === '删除')
    await del!.trigger('click')
    await flushPromises()
    expect(confirmSpy).toHaveBeenCalled()
    expect(deleteCompSpy).toHaveBeenCalledWith('user_demo')
    expect(msgSpy).toHaveBeenCalled()
    expect(listSpy).toHaveBeenCalledTimes(2) // 挂载 1 次 + 删除后刷新 1 次
  })

  it('嵌入态（ComponentHub）：openDesigner 回调优先，头按钮/用户卡均走页签流转不走路由', async () => {
    const cb = vi.fn()
    const w = mountView({ openDesigner: cb })
    await flushPromises()
    await w.find('.head-actions button').trigger('click')
    expect(cb).toHaveBeenCalledWith(undefined)
    const btn = w.findAll('.ucard')[0].findAll('button').find((b) => b.text() === '组件设计器')
    await btn!.trigger('click')
    expect(cb).toHaveBeenCalledWith('user_demo')
    expect(pushSpy).not.toHaveBeenCalled()
  })
})
