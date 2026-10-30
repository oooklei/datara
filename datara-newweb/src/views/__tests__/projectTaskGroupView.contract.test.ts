/**
 * §10.10 R8 任务组管理页契约（项目级资源，P0）。
 *
 * 真源：docs/designs/2026-10-29-dbx-unified-target-design.md §10.10 R8。
 * 断言面：
 *  - 取数只经 `orchestrationApi.listTaskGroups(projectId)`（前端不直连海豚 API），手动刷新不轮询；
 *  - 写入门禁 EDIT_DEFINITION：viewer/developer 不出现新建按钮；行级写权以行 `canManage` 为准；
 *  - 删除语义为海豚「关闭任务组」（无物理删除端点），按钮文案为「关闭」；
 *  - 海豚状态 1=运行中 / 0=已关闭如实映射，不虚构；
 *  - 空态与错误态互斥，错误横幅透出编排网关字符串错误码；
 *  - 共享经 orchestrationApi.share('task_group', ...)。
 */
import { config, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ProjectTaskGroupView from '../ProjectTaskGroupView.vue'
import { authAccount } from '../../services/rebuild/authApi'
import type { TaskGroupRow } from '../../services/rebuild/orchestrationApi'

const api = vi.hoisted(() => ({
  listTaskGroups: vi.fn(),
  createTaskGroup: vi.fn(),
  updateTaskGroup: vi.fn(),
  deleteTaskGroup: vi.fn(),
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

const row = (over: Partial<TaskGroupRow> = {}): TaskGroupRow => ({
  resourceKey: '3',
  ownerId: 1,
  canManage: true,
  id: 3,
  projectCode: '7062341',
  name: '串行清洗组',
  description: '同组节点按优先级串行',
  groupSize: 100,
  status: '1',
  createTime: '2026-10-30 09:00:00',
  updateTime: null,
  ...over,
})

const closedRow = row({ id: 4, resourceKey: '4', name: '已归档组', status: '0' })

function setRole(role: 'admin' | 'developer' | 'operator' | 'viewer'): void {
  authAccount.value = { id: 1, username: role, role }
}

beforeEach(() => {
  config.global.stubs = { RouterLink: { template: '<a><slot /></a>' } }
  api.listTaskGroups.mockResolvedValue([row(), closedRow])
})

afterEach(() => {
  vi.clearAllMocks()
  authAccount.value = null
  vi.unstubAllGlobals()
})

describe('§10.10 R8 任务组管理页取数口径', () => {
  it('按 projectId 取数，一次装载不轮询', async () => {
    setRole('admin')
    const w = mount(ProjectTaskGroupView, { props: { projectId: 7 } })
    await flushPromises()
    expect(api.listTaskGroups).toHaveBeenCalledWith(7)
    expect(api.listTaskGroups).toHaveBeenCalledTimes(1)
    expect(w.find('[data-task-group-list]').exists()).toBe(true)
    expect(w.find('[data-resource-key="3"]').exists()).toBe(true)
  })

  it('projectId 变化须重新取数并清空过滤', async () => {
    setRole('admin')
    const w = mount(ProjectTaskGroupView, { props: { projectId: 7 } })
    await flushPromises()
    await w.setProps({ projectId: 8 })
    await flushPromises()
    expect(api.listTaskGroups).toHaveBeenLastCalledWith(8)
    expect(api.listTaskGroups).toHaveBeenCalledTimes(2)
  })

  it('海豚状态如实映射：1=运行中 / 0=已关闭', async () => {
    setRole('admin')
    const w = mount(ProjectTaskGroupView, { props: { projectId: 7 } })
    await flushPromises()
    expect(w.find('[data-resource-key="3"] [data-col="status"]').text()).toBe('运行中')
    expect(w.find('[data-resource-key="4"] [data-col="status"]').text()).toBe('已关闭')
  })

  it('空态与错误态互斥；错误横幅透出字符串错误码', async () => {
    setRole('admin')
    api.listTaskGroups.mockResolvedValueOnce([])
    let w = mount(ProjectTaskGroupView, { props: { projectId: 7 } })
    await flushPromises()
    expect(w.find('[data-empty]').exists()).toBe(true)
    expect(w.find('[data-task-group-list]').exists()).toBe(false)

    api.listTaskGroups.mockRejectedValueOnce(Object.assign(new Error('task group denied'), { code: 1003 }))
    w = mount(ProjectTaskGroupView, { props: { projectId: 7 } })
    await flushPromises()
    expect(w.find('[data-error]').text()).toContain('code 1003')
    expect(w.find('[data-error]').text()).toContain('task group denied')
    expect(w.find('[data-empty]').exists()).toBe(false)
    expect(w.find('[data-task-group-list]').exists()).toBe(false)
  })
})

describe('§10.10 R8 写入门禁与 owner 隔离', () => {
  it('EDIT_DEFINITION 未授予时不出现新建按钮', async () => {
    setRole('operator')
    const w = mount(ProjectTaskGroupView, { props: { projectId: 7 } })
    await flushPromises()
    expect(w.find('[data-create]').exists()).toBe(false)
  })

  it('行级写权以 canManage 为准：只读行禁用编辑/关闭/共享', async () => {
    setRole('admin')
    api.listTaskGroups.mockResolvedValue([row({ canManage: false })])
    const w = mount(ProjectTaskGroupView, { props: { projectId: 7 } })
    await flushPromises()
    const tr = w.find('[data-resource-key="3"]')
    expect(tr.attributes('data-can-manage')).toBe('false')
    expect(tr.find('[data-edit]').attributes('disabled')).toBeDefined()
    expect(tr.find('[data-delete]').attributes('disabled')).toBeDefined()
    expect(tr.find('[data-share]').attributes('disabled')).toBeDefined()
    expect(tr.find('[data-writable]').text()).toBe('只读')
  })

  it('新建提交 projectId + 组大小，经 createTaskGroup 落库', async () => {
    setRole('admin')
    api.createTaskGroup.mockResolvedValue({})
    const w = mount(ProjectTaskGroupView, { props: { projectId: 7 } })
    await flushPromises()
    await w.find('[data-create]').trigger('click')
    await w.find('[data-name]').setValue('新串行组')
    await w.find('[data-group-size]').setValue(50)
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(api.createTaskGroup).toHaveBeenCalledWith(
      expect.objectContaining({ projectId: 7, name: '新串行组', groupSize: 50 }),
    )
  })

  it('关闭映射海豚 close-task-group（按钮文案「关闭」，非物理删除）', async () => {
    setRole('admin')
    api.deleteTaskGroup.mockResolvedValue({})
    vi.stubGlobal('confirm', () => true)
    const w = mount(ProjectTaskGroupView, { props: { projectId: 7 } })
    await flushPromises()
    expect(w.find('[data-resource-key="3"] [data-delete]').text()).toBe('关闭')
    await w.find('[data-resource-key="3"] [data-delete]').trigger('click')
    await flushPromises()
    expect(api.deleteTaskGroup).toHaveBeenCalledWith(3)
  })

  it('共享经 share(task_group) 且失败不关闭弹窗', async () => {
    setRole('admin')
    api.share.mockRejectedValue(Object.assign(new Error('share failed'), { code: 1003 }))
    const w = mount(ProjectTaskGroupView, { props: { projectId: 7 } })
    await flushPromises()
    await w.find('[data-resource-key="3"] [data-share]').trigger('click')
    await w.find('[data-share-username]').setValue('lisi')
    await w.find('form[aria-label="共享任务组"]').trigger('submit')
    await flushPromises()
    expect(api.share).toHaveBeenCalledWith('task_group', '3', 'lisi')
    expect(w.find('[data-share-error]').text()).toContain('share failed')
    expect(w.find('[data-share-username]').exists()).toBe(true)
  })
})

describe('§10.10 R8 列表搜索与口径声明', () => {
  it('D13 列表搜索：关键字前端过滤行，不触发后端', async () => {
    setRole('admin')
    const w = mount(ProjectTaskGroupView, { props: { projectId: 7 } })
    await flushPromises()
    expect(w.findAll('[data-resource-key]')).toHaveLength(2)
    await w.find('[data-filter-keyword]').setValue('归档')
    expect(w.findAll('[data-resource-key]').map((r) => r.attributes('data-resource-key'))).toEqual(['4'])
    expect(api.listTaskGroups).toHaveBeenCalledTimes(1)
    await w.find('[data-filter-keyword]').setValue('zzz')
    expect(w.find('[data-task-group-list]').text()).toContain('无匹配记录')
  })

  it('口径声明：删除映射关闭 + 无轮询', async () => {
    setRole('admin')
    const w = mount(ProjectTaskGroupView, { props: { projectId: 7 } })
    await flushPromises()
    expect(w.find('[data-scope-note]').text()).toContain('关闭任务组')
    expect(w.find('[data-scope-note]').text()).toContain('不做轮询')
  })
})
