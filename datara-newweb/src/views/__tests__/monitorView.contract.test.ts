import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import View from '../depops/MonitorView.vue'
import type { MonitorSnapshot } from '../../services/rebuild/monitorApi'

// 契约工厂 mock：视图仅经 createMonitorContract().fetchMonitorNodes() 取数（验收 ①）
const fetchMonitorNodes = vi.hoisted(() => vi.fn())
vi.mock('../../services/rebuild/monitorApi', async () => {
  const actual =
    await vi.importActual<typeof import('../../services/rebuild/monitorApi')>(
      '../../services/rebuild/monitorApi',
    )
  return { ...actual, createMonitorContract: () => ({ fetchMonitorNodes }) }
})

const masterFresh = {
  module: 'master' as const,
  node: 'master-1',
  cpu: 12.5,
  mem: 48.2,
  memUsedMb: 4945,
  memTotalMb: 10240,
  disk: 71.0,
  heartbeat: 'online' as const,
  metricState: 'fresh' as const,
  lastSeen: '2026-10-23 02:00:00',
  tags: ['core'],
}
const workerStaleNoMetrics = {
  module: 'worker' as const,
  node: 'worker-2',
  cpu: null,
  mem: null,
  memUsedMb: null,
  memTotalMb: null,
  disk: null,
  heartbeat: 'online' as const,
  metricState: 'stale' as const,
  lastSeen: '2026-10-22 23:58:00',
  tags: [],
}
const sshUnsupported = {
  module: 'ssh' as const,
  node: 'prod-jump',
  cpu: null,
  mem: null,
  memUsedMb: null,
  memTotalMb: null,
  disk: null,
  heartbeat: 'unknown' as const,
  metricState: 'unsupported' as const,
  lastSeen: null,
  tags: ['prod'],
}
const snapshot = (nodes: MonitorSnapshot['nodes'], zkAvailable = true): MonitorSnapshot => ({
  zkAvailable,
  generatedAt: '2026-10-23 02:00:00',
  nodes,
})

afterEach(() => vi.clearAllMocks())

describe('集群监控组件段（IMPL-v4-16，无路由直挂）', () => {
  it('renders mixed master/worker/ssh rows with full field coverage', async () => {
    fetchMonitorNodes.mockResolvedValue(snapshot([masterFresh, workerStaleNoMetrics, sshUnsupported]))
    const w = mount(View)
    await flushPromises()
    expect(fetchMonitorNodes).toHaveBeenCalledTimes(1)
    expect(w.find('[data-node-list]').exists()).toBe(true)
    expect(w.find('[data-node="master:master-1"]').exists()).toBe(true)
    expect(w.find('[data-node="worker:worker-2"]').exists()).toBe(true)
    expect(w.find('[data-node="ssh:prod-jump"]').exists()).toBe(true)
    // 字段覆盖：cpu / mem / memUsedMb+memTotalMb / disk / lastSeen / tags
    const master = w.find('[data-node="master:master-1"]')
    expect(master.find('[data-cpu]').text()).toBe('12.5%')
    expect(master.find('[data-mem]').text()).toBe('48.2%')
    expect(master.find('[data-mem-mb]').text()).toBe('4945 / 10240')
    expect(master.find('[data-disk]').text()).toBe('71%')
    expect(master.find('[data-last-seen]').text()).toBe('2026-10-23 02:00:00')
    expect(master.find('[data-tags]').text()).toBe('core')
    // 头部：zkAvailable + generatedAt
    expect(w.find('[data-zk]').attributes('data-zk')).toBe('true')
    expect(w.find('[data-generated]').text()).toContain('2026-10-23 02:00:00')
  })

  it('renders empty metrics honestly as — and distinguishes stale / unsupported / unknown', async () => {
    fetchMonitorNodes.mockResolvedValue(snapshot([workerStaleNoMetrics, sshUnsupported], false))
    const w = mount(View)
    await flushPromises()
    const worker = w.find('[data-node="worker:worker-2"]')
    // 空指标如实显示 —，不虚构数值
    expect(worker.find('[data-cpu]').text()).toBe('—')
    expect(worker.find('[data-mem]').text()).toBe('—')
    expect(worker.find('[data-mem-mb]').text()).toBe('—')
    expect(worker.find('[data-disk]').text()).toBe('—')
    // stale / unsupported 可辨识文案
    expect(worker.find('[data-metric-state]').attributes('data-metric-state')).toBe('stale')
    expect(worker.find('[data-metric-state]').text()).toBe('过期')
    const ssh = w.find('[data-node="ssh:prod-jump"]')
    expect(ssh.find('[data-metric-state]').text()).toBe('不支持')
    expect(ssh.find('[data-last-seen]').text()).toBe('—')
    // heartbeat=unknown 可辨识，且 ZK 不可用如实呈现
    expect(ssh.find('[data-heartbeat]').text()).toBe('未知（无法判定）')
    expect(w.find('[data-zk]').attributes('data-zk')).toBe('false')
    expect(w.find('[data-zk]').text()).toContain('不可用')
  })

  it('shows the empty state when no nodes are reported', async () => {
    fetchMonitorNodes.mockResolvedValue(snapshot([]))
    const w = mount(View)
    await flushPromises()
    expect(w.find('[data-empty]').exists()).toBe(true)
    expect(w.find('[data-node-list]').exists()).toBe(false)
  })

  it('surfaces non-zero envelope codes in the error banner without an empty-shell table', async () => {
    fetchMonitorNodes.mockRejectedValue(Object.assign(new Error('cluster metrics unavailable'), { code: 5002 }))
    const w = mount(View)
    await flushPromises()
    expect(w.find('[role=alert]').text()).toContain('code 5002')
    expect(w.find('[role=alert]').text()).toContain('cluster metrics unavailable')
    expect(w.find('[data-node-list]').exists()).toBe(false)
    expect(w.find('[data-empty]').exists()).toBe(false)
  })

  it('keeps the last snapshot on refresh failure instead of blanking the table', async () => {
    fetchMonitorNodes.mockResolvedValueOnce(snapshot([masterFresh]))
    const w = mount(View)
    await flushPromises()
    fetchMonitorNodes.mockRejectedValueOnce(Object.assign(new Error('redis unreachable'), { code: 5002 }))
    await w.find('[data-refresh]').trigger('click')
    await flushPromises()
    expect(fetchMonitorNodes).toHaveBeenCalledTimes(2)
    expect(w.find('[role=alert]').text()).toContain('redis unreachable')
    expect(w.find('[data-node-list]').exists()).toBe(true)
  })

  it('refreshes manually with a fresh payload and never polls', async () => {
    fetchMonitorNodes.mockResolvedValueOnce(snapshot([masterFresh]))
    const w = mount(View)
    await flushPromises()
    expect(w.find('[data-node="master:master-1"]').exists()).toBe(true)
    fetchMonitorNodes.mockResolvedValueOnce(snapshot([sshUnsupported]))
    await w.find('[data-refresh]').trigger('click')
    await flushPromises()
    expect(fetchMonitorNodes).toHaveBeenCalledTimes(2)
    expect(w.find('[data-node="master:master-1"]').exists()).toBe(false)
    expect(w.find('[data-node="ssh:prod-jump"]').exists()).toBe(true)
    // 红线：无定时轮询（仅挂载 1 次 + 手动 1 次）
    expect(fetchMonitorNodes).toHaveBeenCalledTimes(2)
  })
})
