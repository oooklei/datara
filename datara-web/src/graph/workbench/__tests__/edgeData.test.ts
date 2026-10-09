import { describe, expect, it } from 'vitest'
import { dagProfile } from '../../profiles/dag'
import { EDGE_DATA_TYPE_VISUALS, capPreviewRows } from '../edgeData'

describe('edge data presentation', () => {
  it('maps contract data types to stable colors and caps preview rows at 100', () => {
    expect(EDGE_DATA_TYPE_VISUALS).toMatchObject({
      table: { color: '#2563eb' },
      dataset: { color: '#0891b2' },
      stream: { color: '#7c3aed' },
      file: { color: '#ea580c' },
      any: { color: '#64748b' },
    })
    expect(capPreviewRows(Array.from({ length: 120 }, (_, i) => [i]), 250)).toHaveLength(100)
    expect(capPreviewRows(Array.from({ length: 50 }, (_, i) => [i]), 12)).toHaveLength(12)
  })

  it('registers reroute as an editing-only DAG node', () => {
    expect(dagProfile.nodeTypes.reroute).toMatchObject({ type: 'reroute', runtimeOnly: false })
    expect(dagProfile.palette.flatMap((group) => group.items).some((item) => item.type === 'reroute')).toBe(true)
  })
})
