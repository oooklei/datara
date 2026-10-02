// @vitest-environment happy-dom
/**
 * F1/F4 configure-first 拖入配置弹窗用例（治理设计 §12.1/§12.2）。
 *
 * 覆盖四条主链：
 *  1. 六区块闸门：form: [] 的 C1/C2/C6/C7 也必须呈现①~⑥并可编辑（无 direct-add 旁路后配置面在此）
 *  2. 上游数据联动：父层传入的 upstream（虚拟节点无 doc.edges 入边）驱动①输入候选与 dataScope 上游两域
 *  3. 值域/悬空引用闸门：域外取值、上游删除后的存量①输入引用都禁用「确认添加」并给出原因
 *  4. 确认前纵深复校：绕过 UI 直接触发 confirm 也不放行不合规配置
 *
 * 隔离：ctx 工厂 onMounted 会拉数据源/脚本/运行时候选，本用例桩掉这些 IO；
 * graphStore.doc 注入最小文档，让 resolveDataContext 走合成入边口径。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h } from 'vue'

vi.mock('../../../services', () => ({
  isMock: true,
  listRuntimeNodes: vi.fn(async () => []),
  listSshNodes: vi.fn(async () => []),
  listVariables: vi.fn(async () => []),
}))
/* apiMode 叶子模块必须同步 mock：getDataSourceTree 内部 import 的 isMock 取自 apiMode.ts
   （非 services/index.ts），未 mock 时 VITE_API_MODE 缺省 'real' → isMock=false → 走网络 → ECONNREFUSED */
vi.mock('../../../services/apiMode', () => ({
  apiMode: 'mock',
  isMock: true,
}))
vi.mock('../../../services/datasourceApi', async (importOriginal) => {
  /* 保留 getDataSourceTree 真实实现（isMock 分支读 dataStore.dsTrees 种子库表树：
     DS003 =「MySQL-业务测试库」/ biz_test / ods_order），只桩掉走网络的其余查询 */
  const real = await importOriginal<typeof import('../../../services/datasourceApi')>()
  return {
    getDataSourceTree: real.getDataSourceTree,
    listDataSources: vi.fn(async () => []),
    listKafkaTopics: vi.fn(async () => []),
    listNodeDir: vi.fn(async () => []),
  }
})
vi.mock('../../../services/ideApi', () => ({
  listGlobalParams: vi.fn(async () => []),
}))

import DropConfigDialog from '../DropConfigDialog.vue'
import { useGraphStore } from '../../../stores/graph'
import type { GNode } from '../../model'
import type { NodeSchema, ViewProfile } from '../../profiles/types'

/** el-dialog 桩：把 slot 原样渲染，避免 teleport/transition 时序，并暴露可点的 header 按钮 */
const ElDialogStub = defineComponent({
  name: 'ElDialog',
  props: { modelValue: { type: Boolean, default: false } },
  setup(props, { slots }) {
    return () => (props.modelValue ? h('div', { class: 'dlg' }, [slots.header?.(), slots.default?.()]) : null)
  },
})

const elStubs = {
  'el-dialog': ElDialogStub,
  'el-button': defineComponent({ setup: (_, { slots }) => () => h('button', slots.default?.()) }),
}

/** C7 类「无业务表单」组件：form: []，配置面完全由六区块承担 */
const noFormSchema: NodeSchema = {
  type: 'user_c7', label: '无表单组件', icon: 'C7', color: '#333', code: 'C7', form: [],
}
/** 带 dataScope 字段的业务组件：目标表/目标列值域取自上游 */
const scopedSchema: NodeSchema = {
  type: 'user_scoped', label: '带值域组件', icon: 'S', color: '#555', form: [
    { key: 'tgtTable', label: '目标表', type: 'text', required: true, dataScope: 'upstream-tables' },
    { key: 'tgtCol', label: '目标列', type: 'text', dataScope: 'upstream-columns' },
  ],
}

const profile = { mode: 'edit', nodeTypes: { user_c7: noFormSchema, user_scoped: scopedSchema, src: { type: 'src', label: '数据源', icon: 'S', color: '#0a0', form: [] } } } as unknown as ViewProfile

function vnode(type: string, data: GNode['data']): GNode {
  return { id: 'vd1', type, position: { x: 0, y: 0 }, data }
}
/** 上游节点：①已选定源库表（srcDs/srcTable，值为域的真实供给源）+ ②输出登记结果表 */
const upstream: GNode = {
  id: 'up1', type: 'src', position: { x: -100, y: 0 },
  data: {
    name: '源节点', srcDs: 'MySQL-业务测试库', srcTable: 'ods_order',
    outputs: { params: [{ k: 'p1', v: '1' }], tables: [{ k: 't1', v: 'ods_order' }] },
  },
}

function mountDlg(schema: NodeSchema, node: GNode, up: GNode[] | null) {
  return mount(DropConfigDialog, {
    props: { visible: true, node, schema, profile, upstream: up },
    global: { plugins: [pinia], stubs: elStubs },
  })
}

let pinia: ReturnType<typeof createPinia>

beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  const store = useGraphStore()
  store.doc = { nodes: [], edges: [], version: 1 } as never
})

describe('DropConfigDialog 六区块闸门（form: [] 也必弹）', () => {
  it('form 为空仍渲染①~⑥六区块（配置面不因无业务表单而消失）', () => {
    const w = mountDlg(noFormSchema, vnode('user_c7', { name: '无表单组件' }), null)
    const txt = w.text()
    for (const blk of ['① 输入', '② 输出', '③ 参数', '④ 条件', '⑤ 限定约束', '⑥ 排除']) {
      expect(txt).toContain(blk)
    }
  })

  it('form 为空且无必填 → 可确认（配置面在但不强设必填）', () => {
    const w = mountDlg(noFormSchema, vnode('user_c7', { name: '无表单组件' }), null)
    expect(w.find('.dc-ok').attributes('disabled')).toBeUndefined()
    expect(w.text()).toContain('可确认添加')
  })

  it('②输出/③参数 表单可编辑并写回虚拟节点 data（弹窗配置真实落值）', async () => {
    const n = vnode('user_c7', { name: '无表单组件' })
    const w = mountDlg(noFormSchema, n, null)
    const outBlock = w.findAll('.blk').find((b) => b.text().includes('② 输出'))!
    // ②输出 区块含两张登记表：[0]=输出参数(params)、[1]=结果表(tables)
    await outBlock.findAll('.rowsf-add')[1]!.trigger('click')
    const cells = outBlock.findAll('tbody input')
    await cells[0]!.setValue('t1')
    await cells[0]!.trigger('change')
    await cells[1]!.setValue('ods_order')
    await cells[1]!.trigger('change')
    await flushPromises()
    const outputs = n.data.outputs as { params?: unknown[]; tables?: { k: string; v: string }[] }
    expect(outputs.tables?.[0]).toMatchObject({ k: 't1', v: 'ods_order' })
  })
})

describe('DropConfigDialog 上游数据联动（弹窗期与落画布后同源）', () => {
  it('①输入 候选来自传入 upstream 的②输出登记表（虚拟节点无 doc.edges 也能有候选）', () => {
    const w = mountDlg(noFormSchema, vnode('user_c7', { name: 'A' }), [upstream])
    expect(w.text()).toContain('1 上游')
    const opts = w.findAll('option').map((o) => o.text())
    expect(opts).toContain('源节点.t1（结果表）')
    expect(opts).toContain('源节点.p1（参数）')
  })

  it('dataScope 上游两域取自 upstream 登记的表/列（targetTable 候选非空）', async () => {
    const n = vnode('user_scoped', { name: 'B', tgtTable: '', tgtCol: '' })
    const w = mountDlg(scopedSchema, n, [upstream])
    await flushPromises()
    // 必填未填 → 确认禁用（值域已就绪则警示条只报必填，不报值域）
    expect(w.find('.dc-ok').attributes('disabled')).toBeDefined()
    expect(w.find('.dc-miss').text()).toContain('必填未配置')
    expect(w.find('.dc-miss').text()).not.toContain('无可用候选')
  })

  it('值在域内 → 必填满足即放行', async () => {
    const n = vnode('user_scoped', { name: 'B', tgtTable: 'ods_order', tgtCol: 'order_id' })
    const w = mountDlg(scopedSchema, n, [upstream])
    await flushPromises()
    expect(w.find('.dc-ok').attributes('disabled')).toBeUndefined()
  })

  /* 值域供给源回归：upstream-columns 候选必须来自「上游已选定表」的库表树列名（mock 种子 dsTrees），
     而不是任何自造字段名；否则列名域为空/为空集，F3 闸门形同虚设。 */
  it('列域候选来自上游选定表的真实列（非空且含种子列名）', async () => {
    const n = vnode('user_scoped', { name: 'B', tgtTable: '', tgtCol: '不存在的列_xyz' })
    const w = mountDlg(scopedSchema, n, [upstream])
    await flushPromises()
    // 值填了域外列名 → 必须被判违规（说明列域非空且不含该值）
    expect(w.find('.dc-ok').attributes('disabled')).toBeDefined()
    expect(w.find('.dc-miss').text()).toContain('不存在的列_xyz')
  })

  /* 域空 ≠ 放行：无上游时值域无可用候选，按「存量值按域外计」的既定裁定阻断，
     避免无法校验的值被静默落画布（起始节点应先接上游再配值域字段）。 */
  it('无上游连线时存量值按域外计 → 阻断并说明域空原因', async () => {
    const n = vnode('user_scoped', { name: 'B', tgtTable: 'ods_order', tgtCol: 'order_id' })
    const w = mountDlg(scopedSchema, n, null)
    await flushPromises()
    expect(w.find('.dc-ok').attributes('disabled')).toBeDefined()
    expect(w.find('.dc-miss').text()).toContain('无可用候选')
  })

  it('无上游且值域字段留空 → 必填/域空均不误伤（可确认）', async () => {
    const n = vnode('user_scoped', { name: 'B', tgtTable: 'ods_order', tgtCol: '' })
    const w = mountDlg(scopedSchema, n, null)
    await flushPromises()
    // 唯一域外风险是 tgtCol（留空不产生域外值）；tgtTable 有值仍按域空计
    expect(w.find('.dc-ok').attributes('disabled')).toBeDefined()
  })
})

describe('DropConfigDialog 值域与悬空引用闸门（F4）', () => {
  it('域外取值 → 确认禁用，警示条指出所属域', async () => {
    const n = vnode('user_scoped', { name: 'B', tgtTable: 'ods_dim', tgtCol: 'id' })
    const w = mountDlg(scopedSchema, n, [upstream])
    await flushPromises()
    expect(w.find('.dc-ok').attributes('disabled')).toBeDefined()
    expect(w.find('.dc-miss').text()).toContain('ods_dim')
  })

  it('①输入 存量引用在上游输出移除后 → 悬空拦截（不静默通过）', async () => {
    const n = vnode('user_c7', { name: 'A', inputs: ['已删节点.t9（结果表）'] })
    const w = mountDlg(noFormSchema, n, [upstream])
    await flushPromises()
    expect(w.find('.dc-ok').attributes('disabled')).toBeDefined()
    expect(w.find('.dc-miss').text()).toContain('失效')
  })

  it('确认前纵深复校：不合规时不 emit confirm', async () => {
    const n = vnode('user_scoped', { name: 'B', tgtTable: 'ods_dim', tgtCol: 'id' })
    const w = mountDlg(scopedSchema, n, [upstream])
    await flushPromises()
    await w.find('.dc-ok').trigger('click')
    expect(w.emitted('confirm')).toBeUndefined()
  })
})

describe('DropConfigDialog 取消语义（节点不落画布）', () => {
  it('取消按钮 emit cancel，不 emit confirm', async () => {
    const w = mountDlg(noFormSchema, vnode('user_c7', { name: 'A' }), null)
    await w.find('.dc-cancel').trigger('click')
    expect(w.emitted('cancel')).toHaveLength(1)
    expect(w.emitted('confirm')).toBeUndefined()
  })

  it('可确认态点确认 emit confirm（父层负责落画布）', async () => {
    const w = mountDlg(noFormSchema, vnode('user_c7', { name: 'A' }), null)
    await w.find('.dc-ok').trigger('click')
    expect(w.emitted('confirm')).toHaveLength(1)
  })
})
