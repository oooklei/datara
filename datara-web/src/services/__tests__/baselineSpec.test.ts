import { describe, it, expect } from 'vitest'
import {
  normalizeBaselineSpec, validateBaselineSpec, allFieldKeys, diffSummary,
  type BaselineSpec,
} from '../baselineSpec'

/* M-B0 八段 DSL：归一化 / 结构校验 / 键全集 / 旧声明 diff（纯函数单测） */

/** 合法八段样例（三段字段 + 五类横切 + 血缘 + 渲染） */
function goodSpec(): BaselineSpec {
  return normalizeBaselineSpec({
    form: {
      inputs: [{ key: 'srcTable', label: '源表', uiType: 'resource', required: true, visible: true, cap: { kinds: ['table'] } }],
      outputs: [{ key: 'tgtTable', label: '目标表', uiType: 'resource', required: true, visible: true }],
      params: [
        { key: 'mode', label: '模式', uiType: 'select', required: false, visible: true, options: [{ label: '并行', value: 'parallel' }] },
        { key: 'parallel', label: '并行度', uiType: 'number', required: false, visible: false, default: 4 },
      ],
      conditions: [{ id: 'c1', when: { field: 'mode', op: 'eq', value: 'parallel' }, show: ['parallel'] }],
      constraints: [{ field: 'parallel', type: 'min', value: 1, msg: '至少 1' }],
      exclusions: [{ when: { field: 'mode', value: 'single' }, exclude: { field: 'parallel', values: [2, 4] } }],
      refs: [{ field: 'srcTable', scopes: ['wf', 'env'] }],
      exports: [{ key: 'rows', from: 'log', type: 'int', logKey: 'row_count' }],
    },
    lineage: { assets: [{ role: 'source', pick: 'srcTable', assetType: 'table' }] },
    render: { icon: '⇄', color: '#4C7CF0', summary: '同步', ports: { inputs: [{ name: 'in', type: 'any' }], outputs: [{ name: 'out', type: 'any' }] } },
    dropPolicy: { autoName: '{type}-{n}' },
    paletteVisible: true,
  })
}

describe('normalizeBaselineSpec', () => {
  it('空底稿 {} 补全为完整可编辑形态（八段空数组/渲染骨架/缺省布尔）', () => {
    const s = normalizeBaselineSpec({})
    expect(s.form.inputs).toEqual([])
    expect(s.form.outputs).toEqual([])
    expect(s.form.params).toEqual([])
    expect(s.form.conditions).toEqual([])
    expect(s.form.constraints).toEqual([])
    expect(s.form.exclusions).toEqual([])
    expect(s.form.refs).toEqual([])
    expect(s.form.exports).toEqual([])
    expect(s.lineage.assets).toEqual([])
    expect(s.render).toEqual({ icon: '', color: '', summary: '', ports: { inputs: [], outputs: [] } })
    expect(s.dropPolicy).toEqual({})
    expect(s.paletteVisible).toBe(true)
    expect(s.meta).toBeUndefined()
  })

  it('null/数组等非对象输入按空底稿处理', () => {
    for (const raw of [null, undefined, 42, 'x', [], true]) {
      const s = normalizeBaselineSpec(raw)
      expect(s.form.inputs).toEqual([])
      expect(s.form.exports).toEqual([])
    }
  })

  it('非法 uiType 回退 text；options 仅 select 携带、cap 仅 resource 携带', () => {
    const s = normalizeBaselineSpec({
      form: {
        inputs: [
          { key: 'a', label: 'A', uiType: 'wasm', required: true }, // 非法 uiType → text
          { key: 'b', label: 'B', uiType: 'select', options: [{ label: '开', value: 'on' }] },
          { key: 'c', label: 'C', uiType: 'resource', cap: { kinds: ['table'] } },
          { key: 'd', label: 'D', uiType: 'text', options: [{ label: '脏数据', value: 'x' }] }, // 非 select 不落 options
        ],
      },
    })
    const [a, b, c, d] = s.form.inputs
    expect(a.uiType).toBe('text')
    expect(a.options).toBeUndefined()
    expect(a.visible).toBe(true) // visible 缺省 true
    expect(b.uiType).toBe('select')
    expect(b.options).toEqual([{ label: '开', value: 'on' }])
    expect(c.cap).toEqual({ kinds: ['table'] })
    expect(d.options).toBeUndefined()
  })

  it('非法 op 回退 eq；scopes 过滤白名单五域；from 回退 result；visible=false 保留', () => {
    const s = normalizeBaselineSpec({
      form: {
        params: [{ key: 'x', label: 'X', uiType: 'text', required: false, visible: false }],
        conditions: [{ id: 'c', when: { field: 'x', op: 'hack', value: 1 }, show: ['x'] }],
        refs: [{ field: 'x', scopes: ['wf', 'bogus', 'global'] }],
        exports: [{ key: 'o', from: 'stdout', type: 'str' }],
      },
    })
    expect(s.form.conditions[0].when.op).toBe('eq')
    expect(s.form.refs[0].scopes).toEqual(['wf', 'global'])
    expect(s.form.exports[0].from).toBe('result')
    expect(s.form.params[0].visible).toBe(false)
  })

  it('meta 迁移标记与实测草稿（testDrafts）归一化保留', () => {
    const s = normalizeBaselineSpec({
      form: {},
      meta: { migratedAt: '2026-09-28 10:00:00', source: 'dag_catalog', testDrafts: [{ batch: 'B1', dataflow: 'ods→dwd', result: 'pass' }] },
    })
    expect(s.meta?.migratedAt).toBe('2026-09-28 10:00:00')
    expect(s.meta?.source).toBe('dag_catalog')
    expect(s.meta?.testDrafts).toEqual([{ batch: 'B1', dataflow: 'ods→dwd', result: 'pass' }])
  })
})

describe('validateBaselineSpec', () => {
  it('合法样例零违规（含 from=log 带 logKey）', () => {
    expect(validateBaselineSpec(goodSpec())).toEqual([])
  })

  it('非对象输入违规；禁用片段（=> / function / ${）被全扫描捕获', () => {
    expect(validateBaselineSpec('nope').length).toBeGreaterThan(0)
    expect(validateBaselineSpec(null).length).toBeGreaterThan(0)
    const s = goodSpec()
    s.form.params[0].label = '并行 => eval('
    const vs = validateBaselineSpec(s)
    expect(vs.some((v) => v.msg.includes('=>'))).toBe(true)
  })

  it('form 八段键白名单：越界键报违规', () => {
    const s = goodSpec() as unknown as Record<string, unknown>
    const form = s.form as Record<string, unknown>
    form.secret = [{ key: 'x' }]
    const vs = validateBaselineSpec(s)
    expect(vs.some((v) => v.path === 'form.secret')).toBe(true)
  })

  it('字段行 key/label/uiType 必填、uiType 不在 9 基元报违规', () => {
    const s = goodSpec()
    s.form.params.push({ key: '', label: '', uiType: 'wasm' as never, required: false, visible: true })
    const vs = validateBaselineSpec(s)
    expect(vs.some((v) => v.path === 'form.params[2].key')).toBe(true)
    expect(vs.some((v) => v.path === 'form.params[2].label')).toBe(true)
    expect(vs.some((v) => v.path === 'form.params[2].uiType')).toBe(true)
  })

  it('同段 key 重复报违规（不同段同名合法）', () => {
    const s = goodSpec()
    s.form.params.push({ ...s.form.params[0] })
    const vs = validateBaselineSpec(s)
    expect(vs.some((v) => v.msg.includes('重复'))).toBe(true)
    // inputs.srcTable 与 params.srcTable 同名不算同段重复，但引用检查仍可用
    expect(validateBaselineSpec(goodSpec())).toEqual([])
  })

  it('conditions.show / when.field 引用不存在字段报违规', () => {
    const s = goodSpec()
    s.form.conditions[0].show.push('ghost')
    s.form.conditions.push({ id: 'c2', when: { field: 'nope', op: 'eq' }, show: [] })
    const vs = validateBaselineSpec(s)
    expect(vs.some((v) => v.path === 'form.conditions[0].show' && v.msg.includes('ghost'))).toBe(true)
    expect(vs.some((v) => v.path === 'form.conditions[1].when.field')).toBe(true)
  })

  it('constraints.field / refs.field 引用不存在字段报违规', () => {
    const s = goodSpec()
    s.form.constraints.push({ field: 'ghost', type: 'regex', value: '^a' })
    s.form.refs.push({ field: 'ghost', scopes: ['wf'] })
    const vs = validateBaselineSpec(s)
    expect(vs.some((v) => v.path === 'form.constraints[1].field')).toBe(true)
    expect(vs.some((v) => v.path === 'form.refs[1].field')).toBe(true)
  })

  it('exports.from=log 缺 logKey 报违规；from 枚举外报违规', () => {
    const s = goodSpec()
    delete s.form.exports[0].logKey
    s.form.exports.push({ key: 'bad', from: 'stdout' as never, type: 'str' })
    const vs = validateBaselineSpec(s)
    expect(vs.some((v) => v.path === 'form.exports[0].logKey')).toBe(true)
    expect(vs.some((v) => v.path === 'form.exports[1].from')).toBe(true)
  })

  it('lineage.role/pick/assetType 非法报违规；NaN 被纯数据扫描捕获', () => {
    const s = goodSpec()
    s.lineage.assets.push({ role: 'side' as never, pick: '', assetType: 'db' as never })
    s.form.params[1].default = Number.NaN
    const vs = validateBaselineSpec(s)
    expect(vs.some((v) => v.path === 'lineage.assets[1].role')).toBe(true)
    expect(vs.some((v) => v.path === 'lineage.assets[1].pick')).toBe(true)
    expect(vs.some((v) => v.path === 'lineage.assets[1].assetType')).toBe(true)
    expect(vs.some((v) => v.msg.includes('NaN'))).toBe(true)
  })
})

describe('allFieldKeys / diffSummary', () => {
  it('allFieldKeys 返回三段键全集（inputs+outputs+params）', () => {
    const s = goodSpec()
    expect(allFieldKeys(s)).toEqual(['srcTable', 'tgtTable', 'mode', 'parallel'])
  })

  it('diffSummary：旧字段 key 仍在新三段 = migrated，否则 = pending', () => {
    const s = goodSpec()
    const olds = [
      { key: 'srcTable', label: '源表' },
      { key: 'mode', label: '模式' },
      { key: 'legacyFlag', label: '仅旧版' },
      { key: 'oldWhen', label: '旧条件' },
    ]
    const d = diffSummary(olds, s)
    expect(d.oldCount).toBe(4)
    expect(d.newCount).toBe(4)
    expect(d.migrated).toEqual(['srcTable', 'mode'])
    expect(d.pending).toEqual(['legacyFlag', 'oldWhen'])
  })

  it('diffSummary：旧列表为空 / 旧行缺 key 时容错', () => {
    const s = goodSpec()
    expect(diffSummary([], s)).toEqual({ oldCount: 0, newCount: 4, migrated: [], pending: [] })
    const d = diffSummary([{ label: '无 key' }, { key: 'mode' }], s)
    expect(d.oldCount).toBe(1)
    expect(d.migrated).toEqual(['mode'])
    expect(d.pending).toEqual([])
  })
})
