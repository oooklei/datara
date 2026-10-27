import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  route: { value: { path: '/p/33/ide' } },
  token: { value: '' },
  account: { value: null as { username: string } | null },
}))

vi.mock('vue-router', () => ({
  useRoute: () => mocks.route.value,
}))

vi.mock('../services/http', () => ({
  getToken: () => mocks.token.value,
}))

vi.mock('../services/rebuild/authApi', () => ({
  authAccount: mocks.account,
}))

import App from '../App.vue'

describe('App shell session contract', () => {
  beforeEach(() => {
    mocks.route.value = { path: '/p/33/ide' }
    mocks.token.value = ''
    mocks.account.value = null
  })

  it('renders the authenticated shell when an HttpOnly session restored the account', () => {
    mocks.account.value = { username: 'dev' }

    const wrapper = mount(App, {
      global: {
        stubs: {
          AppShell: { template: '<main data-test="app-shell" />' },
          RouterView: { template: '<main data-test="router-view" />' },
        },
      },
    })

    expect(wrapper.find('[data-test="app-shell"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="router-view"]').exists()).toBe(false)
  })
})
