import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { getTokenMock, replaceMock, listProjectsMock, routeQuery } = vi.hoisted(() => ({ getTokenMock: vi.fn(), replaceMock: vi.fn(), listProjectsMock: vi.fn(), routeQuery: { redirect: '/p/7/ide' } }))
vi.mock('vue-router', () => ({
  useRouter: () => ({ replace: replaceMock }),
  useRoute: () => ({ query: routeQuery }),
}))
vi.mock('../../services/http', () => ({ getToken: getTokenMock }))
vi.mock('../../services/rebuild/projectApi', () => ({ listProjects: listProjectsMock }))

import LoginView from '../LoginView.vue'

describe('AUTH-UI-02 LoginView 安全验证入口', () => {
  beforeEach(() => {
    getTokenMock.mockReset().mockReturnValue('')
    replaceMock.mockReset()
    listProjectsMock.mockReset().mockResolvedValue({ list: [] })
    routeQuery.redirect = '/p/7/ide'
  })

  it('匿名页不提供账号、密码、验证 key 或 token 输入面', () => {
    const wrapper = mount(LoginView)

    expect(wrapper.find('form').exists()).toBe(false)
    expect(wrapper.findAll('input')).toHaveLength(0)
    expect(wrapper.text()).not.toMatch(/用户名|密码/)
    expect(wrapper.text()).toContain('短时令牌')
  })

  it('仅检测当前页面内存中的运行时 token，并回到原始业务地址', async () => {
    getTokenMock.mockReturnValue('runtime-token')
    const wrapper = mount(LoginView)

    await wrapper.get('[data-recheck-session]').trigger('click')

    expect(listProjectsMock).toHaveBeenCalledTimes(1)
    expect(replaceMock).toHaveBeenCalledWith('/p/7/ide')
  })

  it('撤销或过期 token 后端校验失败时留在登录页', async () => {
    getTokenMock.mockReturnValue('revoked-token')
    listProjectsMock.mockRejectedValueOnce(new Error('invalid token'))
    const wrapper = mount(LoginView)

    await wrapper.get('[data-recheck-session]').trigger('click')

    expect(replaceMock).not.toHaveBeenCalled()
    expect(wrapper.get('[role="status"]').text()).toContain('会话已失效')
  })

  it('拒绝协议相对形式的外部回跳地址', async () => {
    getTokenMock.mockReturnValue('runtime-token')
    routeQuery.redirect = '//malicious.example/steal'
    const wrapper = mount(LoginView)

    await wrapper.get('[data-recheck-session]').trigger('click')

    expect(replaceMock).toHaveBeenCalledWith('/')
  })

  it('未注入 token 时保持在引导页且不给出凭据输入控件', async () => {
    const wrapper = mount(LoginView)

    await wrapper.get('[data-recheck-session]').trigger('click')

    expect(replaceMock).not.toHaveBeenCalled()
    expect(wrapper.get('[role="status"]').text()).toContain('尚未检测到有效会话')
  })
})
