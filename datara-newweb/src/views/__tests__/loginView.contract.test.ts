import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { loginMock, replaceMock } = vi.hoisted(() => ({ loginMock: vi.fn(), replaceMock: vi.fn() }))
vi.mock('vue-router', () => ({
  useRouter: () => ({ replace: replaceMock }),
  useRoute: () => ({ query: { redirect: '/p/7/ide' } }),
}))
vi.mock('../../services/rebuild/authApi', () => ({ login: loginMock }))

import LoginView from '../LoginView.vue'

describe('LoginView 认证闭环', () => {
  beforeEach(() => { loginMock.mockReset(); replaceMock.mockReset() })

  it('提交真实凭据并回跳原始业务地址', async () => {
    loginMock.mockResolvedValue({ token: 'ephemeral', account: { id: 1, username: 'admin', role: 'admin' } })
    const wrapper = mount(LoginView)
    const inputs = wrapper.findAll('input')
    await inputs[0].setValue('admin')
    await inputs[1].setValue('secret')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(loginMock).toHaveBeenCalledWith('admin', 'secret')
    expect(replaceMock).toHaveBeenCalledWith('/p/7/ide')
  })

  it('空表单 fail-closed 且展示错误，不调用后端', async () => {
    const wrapper = mount(LoginView)
    await wrapper.find('form').trigger('submit')
    expect(loginMock).not.toHaveBeenCalled()
    expect(wrapper.find('[role="alert"]').text()).toContain('请输入用户名与密码')
  })
})
