import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useTemplateStore } from '../templateStore'
import * as api from '../../services/templateApi'

vi.mock('../../services/templateApi')

beforeEach(() => {
  setActivePinia(createPinia())
  vi.resetAllMocks()
})

describe('workflow template store', () => {
  it('loads templates and instantiates a selected template', async () => {
    vi.mocked(api.listTemplates).mockResolvedValue([{ id: 7, name: 'ETL base', category: 'ETL', description: '', version: 2, updatedAt: 'now' }])
    vi.mocked(api.instantiateTemplate).mockResolvedValue({ id: 'wf_new', code: 12, version: 1 })
    const store = useTemplateStore()
    await store.load()
    expect(store.templates[0]?.version).toBe(2)
    await expect(store.instantiate(7, 'My ETL')).resolves.toEqual({ id: 'wf_new', code: 12, version: 1 })
    expect(api.instantiateTemplate).toHaveBeenCalledWith(7, 'My ETL')
  })

  it('keeps upgrades optional and exposes a diff only after confirmation flow starts', async () => {
    vi.mocked(api.getUpgradeStatus).mockResolvedValue({ upgradeAvailable: true, templateId: 7, currentVersion: 1, latestVersion: 2 })
    vi.mocked(api.previewTemplateUpgrade).mockResolvedValue({ workflowVersion: 3, currentVersion: 1, latestVersion: 2, diff: [{ path: 'nodes[1].data.name', before: 'End', after: 'Finish' }] })
    const store = useTemplateStore()
    await store.checkUpgrade('wf_old')
    expect(store.upgradeNotice?.upgradeAvailable).toBe(true)
    expect(store.upgradePreview).toBeNull()
    await store.previewUpgrade('wf_old')
    expect(store.upgradePreview?.diff).toHaveLength(1)
  })

  it('confirms exactly the previewed workflow/template versions', async () => {
    const doc = { id: 'wf_old', name: 'Old', version: 4, meta: { profile: 'dag' }, nodes: [], edges: [] }
    vi.mocked(api.getUpgradeStatus).mockResolvedValue({ upgradeAvailable: true, templateId: 7, currentVersion: 1, latestVersion: 2 })
    vi.mocked(api.previewTemplateUpgrade).mockResolvedValue({ workflowVersion: 3, currentVersion: 1, latestVersion: 2, diff: [] })
    vi.mocked(api.confirmTemplateUpgrade).mockResolvedValue(doc)
    const store = useTemplateStore()
    await store.checkUpgrade('wf_old')
    await store.previewUpgrade('wf_old')
    await store.confirmUpgrade('wf_old')
    expect(api.confirmTemplateUpgrade).toHaveBeenCalledWith(7, 'wf_old', {
      baseVersion: 3, templateVersion: 1, targetTemplateVersion: 2,
    })
  })
})
