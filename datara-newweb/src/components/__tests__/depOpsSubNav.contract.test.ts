import { config, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'
import DepOpsSubNav from '../DepOpsSubNav.vue'
import { authAccount } from '../../services/rebuild/authApi'

/** 部署运维只展示当前 worker 运行模型所需入口。 */
beforeEach(() => {
  config.global.stubs = { RouterLink: { template: '<a><slot /></a>' } }
  authAccount.value = { id: 1, username: 'admin', role: 'admin' }
})

describe('DepOpsSubNav 部署运维子导航', () => {
  it('hides monitor entry from a developer without monitor permission', () => {
    authAccount.value = { id: 7, username: 'zhangsan', role: 'developer' }
    const w = mount(DepOpsSubNav)
    expect(w.find('[data-sub-nav-item="monitor"]').exists()).toBe(false)
  })

  it('renders deployment-ops entries without legacy node registration', () => {
    const w = mount(DepOpsSubNav)
    expect(w.find('[data-sub-nav]').exists()).toBe(true)
    const items = w.findAll('[data-sub-nav-item]')
    expect(items.map((i) => i.attributes('data-sub-nav-item'))).toEqual([
      'monitor',
      'ssh',
      'worker-group',
      'environment',
      'queue',
      'cluster',
      'resource-file',
    ])
    // stub 下 RouterLink 的 to 由属性透传到 <a>
    expect(items[0]!.attributes('to')).toBe('/dep/monitor')
    // §10.10 R9 的运行依赖文件树
    expect(items[1]!.attributes('to')).toBe('/dep/ssh')
    expect(items[1]!.text()).toBe('SSH 试运行节点')
    expect(items[6]!.attributes('to')).toBe('/dep/resource-file')
    expect(items[6]!.text()).toBe('运行依赖文件')
  })

  it('carries an accessible label and no data fetching side effects', () => {
    const w = mount(DepOpsSubNav)
    expect(w.find('nav').attributes('aria-label')).toBe('部署运维子导航')
    expect(w.findAll('[data-node-list]').length).toBe(0)
  })
})
