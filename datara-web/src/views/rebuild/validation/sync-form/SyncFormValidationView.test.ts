// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  explore: vi.fn(),
  autoMap: vi.fn(),
  savePlan: vi.fn(),
  listPlans: vi.fn(),
  getCapabilities: vi.fn(),
}))

vi.mock('../../../../services/rebuild/syncComponentApi', () => ({
  createSyncComponentContract: () => api,
  SyncApiError: class SyncApiError extends Error {},
}))

import SyncFormValidationView from './SyncFormValidationView.vue'

afterEach(() => vi.clearAllMocks())

describe('SyncFormValidationView', () => {
  it('keeps a user-entered mapping expression in the saved transform snapshot', async () => {
    api.explore.mockResolvedValue({ items: [{ column_name: 'customer_name', data_type: 'varchar' }], truncated: false, limit: 200 })
    api.autoMap.mockResolvedValue([{
      source_column: 'customer_name',
      target_column: 'customer_name',
      source_type: 'varchar',
      target_type: 'varchar',
      transform_expression: '',
      nullable: true,
      default_value: null,
      mapping_status: 'AUTO',
    }])
    api.savePlan.mockResolvedValue({ saved: true, workflow_version: 1, task_id: 'sync-task' })
    const wrapper = mount(SyncFormValidationView, { global: { plugins: [ElementPlus] } })

    await wrapper.get('[data-testid="sync-explore-source"]').trigger('click')
    await wrapper.get('[data-testid="sync-explore-target"]').trigger('click')
    await wrapper.get('[data-testid="sync-auto-map"]').trigger('click')
    await flushPromises()
    await wrapper.get('input[placeholder="例如 UPPER(customer_name)"]').setValue('UPPER(customer_name)')
    await wrapper.get('[data-testid="sync-save-plan"]').trigger('click')
    await flushPromises()

    expect(api.savePlan).toHaveBeenCalledWith(expect.objectContaining({
      mappings: [expect.objectContaining({ transform_expression: 'UPPER(customer_name)' })],
      transform_config: {
        transform_expression: { customer_name: 'UPPER(customer_name)' },
        filter_condition: '',
      },
    }))
    wrapper.unmount()
  })
})
