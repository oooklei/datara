// @vitest-environment happy-dom
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import WorkflowUpgradeActions from '../WorkflowUpgradeActions.vue'
import { useTemplateStore } from '../../../stores/templateStore'

vi.mock('element-plus', () => ({ ElMessage: { success: vi.fn() }, ElMessageBox: { confirm: vi.fn().mockResolvedValue('confirm') } }))
vi.mock('../../../services/templateApi', () => ({
  listTemplates: vi.fn(), getUpgradeStatus: vi.fn(), previewTemplateUpgrade: vi.fn(), instantiateTemplate: vi.fn(), confirmTemplateUpgrade: vi.fn(),
}))

describe('workflow list optional upgrade actions', () => {
  it('renders the notice and opens diff from a mounted row action', async () => {
    setActivePinia(createPinia())
    const store = useTemplateStore()
    store.upgradeNotice = { upgradeAvailable: true, templateId: 4, currentVersion: 1, latestVersion: 2 }
    store.previewUpgrade = vi.fn().mockResolvedValue(undefined)
    const status = { upgradeAvailable: true, templateId: 4, currentVersion: 1, latestVersion: 2 }
    const wrapper = mount(WorkflowUpgradeActions, { props: { workflowId: 'wf_old', status } })
    expect(wrapper.text()).toContain('可选升级')
    await wrapper.get('[data-testid="list-preview-upgrade"]').trigger('click')
    expect(store.previewUpgrade).toHaveBeenCalledWith('wf_old')
  })

  it('uses the row status instead of another workflow global notice', () => {
    setActivePinia(createPinia())
    const store = useTemplateStore()
    store.upgradeNotice = { upgradeAvailable: true, templateId: 9, currentVersion: 1, latestVersion: 3 }

    const wrapper = mount(WorkflowUpgradeActions, {
      props: {
        workflowId: 'wf_current',
        status: { upgradeAvailable: false, templateId: 4, currentVersion: 2, latestVersion: 2 },
      },
    })

    expect(wrapper.find('[data-testid="list-preview-upgrade"]').exists()).toBe(false)
  })

  it('keeps each row diff independent when two rows preview in turn', async () => {
    setActivePinia(createPinia())
    const store = useTemplateStore()
    const status = { upgradeAvailable: true, templateId: 4, currentVersion: 1, latestVersion: 2 }
    const rowA = mount(WorkflowUpgradeActions, { props: { workflowId: 'wf_a', status } })
    const rowB = mount(WorkflowUpgradeActions, { props: { workflowId: 'wf_b', status } })

    store.previewUpgrade = vi.fn().mockResolvedValue({ workflowVersion: 1, currentVersion: 1, latestVersion: 2, diff: [{ path: 'wf_a/nodes[0].name', before: 'A', after: 'A2' }] })
    await rowA.get('[data-testid="list-preview-upgrade"]').trigger('click')

    store.previewUpgrade = vi.fn().mockResolvedValue({ workflowVersion: 1, currentVersion: 1, latestVersion: 2, diff: [{ path: 'wf_b/nodes[0].name', before: 'B', after: 'B2' }] })
    await rowB.get('[data-testid="list-preview-upgrade"]').trigger('click')

    expect(rowA.text()).toContain('wf_a/nodes[0].name')
    expect(rowA.text()).not.toContain('wf_b/nodes[0].name')
    expect(rowB.text()).toContain('wf_b/nodes[0].name')
  })

  it('keeps each row diff independent when previews resolve concurrently', async () => {
    setActivePinia(createPinia())
    const store = useTemplateStore()
    const status = { upgradeAvailable: true, templateId: 4, currentVersion: 1, latestVersion: 2 }
    const rowA = mount(WorkflowUpgradeActions, { props: { workflowId: 'wf_a', status } })
    const rowB = mount(WorkflowUpgradeActions, { props: { workflowId: 'wf_b', status } })
    const diffA = { workflowVersion: 1, currentVersion: 1, latestVersion: 2, diff: [{ path: 'wf_a/nodes[0].name', before: 'A', after: 'A2' }] }
    const diffB = { workflowVersion: 1, currentVersion: 1, latestVersion: 2, diff: [{ path: 'wf_b/nodes[0].name', before: 'B', after: 'B2' }] }
    let releaseA!: () => void
    let releaseB!: () => void
    const gateA = new Promise<void>((resolve) => { releaseA = resolve })
    const gateB = new Promise<void>((resolve) => { releaseB = resolve })

    store.previewUpgrade = vi.fn().mockImplementation(async (workflowId: string) => {
      const diff = workflowId === 'wf_a' ? diffA : diffB
      await (workflowId === 'wf_a' ? gateA : gateB)
      store.upgradePreview = diff
      return diff
    })

    const clickA = rowA.get('[data-testid="list-preview-upgrade"]').trigger('click')
    const clickB = rowB.get('[data-testid="list-preview-upgrade"]').trigger('click')
    releaseA()
    releaseB()
    await Promise.all([clickA, clickB])
    await flushPromises()

    expect(rowA.text()).toContain('wf_a/nodes[0].name')
    expect(rowA.text()).not.toContain('wf_b/nodes[0].name')
    expect(rowB.text()).toContain('wf_b/nodes[0].name')
  })
})
