import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import View from '../SecAuditView.vue'

const listAccessLogs = vi.hoisted(() => vi.fn())
vi.mock('../../services/rebuild/secAuditApi', async (load) => {
  const actual = await load<typeof import('../../services/rebuild/secAuditApi')>()
  return { ...actual, createSecAuditContract: () => ({ listAccessLogs }) }
})

describe('security audit view', () => {
  beforeEach(() => {
    listAccessLogs.mockReset()
    listAccessLogs.mockResolvedValue({
      total: 1,
      facets: { allow: 1 },
      list: [{
        id: 1, userName: 'admin', action: 'query', target: '/projects', rowsSeen: 0,
        result: 'allow', reason: 'http_status_200', requestId: 'req-1',
        accessedAt: '2026-10-25T09:00:00',
      }],
    })
  })

  it('loads real audit rows and applies admin filters', async () => {
    const wrapper = mount(View)
    await flushPromises()

    expect(wrapper.find('[data-audit-list]').exists()).toBe(true)
    expect(wrapper.text()).toContain('admin')
    expect(listAccessLogs).toHaveBeenNthCalledWith(1, {
      userName: undefined, action: undefined, result: undefined, limit: 20, offset: 0,
    })

    await wrapper.find('[data-filter-user]').setValue('admin')
    await wrapper.find('[data-filter-result]').setValue('allow')
    await wrapper.find('[data-apply]').trigger('click')
    await flushPromises()

    expect(listAccessLogs).toHaveBeenLastCalledWith({
      userName: 'admin', action: undefined, result: 'allow', limit: 20, offset: 0,
    })
  })
})
