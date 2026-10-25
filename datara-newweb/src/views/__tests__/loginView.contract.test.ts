import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { getTokenMock, replaceMock } = vi.hoisted(() => ({ getTokenMock: vi.fn(), replaceMock: vi.fn() }))
vi.mock('vue-router', () => ({
  useRouter: () => ({ replace: replaceMock }),
  useRoute: () => ({ query: { redirect: '/p/7/ide' } }),
}))
vi.mock('../../services/http', () => ({ getToken: getTokenMock }))

import LoginView from '../LoginView.vue'

describe('AUTH-UI-02 LoginView 安全验证入口', () => {
  beforeEach(() => {
    getTokenMock.mockReset().mockReturnValue('')
    replaceMock.mockReset()
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

    expect(replaceMock).toHaveBeenCalledWith('/p/7/ide')
  })

  it('未注入 token 时保持在引导页且不给出凭据输入控件', async () => {
    const wrapper = mount(LoginView)

    await wrapper.get('[data-recheck-session]').trigger('click')

    expect(replaceMock).not.toHaveBeenCalled()
    expect(wrapper.get('[role="status"]').text()).toContain('尚未检测到有效会话')
  })
})
