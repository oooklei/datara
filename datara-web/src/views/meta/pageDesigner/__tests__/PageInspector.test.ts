// @vitest-environment happy-dom
/**
 * Task 12 右侧属性面板用例（happy-dom）：
 * - 选中 widget → 布局/样式/数据绑定 三段 tabs；未选中 → 画布段（宽度/高度/背景填充）
 * - text widget：value 槽 scalar 候选 select + 手动输入开关；切手动输入后 a-input 出现
 *   （placeholder=模板默认值文案）；blur 空值 → updateWidget patch bindings.value.fallback === placeholder（resolveFallback 语义）
 * - table widget：dataset 槽候选首项 value 为 ds:1（catalog 桩）
 * - kind 映射：ds:→query / $wf.$param.$system→variable（fallback 恒为槽默认文案）
 * - dataset 槽库表钻取（D3/M3）：回显 ds:{id} → 库→表→字段懒加载（库列表按 dsId 缓存），
 *   选表 → updateWidget 生成只读查询绑定 SELECT * FROM db.table；换数据源保留已生成 query；
 *   钻取是辅助器不改变绑定回显；失败 ElMessage.error 不打断绑定
 * el-* 桩为原生元素（与既有组件用例同法）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ElMessage } from 'element-plus'
import PageInspector, { bindingOf } from '../inspector/PageInspector.vue'
import { normalizePage, type PageDSL } from '../designerModel'
import type { ResourceCatalog } from '../bindingCatalog'

/* pd* 库表钻取服务 mock（D3）：PageInspector 经 ../pageApi 拉库/表/字段 */
const pdDatabasesSpy = vi.hoisted(() => vi.fn())
const pdTablesSpy = vi.hoisted(() => vi.fn())
const pdColumnsSpy = vi.hoisted(() => vi.fn())
vi.mock('../pageApi', () => ({
  pdDatabases: pdDatabasesSpy,
  pdTables: pdTablesSpy,
  pdColumns: pdColumnsSpy,
}))

const CATALOG: ResourceCatalog = {
  datasources: [{ id: 1, name: '主库', type: 'mysql', db: 'mysql' }],
  workflows: [{ code: 1, name: '演示流', vars: [{ path: '$wf.demo.v', label: '演示变量', type: 'string' }] }],
  globalParams: [],
  timeParams: [],
  components: [],
}

const stubs = {
  ElTabs: { template: '<div class="stub-tabs"><slot /></div>' },
  ElTabPane: { props: ['label', 'name'], template: '<div class="stub-pane"><div class="stub-pane-label">{{ label }}</div><slot /></div>' },
  ElSelect: { name: 'ElSelect', props: ['modelValue'], emits: ['update:modelValue'], template: '<div class="stub-select"><slot /></div>' },
  ElTag: { template: '<span class="stub-tag"><slot /></span>' },
  ElButton: { name: 'ElButton', emits: ['click'], template: '<button class="stub-btn" @click="$emit(\'click\')"><slot /></button>' },
  ElOption: { props: ['label', 'value'], template: '<div class="stub-option" :value="value">{{ label }}</div>' },
  ElSwitch: {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<input type="checkbox" class="stub-switch" :checked="modelValue" @change="$emit(\'update:modelValue\', $event.target.checked)" />',
  },
  ElInput: {
    props: ['modelValue'],
    emits: ['update:modelValue', 'blur'],
    template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" @blur="$emit(\'blur\')" />',
  },
  ElInputNumber: {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<input type="number" :value="modelValue" @change="$emit(\'update:modelValue\', Number($event.target.value))" />',
  },
}

function makePage(kinds: string[]): PageDSL {
  return normalizePage({
    page: {
      version: 1,
      canvas: { width: 288, height: 520, background: { fill: '#ffffff' } },
      widgets: kinds.map((k, i) => ({ id: `w${i + 1}`, kind: k, rect: { x: 8, y: 8, w: 120, h: 32 }, props: {}, style: {}, bindings: {} })),
    },
  })
}

function mountInspector(props: Record<string, unknown> = {}) {
  return mount(PageInspector, {
    props: { page: makePage(['text']), catalog: CATALOG, ...props },
    global: { components: stubs },
  })
}

beforeEach(() => {
  vi.clearAllMocks()
})

type InspWrap = ReturnType<typeof mountInspector>

/** 模拟宿主：最近一次 updateWidget patch 应用回 page props（绑定回显依赖宿主落值，同宿主 onUpdateWidget 的 Object.assign 口径） */
async function syncLastPatch(w: InspWrap): Promise<void> {
  const evts = w.emitted('updateWidget')
  if (!evts?.length) return
  const [id, patch] = evts[evts.length - 1] as [string, Record<string, unknown>]
  // props 为响应式代理（structuredClone 不可克隆），JSON 深拷贝同宿主 pushClone 口径
  const page = JSON.parse(JSON.stringify(w.props('page'))) as PageDSL
  const widget = page.widgets.find((x) => x.id === id)
  if (widget) Object.assign(widget, patch)
  await w.setProps({ page })
}

describe('PageInspector', () => {
  it('选中 widget：渲染 布局/样式/数据绑定 三段', () => {
    const w = mountInspector({ selectedId: 'w1' })
    const labels = w.findAll('.stub-pane-label').map((n) => n.text())
    expect(labels).toContain('布局')
    expect(labels).toContain('样式')
    expect(labels).toContain('数据绑定')
  })

  it('text widget：value 槽 scalar select + 手动输入开关；空值 blur 落 placeholder 默认', async () => {
    const w = mountInspector({ selectedId: 'w1' })
    expect(w.find('.stub-select').exists()).toBe(true)
    expect(w.find('.stub-switch').exists()).toBe(true)
    // 切手动输入 → a-input 出现，placeholder = 模板默认值文案
    await w.find('.stub-switch').setValue(true)
    const inp = w.find('.pd-insp-manual input')
    expect(inp.exists()).toBe(true)
    expect(inp.attributes('placeholder')).toBe('文本内容')
    // blur 空值 → fallback 落 placeholder 文案
    await inp.setValue('')
    await inp.trigger('blur')
    const evts = w.emitted('updateWidget')
    expect(evts).toBeTruthy()
    const [, patch] = evts![0] as [string, { bindings: Record<string, { fallback: string }> }]
    expect(patch.bindings.value.fallback).toBe('文本内容')
  })

  it('table widget：dataset 槽候选首项 value 为 ds:1', () => {
    const w = mountInspector({ page: makePage(['table']), selectedId: 'w1' })
    const opts = w.findAll('.stub-option')
    expect(opts.length).toBeGreaterThan(0)
    expect(opts[0].attributes('value')).toBe('ds:1')
  })

  it('绑定 kind 映射：ds:→query（形状=datasourceId 无 query 字段）/ $wf.$param.$system→variable（fallback 恒为槽默认文案）', () => {
    // 新形状（后端 _validate_page_spec 同口径）：数据源引用型绑定仅 datasourceId，SQL 后续在数据集钻取中补
    expect(bindingOf('ds:1', '默认')).toEqual({ kind: 'query', datasourceId: 1, fallback: '默认' })
    for (const v of ['$wf.a.b', '$param.a', '$system.date']) {
      const b = bindingOf(v, '默认')
      expect(b.kind).toBe('variable')
      expect(b.path).toBe(v)
      expect(b.fallback).toBe('默认')
    }
  })

  it('未选中：显示画布段（宽度/高度/背景填充输入）', () => {
    const w = mountInspector({ selectedId: undefined })
    expect(w.text()).toContain('画布')
    expect(w.text()).toContain('宽度')
    expect(w.text()).toContain('高度')
    expect(w.text()).toContain('背景填充')
  })
})

describe('PageInspector dataset 槽库表钻取（D3/M3）', () => {
  it('选择 ds:1 → 钻取区出现并拉取库列表（mock pdDatabases）', async () => {
    pdDatabasesSpy.mockResolvedValue(['datara_dw', 'ods'])
    const w = mountInspector({ page: makePage(['table']), selectedId: 'w1' })
    await flushPromises()
    expect(w.find('.pd-insp-dd').exists()).toBe(false)
    expect(pdDatabasesSpy).not.toHaveBeenCalled()
    await w.findComponent({ name: 'ElSelect' }).vm.$emit('update:modelValue', 'ds:1')
    await syncLastPatch(w)
    expect(w.find('.pd-insp-dd').exists()).toBe(true)
    expect(pdDatabasesSpy).toHaveBeenCalledWith(1)
    await flushPromises()
    const dbOpts = w.findAll('.pd-insp-dd .stub-option').map((o) => o.attributes('value'))
    expect(dbOpts).toEqual(['datara_dw', 'ods'])
  })

  it('选库→选表 → updateWidget 生成只读查询绑定 + 字段标签（12 上限溢出 …N more）', async () => {
    pdDatabasesSpy.mockResolvedValue(['datara_dw'])
    pdTablesSpy.mockResolvedValue([
      { name: 't1', kind: 'table', rows: 128, comment: '' },
      { name: 'v_dim', kind: 'view', rows: null, comment: '' },
    ])
    pdColumnsSpy.mockResolvedValue(
      Array.from({ length: 14 }, (_, i) => ({
        name: `c${i}`, dataType: 'varchar', columnType: 'varchar(64)', length: 64,
        nullable: true, key: '', comment: '', extra: '', defaultValue: null,
      })),
    )
    const w = mountInspector({ page: makePage(['table']), selectedId: 'w1' })
    await w.findComponent({ name: 'ElSelect' }).vm.$emit('update:modelValue', 'ds:1')
    await syncLastPatch(w)
    await flushPromises()
    // 选库 → 懒拉表清单（选项 label 带 kind/rows 摘要）
    const dbSel = w.findAllComponents({ name: 'ElSelect' }).find((c) => c.classes().includes('pd-insp-dd-db'))
    await dbSel!.vm.$emit('update:modelValue', 'datara_dw')
    await flushPromises()
    expect(pdTablesSpy).toHaveBeenCalledWith(1, 'datara_dw')
    const tbOpts = w.findAll('.pd-insp-dd .stub-option').map((o) => o.text())
    expect(tbOpts.some((t) => t.includes('t1 (table'))).toBe(true)
    expect(tbOpts.some((t) => t.includes('v_dim (view'))).toBe(true)
    // 选表 → 生成只读查询绑定（免手写 SQL）
    const tbSel = w.findAllComponents({ name: 'ElSelect' }).find((c) => c.classes().includes('pd-insp-dd-tb'))
    await tbSel!.vm.$emit('update:modelValue', 't1')
    await flushPromises()
    const evts = w.emitted('updateWidget')!
    const [, patch] = evts[evts.length - 1] as [string, { bindings: Record<string, { kind: string; datasourceId: number; query: string; fallback: string }> }]
    expect(patch.bindings.data).toEqual({ kind: 'query', datasourceId: 1, query: 'SELECT * FROM datara_dw.t1', fallback: '暂无数据' })
    expect(pdColumnsSpy).toHaveBeenCalledWith(1, 'datara_dw', 't1')
    // 字段只读标签：最多 12 个 + 溢出文案
    expect(w.findAll('.pd-insp-dd .stub-tag')).toHaveLength(12)
    expect(w.find('.pd-insp-dd-more').text()).toBe('…2 more')
    // 钻取是辅助器：绑定回显仍是 ds:1
    expect(w.findComponent({ name: 'ElSelect' }).props('modelValue')).toBe('ds:1')
  })

  it('非 dataset 槽 / 非 ds: 回显 → 不渲染钻取区', async () => {
    // text widget scalar 槽绑变量 → 不渲染
    const w1 = mountInspector({ selectedId: 'w1' })
    await w1.findComponent({ name: 'ElSelect' }).vm.$emit('update:modelValue', '$wf.demo.v')
    await syncLastPatch(w1)
    expect(w1.find('.pd-insp-dd').exists()).toBe(false)
    expect(pdDatabasesSpy).not.toHaveBeenCalled()
    // table widget dataset 槽 static 绑定（回显空）→ 不渲染
    const page = makePage(['table'])
    page.widgets[0].bindings = { data: { kind: 'static', fallback: 'x' } }
    const w2 = mountInspector({ page, selectedId: 'w1' })
    await flushPromises()
    expect(w2.find('.pd-insp-dd').exists()).toBe(false)
    expect(pdDatabasesSpy).not.toHaveBeenCalled()
  })

  it('库列表按 dsId 缓存：切走再切回同数据源不重复请求', async () => {
    pdDatabasesSpy.mockResolvedValue(['datara_dw'])
    const page = makePage(['table', 'table'])
    page.widgets[0].bindings = { data: { kind: 'query', datasourceId: 1, fallback: '暂无数据' } }
    page.widgets[1].bindings = { data: { kind: 'query', datasourceId: 1, fallback: '暂无数据' } }
    const w = mountInspector({ page, selectedId: 'w1' })
    await flushPromises()
    expect(pdDatabasesSpy).toHaveBeenCalledTimes(1)
    await w.setProps({ selectedId: 'w2' })
    await flushPromises()
    await w.setProps({ selectedId: 'w1' })
    await flushPromises()
    expect(pdDatabasesSpy).toHaveBeenCalledTimes(1)
  })

  it('库列表失败：ElMessage.error 且绑定回显不打断', async () => {
    pdDatabasesSpy.mockRejectedValue(new Error('连接超时'))
    const errSpy = vi.spyOn(ElMessage, 'error').mockImplementation((() => ({})) as never)
    const w = mountInspector({ page: makePage(['table']), selectedId: 'w1' })
    await w.findComponent({ name: 'ElSelect' }).vm.$emit('update:modelValue', 'ds:1')
    await syncLastPatch(w)
    await flushPromises()
    expect(errSpy).toHaveBeenCalledTimes(1)
    expect(String(errSpy.mock.calls[0][0])).toContain('库列表加载失败')
    expect(w.findComponent({ name: 'ElSelect' }).props('modelValue')).toBe('ds:1')
    vi.restoreAllMocks()
  })

  it('换数据源：已生成 query 保留（显式重选表才覆盖）且钻取选择器重置', async () => {
    pdDatabasesSpy.mockResolvedValue(['datara_dw'])
    pdTablesSpy.mockResolvedValue([{ name: 't1', kind: 'table', rows: 128, comment: '' }])
    pdColumnsSpy.mockResolvedValue([])
    const w = mountInspector({ page: makePage(['table']), selectedId: 'w1' })
    // ds:1 → 选库选表生成 query
    await w.findComponent({ name: 'ElSelect' }).vm.$emit('update:modelValue', 'ds:1')
    await syncLastPatch(w)
    await flushPromises()
    const dbSel = () => w.findAllComponents({ name: 'ElSelect' }).find((c) => c.classes().includes('pd-insp-dd-db'))!
    const tbSel = () => w.findAllComponents({ name: 'ElSelect' }).find((c) => c.classes().includes('pd-insp-dd-tb'))!
    await dbSel().vm.$emit('update:modelValue', 'datara_dw')
    await flushPromises()
    await tbSel().vm.$emit('update:modelValue', 't1')
    await syncLastPatch(w)
    await flushPromises()
    // 换数据源 ds:2：query 保留
    await w.findComponent({ name: 'ElSelect' }).vm.$emit('update:modelValue', 'ds:2')
    await syncLastPatch(w)
    const evts = w.emitted('updateWidget')!
    const [, patch] = evts[evts.length - 1] as [string, { bindings: Record<string, { kind: string; datasourceId: number; query?: string; fallback: string }> }]
    expect(patch.bindings.data.datasourceId).toBe(2)
    expect(patch.bindings.data.query).toBe('SELECT * FROM datara_dw.t1')
    // 钻取选择器重置（库/表清空）
    await flushPromises()
    expect(dbSel().props('modelValue')).toBe('')
    expect(tbSel().props('modelValue')).toBe('')
  })
})

describe('PageInspector 布局 tab 层级控制（D5/M6）', () => {
  it('层级行四按钮（置顶/上移/下移/置底）点击 → emit reorder [id, action]', async () => {
    const w = mountInspector({ page: makePage(['text']), selectedId: 'w1' })
    const btns = w.findAll('.stub-btn')
    expect(btns.map((b) => b.text())).toEqual(['置顶', '上移', '下移', '置底'])
    const want: [string, string][] = [['置顶', 'top'], ['上移', 'up'], ['下移', 'down'], ['置底', 'bottom']]
    for (const [label] of want) {
      await btns.find((b) => b.text() === label)!.trigger('click')
    }
    expect(w.emitted('reorder')).toEqual([
      ['w1', 'top'], ['w1', 'up'], ['w1', 'down'], ['w1', 'bottom'],
    ])
  })
})
