/**
 * 模型版本页契约测试：版本列表、新建快照、差异对比、回滚。
 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  listVersions: vi.fn(), createVersion: vi.fn(), diffVersion: vi.fn(), rollbackVersion: vi.fn(),
}))
vi.mock('../../services/rebuild/modelApi', () => ({ modelApi: api }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: {} }) }))

import View from '../dwmodel/ModelVersionView.vue'

const versions = [
  { id: 3, version: 3, changeNote: 'v3', createdBy: 'admin', createdAt: '2026-10-21T12:00:00' },
  { id: 2, version: 2, changeNote: '', createdBy: 'admin', createdAt: '2026-10-21T11:00:00' },
]

describe('model version view', () => {
  beforeEach(() => {
    for (const fn of Object.values(api)) fn.mockReset()
    api.listVersions.mockResolvedValue(versions)
    api.createVersion.mockResolvedValue({ id: 4, version: 4, changeNote: 'v4' })
    api.diffVersion.mockResolvedValue({ added: [{ name: 'amount', dataType: 'decimal' }], removed: [], changed: [], relationsChanged: false })
    api.rollbackVersion.mockResolvedValue({ status: 'draft', version: 5, sourceVersion: 3 })
  })

  it('lists versions and creates a snapshot with the change note', async () => {
    const wrapper = mount(View, { props: { modelId: 8 } })
    await flushPromises()
    expect(api.listVersions).toHaveBeenCalledWith(8)
    expect(wrapper.find('[data-version-list]').exists()).toBe(true)
    expect(wrapper.find('[data-version-id="3"]').text()).toContain('v3')

    await wrapper.find('[data-version-note]').setValue('v4')
    await wrapper.find('[data-version-create]').trigger('click')
    await flushPromises()
    expect(api.createVersion).toHaveBeenCalledWith(8, { changeNote: 'v4' })
  })

  it('shows a version diff and rolls back a version', async () => {
    const wrapper = mount(View, { props: { modelId: 8 } })
    await flushPromises()

    await wrapper.find('[data-version-diff="3"]').trigger('click')
    await flushPromises()
    expect(api.diffVersion).toHaveBeenCalledWith(8, 3)
    expect(wrapper.find('[data-version-diff-dialog]').exists()).toBe(true)
    expect(wrapper.find('[data-diff-added]').text()).toContain('amount')

    await wrapper.find('[data-version-rollback="3"]').trigger('click')
    await flushPromises()
    expect(api.rollbackVersion).toHaveBeenCalledWith(8, 3)
  })
})
