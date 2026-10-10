import { describe, expect, it } from 'vitest'
import { classifySpecChange } from '../componentSpec'

describe('component spec upgrade classification', () => {
  it('reports each breaking category deterministically', () => {
    const result = classifySpecChange(
      { fields: [
        { key: 'gone', uiType: 'text', required: false, label: '', desc: '' },
        { key: 'kind', uiType: 'text', required: false, label: '', desc: '' },
        { key: 'must', uiType: 'text', required: false, label: '', desc: '' },
      ], outputs: [{ name: 'old', type: 'table' }] },
      { fields: [
        { key: 'kind', uiType: 'number', required: false, label: '', desc: '' },
        { key: 'must', uiType: 'text', required: true, label: '', desc: '' },
      ], outputs: [] },
    )
    expect(result).toMatchObject({
      removed: ['gone'], uiChanged: ['kind'], requiredTightened: ['must'], outputsRemoved: ['old'], breaking: true,
    })
  })
})
