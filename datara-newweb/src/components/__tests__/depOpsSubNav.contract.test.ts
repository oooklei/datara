import { config, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'
import DepOpsSubNav from '../DepOpsSubNav.vue'
import { authAccount } from '../../services/rebuild/authApi'

/**
 * 部署运维子导航契约（对齐 docs/increments/2026-10-28-旧前端对标审计-04其余业务域.md §2.1）：
 * 旧前端「SSH 节点管理在『运行时节点』页」，新前端 /dep/ssh 功能完备但无入口可达，
 * 故顶栏部署运维图标下的三个子页须互相可达。
 */
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

  it('renders the nine deployment-ops entries with route targets', () => {
    const w = mount(DepOpsSubNav)
    expect(w.find('[data-sub-nav]').exists()).toBe(true)
    const items = w.findAll('[data-sub-nav-item]')
    expect(items.map((i) => i.attributes('data-sub-nav-item'))).toEqual([
      'runtime',
      'monitor',
      'ssh',
      'worker-group',
      'environment',
      'queue',
      'cluster',
      'resource-file',
      'task-group',
    ])
    // stub 下 RouterLink 的 to 由属性透传到 <a>
    expect(items[0]!.attributes('to')).toBe('/dep/runtime')
    expect(items[1]!.attributes('to')).toBe('/dep/monitor')
    expect(items[2]!.attributes('to')).toBe('/dep/ssh')
    // §10.10 R9 资源文件（全局文件树）
    expect(items[7]!.attributes('to')).toBe('/dep/resource-file')
    // §10.10 R8 快捷入口：全局别名 /task-group 解析到当前项目
    expect(items[8]!.attributes('to')).toBe('/task-group')
  })

  it('carries an accessible label and no data fetching side effects', () => {
    const w = mount(DepOpsSubNav)
    expect(w.find('nav').attributes('aria-label')).toBe('部署运维子导航')
    expect(w.findAll('[data-node-list]').length).toBe(0)
  })
})
