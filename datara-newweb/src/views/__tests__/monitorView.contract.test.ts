import { config, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import View from '../depops/MonitorView.vue'
import { authAccount } from '../../services/rebuild/authApi'
import type { MonitorSnapshot } from '../../services/rebuild/monitorApi'
import type {
  OrchestrationDatabaseRow,
  OrchestrationNodeType,
  OrchestrationServerRow,
} from '../../services/rebuild/orchestrationApi'

// 契约工厂 mock：视图仅经 createMonitorContract().fetchMonitorNodes() 取数（验收 ①）
const fetchMonitorNodes = vi.hoisted(() => vi.fn())
vi.mock('../../services/rebuild/monitorApi', async () => {
  const actual =
    await vi.importActual<typeof import('../../services/rebuild/monitorApi')>(
      '../../services/rebuild/monitorApi',
    )
  return { ...actual, createMonitorContract: () => ({ fetchMonitorNodes }) }
})

// §10.11：监控中心另经 projectApi 与 orchestrationApi 取数；测试中隔离真实 HTTP
const orch = vi.hoisted(() => ({
  fetchMonitorServers: vi.fn(),
  fetchMonitorDatabases: vi.fn(),
  fetchMasterWorkflowExecutors: vi.fn(),
  fetchWorkerTaskExecutors: vi.fn(),
  fetchTaskStateCount: vi.fn(),
  fetchWorkflowStateCount: vi.fn(),
  fetchDefineUserCount: vi.fn(),
}))
vi.mock('../../services/rebuild/orchestrationApi', async () => {
  const actual =
    await vi.importActual<typeof import('../../services/rebuild/orchestrationApi')>(
      '../../services/rebuild/orchestrationApi',
    )
  return { ...actual, orchestrationApi: orch }
})

const listProjects = vi.hoisted(() => vi.fn())
vi.mock('../../services/rebuild/projectApi', async () => {
  const actual =
    await vi.importActual<typeof import('../../services/rebuild/projectApi')>(
      '../../services/rebuild/projectApi',
    )
  return { ...actual, listProjects }
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

/** 海豚 master/worker 行的最小完整字段集（camelCase 拉平契约，见后端 _server_row）。 */
const dsServer = (over: Partial<OrchestrationServerRow> = {}): OrchestrationServerRow => ({
  id: 1,
  host: '192.168.1.9',
  port: 5678,
  serverDirectory: '/ds/server',
  createTime: '2026-10-29 09:00:00',
  lastHeartbeatTime: '2026-10-29 10:00:00',
  heartbeatAgeSeconds: 1.2,
  heartbeatState: 'online',
  serverStatus: 'NORMAL',
  cpuUsage: 12.5,
  memoryUsage: 40,
  diskUsage: 60,
  loadAverage: null,
  jvmCpuUsage: null,
  jvmMemoryUsage: null,
  jvmHeapUsed: null,
  jvmHeapMax: null,
  jvmNonHeapUsed: null,
  jvmNonHeapMax: null,
  processId: null,
  startTime: null,
  reportTime: null,
  workerGroup: 'default',
  threadPoolUsage: null,
  workerHostWeight: null,
  heartbeat: {},
  ...over,
})
const dbRow = (over: Partial<OrchestrationDatabaseRow> = {}): OrchestrationDatabaseRow => ({
  dbType: 'POSTGRE_SQL',
  state: 'YES',
  maxConnections: 100,
  maxUsedConnections: 3,
  threadsConnections: 35,
  threadsRunningConnections: 1,
  date: '2026-10-29 10:00:00',
  ...over,
})

afterEach(() => {
  vi.clearAllMocks()
  authAccount.value = null
})

// 部署运维子导航使用 RouterLink；无 router 装配时全局 stub 为普通 <a>（沿用 systemAdminView 既有范式）
beforeEach(() => {
  config.global.stubs = { RouterLink: { template: '<a><slot /></a>' } }
  // DepOpsSubNav 的 monitor 入口受 monitor:read 门禁；注入 admin 登录态使七项子导航齐备
  authAccount.value = { id: 1, username: 'admin', role: 'admin' }
  // 默认放行：各契约均返回可渲染数据，用例内按需覆盖
  fetchMonitorNodes.mockResolvedValue(snapshot([masterFresh]))
  listProjects.mockResolvedValue({ total: 1, list: [{ id: 1, name: 'demo' }] })
  orch.fetchMonitorServers.mockImplementation((nodeType: OrchestrationNodeType) =>
    Promise.resolve(nodeType === 'MASTER' ? [dsServer()] : []),
  )
  orch.fetchMonitorDatabases.mockResolvedValue([dbRow()])
  orch.fetchMasterWorkflowExecutors.mockResolvedValue([])
  orch.fetchWorkerTaskExecutors.mockResolvedValue([])
  orch.fetchTaskStateCount.mockResolvedValue({ totalCount: 0, taskInstanceStatusCounts: [] })
  orch.fetchWorkflowStateCount.mockResolvedValue({ totalCount: 0, workflowInstanceStatusCounts: [] })
  orch.fetchDefineUserCount.mockResolvedValue({ count: 0, userList: [] })
})

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

  it('D13 列表搜索：关键字前端过滤节点行，不触发后端', async () => {
    fetchMonitorNodes.mockResolvedValue(snapshot([masterFresh, sshUnsupported]))
    const w = mount(View)
    await flushPromises()

    expect(w.findAll('[data-node-list] tbody tr')).toHaveLength(2)
    await w.get('[data-filter-keyword]').setValue('prod-jump')
    const rows = w.findAll('[data-node-list] tbody tr')
    expect(rows).toHaveLength(1)
    expect(rows[0]!.text()).toContain('prod-jump')
    expect(fetchMonitorNodes).toHaveBeenCalledTimes(1)

    await w.get('[data-filter-keyword]').setValue('不存在')
    expect(w.find('[data-node-list] tbody').text()).toContain('无匹配节点')
  })

  it('exposes the deployment-ops sub navigation so runtime/ssh entries are reachable', () => {
    const w = mount(View)
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
    expect(items[0]!.attributes('to')).toBe('/dep/runtime')
  })
})

describe('§10.11 海豚监控三区块 + 首页三张统计卡', () => {
  it('renders master / worker / alert / database rows from the orchestration contract', async () => {
    orch.fetchMonitorServers.mockImplementation((nodeType: OrchestrationNodeType) =>
      Promise.resolve(nodeType === 'MASTER' ? [dsServer()] : [dsServer({ id: 2, port: 1236 })]),
    )
    orch.fetchMonitorDatabases.mockResolvedValue([dbRow(), dbRow({ dbType: 'MYSQL', state: 'NO' })])
    const w = mount(View)
    await flushPromises()

    expect(w.find('[data-master-list]').exists()).toBe(true)
    expect(w.find('[data-master="192.168.1.9:5678"]').exists()).toBe(true)
    expect(w.find('[data-master="192.168.1.9:5678"]').find('[data-cpu]').text()).toBe('12.5%')
    expect(w.find('[data-master-count]').text()).toBe('1')
    expect(w.find('[data-worker-list]').exists()).toBe(true)
    expect(w.find('[data-worker="192.168.1.9:1236"]').find('[data-worker-group]').text()).toBe('default')
    expect(w.find('[data-alert-list]').exists()).toBe(true)
    expect(w.find('[data-db-list]').exists()).toBe(true)
    expect(w.findAll('[data-db-list] tbody tr')).toHaveLength(2)
    // 海豚元数据库连接池展示（非 dbx 业务库）
    expect(w.find('[data-db-section]').text()).toContain('海豚元数据库')
  })

  it('drills into running workflow instances for a master row and exposes raw executor fields', async () => {
    orch.fetchMasterWorkflowExecutors.mockResolvedValue([
      {
        name: 'wf-1',
        workflowDefinitionCode: '100',
        state: 'RUNNING_EXECUTION',
        startTime: '2026-10-29 09:30:00',
        runTimes: 1,
      },
    ])
    const w = mount(View)
    await flushPromises()

    await w.find('[data-drill]').trigger('click')
    await flushPromises()
    expect(orch.fetchMasterWorkflowExecutors).toHaveBeenCalledWith('192.168.1.9:5678')
    expect(w.find('[data-drill-panel]').attributes('data-drill-kind')).toBe('master')
    expect(w.find('[data-executor-name]').text()).toBe('wf-1')
    expect(w.find('[data-executor-state]').text()).toBe('RUNNING_EXECUTION')
    expect(w.find('[data-executor-run-times]').text()).toBe('1')
    // 再次点击同一行收起
    await w.find('[data-drill]').trigger('click')
    await flushPromises()
    expect(w.find('[data-drill-panel]').exists()).toBe(false)
  })

  it('renders the /home three cards with the fixed state set even when counts are zero', async () => {
    orch.fetchTaskStateCount.mockResolvedValue({
      totalCount: 3,
      taskInstanceStatusCounts: [{ state: 'SUCCESS', count: 3 }],
    })
    orch.fetchWorkflowStateCount.mockResolvedValue({
      totalCount: 1,
      workflowInstanceStatusCounts: [{ state: 'RUNNING_EXECUTION', count: 1 }],
    })
    orch.fetchDefineUserCount.mockResolvedValue({ count: 5, userList: [{ userName: 'alice', count: 5 }] })
    const w = mount(View)
    await flushPromises()

    expect(w.find('[data-analysis-cards]').exists()).toBe(true)
    expect(w.find('[data-analysis-task]').text()).toContain('3')
    expect(w.find('[data-analysis-workflow]').text()).toContain('1')
    // 状态全集固定 10 项；未返回的状态补 0 不丢项
    expect(w.findAll('[data-analysis-task] .legend-line')).toHaveLength(10)
    expect(w.findAll('[data-analysis-workflow] .legend-line')).toHaveLength(10)
    expect(w.findAll('[data-analysis-task] .legend-line')[0]!.text()).toContain('已提交')
    // 按用户柱状
    expect(w.find('[data-analysis-define] .bar-row .bar-name').text()).toBe('alice')
    expect(w.find('[data-analysis-define] .bar-val').text()).toBe('5')
  })

  it('queries the analysis window per datara projectId and never accepts an arbitrary projectCode', async () => {
    listProjects.mockResolvedValue({
      total: 2,
      list: [
        { id: 1, name: 'demo' },
        { id: 2, name: 'prod' },
      ],
    })
    const w = mount(View)
    await flushPromises()
    const calls = () => orch.fetchTaskStateCount.mock.calls

    expect(w.findAll('[data-analysis-project] option')).toHaveLength(3)
    // 挂载默认选中第一项（projectCode 由后端解析）
    expect(orch.fetchTaskStateCount).toHaveBeenCalledWith(1, undefined, undefined)

    await w.find('[data-analysis-project]').setValue('2')
    await w.find('[data-analysis-start]').setValue('2026-10-01')
    await w.find('[data-analysis-end]').setValue('2026-10-31')
    await w.find('[data-analysis-query]').trigger('click')
    await flushPromises()

    expect(orch.fetchTaskStateCount).toHaveBeenCalledWith(2, '2026-10-01', '2026-10-31')
    expect(orch.fetchWorkflowStateCount).toHaveBeenCalledWith(2, '2026-10-01', '2026-10-31')
    expect(orch.fetchDefineUserCount).toHaveBeenCalledWith(2)
    // 红线：只传 projectId，不出现 projectCode 实参
    for (const call of calls()) {
      expect(call.length).toBeLessThanOrEqual(3)
    }
  })

  it('keeps sections independent: one section failing does not blank the others', async () => {
    orch.fetchMonitorDatabases.mockRejectedValue(
      Object.assign(new Error('db pool unavailable'), { code: 5002 }),
    )
    const w = mount(View)
    await flushPromises()

    expect(w.find('[data-db-error]').text()).toContain('db pool unavailable')
    expect(w.find('[data-node-list]').exists()).toBe(true)
    expect(w.find('[data-master-list]').exists()).toBe(true)
    expect(w.find('[data-db-list]').exists()).toBe(false)
  })

  it('keeps the last analysis snapshot on refresh failure', async () => {
    orch.fetchTaskStateCount
      .mockResolvedValueOnce({
        totalCount: 2,
        taskInstanceStatusCounts: [{ state: 'SUCCESS', count: 2 }],
      })
      .mockRejectedValueOnce(Object.assign(new Error('analysis down'), { code: 5002 }))
    const w = mount(View)
    await flushPromises()
    expect(w.find('[data-analysis-task]').text()).toContain('2')

    await w.find('[data-analysis-query]').trigger('click')
    await flushPromises()
    expect(w.find('[data-analysis-error]').text()).toContain('analysis down')
    expect(w.find('[data-analysis-task]').text()).toContain('2')
  })
})
