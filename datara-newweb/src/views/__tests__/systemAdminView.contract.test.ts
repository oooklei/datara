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
})

describe('SystemAdminView（系统管理段承载页）', () => {
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

  it('段接线：ProjectSegmentView system 段渲染 SystemAdminView 并透传 projectId', async () => {
    listSpy.mockResolvedValue({ list: [] })

    const wrapper = mount(ProjectSegmentView, { props: { projectId: 9, seg: 'system' } })
    await flushPromises()

    expect(wrapper.findComponent(SystemAdminView).exists()).toBe(true)
    expect(wrapper.findComponent(SystemAdminView).props('projectId')).toBe(9)
    expect(listSpy).toHaveBeenCalledWith(9)
  })
})
