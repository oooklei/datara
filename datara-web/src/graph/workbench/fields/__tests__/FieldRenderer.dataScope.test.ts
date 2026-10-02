// @vitest-environment happy-dom
/**
 * F3 dataScope 值域过滤交互用例（FieldRenderer 挂载级；Inspector/弹窗共用该渲染器，一处验证双入口生效）：
 * - 上游无 schema（空上游降级）→ select 禁用 + 行内原因提示（「禁用必说明」交互约定）
 * - 域非空 → 候选只来自 DataContext 对应域（静态 options 干扰项不出现）
 * - expr readonly + dataScope：候选收窄到对应域、写回 ${var} 形态；域空禁用
 * - 值域外存量值兜底展示（不静默丢值）
 * ctx 为最小桩（FieldCtx 全字段），dataCtx 由用例直接注入；useGraphStore 需 pinia 激活。
 */
import { describe, expect, it } from 'vitest'
import { computed, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import FieldRenderer from '../FieldRenderer.vue'
import type { FieldSchema, NodeSchema } from '../../../profiles/types'
import type { DataContext } from '../../../profiles/formLinkage'
import type { FieldCtx } from '../fieldCtx'

/** 最小 FieldCtx 桩：仅 dataCtx 可变，其余置空值/空实现（F3 分支不触达其余通道） */
function makeCtx(dc: DataContext): FieldCtx {
  const emptySchema: NodeSchema = { type: 'stub', label: '桩', icon: '?', color: '#000', form: [] }
  return {
    upstream: computed(() => []),
    upSchema: () => emptySchema,
    upstreamOpts: computed(() => []),
    upstreamOuts: computed(() => []),
    epProbe: computed(() => null),
    dsRows: ref([]),
    scripts: ref([]),
    runtimeNodes: ref([]),
    tagOptions: computed(() => []),
    varOptions: ref(['run.instanceId', 'dialog_only_var']),
    dataCtx: computed(() => dc),
    pickTrees: ref({}),
    pickTreeErr: ref({}),
    pickTreeBusy: ref({}),
    topicOpts: ref({}),
    topicErr: ref({}),
    topicBusy: ref({}),
    dirNavs: ref({}),
    ensureTree: async () => null,
    ensureTopics: async () => {},
    lsDir: () => {},
    loadScriptCode: () => {},
    saveToScript: () => {},
    saveAsNewScript: async () => {},
    markDirty: () => {},
    schema: computed(() => emptySchema),
  }
}

function mountField(field: FieldSchema, dc: DataContext, data: Record<string, unknown> = {}) {
  setActivePinia(createPinia())
  return mount(FieldRenderer, {
    props: { field, data, mode: 'edit' as const, nodeId: 'n1', ctx: makeCtx(dc) },
    /* 模板其余分支的 el-* 组件：Vue 编译期提升 resolveComponent 触发告警，桩掉消噪音 */
    global: {
      components: {
        ElCascader: { template: '<div />' },
        ElSelect: { template: '<div><slot /></div>' },
        ElOption: { template: '<div />' },
      },
    },
  })
}

const selectOf = (w: { find: (s: string) => { element: Element } }) => w.find('select').element as HTMLSelectElement

describe('F3 dataScope 字段渲染（Inspector/弹窗共用 FieldRenderer）', () => {
  it('上游无 schema → upstream-columns 域空：select 禁用 + 行内原因提示；值域外存量值兜底展示', () => {
    const dc: DataContext = { upstreamColumns: [], upstreamTables: [], vars: ['gp1'], timeParams: ['biz_date'], downstreamNeeds: [] }
    const w = mountField(
      { key: 'refCol', label: '引用列', type: 'select', dataScope: 'upstream-columns' },
      dc,
      { refCol: 'legacy_col' },
    )
    expect(selectOf(w).disabled).toBe(true)
    expect(w.text()).toContain('上游无可引用列')
    const opts = w.findAll('option').map((o) => o.text())
    expect(opts.some((t) => t.includes('legacy_col') && t.includes('值域外'))).toBe(true) // 不静默丢值
  })

  it('域非空 → 候选只来自 DataContext（静态 options 干扰项不出现），select 可用', () => {
    const dc: DataContext = { upstreamColumns: [], upstreamTables: [], vars: ['gp_rate', 'run.instanceId'], timeParams: [], downstreamNeeds: [] }
    const w = mountField(
      { key: 'v', label: '引用变量', type: 'select', dataScope: 'workflow-vars', options: [{ value: 'static_x', label: '静态干扰项' }] },
      dc,
    )
    expect(selectOf(w).disabled).toBe(false)
    const texts = w.findAll('option').map((o) => o.text())
    expect(texts).toContain('gp_rate')
    expect(texts.some((t) => t.includes('静态干扰项'))).toBe(false) // 值域只来自 DataContext
  })

  it('expr readonly + time-params：候选收窄到时间域写回 ${var}；域空禁用并说明', () => {
    const ok: DataContext = { upstreamColumns: [], upstreamTables: [], vars: ['gp1'], timeParams: ['biz_date'], downstreamNeeds: [] }
    const w1 = mountField({ key: 't', label: '时间参数', type: 'expr', readonly: true, dataScope: 'time-params' }, ok)
    expect(selectOf(w1).disabled).toBe(false)
    const vals = w1.findAll('option').map((o) => (o.element as HTMLOptionElement).value)
    expect(vals).toContain('${biz_date}')
    expect(vals).not.toContain('${gp1}') // workflow-vars 域不串入

    const empty: DataContext = { upstreamColumns: [], upstreamTables: [], vars: ['gp1'], timeParams: [], downstreamNeeds: [] }
    const w2 = mountField({ key: 't', label: '时间参数', type: 'expr', readonly: true, dataScope: 'time-params' }, empty)
    expect(selectOf(w2).disabled).toBe(true)
    expect(w2.text()).toContain('内置时间参数不可用')
  })
})
