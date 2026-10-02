// @vitest-environment happy-dom
/**
 * E1 实例详情 SSE 接线用例（InstanceRunsView）：
 * - 运行中实例打开详情 → 订阅 streamInstanceEvents；终态实例不订阅；
 * - task_state_changed → 单节点 patch：run.nodeStatus 染色 + 任务表行状态/attempt 更新；
 * - instance_finished → 关流 + 终态一次性全量刷新（getInstanceDetail 再调一次）；
 * - onerror → 关流降级 3s 轮询（fake timers 推进断言）。
 * services / datasourceApi / element-plus 模块 mock；el-drawer 以渲染 slot 的桩替身（无 teleport）。
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent } from 'vue'

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(() => Promise.resolve()) },
}))

const pushSpy = vi.hoisted(() => vi.fn())
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: pushSpy }),
  useRoute: () => ({ params: {}, query: {} }),
}))

const listDefSpy = vi.hoisted(() => vi.fn())
const listPageSpy = vi.hoisted(() => vi.fn())
const getDetailSpy = vi.hoisted(() => vi.fn())
const graphGetSpy = vi.hoisted(() => vi.fn())
const streamSpy = vi.hoisted(() => vi.fn())
vi.mock('../../../services', () => ({
  listDefinitions: listDefSpy,
  listInstancesPage: listPageSpy,
  getInstanceDetail: getDetailSpy,
  stopInstance: vi.fn(),
  rerunInstance: vi.fn(),
  rerunFailedTasks: vi.fn(),
  getTaskLog: vi.fn(),
  graphService: { get: graphGetSpy },
  deleteInstanceLogs: vi.fn(),
  deleteInstanceLogsBatch: vi.fn(),
  streamInstanceEvents: streamSpy,
  // stores/auth 经 services 取模式开关（缺失会在渲染期抛错 → DOM 停在加载占位行）
  isMock: false,
  apiMode: 'api',
}))
vi.mock('../../../services/datasourceApi', () => ({ listTmpData: vi.fn() }))

import InstanceRunsView from '../InstanceRunsView.vue'
import { useRunStore } from '../../../stores/run'

/** el-drawer 桩：modelValue=true 时内联渲染 slot（绕开 EP teleport，断言 DOM 可达） */
const ElDrawerStub = defineComponent({
  name: 'ElDrawer',
  props: { modelValue: { type: Boolean, default: false } },
  template: '<div v-if="modelValue" class="el-drawer-stub"><slot /></div>',
})

const DOC = {
  id: 'doc1', name: '用例流', version: 1, meta: { profile: 'dag' }, edges: [],
  nodes: [{ id: 'n1', type: 'sql', position: { x: 0, y: 0 }, data: { name: '节点A' } }],
}

const LIST_ROW = { id: 1, instanceId: 'i-run-1', wfCode: 1, state: 'running', runMode: 'manual' }

function detailOf(state: string, taskState: string, attempt = 1) {
  return {
    ...LIST_ROW, state,
    taskInstances: [{
      id: 11, instanceId: 'i-run-1', nodeId: 'n1', nodeType: 'sql', name: '节点A',
      state: taskState, attempt, loopIter: 0,
      startTime: '2026-09-27 10:00:00', endTime: null,
    }],
  }
}

let handlers: {
  onOpen?: () => void
  onTaskChanged?: (e: Record<string, unknown>) => void
  onFinished?: (e: Record<string, unknown>) => void
  onError?: () => void
} | null = null
const fakeEs = { close: vi.fn() }

beforeEach(() => {
  vi.clearAllMocks()
  setActivePinia(createPinia())
  handlers = null
  fakeEs.close.mockClear()
  streamSpy.mockImplementation((_id: string, h: typeof handlers) => {
    handlers = h
    return fakeEs
  })
  listDefSpy.mockResolvedValue([{ id: 'def-5', name: '工作流W', code: 1 }])
  listPageSpy.mockResolvedValue({ list: [LIST_ROW], total: 1 })
  getDetailSpy.mockResolvedValue(detailOf('running', 'running'))
  graphGetSpy.mockResolvedValue(DOC)
})
afterEach(() => { vi.useRealTimers() })

/** 微任务冲刷（不用 flushPromises 的 setTimeout，兼容 fake timers） */
async function tick() {
  for (let i = 0; i < 10; i++) await Promise.resolve()
}

async function mountAndOpenDetail() {
  const wrapper = mount(InstanceRunsView, {
    global: { stubs: { ElDrawer: ElDrawerStub, GraphWorkbench: true } },
  })
  await tick()
  const row = wrapper.findAll('tbody tr')[0]!
  await row.findAll('button').find((b) => b.text() === '详情')!.trigger('click')
  await tick()
  return wrapper
}

describe('InstanceRunsView 实例状态流（E1）', () => {
  it('运行中实例打开详情 → 订阅流；终态实例不订阅', async () => {
    await mountAndOpenDetail()
    expect(streamSpy).toHaveBeenCalledTimes(1)
    expect(streamSpy.mock.calls[0][0]).toBe('i-run-1')

    streamSpy.mockClear()
    getDetailSpy.mockResolvedValue(detailOf('success', 'success'))
    listPageSpy.mockResolvedValue({ list: [{ ...LIST_ROW, state: 'success' }], total: 1 })
    const wrapper2 = mount(InstanceRunsView, {
      global: { stubs: { ElDrawer: ElDrawerStub, GraphWorkbench: true } },
    })
    await tick()
    const row2 = wrapper2.findAll('tbody tr')[0]!
    await row2.findAll('button').find((b) => b.text() === '详情')!.trigger('click')
    await tick()
    expect(streamSpy).not.toHaveBeenCalled()
  })

  it('task_state_changed → 单节点 patch：nodeStatus 染色 + 任务表行更新（不触发全量刷新）', async () => {
    const run = useRunStore()
    const wrapper = await mountAndOpenDetail()
    expect(getDetailSpy).toHaveBeenCalledTimes(1)
    handlers!.onTaskChanged!({ taskId: 11, nodeId: 'n1', state: 'success', attempt: 3, loopIter: 0, startTime: '2026-09-27 10:00:01', endTime: '2026-09-27 10:00:05' })
    await tick()
    expect(run.nodeStatus['n1']).toBe('success') // DAG 染色源
    expect(getDetailSpy).toHaveBeenCalledTimes(1) // 未触发 loadDetail 全量刷新
    // 任务表行 pill 已更新为「成功」/ #3
    const sideText = wrapper.find('.el-drawer-stub .dt-side').text()
    expect(sideText).toContain('成功')
    expect(sideText).toContain('#3')
  })

  it('instance_finished → 关流 + 终态一次性全量刷新；未知任务行（循环扩行）触发一次 loadDetail', async () => {
    await mountAndOpenDetail()
    handlers!.onFinished!({ instanceId: 'i-run-1', state: 'success', endTime: '2026-09-27 10:01:00' })
    await tick()
    expect(fakeEs.close).toHaveBeenCalled()
    expect(getDetailSpy).toHaveBeenCalledTimes(2) // 打开 1 次 + 终态收口 1 次

    // 循环扩行：未知 taskId → 全量补一次
    await mountAndOpenDetail()
    getDetailSpy.mockClear()
    handlers!.onTaskChanged!({ taskId: 99, nodeId: 'n1', state: 'running', attempt: 1, loopIter: 2 })
    await tick()
    expect(getDetailSpy).toHaveBeenCalledTimes(1)
  })

  it('onerror → 关流并降级 3s 轮询（fake timers 推进断言）', async () => {
    await mountAndOpenDetail()
    vi.useFakeTimers()
    handlers!.onError!()
    expect(fakeEs.close).toHaveBeenCalled()
    expect(getDetailSpy).toHaveBeenCalledTimes(1)
    vi.advanceTimersByTime(3000)
    await tick()
    expect(getDetailSpy).toHaveBeenCalledTimes(2) // 3s 轮询触发一次 loadDetail
    vi.advanceTimersByTime(3000)
    await tick()
    expect(getDetailSpy).toHaveBeenCalledTimes(3)
  })
})
