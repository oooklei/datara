import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import View from '../depops/RuntimeNodeView.vue'
import type { RuntimeNode, RuntimeNodeDirListing } from '../../services/rebuild/runtimeNodeApi'

// 契约工厂 mock：视图仅经 createRuntimeNodeContract().listRuntimeNodes()/lsRuntimeNodeDir() 取数（验收 ①）
const listRuntimeNodes = vi.hoisted(() => vi.fn())
const lsRuntimeNodeDir = vi.hoisted(() => vi.fn())
vi.mock('../../services/rebuild/runtimeNodeApi', () => ({
  createRuntimeNodeContract: () => ({ listRuntimeNodes, lsRuntimeNodeDir }),
}))

const node = (over: Partial<RuntimeNode> = {}): RuntimeNode => ({
  id: 1,
  name: 'alpha',
  kind: 'worker',
  host: '192.168.1.9',
  port: 22,
  user: 'deploy',
  runtimeDir: '/opt/datara',
  status: 'online',
  lastHeartbeat: '2026-10-23 02:00:00',
  ...over,
})

const listing = (path: string, entries: RuntimeNodeDirListing['entries']): RuntimeNodeDirListing => ({ path, entries })

afterEach(() => vi.clearAllMocks())

describe('运行时节点组件段（IMPL-v4-17，无路由直挂）', () => {
  it('renders the node list with full nine-field coverage and honest — for nulls', async () => {
    listRuntimeNodes.mockResolvedValue([
      node(),
      node({ id: 2, name: 'beta', kind: 'master', host: null, port: null, user: null, runtimeDir: null, status: 'offline', lastHeartbeat: null }),
    ])
    const w = mount(View)
    await flushPromises()
    expect(listRuntimeNodes).toHaveBeenCalledTimes(1)
    expect(w.find('[data-node-list]').exists()).toBe(true)
    expect(w.find('[data-node="1"]').exists()).toBe(true)
    expect(w.find('[data-node="2"]').exists()).toBe(true)
    // 字段覆盖：name / kind / host / port / user / runtimeDir / status / lastHeartbeat
    const a = w.find('[data-node="1"]')
    expect(a.find('[data-node-name]').text()).toBe('alpha')
    expect(a.find('[data-node-kind]').text()).toBe('worker')
    expect(a.find('[data-node-host]').text()).toBe('192.168.1.9')
    expect(a.find('[data-node-port]').text()).toBe('22')
    expect(a.find('[data-node-user]').text()).toBe('deploy')
    expect(a.find('[data-node-dir]').text()).toBe('/opt/datara')
    expect(a.find('[data-node-status]').text()).toBe('online')
    expect(a.find('[data-node-heartbeat]').text()).toBe('2026-10-23 02:00:00')
    // 空字段如实显示 —，不虚构内容
    const b = w.find('[data-node="2"]')
    expect(b.find('[data-node-host]').text()).toBe('—')
    expect(b.find('[data-node-port]').text()).toBe('—')
    expect(b.find('[data-node-user]').text()).toBe('—')
    expect(b.find('[data-node-dir]').text()).toBe('—')
    expect(b.find('[data-node-heartbeat]').text()).toBe('—')
  })

  it('shows the empty state when no nodes are registered', async () => {
    listRuntimeNodes.mockResolvedValue([])
    const w = mount(View)
    await flushPromises()
    expect(w.find('[data-empty]').exists()).toBe(true)
    expect(w.find('[data-node-list]').exists()).toBe(false)
  })

  it('surfaces non-zero envelope codes in the error banner without an empty-shell table', async () => {
    listRuntimeNodes.mockRejectedValue(Object.assign(new Error('runtime nodes unavailable'), { code: 5002 }))
    const w = mount(View)
    await flushPromises()
    expect(w.find('[role=alert]').text()).toContain('code 5002')
    expect(w.find('[role=alert]').text()).toContain('runtime nodes unavailable')
    expect(w.find('[data-node-list]').exists()).toBe(false)
    expect(w.find('[data-empty]').exists()).toBe(false)
  })

  it('keeps the last snapshot on refresh failure instead of blanking the table', async () => {
    listRuntimeNodes.mockResolvedValueOnce([node()])
    const w = mount(View)
    await flushPromises()
    listRuntimeNodes.mockRejectedValueOnce(Object.assign(new Error('redis unreachable'), { code: 5002 }))
    await w.find('[data-refresh]').trigger('click')
    await flushPromises()
    expect(listRuntimeNodes).toHaveBeenCalledTimes(2)
    expect(w.find('[role=alert]').text()).toContain('redis unreachable')
    expect(w.find('[data-node-list]').exists()).toBe(true)
  })

  it('refreshes manually with a fresh payload and never polls', async () => {
    listRuntimeNodes.mockResolvedValueOnce([node()])
    const w = mount(View)
    await flushPromises()
    expect(w.find('[data-node="1"]').exists()).toBe(true)
    listRuntimeNodes.mockResolvedValueOnce([node({ id: 2, name: 'beta' })])
    await w.find('[data-refresh]').trigger('click')
    await flushPromises()
    expect(listRuntimeNodes).toHaveBeenCalledTimes(2)
    expect(w.find('[data-node="1"]').exists()).toBe(false)
    expect(w.find('[data-node="2"]').exists()).toBe(true)
    // 红线：无定时轮询（仅挂载 1 次 + 手动 1 次）
    expect(listRuntimeNodes).toHaveBeenCalledTimes(2)
  })

  it('browses a node directory over SFTP and walks into a sub-directory', async () => {
    listRuntimeNodes.mockResolvedValue([node()])
    lsRuntimeNodeDir.mockResolvedValue(
      listing('/opt/datara', [
        { name: 'logs', dir: true, size: 0, mtime: 1698000000 },
        { name: 'app.log', dir: false, size: 1024, mtime: 1698000000 },
      ]),
    )
    const w = mount(View)
    await flushPromises()
    await w.find('[data-node="1"]').trigger('click')
    await flushPromises()
    expect(lsRuntimeNodeDir).toHaveBeenCalledWith(1, '')
    expect(w.find('[data-ls-panel]').exists()).toBe(true)
    expect(w.find('[data-ls-path]').text()).toContain('/opt/datara')
    expect(w.find('[data-entry-list]').exists()).toBe(true)
    expect(w.find('[data-entry="logs"]').exists()).toBe(true)
    expect(w.find('[data-entry="app.log"]').exists()).toBe(true)
    // 目录/文件类型与大小如实呈现
    const logs = w.find('[data-entry="logs"]')
    expect(logs.find('[data-entry-type]').text()).toBe('目录')
    expect(logs.find('[data-entry-size]').text()).toBe('—')
    const appLog = w.find('[data-entry="app.log"]')
    expect(appLog.find('[data-entry-type]').text()).toBe('文件')
    expect(appLog.find('[data-entry-size]').text()).toBe('1024')
    // 进入子目录：请求路径拼接，空目录如实呈现
    lsRuntimeNodeDir.mockResolvedValueOnce(listing('/opt/datara/logs', []))
    await w.find('[data-entry="logs"]').trigger('click')
    await flushPromises()
    expect(lsRuntimeNodeDir).toHaveBeenLastCalledWith(1, '/opt/datara/logs')
    expect(w.find('[data-ls-empty]').exists()).toBe(true)
  })

  it('surfaces directory-listing failures without fabricating entries', async () => {
    listRuntimeNodes.mockResolvedValue([node()])
    lsRuntimeNodeDir.mockRejectedValue(Object.assign(new Error('sftp connection refused'), { code: 5002 }))
    const w = mount(View)
    await flushPromises()
    await w.find('[data-node="1"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-ls-error]').text()).toContain('code 5002')
    expect(w.find('[data-entry-list]').exists()).toBe(false)
  })
})
