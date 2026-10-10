import { describe, expect, it } from 'vitest'
import { patchById } from '../syncFromDoc'

interface Model { id: string; label: string }
interface Flow { id: string; label: string; selected?: boolean; dimensions?: { width: number } }

const project = (model: Model): Flow => ({ id: model.id, label: model.label })

describe('patchById', () => {
  it('patches model fields while retaining renderer-only state and model order', () => {
    const current: Flow[] = [
      { id: 'b', label: 'old-b', selected: true, dimensions: { width: 160 } },
      { id: 'gone', label: 'gone' },
    ]

    const result = patchById(current, [{ id: 'a', label: 'A' }, { id: 'b', label: 'B' }], project)

    expect(result.items).toEqual([
      { id: 'a', label: 'A' },
      { id: 'b', label: 'B', selected: true, dimensions: { width: 160 } },
    ])
    expect(result).toMatchObject({ added: 1, updated: 1, removed: 1 })
  })

  it('does not mutate the existing render list', () => {
    const current: Flow[] = [{ id: 'a', label: 'old', selected: true }]
    const result = patchById(current, [{ id: 'a', label: 'new' }], project)

    expect(current).toEqual([{ id: 'a', label: 'old', selected: true }])
    expect(result.items[0]).not.toBe(current[0])
  })
})
