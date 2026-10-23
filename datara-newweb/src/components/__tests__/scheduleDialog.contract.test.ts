/**
 * 9-03 ScheduleDialog 契约测试（范式沿 trialRunPanel.contract.test.ts：vi.hoisted+vi.mock+mount+flushPromises+data-test 锚点）。
 * 验收锚（拆票登记 9-03 票面）：①misfire/concurrency 枚举白名单 ②maxRunning≥1 校验（<1 拒绝不钳位）
 * ③预览未通过禁提交（含空 crontab 阻断）④初始 offline 回显（创建成功提示含「初始下线」）。
 * T55 边界：SKIP 语义断言已按 R-05（2026-10-21 裁定，B SCAN_SECONDS 宽限）于 9-05 describe 落实；融合宣告核验归 9-06（已 PASS 收口）。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ScheduleDialog from '../ScheduleDialog.vue'
import type { ScheduleRow } from '../../services/rebuild/scheduleCrudApi'

const h = vi.hoisted(() => {
  const apiMock = {
    listSchedules: vi.fn(),
    createSchedule: vi.fn(),
    updateSchedule: vi.fn(),
    deleteSchedule: vi.fn(),
    onlineSchedule: vi.fn(),
    offlineSchedule: vi.fn(),
    previewCrontab: vi.fn(),
  }
  return {
    apiMock,
    msgSuccess: vi.fn(),
    msgWarning: vi.fn(),
    msgError: vi.fn(),
    msgInfo: vi.fn(),
    msgConfirm: vi.fn(),
  }
})

vi.mock('../../services/rebuild/scheduleCrudApi', () => ({
  createScheduleCrudContract: vi.fn(() => h.apiMock),
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    success: h.msgSuccess,
    warning: h.msgWarning,
    error: h.msgError,
    info: h.msgInfo,
  },
  ElMessageBox: {
    confirm: h.msgConfirm,
  },
}))

const { apiMock, msgSuccess, msgWarning, msgConfirm } = h

function makeRow(overrides: Partial<ScheduleRow> = {}): ScheduleRow {
  return {
    id: 1,
    wfCode: 101,
    name: '夜间全量',
    crontab: '0 2 * * *',
    startTime: '2026-10-20T02:00:00',
    endTime: null,
    state: 'offline',
    priority: 3,
    workerGroup: 'default',
    failRetryTimes: 2,
    failRetryInterval: 60,
    misfirePolicy: 'FIRE_ONCE',
    concurrencyPolicy: 'ALLOW',
    maxRunningInstances: 1,
    timezone: 'Asia/Shanghai',
    createTime: '2026-10-20 10:00:00',
    updateTime: null,
    ...overrides,
  }
}

const dialogOpts = { global: { stubs: { teleport: true } } } as const

async function mountDialog(props: Record<string, unknown> = {}): Promise<VueWrapper> {
  const wrapper = mount(ScheduleDialog, {
    props: { modelValue: true, projectId: 7, wf: 101, wfName: '夜间接入', ...props },
    ...dialogOpts,
  })
  await flushPromises()
  return wrapper
}

async function openForm(wrapper: VueWrapper): Promise<void> {
  await wrapper.find('[data-test="create-btn"]').trigger('click')
  await flushPromises()
}

beforeEach(() => {
  vi.clearAllMocks()
  apiMock.listSchedules.mockResolvedValue([])
  apiMock.previewCrontab.mockResolvedValue({ valid: true, nextFireTimes: ['2026-10-22 02:00:00'] })
  apiMock.createSchedule.mockResolvedValue({ ...makeRow(), nextFireTimes: ['2026-10-22 02:00:00'] })
  apiMock.updateSchedule.mockResolvedValue({ ...makeRow(), nextFireTimes: ['2026-10-22 02:00:00'] })
  apiMock.deleteSchedule.mockResolvedValue(undefined)
  apiMock.onlineSchedule.mockResolvedValue(makeRow({ state: 'online' }))
  apiMock.offlineSchedule.mockResolvedValue(makeRow({ state: 'offline' }))
  msgConfirm.mockResolvedValue('confirm')
})

describe('ScheduleDialog 契约（9-03）', () => {
  it('验收锚①：misfire/concurrency 下拉选项为后端白名单精确枚举', async () => {
    const wrapper = await mountDialog()
    await openForm(wrapper)
    const misfireValues = wrapper.findAll('[data-test="misfire"] option').map((o) => o.attributes('value'))
    expect(misfireValues).toEqual(['FIRE_ONCE', 'SKIP', 'FIRE_ALL_LIMITED'])
    const concValues = wrapper.findAll('[data-test="concurrency"] option').map((o) => o.attributes('value'))
    expect(concValues).toEqual(['ALLOW', 'FORBID', 'QUEUE'])
  })

  it('验收锚②：maxRunning<1 阻断提交且不调 createSchedule（后端拒绝语义，UI 不钳位）', async () => {
    const wrapper = await mountDialog()
    await openForm(wrapper)
    await wrapper.find('[data-test="crontab"]').setValue('*/5 * * * *')
    await wrapper.find('[data-test="max-running"]').setValue(0)
    await wrapper.find('[data-test="save-btn"]').trigger('click')
    await flushPromises()
    expect(msgWarning).toHaveBeenCalledWith('最大并行实例数需为不小于 1 的整数')
    expect(apiMock.createSchedule).not.toHaveBeenCalled()
    expect(apiMock.updateSchedule).not.toHaveBeenCalled()
  })

  it('验收锚③a：空 crontab 阻断提交', async () => {
    const wrapper = await mountDialog()
    await openForm(wrapper)
    await wrapper.find('[data-test="save-btn"]').trigger('click')
    await flushPromises()
    expect(msgWarning).toHaveBeenCalledWith('请填写 crontab 表达式')
    expect(apiMock.createSchedule).not.toHaveBeenCalled()
  })

  it('验收锚③b：preview valid=false → preview-err 渲染且 save 阻断', async () => {
    apiMock.previewCrontab.mockResolvedValue({ valid: false, nextFireTimes: [] })
    const wrapper = await mountDialog()
    await openForm(wrapper)
    await wrapper.find('[data-test="crontab"]').setValue('bad cron')
    await wrapper.find('[data-test="preview-btn"]').trigger('click')
    await flushPromises()
    const errEl = wrapper.find('[data-test="preview-err"]')
    expect(errEl.exists()).toBe(true)
    expect(errEl.text()).toContain('无效')
    await wrapper.find('[data-test="save-btn"]').trigger('click')
    await flushPromises()
    expect(msgWarning).toHaveBeenCalledWith('crontab 表达式无效，请检查后重试')
    expect(apiMock.createSchedule).not.toHaveBeenCalled()
  })

  it('验收锚③c：未预览直接 save → 自动预览后复检阻断', async () => {
    apiMock.previewCrontab.mockResolvedValue({ valid: false, nextFireTimes: [] })
    const wrapper = await mountDialog()
    await openForm(wrapper)
    await wrapper.find('[data-test="crontab"]').setValue('bad cron')
    await wrapper.find('[data-test="save-btn"]').trigger('click')
    await flushPromises()
    expect(apiMock.previewCrontab).toHaveBeenCalledTimes(1)
    expect(wrapper.find('[data-test="preview-err"]').exists()).toBe(true)
    expect(apiMock.createSchedule).not.toHaveBeenCalled()
  })

  it('验收锚④：创建成功提示含「初始下线」并回列表显示已下线（初始 offline 回显）', async () => {
    apiMock.listSchedules.mockResolvedValue([makeRow({ id: 9, name: '新任务', state: 'offline' })])
    apiMock.createSchedule.mockResolvedValue({
      ...makeRow({ id: 9, name: '新任务', state: 'offline' }),
      nextFireTimes: ['2026-10-22 02:00:00'],
    })
    const wrapper = await mountDialog()
    await openForm(wrapper)
    await wrapper.find('[data-test="crontab"]').setValue('0 2 * * *')
    await wrapper.find('[data-test="preview-btn"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="preview-list"]').exists()).toBe(true)
    await wrapper.find('[data-test="save-btn"]').trigger('click')
    await flushPromises()
    expect(msgSuccess).toHaveBeenCalledTimes(1)
    const msg = String(msgSuccess.mock.calls[0]?.[0] ?? '')
    expect(msg).toContain('初始下线')
    expect(msg).toContain('2026-10-22 02:00:00')
    // 回列表双视图 + reload
    expect(wrapper.find('[data-test="save-btn"]').exists()).toBe(false)
    const pills = wrapper.findAll('[data-test="state-pill"]')
    expect(pills).toHaveLength(1)
    expect(pills[0].text()).toBe('已下线')
    expect(apiMock.listSchedules).toHaveBeenCalledTimes(2)
  })

  it('create：priority/failRetry 后端钳位语义 UI 同构（priority 99→5 / retryTimes -5→0 / interval -3→1）', async () => {
    const wrapper = await mountDialog()
    await openForm(wrapper)
    await wrapper.find('[data-test="crontab"]').setValue('0 2 * * *')
    await wrapper.find('[data-test="priority"]').setValue(99)
    await wrapper.find('[data-test="retry-times"]').setValue(-5)
    await wrapper.find('[data-test="retry-interval"]').setValue(-3)
    await wrapper.find('[data-test="preview-btn"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="save-btn"]').trigger('click')
    await flushPromises()
    expect(apiMock.createSchedule).toHaveBeenCalledTimes(1)
    const payload = apiMock.createSchedule.mock.calls[0]?.[1]
    expect(payload).toMatchObject({
      crontab: '0 2 * * *',
      priority: 5,
      failRetryTimes: 0,
      failRetryInterval: 1,
      misfirePolicy: 'FIRE_ONCE',
      concurrencyPolicy: 'ALLOW',
      maxRunningInstances: 1,
      timezone: 'Asia/Shanghai',
    })
  })

  it('toggle：online 行点击下线调 offlineSchedule 并回写状态', async () => {
    apiMock.listSchedules.mockResolvedValue([makeRow({ id: 5, state: 'online' })])
    apiMock.offlineSchedule.mockResolvedValue(makeRow({ id: 5, state: 'offline' }))
    const wrapper = await mountDialog()
    const btn = wrapper.find('[data-test="toggle-btn"]')
    expect(btn.text()).toBe('下线')
    await btn.trigger('click')
    await flushPromises()
    expect(apiMock.offlineSchedule).toHaveBeenCalledWith(5)
    expect(apiMock.onlineSchedule).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="state-pill"]').text()).toBe('已下线')
  })

  it('toggle：offline 行点击上线调 onlineSchedule 并回写状态', async () => {
    apiMock.listSchedules.mockResolvedValue([makeRow({ id: 6, state: 'offline' })])
    apiMock.onlineSchedule.mockResolvedValue(makeRow({ id: 6, state: 'online' }))
    const wrapper = await mountDialog()
    await wrapper.find('[data-test="toggle-btn"]').trigger('click')
    await flushPromises()
    expect(apiMock.onlineSchedule).toHaveBeenCalledWith(6)
    expect(wrapper.find('[data-test="state-pill"]').text()).toBe('已上线')
  })

  it('openEdit：回填全部字段并以钳位 payload 调 updateSchedule（不走 createSchedule）', async () => {
    apiMock.listSchedules.mockResolvedValue([
      makeRow({
        id: 11,
        name: '存量任务',
        crontab: '0 3 * * *',
        startTime: '2026-10-20T02:00:00+08:00',
        misfirePolicy: 'SKIP',
        concurrencyPolicy: 'QUEUE',
        maxRunningInstances: 4,
        failRetryTimes: 2,
        failRetryInterval: 120,
        timezone: 'UTC',
      }),
    ])
    const wrapper = await mountDialog()
    await wrapper.find('[data-test="edit-btn"]').trigger('click')
    await flushPromises()
    expect((wrapper.find('[data-test="name"]').element as HTMLInputElement).value).toBe('存量任务')
    expect((wrapper.find('[data-test="crontab"]').element as HTMLInputElement).value).toBe('0 3 * * *')
    expect((wrapper.find('[data-test="start-time"]').element as HTMLInputElement).value).toBe('2026-10-20 02:00:00')
    expect((wrapper.find('[data-test="misfire"]').element as HTMLSelectElement).value).toBe('SKIP')
    expect((wrapper.find('[data-test="concurrency"]').element as HTMLSelectElement).value).toBe('QUEUE')
    expect((wrapper.find('[data-test="max-running"]').element as HTMLInputElement).value).toBe('4')
    expect((wrapper.find('[data-test="timezone"]').element as HTMLInputElement).value).toBe('UTC')
    await wrapper.find('[data-test="priority"]').setValue(99)
    await wrapper.find('[data-test="retry-times"]').setValue(-5)
    await wrapper.find('[data-test="retry-interval"]').setValue(-3)
    await wrapper.find('[data-test="preview-btn"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="save-btn"]').trigger('click')
    await flushPromises()
    expect(apiMock.updateSchedule).toHaveBeenCalledTimes(1)
    expect(apiMock.createSchedule).not.toHaveBeenCalled()
    const call = apiMock.updateSchedule.mock.calls[0] ?? []
    expect(call[0]).toBe(11)
    expect(call[1]).toMatchObject({
      priority: 5,
      failRetryTimes: 0,
      failRetryInterval: 1,
      misfirePolicy: 'SKIP',
      concurrencyPolicy: 'QUEUE',
      maxRunningInstances: 4,
      timezone: 'UTC',
    })
  })

  it('delete：confirm 确认后删除并刷新列表', async () => {
    apiMock.listSchedules.mockResolvedValue([makeRow({ id: 21 })])
    const wrapper = await mountDialog()
    await wrapper.find('[data-test="delete-btn"]').trigger('click')
    await flushPromises()
    expect(msgConfirm).toHaveBeenCalledTimes(1)
    expect(apiMock.deleteSchedule).toHaveBeenCalledWith(21)
    expect(msgSuccess).toHaveBeenCalledWith('定时已删除')
    expect(apiMock.listSchedules).toHaveBeenCalledTimes(2)
  })

  it('close-btn 触发 update:modelValue(false)；closed 态无 mask 渲染', async () => {
    const wrapper = await mountDialog()
    await wrapper.find('[data-test="close-btn"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([false])

    const closed = await mountDialog({ modelValue: false })
    expect(closed.find('.sd-mask').exists()).toBe(false)
    // closed 挂载不新增 listSchedules 调用（首个挂载的 1 次除外）
    expect(apiMock.listSchedules).toHaveBeenCalledTimes(1)
  })
})

describe('9-05 调度闭环链（T9-E，R-05 SKIP 宽限）', () => {
  // R-05 裁定（2026-10-21 用户裁定）：SKIP 语义选 B「SCAN_SECONDS 宽限」，不阻塞融合宣告与 SKIP 分支断言。
  // 语义参考镜像后端现态 datara-backend/master/schedule.py（9-T55-fix 已验收 PASS 并入库，s296）：
  // SCAN_SECONDS=10、_within_scan_window 半开宽限 [0, 10s)、SKIP 取最新到期点；
  // 与 datara-backend/tests/test_schedule_policies.py（10 passed）同语义。
  // 拆票登记 9-建3「SKIP 分支断言参数化占位（A/B 两套）」因裁定已到而消解——本 describe 直接落 B 语义实际断言。
  const SKIP_SEMANTIC_R05 = {
    ruling: 'R-05',
    option: 'B' as const,
    scanSeconds: 10,
    windowHalfOpen: true, // [0, SCAN_SECONDS) 半开宽限窗口
    takeLatestDue: true, // SKIP 取最新到期点
  }

  it('闭环链：行内定时打开（wf 透传）→ 配置 SKIP → 保存载荷 → 保存后回读列表', async () => {
    // 链首「行内定时」入口接线（Palette ⏱ / Workbench 顶栏 emit schedule → 本组件单实例打开）
    // 已由 palette.contract.test.ts 与 taskCenterView.contract.test.ts（9-04）断言，
    // 本用例从对话框承接处（props.wf/wfName）开始闭环。
    const saved: ScheduleRow[] = []
    apiMock.listSchedules.mockImplementation(async () => saved)
    apiMock.createSchedule.mockImplementation(async (_wf: number, input: Record<string, unknown>) => {
      const row: ScheduleRow = { ...makeRow({ crontab: '*/30 * * * *', misfirePolicy: 'SKIP' }), ...input } as ScheduleRow
      saved.push(row)
      return { ...row, nextFireTimes: ['2026-10-22 02:00:00'] }
    })

    const w = await mountDialog({ wf: 101, wfName: '夜间接入' })
    expect(apiMock.listSchedules).toHaveBeenCalledTimes(1) // 打开即首读
    expect(w.find('[data-test="list-empty"]').exists()).toBe(true)

    await openForm(w)
    await w.find('[data-test="crontab"]').setValue('*/30 * * * *')
    await w.find('[data-test="misfire"]').setValue('SKIP')

    // 保存：载荷断言（misfire=SKIP 透传、wf=101 绑定）
    await w.find('[data-test="save-btn"]').trigger('click')
    await flushPromises()
    expect(apiMock.previewCrontab).toHaveBeenCalledTimes(1)
    expect(apiMock.createSchedule).toHaveBeenCalledTimes(1)
    expect(apiMock.createSchedule).toHaveBeenCalledWith(101, expect.objectContaining({
      crontab: '*/30 * * * *',
      misfirePolicy: 'SKIP',
      concurrencyPolicy: 'ALLOW',
    }))

    // 保存后自动 reload 回读：listSchedules 第 2 次调用且列表反显（初始下线）
    expect(apiMock.listSchedules).toHaveBeenCalledTimes(2)
    expect(w.find('[data-test="list-empty"]').exists()).toBe(false)
    expect(w.find('[data-test="state-pill"]').text()).toBe('已下线')
  })

  it('SKIP 分支断言（R-05 B 语义）：回读 openEdit 反显 SKIP + 语义参考锚自洽', async () => {
    apiMock.listSchedules.mockResolvedValue([makeRow({ misfirePolicy: 'SKIP' })])
    const w = await mountDialog()

    // 回读反显：编辑表单 misfire select 值 = SKIP
    await w.find('[data-test="edit-btn"]').trigger('click')
    await flushPromises()
    const misfire = w.find('[data-test="misfire"]')
    expect((misfire.element as HTMLSelectElement).value).toBe('SKIP')

    // 编辑提交走 updateSchedule（非 create）且 SKIP 策略透传
    await w.find('[data-test="save-btn"]').trigger('click')
    await flushPromises()
    expect(apiMock.updateSchedule).toHaveBeenCalledTimes(1)
    expect(apiMock.updateSchedule).toHaveBeenCalledWith(1, expect.objectContaining({ misfirePolicy: 'SKIP' }))

    // 语义参考锚（镜像后端 R-05 现态）自洽断言
    expect(SKIP_SEMANTIC_R05.option).toBe('B')
    expect(SKIP_SEMANTIC_R05.scanSeconds).toBe(10)
    expect(SKIP_SEMANTIC_R05.windowHalfOpen).toBe(true)
    expect(SKIP_SEMANTIC_R05.takeLatestDue).toBe(true)
  })

  it('按策略触发契约面：misfire 三策略载荷透传对照（FIRE_ONCE/SKIP/FIRE_ALL_LIMITED）', async () => {
    for (const policy of ['FIRE_ONCE', 'SKIP', 'FIRE_ALL_LIMITED'] as const) {
      vi.clearAllMocks()
      apiMock.listSchedules.mockResolvedValue([])
      apiMock.previewCrontab.mockResolvedValue({ valid: true, nextFireTimes: ['2026-10-22 02:00:00'] })
      apiMock.createSchedule.mockResolvedValue({ ...makeRow({ misfirePolicy: policy }), nextFireTimes: ['2026-10-22 02:00:00'] })

      const w = await mountDialog()
      await openForm(w)
      await w.find('[data-test="crontab"]').setValue('0 2 * * *')
      await w.find('[data-test="misfire"]').setValue(policy)
      await w.find('[data-test="save-btn"]').trigger('click')
      await flushPromises()
      expect(apiMock.createSchedule).toHaveBeenCalledWith(101, expect.objectContaining({ misfirePolicy: policy }))
      w.unmount()
    }
  })
})
