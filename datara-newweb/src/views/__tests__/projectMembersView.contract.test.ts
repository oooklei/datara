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
  PROJECT_ROLES: ['inherit', 'viewer', 'operator'],
  PROJECT_ROLE_LABELS: { inherit: '继承平台角色', viewer: '项目观察者（只读）', operator: '项目操作员（运维）' },
  MEMBER_ERROR_MESSAGES: { 4002: '不支持的项目角色', 4041: '项目成员不存在或用户名无效', 4042: '项目不存在', 4043: '用户不存在', 4091: '该用户已经是项目成员' },
  addMember: addSpy,
  listMembers: listSpy,
  listProjectRoles: vi.fn().mockResolvedValue([
    { value: 'inherit', label: '继承平台角色', inheritsPlatform: true, permissions: null },
    { value: 'viewer', label: '项目观察者（只读）', inheritsPlatform: false, permissions: null },
    { value: 'operator', label: '项目操作员（运维）', inheritsPlatform: false, permissions: null },
  ]),
  removeMember: removeSpy,
  updateMemberRole: patchSpy,
}))

function _member(userId: number, role: string, opts: Partial<{ username: string; projectRole: string | null; status: string; joinedAt: string }> = {}) {
  return {
    userId,
    username: opts.username ?? `user${userId}`,
    role,
    projectRole: (opts.projectRole as 'inherit' | 'viewer' | 'operator' | null) ?? null,
    status: opts.status ?? 'enabled',
    joinedAt: opts.joinedAt ?? null,
  }
}

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
        _member(7, 'developer', { projectRole: 'inherit' }),
        _member(9, 'viewer', { projectRole: 'viewer' }),
      ],
    })

    const wrapper = mountView()
    await flushPromises()

    const row7 = wrapper.find('[data-member-id="7"]')
    const row9 = wrapper.find('[data-member-id="9"]')
    expect(row7.exists()).toBe(true)
    expect(row7.find('[data-member-user-id]').text()).toBe('7')
    expect((row7.find('[data-role-select]').element as HTMLSelectElement).value).toBe('inherit')
    expect((row9.find('[data-role-select]').element as HTMLSelectElement).value).toBe('viewer')
  })

  it('项目路由切换后重新加载新项目成员且不保留旧项目列表', async () => {
    let resolveSecond!: (value: { list: ReturnType<typeof _member>[] }) => void
    listSpy
      .mockResolvedValueOnce({ list: [_member(7, 'developer', { projectRole: 'inherit' })] })
      .mockReturnValueOnce(new Promise((resolve) => { resolveSecond = resolve }))

    const wrapper = mountView({ projectId: 1 })
    await flushPromises()
    expect(wrapper.find('[data-member-id="7"]').exists()).toBe(true)

    await wrapper.setProps({ projectId: 2 })
    await wrapper.vm.$nextTick()
    expect(listSpy).toHaveBeenLastCalledWith(2)
    expect(wrapper.find('[data-loading]').exists()).toBe(true)
    expect(wrapper.find('[data-member-id="7"]').exists()).toBe(false)

    resolveSecond({ list: [_member(8, 'viewer', { projectRole: 'viewer' })] })
    await flushPromises()
    expect(wrapper.find('[data-member-id="8"]').exists()).toBe(true)
  })

  it('快速切换项目时丢弃旧项目迟到的成员响应', async () => {
    let resolveFirst!: (value: { list: ReturnType<typeof _member>[] }) => void
    let resolveSecond!: (value: { list: ReturnType<typeof _member>[] }) => void
    listSpy
      .mockReturnValueOnce(new Promise((resolve) => { resolveFirst = resolve }))
      .mockReturnValueOnce(new Promise((resolve) => { resolveSecond = resolve }))

    const wrapper = mountView({ projectId: 1 })
    await wrapper.setProps({ projectId: 2 })
    await wrapper.vm.$nextTick()

    resolveSecond({ list: [_member(8, 'viewer', { projectRole: 'viewer' })] })
    await flushPromises()
    resolveFirst({ list: [_member(7, 'admin', { projectRole: 'inherit' })] })
    await flushPromises()

    expect(wrapper.find('[data-member-id="8"]').exists()).toBe(true)
    expect(wrapper.find('[data-member-id="7"]').exists()).toBe(false)
  })

  it('添加成员：提交 → addMember(projectId, {username, role})，成功后重载并清空输入', async () => {
    listSpy.mockResolvedValue({ list: [] })
    addSpy.mockResolvedValue({ projectId: 1, userId: 5, username: 'bob', role: 'inherit', projectRole: 'inherit' })

    const wrapper = mountView()
    await flushPromises()

    await wrapper.find('[data-username-input]').setValue('bob')
    await wrapper.find('[data-role-input]').setValue('inherit')
    await wrapper.find('[data-add-btn]').trigger('submit')
    await flushPromises()

    expect(addSpy).toHaveBeenCalledTimes(1)
    expect(addSpy).toHaveBeenCalledWith(1, { username: 'bob', role: 'inherit' })
    expect(listSpy).toHaveBeenCalledTimes(2)
    expect((wrapper.find('[data-username-input]').element as HTMLInputElement).value).toBe('')
  })

  it('移除成员：点击移除 → removeMember(projectId, userId)，成功后重载', async () => {
    listSpy.mockResolvedValue({ list: [_member(7, 'developer', { projectRole: 'inherit' })] })
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
    listSpy.mockResolvedValue({ list: [_member(7, 'developer', { projectRole: 'inherit' })] })
    patchSpy.mockResolvedValue({ projectId: 1, userId: 7, role: 'viewer', projectRole: 'viewer' })

    const wrapper = mountView()
    await flushPromises()

    await wrapper.find('[data-member-id="7"] [data-role-select]').setValue('viewer')
    await flushPromises()

    expect(patchSpy).toHaveBeenCalledTimes(1)
    expect(patchSpy).toHaveBeenCalledWith(1, 7, 'viewer')
    expect((wrapper.find('[data-member-id="7"] [data-role-select]').element as HTMLSelectElement).value).toBe('viewer')
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

  it('D13 列表搜索：关键字前端过滤成员，不触发后端', async () => {
    listSpy.mockResolvedValue({
      list: [
        _member(7, 'developer', { projectRole: 'inherit' }),
        _member(9, 'viewer', { projectRole: 'viewer' }),
      ],
    })

    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.findAll('[data-member-id]')).toHaveLength(2)
    await wrapper.get('[data-filter-keyword]').setValue('7')
    const rows = wrapper.findAll('[data-member-id]')
    expect(rows).toHaveLength(1)
    expect(rows[0]!.attributes('data-member-id')).toBe('7')
    expect(listSpy).toHaveBeenCalledTimes(1)

    await wrapper.get('[data-filter-keyword]').setValue('不存在')
    expect(wrapper.get('table tbody').text()).toContain('无匹配成员')
  })
})
