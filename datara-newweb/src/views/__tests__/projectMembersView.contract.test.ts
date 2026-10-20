/**
 * ProjectMembersView 组件契约测试（L3-04）。
 *
 * 范式：vi.hoisted 提升间谍 → vi.mock 契约层 → mount + flushPromises；
 * 锚定票面「成员 CRUD + 权限校验通过」的 FE 侧口径（权限闸门在后端，403 呈现为错误态）。
 */

import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ProjectMembersView from '../ProjectMembersView.vue'

const { addSpy, listSpy, patchSpy, removeSpy } = vi.hoisted(() => ({
  addSpy: vi.fn(),
  listSpy: vi.fn(),
  patchSpy: vi.fn(),
  removeSpy: vi.fn(),
}))

vi.mock('../../services/rebuild/memberApi', () => ({
  MEMBER_ROLES: ['admin', 'developer', 'operator', 'viewer'],
  addMember: addSpy,
  listMembers: listSpy,
  removeMember: removeSpy,
  updateMemberRole: patchSpy,
}))

function mountView(props: { projectId: number } = { projectId: 1 }) {
  return mount(ProjectMembersView, { props })
}

beforeEach(() => {
  addSpy.mockReset()
  listSpy.mockReset()
  patchSpy.mockReset()
  removeSpy.mockReset()
})

describe('ProjectMembersView（项目成员管理页）', () => {
  it('加载态：listMembers 未落定时呈现 role=status 加载中', () => {
    listSpy.mockReturnValue(new Promise(() => {}))

    const wrapper = mountView()

    const status = wrapper.find('[data-loading]')
    expect(status.exists()).toBe(true)
    expect(status.attributes('role')).toBe('status')
  })

  it('列表渲染：成员行锚点 data-member-id + 角色 select 当前值', async () => {
    listSpy.mockResolvedValue({
      list: [
        { userId: 7, role: 'developer' },
        { userId: 9, role: 'viewer' },
      ],
    })

    const wrapper = mountView()
    await flushPromises()

    const row7 = wrapper.find('[data-member-id="7"]')
    const row9 = wrapper.find('[data-member-id="9"]')
    expect(row7.exists()).toBe(true)
    expect(row7.find('[data-member-user-id]').text()).toBe('7')
    expect((row7.find('[data-role-select]').element as HTMLSelectElement).value).toBe('developer')
    expect((row9.find('[data-role-select]').element as HTMLSelectElement).value).toBe('viewer')
  })

  it('添加成员：提交 → addMember(projectId, {username, role})，成功后重载并清空输入', async () => {
    listSpy.mockResolvedValue({ list: [] })
    addSpy.mockResolvedValue({ projectId: 1, username: 'bob', role: 'developer' })

    const wrapper = mountView()
    await flushPromises()

    await wrapper.find('[data-username-input]').setValue('bob')
    await wrapper.find('[data-role-input]').setValue('developer')
    await wrapper.find('[data-add-btn]').trigger('submit')
    await flushPromises()

    expect(addSpy).toHaveBeenCalledTimes(1)
    expect(addSpy).toHaveBeenCalledWith(1, { username: 'bob', role: 'developer' })
    expect(listSpy).toHaveBeenCalledTimes(2)
    expect((wrapper.find('[data-username-input]').element as HTMLInputElement).value).toBe('')
  })

  it('移除成员：点击移除 → removeMember(projectId, userId)，成功后重载', async () => {
    listSpy.mockResolvedValue({ list: [{ userId: 7, role: 'developer' }] })
    removeSpy.mockResolvedValue(undefined)

    const wrapper = mountView()
    await flushPromises()

    await wrapper.find('[data-member-id="7"] [data-remove-btn]').trigger('click')
    await flushPromises()

    expect(removeSpy).toHaveBeenCalledTimes(1)
    expect(removeSpy).toHaveBeenCalledWith(1, 7)
    expect(listSpy).toHaveBeenCalledTimes(2)
  })

  it('变更角色：select 变更 → updateMemberRole(projectId, userId, role)，成功后就地更新', async () => {
    listSpy.mockResolvedValue({ list: [{ userId: 7, role: 'developer' }] })
    patchSpy.mockResolvedValue({ projectId: 1, userId: 7, role: 'admin' })

    const wrapper = mountView()
    await flushPromises()

    await wrapper.find('[data-member-id="7"] [data-role-select]').setValue('admin')
    await flushPromises()

    expect(patchSpy).toHaveBeenCalledTimes(1)
    expect(patchSpy).toHaveBeenCalledWith(1, 7, 'admin')
    expect((wrapper.find('[data-member-id="7"] [data-role-select]').element as HTMLSelectElement).value).toBe('admin')
  })

  it('列表错误态：listMembers 拒绝 → role=alert 呈现错误消息', async () => {
    listSpy.mockRejectedValue(new Error('HTTP 403 /rebuild/projects/1/members'))

    const wrapper = mountView()
    await flushPromises()

    const alert = wrapper.find('[data-list-error]')
    expect(alert.exists()).toBe(true)
    expect(alert.attributes('role')).toBe('alert')
    expect(alert.text()).toContain('403')
  })

  it('操作错误态：addMember 拒绝 → role=alert 呈现操作错误，不中断列表', async () => {
    listSpy.mockResolvedValue({ list: [] })
    addSpy.mockRejectedValue(new Error('HTTP 409 /rebuild/projects/1/members'))

    const wrapper = mountView()
    await flushPromises()

    await wrapper.find('[data-username-input]').setValue('bob')
    await wrapper.find('[data-add-btn]').trigger('submit')
    await flushPromises()

    const alert = wrapper.find('[data-action-error]')
    expect(alert.exists()).toBe(true)
    expect(alert.attributes('role')).toBe('alert')
    expect(alert.text()).toContain('409')
    expect(listSpy).toHaveBeenCalledTimes(1)
  })
})
