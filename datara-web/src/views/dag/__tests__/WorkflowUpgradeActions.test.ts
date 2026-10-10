// @vitest-environment happy-dom
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
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
})
