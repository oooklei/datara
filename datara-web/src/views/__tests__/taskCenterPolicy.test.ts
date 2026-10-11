import { describe, expect, it } from 'vitest'
import { dagProfile } from '../../graph/profiles/dag'
import { workflowEditorProfile } from '../taskCenterPolicy'

describe('task center product policy', () => {
  it('uses one workflow editor for every workflow classification', () => {
    for (const type of ['wf', 'sync', 'etl', 'stream'] as const) {
      expect(workflowEditorProfile(type)).toBe(dagProfile)
      expect(workflowEditorProfile(type).name).not.toContain('设计器')
    }
  })
})
