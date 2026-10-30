/**
 * T4（D-05 / §5A.11）：system 段承载页组合契约。
 *
 * 断言：/p/:projectId/system 现渲染 SystemAdminView——项目成员管理（L3-04 既有
 * 组件，projectId 透传）+ 平台权限矩阵（15.1-C 既有页）双区块；七段菜单契约
 * （projectMenu.contract.test.ts）与 data-seg 锚零触碰。
 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SystemAdminView from '../system/SystemAdminView.vue'
import ProjectSegmentView from '../ProjectSegmentView.vue'
import { authAccount } from '../../services/rebuild/authApi'

const { listSpy } = vi.hoisted(() => ({ listSpy: vi.fn() }))

vi.mock('../../services/rebuild/memberApi', () => ({
  MEMBER_ROLES: ['admin', 'developer', 'operator', 'viewer'],
  addMember: vi.fn(),
  listMembers: listSpy,
  removeMember: vi.fn(),
  updateMemberRole: vi.fn(),
}))

beforeEach(() => {
  listSpy.mockReset()
  authAccount.value = { id: 1, username: 'admin', role: 'admin' }
})

describe('SystemAdminView（系统管理段承载页）', () => {
  it('全局 /sys 无项目参数时展示平台用户、权限与开放能力入口', async () => {
    const wrapper = mount(SystemAdminView, {
      global: { stubs: { UserManagementView: { template: '<div data-user-management />' }, RouterLink: { template: '<a><slot /></a>' } } },
    })
    await flushPromises()
    expect(wrapper.find('[data-user-management]').exists()).toBe(true)
    expect(wrapper.find('section[aria-label="项目成员管理"]').exists()).toBe(false)
    expect(wrapper.find('[data-system-links]').text()).toContain('API 管理')
    expect(wrapper.find('[data-system-links]').text()).not.toContain('LLM 模型')
    expect(wrapper.find('section[aria-label="平台权限矩阵"]').exists()).toBe(true)
  })

  it('非管理员只看到权限说明，不暴露平台用户管理与管理型开放入口', async () => {
    authAccount.value = { id: 4, username: 'viewer', role: 'viewer' }
    const wrapper = mount(SystemAdminView, {
      global: { stubs: { UserManagementView: { template: '<div data-user-management />' }, RouterLink: { template: '<a><slot /></a>' } } },
    })
    await flushPromises()
    expect(wrapper.find('[data-user-management]').exists()).toBe(false)
    expect(wrapper.find('[data-admin-required]').text()).toContain('管理员')
    expect(wrapper.find('[data-system-links]').exists()).toBe(false)
    expect(wrapper.find('section[aria-label="平台权限矩阵"]').exists()).toBe(true)
  })

  it('组合双区块：项目成员管理 + 平台权限矩阵', async () => {
    listSpy.mockResolvedValue({ list: [{ userId: 7, role: 'developer' }] })

    const wrapper = mount(SystemAdminView, { props: { projectId: 1 } })
    await flushPromises()

    const membersBlock = wrapper.find('section[aria-label="项目成员管理"]')
    expect(membersBlock.exists()).toBe(true)
    expect(membersBlock.find('[data-member-id="7"]').exists()).toBe(true)
    const matrixBlock = wrapper.find('section[aria-label="平台权限矩阵"]')
    expect(matrixBlock.exists()).toBe(true)
  })

  it('projectId 透传：listMembers(projectId) 以路由上下文调用', async () => {
    listSpy.mockResolvedValue({ list: [] })

    mount(SystemAdminView, { props: { projectId: 42 } })
    await flushPromises()

    expect(listSpy).toHaveBeenCalledWith(42)
  })

  it('系统管理不再挂入项目功能段，由 /sys 全局顶层路由承载', async () => {
    listSpy.mockResolvedValue({ list: [] })

    const wrapper = mount(ProjectSegmentView, { props: { projectId: 9, seg: 'system' } })
    await flushPromises()

    expect(wrapper.findComponent(SystemAdminView).exists()).toBe(false)
    expect(wrapper.find('h1').text()).toBe('未找到项目功能')
    expect(listSpy).not.toHaveBeenCalled()
  })
})
