import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import UserManagementView from '../system/UserManagementView.vue'

const api = vi.hoisted(() => ({ list: vi.fn(), catalog: vi.fn(), create: vi.fn(), role: vi.fn(), status: vi.fn(), password: vi.fn() }))
vi.mock('../../services/rebuild/userApi', () => ({
  listUsers: api.list,
  listRoleCatalog: api.catalog,
  createUser: api.create,
  updateUserRole: api.role,
  updateUserStatus: api.status,
  updateUserPassword: api.password,
  USER_ROLES: ['admin', 'developer', 'operator', 'viewer'],
}))

beforeEach(() => {
  Object.values(api).forEach((spy) => spy.mockReset())
  api.list.mockResolvedValue({ list: [{ id: 1, username: 'admin', role: 'admin', status: 'enabled', createdAt: null }] })
  api.catalog.mockResolvedValue({ roles: [] })
})

describe('UserManagementView', () => {
  it('loads platform users and applies role/status changes with visible feedback', async () => {
    api.role.mockResolvedValue({})
    api.status.mockResolvedValue({})
    const wrapper = mount(UserManagementView)
    await flushPromises()
    expect(wrapper.get('[data-user-row="1"]').text()).toContain('admin')
    await wrapper.get('[data-user-role="1"]').setValue('developer')
    await wrapper.get('[data-user-status="1"]').trigger('click')
    await flushPromises()
    expect(api.role).toHaveBeenCalledWith(1, 'developer')
    expect(api.status).toHaveBeenCalledWith(1, 'disabled')
    expect(wrapper.get('[role="status"]').text()).toContain('已更新')
  })

  it('creates a user and refreshes the list', async () => {
    api.create.mockResolvedValue({})
    const wrapper = mount(UserManagementView)
    await flushPromises()
    await wrapper.get('[data-new-username]').setValue('analyst')
    await wrapper.get('[data-new-password]').setValue('Analyst@123')
    await wrapper.get('[data-user-create]').trigger('submit')
    await flushPromises()
    expect(api.create).toHaveBeenCalledWith({ username: 'analyst', password: 'Analyst@123', role: 'viewer' })
    expect(api.list).toHaveBeenCalledTimes(2)
  })
})
