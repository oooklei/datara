import { describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'
import type { GraphDocument } from '../../graph/model'
import { resolveTemplateSourceDoc } from '../templateSource'

const doc = (id: string): GraphDocument => ({
  id, name: id, version: 1, meta: { profile: 'dag' }, nodes: [], edges: [],
})

describe('resolveTemplateSourceDoc', () => {
  it('uses a clone of the active in-memory draft instead of loading a stale saved copy', async () => {
    const active = doc('wf_active')
    const load = vi.fn().mockResolvedValue(doc('wf_active'))

    const result = await resolveTemplateSourceDoc(active, 'wf_active', load)

    expect(load).not.toHaveBeenCalled()
    expect(result).toEqual(active)
    expect(result).not.toBe(active)
  })

  it('clones a Vue reactive document before saving it as a template', async () => {
    const active = reactive(doc('wf_reactive'))
    const load = vi.fn()

    const result = await resolveTemplateSourceDoc(active, 'wf_reactive', load)

    expect(load).not.toHaveBeenCalled()
    expect(result).toEqual(doc('wf_reactive'))
    expect(result).not.toBe(active)
  })

  it('loads the requested workflow when another document is active', async () => {
    const saved = doc('wf_requested')
    const load = vi.fn().mockResolvedValue(saved)

    await expect(resolveTemplateSourceDoc(doc('wf_other'), 'wf_requested', load)).resolves.toBe(saved)
    expect(load).toHaveBeenCalledWith('wf_requested')
  })
})
