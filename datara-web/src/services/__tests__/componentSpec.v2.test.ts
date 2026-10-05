import { describe, it, expect } from 'vitest'
import { normalizeSpec } from '../componentSpec'

describe('ComponentSpecV2 normalizeSpec 向后兼容（方案§2.2）', () => {
  it('旧格式 spec：新字段可选不强制，原字段不变', () => {
    const s = normalizeSpec({ icon: 'db', color: '#333', summary: '旧组件', fields: [] })
    expect(s.icon).toBe('db')
    expect(s.outputs).toBeUndefined()
    expect(s.behaviors).toBeUndefined()
    expect(s.extensions).toBeUndefined()
    expect(s.specVersion).toBeUndefined()
  })
  it('新格式 spec：outputs/behaviors/extensions/aliases/category 往返保留', () => {
    const s = normalizeSpec({
      icon: 'sql', color: '#0891b2', summary: 'SQL 执行', category: '批处理与同步/数据源',
      aliases: ['sql', '脚本'], description: '**详细**说明',
      outputs: [{ name: 'result', type: 'table', desc: '结果表' }],
      fields: [{ key: 'sql', label: 'SQL', uiType: 'text', required: true, desc: '', layer: 'required' }],
      behaviors: { prefillFromUpstream: [{ field: 'table', from: 'input.table' }] },
      extensions: { hiddenInputs: ['tenantId', 'runId'], capabilities: { testable: true, previewLimit: 100 } },
      specVersion: '1.1',
      ports: { inputs: [{ name: 'in', type: 'dataset' }], outputs: [{ name: 'out', type: 'table' }] },
    })
    expect(s.category).toBe('批处理与同步/数据源')
    expect(s.aliases).toEqual(['sql', '脚本'])
    expect(s.outputs?.[0].type).toBe('table')
    expect(s.fields?.[0].layer).toBe('required')
    expect(s.behaviors?.prefillFromUpstream?.[0].from).toBe('input.table')
    expect(s.extensions?.hiddenInputs).toEqual(['tenantId', 'runId'])
  })
  it('outputs.type 非法值归一为 any（不炸渲染）', () => {
    const s = normalizeSpec({ outputs: [{ name: 'x', type: 'oops' }] })
    expect(s.outputs?.[0].type).toBe('any')
  })
  it('旧 spec 归一输出恰好只有 V1 键（V2 缺位键不落入 JSON——头注释契约；toStrictEqual 可区分缺位键与 undefined 值键，强于 toEqual）', () => {
    expect(normalizeSpec({ icon: 'db', color: '#333', summary: 'x' })).toStrictEqual({
      icon: 'db',
      color: '#333',
      summary: 'x',
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
    })
  })
  it('outputs 非对象元素整项丢弃（与 normBehaviors 非法项策略一致）', () => {
    const s = normalizeSpec({ outputs: ['x', { name: 'ok', type: 'table' }, 42] })
    expect(s.outputs).toEqual([{ name: 'ok', type: 'table' }])
  })
  it('behaviors：非法 action/from/picker 项丢弃，合法项保留；空 behaviors 不落键', () => {
    const s = normalizeSpec({
      behaviors: {
        onChange: [{ field: 'a', action: 'hack' }, { field: 'b', action: 'refreshOptions' }],
        prefillFromUpstream: [{ field: 't', from: 'input.rows' }, { field: 't2', from: 'input.table' }],
        pick: [{ field: 'p', picker: 'file' }, { field: 'p2', picker: 'cron' }],
      },
    })
    expect(s.behaviors?.onChange).toEqual([{ field: 'b', action: 'refreshOptions' }])
    expect(s.behaviors?.prefillFromUpstream).toEqual([{ field: 't2', from: 'input.table' }])
    expect(s.behaviors?.pick).toEqual([{ field: 'p2', picker: 'cron' }])
    expect(normalizeSpec({ behaviors: {} }).behaviors).toBeUndefined()
  })
  it('extensions：hiddenInputs 过滤非法键；previewLimit 仅接受 >0 有限数并钳制 ≤100；空对象不落键', () => {
    const s = normalizeSpec({ extensions: { hiddenInputs: ['tenantId', 'evil', 'runId'], capabilities: { previewLimit: 500 } } })
    expect(s.extensions?.hiddenInputs).toEqual(['tenantId', 'runId'])
    expect(s.extensions?.capabilities?.previewLimit).toBe(100)
    expect(normalizeSpec({ extensions: { capabilities: { previewLimit: -5 } } }).extensions).toBeUndefined()
    expect(normalizeSpec({ extensions: {} }).extensions).toBeUndefined()
  })
  it('aliases 非字符串元素被过滤', () => {
    expect(normalizeSpec({ aliases: ['a', 123] }).aliases).toEqual(['a'])
  })
})
