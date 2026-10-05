/**
 * Task 5（工作台优化 方案§2.3，R1 风险对策）：spec 驱动渲染 + profile 兜底降级。
 * - resolveNodeSchema：spec 命中且启用 → specToSchema 适配视图（非 profile 同一对象）；
 *   spec 缺失/降级 → profile 兜底（同一性透传）；两者皆无 → undefined 不抛错。
 * - specToSchema：ComponentSpec → NodeSchema 视图适配边界
 *   （displayName 回落 summary、layer=hidden 排除、空 fields、select options 值域收敛、
 *   default 汇总 defaults、outputs/categories 形态不兼容省略不编造）。
 */
import { describe, it, expect } from 'vitest'
import { resolveNodeSchema, specToSchema } from '../specSchema'
import type { NodeSchema, ViewProfile } from '../../profiles/types'
import type { ComponentSpec } from '../../../services/componentSpec'

const schemaOf = (over: Partial<NodeSchema> = {}): NodeSchema => ({
  type: 't1',
  label: '档案组件',
  icon: '▣',
  color: '#2563eb',
  form: [],
  ...over,
})

const profileOf = (nodeTypes: Record<string, NodeSchema>): Pick<ViewProfile, 'nodeTypes'> => ({ nodeTypes })

const specOf = (over: Partial<ComponentSpec> = {}): ComponentSpec => ({
  icon: '▣',
  color: '#2563eb',
  summary: '一句话摘要',
  ports: { inputs: [], outputs: [] },
  fields: [],
  dropPolicy: {
    snapToGrid: false,
    autoName: '',
    prefillFromUpstream: [],
    autoConnect: { upstream: 'nearest', downstream: 'nearest' },
    maxInstances: 0,
  },
  paletteVisible: true,
  ...over,
})

describe('resolveNodeSchema（两源并存：spec 命中驱动，profile 兜底）', () => {
  const profileSchema = schemaOf()
  const profile = profileOf({ t1: profileSchema, t2: schemaOf({ type: 't2', label: '仅档案' }) })

  it('spec 命中且启用 → 返回 specToSchema 适配视图（非 profile 同一对象，关键键来自 spec）', () => {
    const specMap = new Map([['t1', specOf({ displayName: '展示名' })]])
    const s = resolveNodeSchema('t1', profile, specMap, true)
    expect(s).toBeDefined()
    expect(s).not.toBe(profileSchema) // 适配视图，非同一性
    expect(s!.type).toBe('t1')
    expect(s!.label).toBe('展示名')
    expect(s!.desc).toBe('一句话摘要')
    expect(s!.icon).toBe('▣')
    expect(s!.color).toBe('#2563eb')
  })

  it('spec 缺失 → profile 兜底（直接透传，同一性成立）', () => {
    const specMap = new Map<string, ComponentSpec>()
    expect(resolveNodeSchema('t1', profile, specMap, true)).toBe(profileSchema)
    expect(resolveNodeSchema('t2', profile, specMap, true)?.label).toBe('仅档案')
  })

  it('降级（specEnabled=false）→ 强制 profile 兜底，即使 specMap 已有该类型', () => {
    const specMap = new Map([['t1', specOf({ displayName: '展示名' })]])
    expect(resolveNodeSchema('t1', profile, specMap, false)).toBe(profileSchema)
  })

  it('spec 与 profile 皆无 → undefined 且不抛错', () => {
    const specMap = new Map<string, ComponentSpec>()
    expect(resolveNodeSchema('ghost', profile, specMap, true)).toBeUndefined()
    expect(resolveNodeSchema('ghost', profile, specMap, false)).toBeUndefined()
  })
})

describe('specToSchema（ComponentSpec → NodeSchema 视图适配）', () => {
  it('label = displayName ?? summary；desc = summary；无 displayName 回落 summary，两者皆无则空串', () => {
    expect(specToSchema('t1', specOf({ displayName: '展示名' })).label).toBe('展示名')
    expect(specToSchema('t1', specOf()).label).toBe('一句话摘要')
    const bare = specOf()
    bare.summary = ''
    expect(specToSchema('t1', bare).label).toBe('')
    expect(specToSchema('t1', specOf()).desc).toBe('一句话摘要')
  })

  it('form 映射：key/label 直传、uiType→type 恒等、required 直传、layer=hidden 排除（不进表单）', () => {
    const s = specToSchema('t1', specOf({
      fields: [
        { key: 'ds', label: '数据源', uiType: 'resource', required: true, desc: '选个源', layer: 'required', default: 'ds_a' },
        { key: 'note', label: '备注', uiType: 'text', required: false, desc: '', layer: 'optional' },
        { key: 'secret', label: '内部参数', uiType: 'text', required: false, desc: '', layer: 'hidden' },
      ],
    }))
    expect(s.form).toHaveLength(2) // hidden 字段不进表单
    expect(s.form.map((f) => f.key)).toEqual(['ds', 'note'])
    expect(s.form[0]).toMatchObject({ key: 'ds', label: '数据源', type: 'resource', required: true })
    expect(s.form[1]).toMatchObject({ type: 'text', required: false })
  })

  it('select options 映射为 FieldSchema 值域（value 收敛 string）；非 select 不落 options 键', () => {
    const s = specToSchema('t1', specOf({
      fields: [
        { key: 'mode', label: '模式', uiType: 'select', required: false, desc: '', layer: 'required', options: [{ label: '全量', value: 'full' }, { label: '增量', value: 1 }] },
        { key: 'note', label: '备注', uiType: 'text', required: false, desc: '', layer: 'optional' },
      ],
    }))
    expect(s.form[0]!.options).toEqual([{ value: 'full', label: '全量' }, { value: '1', label: '增量' }])
    expect('options' in s.form[1]!).toBe(false)
  })

  it('fields[].default 汇总进 defaults（hidden 不汇入）；空 fields → form 空数组且无 defaults 键', () => {
    const s = specToSchema('t1', specOf({
      fields: [
        { key: 'ds', label: '数据源', uiType: 'resource', required: true, desc: '', layer: 'required', default: 'ds_a' },
        { key: 'secret', label: '内部', uiType: 'text', required: false, desc: '', layer: 'hidden', default: 'x' },
      ],
    }))
    expect(s.defaults).toEqual({ ds: 'ds_a' })

    const empty = specToSchema('t1', specOf())
    expect(empty.form).toEqual([])
    expect('defaults' in empty).toBe(false)
  })

  it('形态不兼容位省略不编造：outputs/categories/code/shape 均缺省', () => {
    const s = specToSchema('t1', specOf({
      category: '批处理与同步/数据源',
      outputs: [{ name: 'out', type: 'table', desc: '结果表' }],
    }))
    expect('outputs' in s).toBe(false) // spec 声明式输出 {name,type,desc} ≠ NodePort {id,label}
    expect('categories' in s).toBe(false) // 字符串分组路径 ≠ ComponentCategory 枚举数组
    expect('code' in s).toBe(false)
    expect('shape' in s).toBe(false)
  })
})
