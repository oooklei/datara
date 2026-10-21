/**
 * INC4-FE-7（WBS 4.5 / s269 派令）验收测试：trial 试运行面板（八能力 UI 承接）。
 *
 * 范式沿 S252（vi.hoisted + vi.mock）：store 桩（trialRun 行为已由 store 契约测试全量覆盖，
 * 本文件只测「UI 事件 → store 调用 → 状态渲染」映射）+ ElMessage 桩（JSON 解析失败提示）。
 *
 * 覆盖：
 *  1. mount 即 open(projectId, definitionId)；setProps 换定义 → open 再调 + JSON 文本重置；
 *  2. 无快照空态：提示文案 + 运行/转正式 disabled + 刷新输出入口不渲染；
 *  3. 快照信息渲染（snap id/digest/status）；
 *  4. running → 快照/运行/转正式 disabled + 运行按钮文案切换；
 *  5. 六选项表单在位（WF-15~WF-20 六 data-test 锚）；
 *  6. nodeCodes 逗号分隔解析（trim+滤空）→ store.options.nodeCodes；
 *  7. 合法 JSON run 链：testVariables/dependencyMock 落地 store.options + run 调用；
 *  8. 非法 JSON：warning 提示 + run 不调用；
 *  9. dryRun/sqlPrecheck checkbox 双向绑定 store.options；
 * 10. runResult 渲染（SUCCEEDED）；DRY_RUN：plan 渲染 + 刷新输出入口不渲染；
 * 11. 输出面渲染（stats/logs/variables）+ 刷新输出按钮 → refreshOutput 调用；
 * 12. promote：remark 带与不带（undefined）→ promote 参数对拍；promoteResult 渲染（含幂等文案）；
 * 13. lastError 错误条渲染。
 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { useTrialRunStore, msgWarning } = vi.hoisted(() => ({
  useTrialRunStore: vi.fn(),
  msgWarning: vi.fn(),
}))

vi.mock('../../stores/trialRun', () => ({ useTrialRunStore }))
vi.mock('element-plus', () => ({
  ElMessage: { warning: msgWarning, success: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

import TrialRunPanel from '../TrialRunPanel.vue'

/* ---- fixture（wire→camel 已由 trialApi/store 契约测试对拍，此处直用域形状） ---- */

const SNAPSHOT = {
  snapshotId: 501,
  definitionId: 42,
  snapshotDigest: 'dg-abc123',
  nodes: [],
  edges: [],
  status: 'ACTIVE',
  createdBy: 3,
  createdAt: '2026-10-21T10:00:00Z',
}

const RUN_OK = { instanceId: 9001, status: 'SUCCEEDED', taskCount: 2, tasks: [], plan: null }
const RUN_DRY = { instanceId: 0, status: 'DRY_RUN', taskCount: 0, tasks: [], plan: ['n1', 'n2'] }

const OUTPUT = {
  logs: [{ taskId: 11, taskCode: 'n1', logs: [{ attemptNo: 1, level: 'INFO', message: 'ok' }] }],
  variables: [
    { name: 'cnt', expression: '1', scope: 'node', resolvedValue: 1, valueType: 'int', source: 'literal', attemptNo: 1 },
  ],
  stats: { successCount: 1, failedCount: 0, skippedCount: 0 },
  found: true,
  instanceType: 'TRIAL',
  status: 'SUCCEEDED',
}

const PROMOTE = { version: 5, status: 'PUBLISHED', snapshotDigest: 'dg-abc123', idempotent: false }
const PROMOTE_IDEM = { version: 5, status: 'PUBLISHED', snapshotDigest: 'dg-abc123', idempotent: true }

/* ---- store 桩 ---- */

function makeStore(over: Record<string, unknown> = {}) {
  const base = {
    projectId: 7 as number | null,
    definitionId: 42 as number | null,
    snapshot: null as unknown,
    options: { nodeCodes: [] as string[], startNode: '', testVariables: {} as Record<string, unknown>, dependencyMock: {} as Record<string, unknown>, dryRun: false, sqlPrecheck: false },
    runResult: null as unknown,
    output: null as unknown,
    promoteResult: null as unknown,
    running: false,
    lastError: null as string | null,
    open: vi.fn(),
    createSnapshot: vi.fn(async () => null),
    run: vi.fn(async () => null),
    refreshOutput: vi.fn(async () => null),
    promote: vi.fn(async () => null),
  }
  return Object.assign(base, over)
}

let store: ReturnType<typeof makeStore>

beforeEach(() => {
  store = makeStore()
  useTrialRunStore.mockReset()
  useTrialRunStore.mockImplementation(() => store)
  msgWarning.mockClear()
})

function mountPanel(props: { projectId?: number; definitionId?: number } = {}) {
  return mount(TrialRunPanel, {
    props: { projectId: props.projectId ?? 7, definitionId: props.definitionId ?? 42 },
  })
}

function textOf(w: ReturnType<typeof mount>, sel: string): string {
  return w.find(sel).text()
}

describe('INC4-FE-7 TrialRunPanel 八能力 UI 承接', () => {
  it('mount 即 open(7,42)；setProps 换定义 → open 再调且 JSON 文本/备注重置', async () => {
    const w = mountPanel()
    expect(store.open).toHaveBeenCalledTimes(1)
    expect(store.open).toHaveBeenCalledWith(7, 42)

    await w.find('[data-test="test-vars"]').setValue('{"a":1}')
    await w.find('[data-test="dep-mock"]').setValue('{"d":"FAILED"}')
    await w.find('[data-test="remark"]').setValue('待清备注')
    await w.setProps({ definitionId: 43 })
    expect(store.open).toHaveBeenLastCalledWith(7, 43)
    expect((w.find('[data-test="test-vars"]').element as HTMLTextAreaElement).value).toBe('{}')
    expect((w.find('[data-test="dep-mock"]').element as HTMLTextAreaElement).value).toBe('{}')
    expect((w.find('[data-test="remark"]').element as HTMLInputElement).value).toBe('')
  })

  it('无快照空态：提示 + 运行/转正式 disabled + 刷新输出入口不渲染', () => {
    const w = mountPanel()
    expect(textOf(w, '[data-test="no-snap"]')).toContain('尚未生成快照')
    expect(w.find('[data-test="run-btn"]').attributes('disabled')).toBeDefined()
    expect(w.find('[data-test="promote-btn"]').attributes('disabled')).toBeDefined()
    expect(w.find('[data-test="refresh-btn"]').exists()).toBe(false)
    expect(textOf(w, '[data-test="no-result"]')).toContain('尚未运行')
  })

  it('快照信息渲染（snap id / digest / status）；点击快照按钮 → createSnapshot', async () => {
    const w = mountPanel()
    expect(w.find('[data-test="snap-info"]').exists()).toBe(false)
    await w.find('[data-test="snapshot-btn"]').trigger('click')
    expect(store.createSnapshot).toHaveBeenCalledTimes(1)

    store.snapshot = SNAPSHOT
    const w2 = mountPanel()
    const info = textOf(w2, '[data-test="snap-info"]')
    expect(info).toContain('snap=501')
    expect(info).toContain('dg-abc123')
    expect(info).toContain('ACTIVE')
  })

  it('running 态：快照/运行/转正式 disabled，运行按钮文案「运行中…」', () => {
    store.snapshot = SNAPSHOT
    store.running = true
    const w = mountPanel()
    expect(w.find('[data-test="snapshot-btn"]').attributes('disabled')).toBeDefined()
    expect(w.find('[data-test="run-btn"]').attributes('disabled')).toBeDefined()
    expect(w.find('[data-test="run-btn"]').text()).toContain('运行中')
    expect(w.find('[data-test="promote-btn"]').attributes('disabled')).toBeDefined()
  })

  it('六选项表单在位（WF-15~WF-20 六锚点）', () => {
    const w = mountPanel()
    for (const sel of ['nodecodes', 'start-node', 'test-vars', 'dep-mock', 'dry-run', 'sql-precheck']) {
      expect(w.find(`[data-test="${sel}"]`).exists()).toBe(true)
    }
  })

  it('nodeCodes 逗号分隔解析：trim + 滤空（空串 = 不限）', async () => {
    const w = mountPanel()
    await w.find('[data-test="nodecodes"]').setValue('a, b ,,c')
    expect(store.options.nodeCodes).toEqual(['a', 'b', 'c'])
    await w.find('[data-test="nodecodes"]').setValue('')
    expect(store.options.nodeCodes).toEqual([])
  })

  it('合法 JSON run 链：testVariables/dependencyMock 落地 options + run 调用', async () => {
    const w = mountPanel()
    store.snapshot = SNAPSHOT
    await flushPromises()
    await w.find('[data-test="test-vars"]').setValue('{"k":1}')
    await w.find('[data-test="dep-mock"]').setValue('{"d1":"SUCCEEDED"}')
    await w.find('[data-test="run-btn"]').trigger('click')
    await flushPromises()
    expect(store.options.testVariables).toEqual({ k: 1 })
    expect(store.options.dependencyMock).toEqual({ d1: 'SUCCEEDED' })
    expect(store.run).toHaveBeenCalledTimes(1)
  })

  it('非法 JSON：warning 提示且 run 不调用（testVariables 先挡）', async () => {
    const w = mountPanel()
    store.snapshot = SNAPSHOT
    await flushPromises()
    await w.find('[data-test="test-vars"]').setValue('not-json')
    await w.find('[data-test="run-btn"]').trigger('click')
    await flushPromises()
    expect(msgWarning).toHaveBeenCalledTimes(1)
    expect(msgWarning.mock.calls[0][0]).toContain('测试变量')
    expect(store.run).not.toHaveBeenCalled()

    // 依赖模拟非法同样拦截
    await w.find('[data-test="test-vars"]').setValue('{}')
    await w.find('[data-test="dep-mock"]').setValue('[1]')
    await w.find('[data-test="run-btn"]').trigger('click')
    await flushPromises()
    expect(msgWarning).toHaveBeenCalledTimes(2)
    expect(msgWarning.mock.calls[1][0]).toContain('依赖模拟')
    expect(store.run).not.toHaveBeenCalled()
  })

  it('dryRun/sqlPrecheck checkbox 双向绑定 store.options', async () => {
    const w = mountPanel()
    await w.find('[data-test="dry-run"]').setValue(true)
    await w.find('[data-test="sql-precheck"]').setValue(true)
    expect(store.options.dryRun).toBe(true)
    expect(store.options.sqlPrecheck).toBe(true)
  })

  it('runResult 渲染（SUCCEEDED）；DRY_RUN：plan 渲染 + 刷新输出入口不渲染', () => {
    store.snapshot = SNAPSHOT
    store.runResult = RUN_OK
    const w = mountPanel()
    const info = textOf(w, '[data-test="run-info"]')
    expect(info).toContain('instance_id=9001')
    expect(info).toContain('SUCCEEDED')
    expect(info).toContain('任务 2')
    expect(w.find('[data-test="plan-list"]').exists()).toBe(false)
    expect(w.find('[data-test="refresh-btn"]').exists()).toBe(true)
    expect(w.find('[data-test="no-output"]').exists()).toBe(true)

    store.runResult = RUN_DRY
    const w2 = mountPanel()
    expect(textOf(w2, '[data-test="plan-list"]')).toContain('n1 → n2')
    expect(w2.find('[data-test="refresh-btn"]').exists()).toBe(false)
    expect(w2.find('[data-test="no-output"]').exists()).toBe(false)
  })

  it('输出面渲染（stats/logs/variables）+ 刷新输出按钮 → refreshOutput 调用', async () => {
    store.snapshot = SNAPSHOT
    store.runResult = RUN_OK
    const w = mountPanel()
    expect(w.find('[data-test="out-panel"]').exists()).toBe(false)
    await w.find('[data-test="refresh-btn"]').trigger('click')
    expect(store.refreshOutput).toHaveBeenCalledTimes(1)

    store.output = OUTPUT
    const w2 = mountPanel()
    expect(textOf(w2, '[data-test="out-stats"]')).toContain('成功 1')
    expect(textOf(w2, '[data-test="out-logs"]')).toContain('n1')
    expect(textOf(w2, '[data-test="out-vars"]')).toContain('cnt = 1')
  })

  it('promote：remark 带/不带参数对拍（空 → undefined）；promoteResult 渲染含幂等文案', async () => {
    store.snapshot = SNAPSHOT
    store.runResult = RUN_OK
    const w = mountPanel()
    await w.find('[data-test="remark"]').setValue('首次发布')
    await w.find('[data-test="promote-btn"]').trigger('click')
    await flushPromises()
    expect(store.promote).toHaveBeenLastCalledWith('首次发布')

    await w.find('[data-test="remark"]').setValue('   ')
    await w.find('[data-test="promote-btn"]').trigger('click')
    await flushPromises()
    expect(store.promote).toHaveBeenLastCalledWith(undefined)

    store.promoteResult = PROMOTE
    const w2 = mountPanel()
    expect(textOf(w2, '[data-test="promote-info"]')).toContain('version=5')

    store.promoteResult = PROMOTE_IDEM
    const w3 = mountPanel()
    expect(textOf(w3, '[data-test="promote-info"]')).toContain('幂等命中')
  })

  it('lastError 错误条渲染', () => {
    store.lastError = 'WF_TRIAL_INVALID: snapshot stale'
    const w = mountPanel()
    expect(textOf(w, '[data-test="err-bar"]')).toContain('WF_TRIAL_INVALID')
  })
})
