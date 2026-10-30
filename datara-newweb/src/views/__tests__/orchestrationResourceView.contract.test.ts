/**
 * §10.10 部署运维资源配置页契约（R1 Worker 分组 / R2 环境 / R3 Yarn 队列 / R4 集群）。
 *
 * 真源：docs/designs/2026-10-29-dbx-unified-target-design.md §10.10。
 * 断言面：
 *  - 取数只经 `orchestrationApi`（前端不直连海豚 API），手动刷新不轮询；
 *  - 写入门禁：队列/集群为全局资源配置（MANAGE_USER，admin-only），普通用户不出现新建按钮；
 *    行级写权以行 `canManage` 为准；
 *  - 海豚 CONFIG 来源的系统默认 worker 分组（systemDefault）只读；
 *  - 空态与错误态互斥，错误横幅透出编排网关字符串错误码；
 *  - 四条路由共用组件实例，kind 变化须重新取数。
 */
import { config, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import OrchestrationResourceView from '../depops/OrchestrationResourceView.vue'
import { authAccount } from '../../services/rebuild/authApi'
import type { ClusterRow, QueueRow, WorkerGroupRow } from '../../services/rebuild/orchestrationApi'

const api = vi.hoisted(() => ({
  listWorkerGroups: vi.fn(),
  createWorkerGroup: vi.fn(),
  updateWorkerGroup: vi.fn(),
  deleteWorkerGroup: vi.fn(),
  listEnvironments: vi.fn(),
  createEnvironment: vi.fn(),
  updateEnvironment: vi.fn(),
  deleteEnvironment: vi.fn(),
  listQueues: vi.fn(),
  createQueue: vi.fn(),
  updateQueue: vi.fn(),
  deleteQueue: vi.fn(),
  listClusters: vi.fn(),
  createCluster: vi.fn(),
  updateCluster: vi.fn(),
  deleteCluster: vi.fn(),
  share: vi.fn(),
  unshare: vi.fn(),
}))

// 部分 mock：权限矩阵/错误码常量走真实实现，仅替换端点对象
vi.mock('../../services/rebuild/orchestrationApi', async () => {
  const actual = await vi.importActual<typeof import('../../services/rebuild/orchestrationApi')>(
    '../../services/rebuild/orchestrationApi',
  )
  return { ...actual, orchestrationApi: api }
})

const ownedGroup: WorkerGroupRow = {
  resourceKey: 'default',
  ownerId: 1,
  canManage: true,
  id: 1,
  name: 'default',
  addrList: '192.168.1.9:1234',
  description: '自建分组',
  systemDefault: false,
  source: 'USER',
  createTime: null,
  updateTime: null,
}

const configGroup: WorkerGroupRow = {
  resourceKey: 'system',
  ownerId: null,
  canManage: false,
  id: null,
  name: 'system',
  addrList: null,
  description: null,
  systemDefault: true,
  source: 'CONFIG',
  createTime: null,
  updateTime: null,
}

const queueRow: QueueRow = {
  resourceKey: '11',
  ownerId: null,
  canManage: false,
  id: '11',
  queue: 'root.default',
  queueName: '默认队列',
  createTime: null,
  updateTime: null,
}

const clusterRow: ClusterRow = {
  resourceKey: 'CLUSTER-CODE-1',
  ownerId: null,
  canManage: true,
  id: 1,
  code: 'CLUSTER-CODE-1',
  name: 'prod-cluster',
  config: 'fs.defaultFS=hdfs://nn:8020',
  description: '生产集群',
  createTime: null,
  updateTime: null,
}

function setRole(role: 'admin' | 'developer' | 'operator' | 'viewer'): void {
  authAccount.value = { id: 1, username: role, role }
}

beforeEach(() => {
  config.global.stubs = { RouterLink: { template: '<a><slot /></a>' } }
  api.listWorkerGroups.mockResolvedValue([ownedGroup, configGroup])
  api.listEnvironments.mockResolvedValue([])
  api.listQueues.mockResolvedValue([queueRow])
  api.listClusters.mockResolvedValue([clusterRow])
})

afterEach(() => {
  vi.clearAllMocks()
  authAccount.value = null
})

describe('§10.10 资源配置页取数口径', () => {
  it('按 kind 走对应端点，一次装载不轮询', async () => {
    setRole('admin')
    const w = mount(OrchestrationResourceView, { props: { kind: 'queue' } })
    await flushPromises()
    expect(api.listQueues).toHaveBeenCalledTimes(1)
    expect(api.listWorkerGroups).not.toHaveBeenCalled()
    expect(w.find('[data-resource-list]').exists()).toBe(true)
    expect(w.find('[data-resource-key="11"]').exists()).toBe(true)
  })

  it('四条路由共用组件实例：kind 变化重新取数并清空过滤', async () => {
    setRole('admin')
    const w = mount(OrchestrationResourceView, { props: { kind: 'queue' } })
    await flushPromises()
    await w.setProps({ kind: 'cluster' })
    await flushPromises()
    expect(api.listClusters).toHaveBeenCalledTimes(1)
    expect(w.find('[data-resource-key="CLUSTER-CODE-1"]').exists()).toBe(true)
  })
})

describe('§10.10 写入门禁', () => {
  it('队列为全局资源配置：viewer 无新建按钮且行级写权只读', async () => {
    setRole('viewer')
    const w = mount(OrchestrationResourceView, { props: { kind: 'queue' } })
    await flushPromises()
    expect(w.find('[data-create]').exists()).toBe(false)
    const row = w.find('[data-resource-key="11"]')
    expect(row.attributes('data-can-manage')).toBe('false')
    expect(row.find('[data-writable]').text()).toBe('只读')
    expect(row.find('[data-edit]').attributes('disabled')).toBeDefined()
    expect(row.find('[data-delete]').attributes('disabled')).toBeDefined()
  })

  it('队列为全局资源配置：admin 可见新建按钮（MANAGE_USER）', async () => {
    setRole('admin')
    const w = mount(OrchestrationResourceView, { props: { kind: 'queue' } })
    await flushPromises()
    expect(w.find('[data-create]').exists()).toBe(true)
  })

  it('集群管理同属 admin-only 写门禁：developer 无新建按钮', async () => {
    setRole('developer')
    const w = mount(OrchestrationResourceView, { props: { kind: 'cluster' } })
    await flushPromises()
    expect(w.find('[data-create]').exists()).toBe(false)
  })

  it('worker 分组用 EDIT_DEFINITION：developer 可新建；海豚 CONFIG 默认分组只读', async () => {
    setRole('developer')
    const w = mount(OrchestrationResourceView, { props: { kind: 'worker_group' } })
    await flushPromises()
    expect(w.find('[data-create]').exists()).toBe(true)
    const system = w.find('[data-resource-key="system"]')
    expect(system.attributes('data-can-manage')).toBe('false')
    expect(system.find('[data-edit]').attributes('disabled')).toBeDefined()
    const owned = w.find('[data-resource-key="default"]')
    expect(owned.find('[data-edit]').attributes('disabled')).toBeUndefined()
  })
})

describe('§10.10 状态与错误面', () => {
  it('空列表呈现空态（非表格、非错误）', async () => {
    setRole('admin')
    const w = mount(OrchestrationResourceView, { props: { kind: 'environment' } })
    await flushPromises()
    expect(w.find('[data-empty]').exists()).toBe(true)
    expect(w.find('[data-resource-list]').exists()).toBe(false)
    expect(w.find('[data-error]').exists()).toBe(false)
  })

  it('加载失败透出编排网关字符串错误码，且不呈现空态', async () => {
    setRole('admin')
    api.listQueues.mockRejectedValueOnce(Object.assign(new Error('队列字段缺失'), { code: 'ORCH_QUEUE_FIELDS_REQUIRED' }))
    const w = mount(OrchestrationResourceView, { props: { kind: 'queue' } })
    await flushPromises()
    const alert = w.find('[data-error]')
    expect(alert.exists()).toBe(true)
    expect(alert.attributes('role')).toBe('alert')
    expect(alert.text()).toContain('ORCH_QUEUE_FIELDS_REQUIRED')
    expect(w.find('[data-empty]').exists()).toBe(false)
  })

  it('承载当前部署运维子导航（含 SSH 试运行与资源配置入口）', async () => {
    setRole('admin')
    const w = mount(OrchestrationResourceView, { props: { kind: 'queue' } })
    await flushPromises()
    expect(w.findAll('[data-sub-nav-item]').map((i) => i.attributes('data-sub-nav-item'))).toEqual([
      'monitor',
      'ssh',
      'worker-group',
      'environment',
      'queue',
      'cluster',
      'resource-file',
    ])
  })
})
