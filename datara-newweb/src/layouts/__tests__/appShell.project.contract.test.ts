/**
 * L3-03 契约测试：AppShell 项目模式分流（/p/ 前缀互斥，s251 派令）
 *
 * 锚定面：项目模式侧栏五组 19 项 RouterLink（data-project-nav / data-seg 稳定锚）、
 * 顶栏当前项目名（listProjects 按 id 匹配 + nameReqSeq 竞态守卫 + 回退文案）与
 * 返回链接（data-project-exit→/）；全局模式行为语义零变化（既有锚归
 * appShell.contract.test.ts 2-05 测试集，本件不重复）。
 * 注：组件测试用独立 memory router + stub 视图，不改产品 routes.ts；
 *     projectApi mock 走 vi.hoisted 提升（本文件唯一服务依赖）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import AppShell from '../AppShell.vue'
import { PROJECT_MENU_GROUPS, PROJECT_MENU_ITEMS, projectItemPath } from '../../navigation/projectMenu'

const { listProjectsSpy } = vi.hoisted(() => ({ listProjectsSpy: vi.fn() }))

vi.mock('../../services/rebuild/projectApi', () => ({
  listProjects: listProjectsSpy,
}))

function stubView(tag: string) {
  return { template: `<div data-stub="${tag}">${tag}</div>` }
}

/** 项目模式测试路由：工作台/功能段两条（stub 视图）+ 全局首页（分流断言用） */
function makeTestRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: stubView('home') },
      { path: '/dag', component: stubView('dag') },
      { path: '/p/:projectId', component: stubView('wb') },
      { path: '/p/:projectId/:pathMatch(.*)*', component: stubView('seg') },
      { path: '/dep/runtime', component: stubView('runtime') },
      { path: '/sys', component: stubView('system') },
    ],
  })
}

beforeEach(() => {
  listProjectsSpy.mockReset()
  listProjectsSpy.mockResolvedValue({
    total: 2,
    list: [
      { id: 9, name: '项目九' },
      { id: 10, name: '项目十' },
    ],
  })
})

describe('UX v3：AppShell 项目模式——侧栏五组十九项导航', () => {
  it('项目模式侧栏：五组十九项 RouterLink，路径与 label 一致', async () => {
    const router = makeTestRouter()
    await router.push('/p/9')
    const w = mount(AppShell, { global: { plugins: [router] } })
    await flushPromises()
    const nav = w.find('[data-project-nav]')
    expect(nav.exists()).toBe(true)
    const links = nav.findAll('a.project-nav-link')
    expect(nav.findAll('[data-project-group]')).toHaveLength(PROJECT_MENU_GROUPS.length)
    expect(links).toHaveLength(19)
    for (let i = 0; i < PROJECT_MENU_ITEMS.length; i++) {
      const item = PROJECT_MENU_ITEMS[i]
      expect(links[i].attributes('data-seg')).toBe(item.id)
      expect(links[i].attributes('href')).toBe(projectItemPath(9, item))
      expect(links[i].find('span.ico').text()).toBe(item.icon)
      expect(links[i].find('span.lbl').text()).toBe(item.label)
    }
  })

  it('项目模式全局菜单不渲染（互斥分流）：.menu-group 为零', async () => {
    const router = makeTestRouter()
    await router.push('/p/9')
    const w = mount(AppShell, {
      global: { plugins: [router] },
      props: { filterOverrides: { batchSwitches: { inc4: true } } },
    })
    await flushPromises()
    expect(w.find('[data-project-nav]').exists()).toBe(true)
    expect(w.findAll('.menu-group')).toHaveLength(0)
  })

  it('AI 挂载点在项目模式保持单实例（与 RouterView 同级，不分流剔除）', async () => {
    const router = makeTestRouter()
    await router.push('/p/9')
    const w = mount(AppShell, { global: { plugins: [router] } })
    await flushPromises()
    expect(w.findAll('#ai-assistant-global-mount')).toHaveLength(1)
  })
})

describe('L3-03：AppShell 项目模式——顶栏当前项目与返回', () => {
  it('全局工作空间切换项目时保留当前功能段', async () => {
    const router = makeTestRouter()
    await router.push('/p/9/ide')
    const w = mount(AppShell, { global: { plugins: [router] } })
    await flushPromises()

    await w.get('[data-project-switcher]').trigger('click')
    await w.findAll('[data-project-option]')[1].trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.fullPath).toBe('/p/10/ide')
  })

  it('顶栏项目名：data-project-name=<projectId>，文本=listProjects 按 id 匹配的 name', async () => {
    const router = makeTestRouter()
    await router.push('/p/9')
    const w = mount(AppShell, { global: { plugins: [router] } })
    await flushPromises()
    expect(w.find('[data-project-name="9"]').text()).toBe('项目九')
    expect(listProjectsSpy).toHaveBeenCalledTimes(1)
  })

  it('返回链接：data-project-exit 常驻项目模式顶栏，href=/（返回项目列表）', async () => {
    const router = makeTestRouter()
    await router.push('/p/9')
    const w = mount(AppShell, { global: { plugins: [router] } })
    await flushPromises()
    const exit = w.find('[data-project-exit]')
    expect(exit.exists()).toBe(true)
    expect(exit.attributes('href')).toBe('/')
    expect(w.find('[data-global-operations]').attributes('href')).toBe('/dep/runtime')
    expect(w.find('[data-global-system]').attributes('href')).toBe('/sys')
  })

  it('项目切换器弹层：成员管理入口直达 /p/:projectId/system（B5-c：ProjectMembersView 可达链，设计真源 §2.1 全局顶层）', async () => {
    const router = makeTestRouter()
    await router.push('/p/9')
    const w = mount(AppShell, { global: { plugins: [router] } })
    await flushPromises()
    expect(w.find('[data-project-members]').exists()).toBe(false)

    await w.get('[data-project-switcher]').trigger('click')
    const members = w.find('[data-project-members]')
    expect(members.exists()).toBe(true)
    expect(members.text()).toContain('成员管理')
    expect(members.attributes('href')).toBe('/p/9/system')
  })

  it('项目切换跟随：push /p/10 后顶栏锚与项目名同步切换', async () => {
    const router = makeTestRouter()
    await router.push('/p/9')
    const w = mount(AppShell, { global: { plugins: [router] } })
    await flushPromises()
    expect(w.find('[data-project-name="9"]').text()).toBe('项目九')
    await router.push('/p/10')
    await flushPromises()
    expect(w.find('[data-project-name="10"]').text()).toBe('项目十')
    expect(w.find('[data-project-name="9"]').exists()).toBe(false)
  })

  it('竞态守卫（nameReqSeq）：连续切换项目，旧项目慢响应返回被丢弃，顶栏不串显', async () => {
    let resolveSlow!: (v: unknown) => void
    listProjectsSpy.mockImplementationOnce(
      () => new Promise((res) => { resolveSlow = res }),
    )
    listProjectsSpy.mockResolvedValueOnce({
      total: 1,
      list: [{ id: 10, name: '项目十' }],
    })
    const router = makeTestRouter()
    await router.push('/p/9')
    const w = mount(AppShell, { global: { plugins: [router] } })
    await flushPromises()
    expect(w.find('[data-project-name="9"]').text()).toBe('')
    await router.push('/p/10')
    await flushPromises()
    expect(w.find('[data-project-name="10"]').text()).toBe('项目十')
    resolveSlow({ total: 1, list: [{ id: 9, name: '项目九' }] })
    await flushPromises()
    expect(w.find('[data-project-name="10"]').text()).toBe('项目十')
  })

  it('离开项目域作废在途项目名请求，再进入其他项目不闪显旧名', async () => {
    let resolveOld!: (v: unknown) => void
    listProjectsSpy.mockImplementationOnce(
      () => new Promise((res) => { resolveOld = res }),
    )
    listProjectsSpy.mockImplementationOnce(() => new Promise(() => {}))
    const router = makeTestRouter()
    await router.push('/p/9')
    const w = mount(AppShell, { global: { plugins: [router] } })
    await flushPromises()

    await router.push('/')
    await flushPromises()
    resolveOld({ total: 1, list: [{ id: 9, name: '项目九' }] })
    await flushPromises()

    await router.push('/p/10')
    await flushPromises()
    expect(w.find('[data-project-name="10"]').text()).toBe('')
  })

  it('回退文案：listProjects 失败 → 项目 #<id>；可见集合无该 id → 项目 #<id>', async () => {
    listProjectsSpy.mockRejectedValue(new Error('HTTP 500 /rebuild/projects'))
    const router = makeTestRouter()
    await router.push('/p/9')
    const w = mount(AppShell, { global: { plugins: [router] } })
    await flushPromises()
    expect(w.find('[data-project-name="9"]').text()).toBe('项目 #9')

    listProjectsSpy.mockResolvedValue({
      total: 1,
      list: [{ id: 10, name: '项目十' }],
    })
    await router.push('/p/99')
    await flushPromises()
    expect(w.find('[data-project-name="99"]').text()).toBe('项目 #99')
  })
})

describe('L3-03：AppShell 全局模式——项目元素零渲染（互斥分流）', () => {
  it('全局模式（/）：无 data-project-nav/data-project-name/data-project-exit；零项目网络请求', async () => {
    const router = makeTestRouter()
    await router.push('/')
    const w = mount(AppShell, {
      global: { plugins: [router] },
      props: { filterOverrides: { batchSwitches: { inc4: true } } },
    })
    await flushPromises()
    expect(w.find('[data-project-nav]').exists()).toBe(false)
    expect(w.find('[data-project-name]').exists()).toBe(false)
    expect(w.find('[data-project-exit]').exists()).toBe(false)
    expect(w.find('[data-global-project]').attributes('href')).toBe('/')
    expect(listProjectsSpy).not.toHaveBeenCalled()
    // 全局菜单语义保持（inc4 批次开 → task-center 组正常渲染）
    expect(w.findAll('.menu-group')).toHaveLength(1)
    expect(w.find('.menu-group[data-group-id="task-center"]').exists()).toBe(true)
  })
})
