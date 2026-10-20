/**
 * L3-02 组件测试：HomeView 项目列表页（权威设计 §5A.11）。
 * 覆盖：加载/错误/空三态、卡片渲染与 data-project-id 锚点、卡片点击 → /p/:projectId、
 * ownOrJoined 徽标（可选字段，未交付不渲染）。
 * 依赖 mock：vue-router.useRouter（首页无真实路由栈）、projectApi.listProjects。
 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { pushSpy, listProjectsMock } = vi.hoisted(() => ({
  pushSpy: vi.fn(),
  listProjectsMock: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: pushSpy }),
}))

vi.mock('../../services/rebuild/projectApi', () => ({
  listProjects: listProjectsMock,
}))

import HomeView from '../HomeView.vue'

beforeEach(() => {
  pushSpy.mockClear()
  listProjectsMock.mockReset()
})

describe('L3-02 HomeView 项目列表页', () => {
  it('加载中：渲染 role=status 加载态且不发其他断言', () => {
    listProjectsMock.mockReturnValue(new Promise(() => {}))
    const w = mount(HomeView)
    expect(w.find('[role="status"]').exists()).toBe(true)
    expect(w.find('[role="status"]').text()).toContain('加载中')
    expect(w.findAll('.project-card')).toHaveLength(0)
  })

  it('数据态：渲染项目卡片，名称与 data-project-id 锚点正确', async () => {
    listProjectsMock.mockResolvedValue({
      total: 2,
      list: [
        { id: 1, name: '数据中台' },
        { id: 2, name: '风控治理' },
      ],
    })
    const w = mount(HomeView)
    await flushPromises()
    expect(w.find('[role="status"]').exists()).toBe(false)
    const cards = w.findAll('.project-card')
    expect(cards).toHaveLength(2)
    expect(cards[0].find('.project-name').text()).toBe('数据中台')
    expect(cards[0].attributes('data-project-id')).toBe('1')
    expect(cards[1].attributes('data-project-id')).toBe('2')
  })

  it('卡片点击 → router.push(/p/:projectId)', async () => {
    listProjectsMock.mockResolvedValue({
      total: 1,
      list: [{ id: 42, name: '风控治理' }],
    })
    const w = mount(HomeView)
    await flushPromises()
    await w.find('[data-project-id="42"]').trigger('click')
    expect(pushSpy).toHaveBeenCalledTimes(1)
    expect(pushSpy).toHaveBeenCalledWith('/p/42')
  })

  it('空态：list 为空渲染空态文案，不渲染卡片', async () => {
    listProjectsMock.mockResolvedValue({ total: 0, list: [] })
    const w = mount(HomeView)
    await flushPromises()
    expect(w.find('.state-empty').exists()).toBe(true)
    expect(w.findAll('.project-card')).toHaveLength(0)
  })

  it('错误态：listProjects reject → role=alert 呈现错误信息', async () => {
    listProjectsMock.mockRejectedValue(new Error('HTTP 500 /rebuild/projects'))
    const w = mount(HomeView)
    await flushPromises()
    expect(w.find('[role="alert"]').exists()).toBe(true)
    expect(w.find('[role="alert"]').text()).toContain('HTTP 500')
    expect(w.findAll('.project-card')).toHaveLength(0)
  })

  it('ownOrJoined 徽标：owner/joined 渲染对应徽标；未交付字段不渲染', async () => {
    listProjectsMock.mockResolvedValue({
      total: 3,
      list: [
        { id: 1, name: '甲', ownOrJoined: 'owner' },
        { id: 2, name: '乙', ownOrJoined: 'joined' },
        { id: 3, name: '丙' },
      ],
    })
    const w = mount(HomeView)
    await flushPromises()
    const cards = w.findAll('.project-card')
    expect(cards[0].find('.project-badge').text()).toBe('我拥有')
    expect(cards[1].find('.project-badge').text()).toBe('我参与')
    expect(cards[1].find('.project-badge').classes()).toContain('joined')
    expect(cards[2].find('.project-badge').exists()).toBe(false)
  })
})
