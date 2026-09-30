// @vitest-environment happy-dom
/**
 * LineageView 表级图加载接线用例（Task 5 质量审查）：
 * - I-1 并发守卫：初始加载与来源筛选重拉并发时序可控 —— 旧响应后至被序号守卫丢弃，不覆盖新状态；
 * - M-1 无中心表初始态显式传 direction=both / depth=0（拉全连通域，防后端默认值漂移）。
 * Task 7 表级交互增强：
 * - 参数下推：选表后切方向 → direction=upstream + 中心表下推重拉（服务端裁剪）；
 * - 以此为中心：center-node 事件（双击/右键）→ 换中心重拉 + 面包屑；回跳复用 centerOn；
 * - 一键影响分析/源头追踪：depth=0 全链请求 + dep_focus 边高亮；
 * - 影响分析独立请求：非全链视图下选表 → 补 downstream 全链请求；
 * - 截断提示：truncated=true → ⚠ 提示渲染。
 * Task 8 实例追溯模式化：
 * - 上下文条：工作流/节点名/状态（ok/err/info pill）/起止时间渲染；详情失败按 "-" 呈现不硬造；
 * - 回到全量：trace 态重置 + replace 清 instance/node 参 + 恢复 both/全链默认视图；
 * - stmt_no 边标注：追溯行 stmtNo → 边 label 追加 #1/#2；切级退出不清路由参。
 * lineageApi / services / element-plus / vue-router 模块 mock；GraphWorkbench 以桩替身承接 doc。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent } from 'vue'
import { ElMessage } from 'element-plus'

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}))

/** 可变路由 query（深链用例挂载前改写） */
const routeQuery = vi.hoisted(() => ({ params: {}, query: {} as Record<string, unknown> }))
/** router.replace spy（Task 8「回到全量」清 instance/node 深链参数断言） */
const routerReplace = vi.hoisted(() => vi.fn())
vi.mock('vue-router', () => ({
  useRoute: () => routeQuery,
  useRouter: () => ({ push: vi.fn(), replace: routerReplace }),
}))

const fetchGraphSpy = vi.hoisted(() => vi.fn())
const listFieldSpy = vi.hoisted(() => vi.fn())
const listTableSpy = vi.hoisted(() => vi.fn())
/** 实例详情 spy（Task 8 追溯上下文；real 专用 API） */
const instanceDetailSpy = vi.hoisted(() => vi.fn())
vi.mock('../../services/lineageApi', () => ({
  fetchLineageGraph: fetchGraphSpy,
  listFieldLineage: listFieldSpy,
  listTableLineage: listTableSpy,
}))

vi.mock('../../services', () => ({
  isMock: false,
  apiMode: 'api',
  getInstanceDetail: instanceDetailSpy,
}))

import LineageView from '../LineageView.vue'
import type { LineageEdgeRow, LineageGraphResult } from '../../services/lineageApi'
import type { GraphDocument } from '../../graph/model'

/** 桩可控 emit 载荷（select=画布点选；center-node=双击/右键「以此为中心」） */
let stubSelect: string | null = null
let stubCenter: string | null = null

/** GraphWorkbench 桩：透传 doc 供断言（无 canvas 依赖）；click/dblclick 上抛模拟画布交互 */
const WorkbenchStub = defineComponent({
  name: 'GraphWorkbench',
  props: {
    profile: { type: Object, default: null },
    docId: { type: String, default: '' },
    doc: { type: Object, default: null },
  },
  emits: ['select', 'center-node'],
  setup(_, { emit }) {
    return {
      fireSelect: () => emit('select', stubSelect),
      fireCenter: () => emit('center-node', stubCenter),
    }
  },
  template: '<div class="wb-stub" @click="fireSelect" @dblclick="fireCenter" />',
})

/** 双节点单边最小图文档输入（fq 前缀区分新旧响应） */
function graphResOf(prefix: string): LineageGraphResult {
  return {
    nodes: [
      { fq: `${prefix}_a`, ds: '', table: `${prefix}_a`, tmpFlag: 0, sources: ['runtime'], wfs: [101] },
      { fq: `${prefix}_b`, ds: '', table: `${prefix}_b`, tmpFlag: 0, sources: ['runtime'], wfs: [101] },
    ],
    edges: [{
      from: `${prefix}_a`, to: `${prefix}_b`, level: 'table',
      sources: ['runtime'], refs: [{ wfCode: 101, nodeId: 'n1', stmtNo: 0 }],
    }],
    opaques: [],
    truncated: false,
  }
}

/** 微任务冲刷（兼容 fake timers 的逐轮 Promise 放行） */
async function tick() {
  for (let i = 0; i < 10; i++) await Promise.resolve()
}

/** 受控响应放行队列：fetchLineageGraph 每次调用压入一个待手动 resolve 的 Promise */
let resolvers: ((v: LineageGraphResult) => void)[] = []
/** 拒绝放行队列（与 resolvers 同序；影响分析补拉失败重试用例用） */
let rejectors: ((e: unknown) => void)[] = []
/** /lineage/fields 返回（字段级用例改写） */
let fieldLineageMock: Record<string, { from: string; transform: string }[]> = {}

beforeEach(() => {
  vi.clearAllMocks()
  setActivePinia(createPinia())
  resolvers = []
  rejectors = []
  routeQuery.query = {}
  fieldLineageMock = {}
  stubSelect = null
  stubCenter = null
  instanceDetailSpy.mockResolvedValue(null)
  listFieldSpy.mockImplementation(() => Promise.resolve(fieldLineageMock))
  listTableSpy.mockResolvedValue([])
  fetchGraphSpy.mockImplementation(
    () => new Promise<LineageGraphResult>((res, rej) => { resolvers.push(res); rejectors.push(rej) }),
  )
})

function mountView() {
  return mount(LineageView, { global: { stubs: { GraphWorkbench: WorkbenchStub } } })
}

describe('LineageView 表级图加载（Task 5）', () => {
  it('M-1：无中心表初始态显式传 direction=both / depth=0（拉全连通域）', async () => {
    const wrapper = mountView()
    await tick()
    expect(fetchGraphSpy).toHaveBeenCalledWith(expect.objectContaining({
      level: 'table', direction: 'both', depth: 0,
    }))
    resolvers[0]!(graphResOf('first'))
    await tick()
    wrapper.unmount()
  })

  it('I-1：来源筛选重拉后，先发旧响应后至被丢弃，不覆盖新状态', async () => {
    const wrapper = mountView()
    await tick()
    // 初始加载（seq1）挂起中 → 点「运行态」触发来源筛选重拉（seq2）
    await wrapper.findAll('button').find((b) => b.text() === '运行态')!.trigger('click')
    await tick()
    expect(fetchGraphSpy).toHaveBeenCalledTimes(2)
    // 新响应先至（seq2 命中回写）→ 旧响应后至必须被守卫丢弃
    resolvers[1]!(graphResOf('new'))
    await tick()
    resolvers[0]!(graphResOf('old'))
    await tick()
    const doc = wrapper.findComponent(WorkbenchStub).props('doc') as GraphDocument | null
    expect(doc).toBeTruthy()
    expect(doc!.nodes.map((n) => n.id)).toEqual(['new_a', 'new_b'])
    wrapper.unmount()
  })
})

/* ---------- Task 6：字段级映射图（页签 / 深链定位） ---------- */

const FIELD_MOCK = {
  'dwd_order.pay_amount': [{ from: 'ods_order.amount', transform: 'amount * 0.9' }],
  'dwd_order.uid': [{ from: 'ods_user.uid', transform: '' }],
}

describe('LineageView 字段级映射（Task 6）', () => {
  it('切字段级 → 下拉选表 → 映射图 chips/连线渲染；映射明细页签平铺 + transform', async () => {
    fieldLineageMock = FIELD_MOCK
    const wrapper = mountView()
    await tick()
    await wrapper.findAll('button').find((b) => b.text() === '字段级血缘')!.trigger('click')
    await tick()
    // 未选表 → 引导空态
    expect(wrapper.find('.fp-empty').text()).toContain('请选择中心表')
    // 下拉选表 → 映射图（默认页签）：2 目标字段 chip + 2 来源 chip + 2 组连线
    await wrapper.find('select.fp-select').setValue('dwd_order')
    const chips = wrapper.findAll('.flm-chip')
    expect(chips.map((c) => c.text())).toEqual(['ods_orderamount', 'ods_useruid', 'pay_amount', 'uid'])
    expect(wrapper.findAll('line.flm-line')).toHaveLength(2)
    // 切「映射明细」→ 平铺映射行（含空 transform 不渲染表达式块）
    await wrapper.findAll('button').find((b) => b.text() === '映射明细')!.trigger('click')
    const rows = wrapper.findAll('.fp-detail .tr-row')
    expect(rows).toHaveLength(2)
    expect(rows[0]!.text()).toContain('dwd_order.pay_amount')
    expect(rows[0]!.text()).toContain('amount * 0.9')
    expect(rows[1]!.find('.tr-expr').exists()).toBe(false)
    wrapper.unmount()
  })

  it('深链 ?level=field&table=&field= → 直达字段级 + 表归一 + field 高亮；换表后高亮不残留', async () => {
    fieldLineageMock = { ...FIELD_MOCK, 'dws_sum.uid': [{ from: 'ods_user.uid', transform: 'u' }] }
    routeQuery.query = { level: 'field', table: 'dwd_order', field: 'uid' }
    const wrapper = mountView()
    await tick()
    resolvers[0]!(graphResOf('ds1'))  // 表级 graph 响应放行，reload 才走到深链分支
    await tick()
    // 直达字段级（表级画布不渲染），中心表按字段映射表集归一为裸名，field=uid 命中高亮 chip
    expect(wrapper.findComponent(WorkbenchStub).exists()).toBe(false)
    expect((wrapper.find('select.fp-select').element as HTMLSelectElement).value).toBe('dwd_order')
    const hl = wrapper.findAll('.flm-chip.hl')
    expect(hl).toHaveLength(1)
    expect(hl[0]!.text()).toBe('uid')
    // 换表即清深链高亮（M-2）：搜索跳表 → 无残留；切回含同名字段 uid 的原表也不误高亮
    await wrapper.find('input.search-in').setValue('dws_sum')
    await wrapper.find('input.search-in').trigger('keyup.enter')
    await tick()
    expect((wrapper.find('select.fp-select').element as HTMLSelectElement).value).toBe('dws_sum')
    expect(wrapper.findAll('.flm-chip.hl')).toHaveLength(0)
    await wrapper.find('select.fp-select').setValue('dwd_order')
    expect(wrapper.findAll('.flm-chip.hl')).toHaveLength(0)
    wrapper.unmount()
  })

  it('深链表无字段映射 → 空态提示（不白屏）；映射图 transform hover 悬浮标签', async () => {
    fieldLineageMock = { 'other_tbl.f1': [{ from: 'src.a', transform: 'a + 1' }] }
    routeQuery.query = { level: 'field', table: 'dwd_order' }
    const wrapper = mountView()
    await tick()
    resolvers[0]!(graphResOf('ds1'))
    await tick()
    expect(wrapper.find('.fp-empty').text()).toContain('暂无字段级映射')
    wrapper.unmount()

    // transform 悬浮标签：hover 映射图连线 → tooltip 展示表达式；移出消失
    fieldLineageMock = FIELD_MOCK
    routeQuery.query = { level: 'field', table: 'dwd_order' }
    const w2 = mountView()
    await tick()
    resolvers[1]!(graphResOf('ds1'))
    await tick()
    await w2.find('g').trigger('mouseenter')
    expect(w2.find('.flm-tip').text()).toBe('amount * 0.9')
    await w2.find('g').trigger('mouseleave')
    expect(w2.find('.flm-tip').exists()).toBe(false)
    w2.unmount()
  })

  it('I-1：from="" 常量项在 reload 末尾统一过滤（两分支共用路径）→ 不出行不画线', async () => {
    fieldLineageMock = {
      'dwd_order.pay_amount': [
        { from: '', transform: "'固定值'" },
        { from: 'ods_order.amount', transform: 'amount * 0.9' },
      ],
    }
    const wrapper = mountView()
    await tick()
    await wrapper.findAll('button').find((b) => b.text() === '字段级血缘')!.trigger('click')
    await tick()
    await wrapper.find('select.fp-select').setValue('dwd_order')
    // 常量项无来源节点：左列无空 chip、连线仅 1 条（映射图）、明细行仅 1 行（过滤在 fieldRows 上游）
    expect(wrapper.findAll('.flm-chip').map((c) => c.text()))
      .toEqual(['ods_orderamount', 'pay_amount'])
    expect(wrapper.findAll('line.flm-line')).toHaveLength(1)
    await wrapper.findAll('button').find((b) => b.text() === '映射明细')!.trigger('click')
    expect(wrapper.findAll('.fp-detail .tr-row')).toHaveLength(1)
    wrapper.unmount()
  })
})

/* ---------- Task 7：表级交互增强（参数下推 / 以此为中心 / 面包屑 / 一键聚焦 / 截断提示） ---------- */

describe('LineageView 表级交互增强（Task 7）', () => {
  it('参数下推：选表补拉下游全链（影响分析）；切「上游」→ upstream/depth=1 中心表重拉；截断提示', async () => {
    const wrapper = mountView()
    await tick()
    resolvers[0]!({ ...graphResOf('first'), truncated: true })
    await tick()
    expect(wrapper.find('.trunc-hint').exists()).toBe(true)
    // 画布点选 first_a：非全链视图（down/1）→ 影响分析独立补拉 downstream 全链（请求 2）
    stubSelect = 'first_a'
    await wrapper.find('.wb-stub').trigger('click')
    await tick()
    expect(fetchGraphSpy).toHaveBeenNthCalledWith(2, expect.objectContaining({
      level: 'table', table: 'first_a', direction: 'downstream', depth: 0,
    }))
    // 切「上游」→ watcher 带当前参数重拉（请求 3：upstream/depth=1/中心表下推）
    await wrapper.findAll('button').find((b) => b.text() === '上游')!.trigger('click')
    await tick()
    expect(fetchGraphSpy).toHaveBeenNthCalledWith(3, expect.objectContaining({
      level: 'table', table: 'first_a', direction: 'upstream', depth: 1,
    }))
    wrapper.unmount()
  })

  it('以此为中心：center-node 换心重拉 + 面包屑渲染；点击面包屑回跳换心', async () => {
    const wrapper = mountView()
    await tick()
    resolvers[0]!(graphResOf('first'))
    await tick()
    // 先点选 first_a（压栈面包屑 + 影响分析补拉 = 请求 2）
    stubSelect = 'first_a'
    await wrapper.find('.wb-stub').trigger('click')
    await tick()
    expect(fetchGraphSpy).toHaveBeenNthCalledWith(2, expect.objectContaining({
      table: 'first_a', direction: 'downstream', depth: 0,
    }))
    // 双击 first_b（双击/右键「以此为中心」）→ 换心重拉（请求 3）
    stubCenter = 'first_b'
    await wrapper.find('.wb-stub').trigger('dblclick')
    await tick()
    expect(fetchGraphSpy).toHaveBeenNthCalledWith(3, expect.objectContaining({
      table: 'first_b', direction: 'downstream', depth: 1,
    }))
    // 面包屑：first_a（可点回跳）› first_b（当前不可点）
    const bar = wrapper.find('.crumb-bar')
    expect(bar.exists()).toBe(true)
    expect(bar.findAll('button.crumb')).toHaveLength(1)
    expect(bar.findAll('button.crumb')[0]!.text()).toBe('first_a')
    expect(bar.find('.crumb.cur').text()).toBe('first_b')
    // 换心后 watch(selected) 补拉 first_b 下游全链（请求 4：影响分析数据保障）
    expect(fetchGraphSpy).toHaveBeenNthCalledWith(4, expect.objectContaining({
      table: 'first_b', direction: 'downstream', depth: 0,
    }))
    // 回跳 first_a → 换心重拉（请求 5）+ 影响分析补拉（请求 6）
    await bar.find('button.crumb').trigger('click')
    await tick()
    expect(fetchGraphSpy).toHaveBeenNthCalledWith(5, expect.objectContaining({
      table: 'first_a', direction: 'downstream', depth: 1,
    }))
    expect(fetchGraphSpy).toHaveBeenNthCalledWith(6, expect.objectContaining({
      table: 'first_a', direction: 'downstream', depth: 0,
    }))
    wrapper.unmount()
  })

  it('一键影响分析 / 源头追踪：depth=0 全链重拉 + dep_focus 边高亮', async () => {
    const wrapper = mountView()
    await tick()
    resolvers[0]!(graphResOf('first'))
    await tick()
    stubSelect = 'first_a'
    await wrapper.find('.wb-stub').trigger('click')
    await tick()  // 请求 2 = 影响分析补拉
    // ⚡ 影响分析：depth 1→0 变化 → watcher 全链重拉（请求 3；响应含中心表防落空清选中）
    await wrapper.findAll('button').find((b) => b.text()!.includes('影响分析'))!.trigger('click')
    await tick()
    expect(fetchGraphSpy).toHaveBeenNthCalledWith(3, expect.objectContaining({
      table: 'first_a', direction: 'downstream', depth: 0,
    }))
    resolvers[2]!(graphResOf('first'))
    await tick()
    // 聚焦高亮：doc 边全部 dep_focus（含运行事实 dep）
    const doc = wrapper.findComponent(WorkbenchStub).props('doc') as GraphDocument
    expect(doc.edges.length).toBeGreaterThan(0)
    expect(doc.edges.every((e) => e.kind === 'dep_focus')).toBe(true)
    // 源头追踪：方向 down→up + depth 已 0 → watcher 一次重拉（请求 4：upstream/depth=0）
    await wrapper.findAll('button').find((b) => b.text() === '源头追踪')!.trigger('click')
    await tick()
    expect(fetchGraphSpy).toHaveBeenNthCalledWith(4, expect.objectContaining({
      table: 'first_a', direction: 'upstream', depth: 0,
    }))
    wrapper.unmount()
  })
})

/* ---------- Task 7 审查修复：impact key 一致性（I-1/M-2）+ 面包屑落空（M-1）+ 同心幂等（M-3） ---------- */

describe('LineageView Task 7 审查修复', () => {
  it('M-3：双击当前中心表 → 幂等跳过（不压栈不重拉）', async () => {
    const wrapper = mountView()
    await tick()
    resolvers[0]!(graphResOf('first'))
    await tick()
    stubSelect = 'first_a'
    await wrapper.find('.wb-stub').trigger('click')
    await tick()  // 请求 2 = first_a 影响分析补拉
    // 双击当前中心表 first_a → centerOn 幂等：无新请求（修复前会同参冗余重拉）
    stubCenter = 'first_a'
    await wrapper.find('.wb-stub').trigger('dblclick')
    await tick()
    expect(fetchGraphSpy).toHaveBeenCalledTimes(2)
    // 面包屑仅 1 项（同中心不压栈）→ crumb-bar 不渲染
    expect(wrapper.find('.crumb-bar').exists()).toBe(false)
    wrapper.unmount()
  })

  it('M-2 + I-1：补拉失败回滚 key 允许同参重试；成功回写 rows 与 key 原子一致', async () => {
    const wrapper = mountView()
    await tick()
    resolvers[0]!(graphResOf('first'))
    await tick()
    // 选 first_a → 补拉（请求 2）失败 → key 回滚置空（不占位）
    stubSelect = 'first_a'
    await wrapper.find('.wb-stub').trigger('click')
    await tick()
    rejectors[1]!(new Error('boom'))
    await tick()
    // 切 first_b → 补拉（请求 3）成功 → rows 回写 + key 同步（I-1）
    stubSelect = 'first_b'
    await wrapper.find('.wb-stub').trigger('click')
    await tick()
    expect(fetchGraphSpy).toHaveBeenNthCalledWith(3, expect.objectContaining({ table: 'first_b' }))
    resolvers[2]!(graphResOf('first'))
    await tick()
    // 切回 first_a（此前失败未占 key）→ 允许重试补拉（请求 4）
    stubSelect = 'first_a'
    await wrapper.find('.wb-stub').trigger('click')
    await tick()
    expect(fetchGraphSpy).toHaveBeenNthCalledWith(4, expect.objectContaining({
      table: 'first_a', direction: 'downstream', depth: 0,
    }))
    wrapper.unmount()
  })

  it('I-1：搜索 miss 回滚后，在途补拉回写 rows 与 key 同步 → 重选同表不重发', async () => {
    const wrapper = mountView()
    await tick()
    resolvers[0]!(graphResOf('first'))
    await tick()
    // 选 first_a → 补拉（请求 2）在途；搜索未命中表 → 快照回滚（请求 3 miss）
    stubSelect = 'first_a'
    await wrapper.find('.wb-stub').trigger('click')
    await tick()
    await wrapper.find('input.search-in').setValue('zzz_miss')
    await wrapper.find('input.search-in').trigger('keyup.enter')
    await tick()
    expect(fetchGraphSpy).toHaveBeenCalledTimes(3)
    resolvers[2]!(graphResOf('r2'))  // miss 响应（不含 zzz_miss）
    await tick()
    // 画布回滚为搜索前快照（first 图）+ miss 提示
    const doc = wrapper.findComponent(WorkbenchStub).props('doc') as GraphDocument
    expect(doc.nodes.map((n) => n.id)).toEqual(['first_a', 'first_b'])
    expect(ElMessage.info).toHaveBeenCalledWith(expect.stringContaining('未找到'))
    // 在途补拉（请求 2）后至 → 守卫通过 → rows 回写且 key 同步（I-1 修复点）
    resolvers[1]!(graphResOf('first'))
    await tick()
    // 清选再重选同表 → key 命中 early-return，不重发请求（rows/key 脱节则会异常重发）
    stubSelect = null
    await wrapper.find('.wb-stub').trigger('click')
    await tick()
    stubSelect = 'first_a'
    await wrapper.find('.wb-stub').trigger('click')
    await tick()
    expect(fetchGraphSpy).toHaveBeenCalledTimes(3)
    wrapper.unmount()
  })

  it('M-1：换心落空 → selected 清空并弹出该 crumb（无 .cur 残留）', async () => {
    const wrapper = mountView()
    await tick()
    resolvers[0]!(graphResOf('first'))
    await tick()
    stubSelect = 'first_a'
    await wrapper.find('.wb-stub').trigger('click')
    await tick()  // 请求 2 = first_a 补拉（在途，无妨）
    // 双击 first_b 换心 → 重拉（请求 3）响应不含 first_b → 落空
    stubCenter = 'first_b'
    await wrapper.find('.wb-stub').trigger('dblclick')
    await tick()
    resolvers[2]!(graphResOf('r2'))
    await tick()
    // 落空清除：first_b crumb 同步弹出 → crumbs 回到 [first_a]（长度 1 不渲染面包屑）
    expect(fetchGraphSpy).toHaveBeenCalledTimes(4)  // 请求 4 = 换心触发的 first_b 补拉（后至被守卫丢弃）
    resolvers[3]!(graphResOf('r2'))
    await tick()
    expect(wrapper.find('.crumb-bar').exists()).toBe(false)
    expect(wrapper.find('.crumb.cur').exists()).toBe(false)
    wrapper.unmount()
  })

  it('M-1：切字段级再切回 → 末项 crumb 同步弹出，不残留 .cur', async () => {
    const wrapper = mountView()
    await tick()
    resolvers[0]!(graphResOf('first'))
    await tick()
    stubSelect = 'first_a'
    await wrapper.find('.wb-stub').trigger('click')
    await tick()  // 请求 2 = first_a 补拉
    // 双击 first_b 换心（请求 3 响应含 first_b，不落空）→ 面包屑两项，.cur=first_b
    stubCenter = 'first_b'
    await wrapper.find('.wb-stub').trigger('dblclick')
    await tick()
    resolvers[2]!(graphResOf('first'))
    await tick()
    expect(wrapper.find('.crumb.cur').text()).toBe('first_b')
    // 切字段级（selected 重置）→ 末项弹出；切回表级 → 不残留 .cur（修复前残留 first_b）
    await wrapper.findAll('button').find((b) => b.text() === '字段级血缘')!.trigger('click')
    await tick()
    await wrapper.findAll('button').find((b) => b.text() === '表级血缘')!.trigger('click')
    await tick()
    expect(wrapper.find('.crumb.cur').exists()).toBe(false)
    expect(wrapper.find('.crumb-bar').exists()).toBe(false)
    wrapper.unmount()
  })
})

/* ---------- Task 8：实例追溯模式化（上下文条 / 回到全量 / stmt_no 边标注） ---------- */

/** /lineage/tables 追溯行（instance_id 过滤返回，LineageEdgeRow 全字段） */
function traceRow(from: string, to: string, stmtNo: number, nodeId = 'n1'): LineageEdgeRow {
  return {
    from, to, task: `etl_${to} (E1)`, wf: 'WF-订单主题日增', instanceId: 'inst-001',
    nodeId, dsName: '', tmpFlag: 0, stmt: `INSERT INTO ${to} SELECT ...`, stmtNo, wfCode: 101,
    createTime: null,
  }
}

/** 实例详情（InstanceRow 形状：状态/起止时间/taskInstances 节点名匹配数据源） */
function instanceDetailOf(state: string) {
  return {
    instanceId: 'inst-001', wfCode: 101, state,
    startTime: '2026-09-30 01:00:00', endTime: '2026-09-30 01:05:00',
    taskInstances: [{
      id: 1, instanceId: 'inst-001', nodeId: 'n1', nodeType: 'sql', name: '加工订单',
      state, attempt: 1, loopIter: 0,
    }],
  }
}

describe('LineageView 实例追溯模式（Task 8）', () => {
  it('上下文条渲染：工作流/节点名/状态（色）/时间；边标注 stmt_no 次序', async () => {
    routeQuery.query = { instance: 'inst-001', node: 'n1' }
    listTableSpy.mockResolvedValue([traceRow('ods_a', 'dwd_b', 1), traceRow('dwd_b', 'ads_c', 2)])
    instanceDetailSpy.mockResolvedValue(instanceDetailOf('failure'))
    const wrapper = mountView()
    await tick()
    // 实例详情被拉取（getInstanceDetail）
    expect(instanceDetailSpy).toHaveBeenCalledWith('inst-001')
    // 上下文条：标题/工作流（追溯行 wf 字段）/节点名（taskInstances 匹配，非裸 nodeId）/状态/时间
    const bar = wrapper.find('.trace-bar')
    expect(bar.exists()).toBe(true)
    expect(bar.text()).toContain('实例追溯')
    expect(bar.text()).toContain('WF-订单主题日增')
    expect(bar.text()).toContain('加工订单')
    const pill = bar.find('.pill')
    expect(pill.classes()).toContain('err')
    expect(pill.text()).toBe('失败')
    expect(bar.text()).toContain('2026-09-30 01:00:00')
    expect(bar.text()).toContain('2026-09-30 01:05:00')
    // stmt_no 边标注：label 追加 #1 / #2（来自追溯行 stmtNo）
    const doc = wrapper.findComponent(WorkbenchStub).props('doc') as GraphDocument
    expect(doc.edges.map((e) => e.label)).toEqual(['etl_dwd_b (E1) #1', 'etl_ads_c (E1) #2'])
    wrapper.unmount()
  })

  it('回到全量：trace 态重置 + 清 instance/node 路由参 + 恢复 both/全链默认视图', async () => {
    routeQuery.query = { instance: 'inst-001', node: 'n1' }
    listTableSpy.mockResolvedValue([traceRow('ods_a', 'dwd_b', 1)])
    instanceDetailSpy.mockResolvedValue(instanceDetailOf('success'))
    const wrapper = mountView()
    await tick()
    expect(wrapper.find('.trace-bar').exists()).toBe(true)
    expect(fetchGraphSpy).not.toHaveBeenCalled()  // trace 走旧 /lineage/tables，不触 graph
    // 点「回到全量」→ 退出追溯
    await wrapper.findAll('button').find((b) => b.text() === '回到全量')!.trigger('click')
    await tick()
    expect(wrapper.find('.trace-bar').exists()).toBe(false)
    // 深链参数清理（replace 携带的 query 不含 instance/node）
    expect(routerReplace).toHaveBeenCalledTimes(1)
    const q = routerReplace.mock.calls[0]![0] as { query: Record<string, unknown> }
    expect(q.query.instance).toBeUndefined()
    expect(q.query.node).toBeUndefined()
    // 恢复表级默认视图：graph 请求 both + depth 0（无中心表初始态语义）
    expect(fetchGraphSpy).toHaveBeenCalledTimes(1)
    expect(fetchGraphSpy).toHaveBeenCalledWith(expect.objectContaining({
      level: 'table', direction: 'both', depth: 0, table: undefined,
    }))
    wrapper.unmount()
  })

  it('实例详情失败 → 追溯主体不阻断：状态/时间按 "-" 呈现，节点名退化 nodeId（不硬造）', async () => {
    routeQuery.query = { instance: 'inst-001', node: 'n1' }
    listTableSpy.mockResolvedValue([traceRow('ods_a', 'dwd_b', 1)])
    instanceDetailSpy.mockRejectedValue(new Error('boom'))
    const wrapper = mountView()
    await tick()
    const bar = wrapper.find('.trace-bar')
    expect(bar.exists()).toBe(true)
    expect(bar.text()).toContain('WF-订单主题日增')  // 追溯行自带的 wf 名仍展示
    const pill = bar.find('.pill')
    expect(pill.classes()).toContain('off')
    expect(pill.text()).toBe('-')
    expect(bar.text()).toContain('n1')  // 详情缺失 → 节点名退化 nodeId
    expect(bar.text()).not.toContain('2026-09-30')  // 时间缺失不硬造
    wrapper.unmount()
  })

  it('切级退出追溯：上下文条消失 + 恢复全量视图；不清路由参（深链可刷新回到追溯）', async () => {
    routeQuery.query = { instance: 'inst-001', node: 'n1' }
    listTableSpy.mockResolvedValue([traceRow('ods_a', 'dwd_b', 1)])
    instanceDetailSpy.mockResolvedValue(instanceDetailOf('success'))
    const wrapper = mountView()
    await tick()
    expect(wrapper.find('.trace-bar').exists()).toBe(true)
    await wrapper.findAll('button').find((b) => b.text() === '字段级血缘')!.trigger('click')
    await tick()
    expect(wrapper.find('.trace-bar').exists()).toBe(false)
    expect(routerReplace).not.toHaveBeenCalled()  // 切级不清参
    expect(fetchGraphSpy).toHaveBeenCalledWith(expect.objectContaining({ direction: 'both', depth: 0 }))
    wrapper.unmount()
  })

  it('trace 中改方向→回到全量：方向/深度复位默认且恢复单发；退出后选表重拉用 down/1（I-1/I-2 回归）', async () => {
    routeQuery.query = { instance: 'inst-001', node: 'n1' }
    listTableSpy.mockResolvedValue([traceRow('ods_a', 'dwd_b', 1)])
    instanceDetailSpy.mockResolvedValue(instanceDetailOf('success'))
    const wrapper = mountView()
    await tick()
    expect(wrapper.find('.trace-bar').exists()).toBe(true)
    // I-1：trace 模式方向/深度控件隐藏（不可点 → 无静默改值入口）
    expect(wrapper.findAll('button').some((b) => ['上游', '2层', '⚡ 影响分析'].includes(b.text()))).toBe(false)
    // 模拟历史静默改值（I-1 修复前控件可见可点）：直改内部参数；watcher 被追溯拦截、无请求
    const ss = (wrapper.vm.$ as unknown as { setupState: Record<string, unknown> }).setupState
    ss.direction = 'up'
    ss.depth = 2
    await tick()
    expect(fetchGraphSpy).not.toHaveBeenCalled()
    // 回到全量：参数复位触发 watcher 单发恢复（changed 路径 exitTrace 自身不再拉，防双发）
    await wrapper.findAll('button').find((b) => b.text() === '回到全量')!.trigger('click')
    await tick()
    expect(wrapper.find('.trace-bar').exists()).toBe(false)
    expect(fetchGraphSpy).toHaveBeenCalledTimes(1)
    expect(fetchGraphSpy).toHaveBeenCalledWith(expect.objectContaining({
      direction: 'both', depth: 0, table: undefined,
    }))
    // 复位基线：退出后选表再切「2层」→ 以复位后的 down/1 为基准重拉（depth 1→2 才有变化；
    // direction 用复位后的 down → downstream；任一未复位则本断言失败）
    resolvers[0]!(graphResOf('second'))
    await tick()
    stubSelect = 'second_a'
    await wrapper.find('.wb-stub').trigger('click')
    await tick()
    await wrapper.findAll('button').find((b) => b.text() === '2层')!.trigger('click')
    await tick()
    expect(fetchGraphSpy).toHaveBeenLastCalledWith(expect.objectContaining({
      direction: 'downstream', depth: 2, table: 'second_a',
    }))
    wrapper.unmount()
  })
})
