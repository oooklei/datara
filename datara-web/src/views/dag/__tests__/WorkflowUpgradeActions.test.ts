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
    const wrapper = mount(WorkflowUpgradeActions, { props: { workflowId: 'wf_old' } })
    expect(wrapper.text()).toContain('可选升级')
    await wrapper.get('[data-testid="list-preview-upgrade"]').trigger('click')
    expect(store.previewUpgrade).toHaveBeenCalledWith('wf_old')
  })
})
