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
      fields: [{ key: 'sql', label: 'SQL', uiType: 'code', required: true, desc: '', layer: 'required' }],
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
})
