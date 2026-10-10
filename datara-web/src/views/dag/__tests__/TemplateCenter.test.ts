// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import TemplateCenter from '../TemplateCenter.vue'
import { useTemplateStore } from '../../../stores/templateStore'
import { useGraphStore } from '../../../stores/graph'

vi.mock('element-plus', () => ({ ElMessage: { success: vi.fn() }, ElMessageBox: { prompt: vi.fn(), confirm: vi.fn().mockResolvedValue('confirm') } }))
vi.mock('../../../services/templateApi', () => ({
  listTemplates: vi.fn().mockResolvedValue([]), getUpgradeStatus: vi.fn(), previewTemplateUpgrade: vi.fn(),
  instantiateTemplate: vi.fn(), confirmTemplateUpgrade: vi.fn(),
}))

beforeEach(() => setActivePinia(createPinia()))

describe('TemplateCenter upgrade interaction', () => {
  it('previews, confirms, and refreshes the active graph', async () => {
    const store = useTemplateStore()
    const graph = useGraphStore()
    graph.setDoc({ id: 'wf_old', name: 'Old', version: 3, meta: { profile: 'dag' }, nodes: [], edges: [] })
    store.upgradeNotice = { upgradeAvailable: true, templateId: 7, currentVersion: 1, latestVersion: 2 }
    store.previewUpgrade = vi.fn().mockImplementation(async () => {
      store.upgradePreview = { workflowVersion: 3, currentVersion: 1, latestVersion: 2, diff: [{ path: 'nodes[0]', before: null, after: 'Start' }] }
    })
    const upgraded = { id: 'wf_old', name: 'Old', version: 4, meta: { profile: 'dag', templateId: 7, templateVersion: 2 }, nodes: [], edges: [] }
    store.confirmUpgrade = vi.fn().mockResolvedValue(upgraded)
    const wrapper = mount(TemplateCenter, { props: { workflowId: 'wf_old' } })
    await wrapper.get('[data-testid="preview-upgrade"]').trigger('click')
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('nodes[0]')
    await wrapper.get('[data-testid="confirm-upgrade"]').trigger('click')
    await Promise.resolve()
    expect(graph.doc).toEqual(upgraded)
    expect(graph.dirty).toBe(false)
  })
})
