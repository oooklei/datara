// @vitest-environment happy-dom
/**
 * M-B0 基线化工作台挂载用例（happy-dom，渲染冒烟）：
 * - 清单看板：progress 分组（同步/ETL/流处理/逻辑控制）+ 状态徽标 + 进度条 + 空态
 * - 设计区：选中组件拉底稿 → 信息条 / 与旧声明 diff / 八段编辑器 / 保存底稿按钮
 * - 保存：携带 draftRev 与 spec；409 乐观锁冲突 → 自动重拉最新底稿
 * - 认可发 v1：二次确认 → publishBaseline → 刷新进度
 * - 修订轮次三态：published 态「复制 vN 开修订」（无保存）；修订中「放弃修订」+「认可发 v2」
 * baselineApi / componentApi 以模块 mock 注入；el-* 组件桩掉消噪音（与设计器用例同法）。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { ElMessageBox } from 'element-plus'

const progressSpy = vi.hoisted(() => vi.fn())
const getDraftSpy = vi.hoisted(() => vi.fn())
const saveDraftSpy = vi.hoisted(() => vi.fn())
const checkSpy = vi.hoisted(() => vi.fn())
const publishSpy = vi.hoisted(() => vi.fn())
const redraftSpy = vi.hoisted(() => vi.fn())
const discardSpy = vi.hoisted(() => vi.fn())
const lineageSpy = vi.hoisted(() => vi.fn())
const getCompSpy = vi.hoisted(() => vi.fn())
/* 目录页「修改/查看」深链 /meta/baseline?type=xxx 定位设计区（query.type 可注入） */
const routeState = vi.hoisted(() => ({ params: {} as Record<string, unknown>, query: {} as Record<string, unknown> }))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: routeState.params, query: routeState.query }),
}))
vi.mock('../../../services/baselineApi', () => ({
  progress: progressSpy,
  getDraft: getDraftSpy,
  saveDraft: saveDraftSpy,
  runCheck: checkSpy,
  publishBaseline: publishSpy,
  redraftBaseline: redraftSpy,
  discardBaselineRevision: discardSpy,
  lineageDecl: lineageSpy,
}))
vi.mock('../../../services/componentApi', () => ({
  getComponent: getCompSpy,
}))

import BaselineWorkbenchView from '../BaselineWorkbenchView.vue'

/* 清单看板：同步类已发 v1 / ETL 类设计中 / 逻辑控制类未开始（覆盖三种状态徽标） */
const PROGRESS = {
  items: [
    { type: 'cdc_ds', code: 'C2', label: '数据源同步', categories: ['sync'], executionModel: 'dag-engine', executor: 'exec_cdc', paletteVisible: true, runtimeOnly: false, status: 'published', draftRev: 5, hasDraft: true, publishedVersion: 1, confirmedBy: 'alice', confirmedAt: '2026-09-28 10:00:00', updatedAt: '2026-09-28 10:00:00' },
    { type: 'sql_transform', code: 'C10', label: 'SQL 转换', categories: ['etl'], executionModel: 'dag-engine', executor: null, paletteVisible: true, runtimeOnly: false, status: 'designing', draftRev: 2, hasDraft: true, publishedVersion: 0, confirmedBy: null, confirmedAt: null, updatedAt: '2026-09-28 09:00:00' },
    { type: 'end', code: 'C3', label: '结束', categories: ['general'], executionModel: 'dag-engine', executor: null, paletteVisible: true, runtimeOnly: false, status: 'pending', draftRev: 0, hasDraft: false, publishedVersion: 0, confirmedBy: null, confirmedAt: null, updatedAt: '' },
  ],
  stats: { total: 3, byStatus: { pending: 1, designing: 1, published: 1 } },
}

/* 底稿：旧声明 sql/mode 已迁入 params，legacy_only 留 pending；testRecords 一条 */
const DRAFT = {
  type: 'sql_transform', status: 'designing', draftRev: 2,
  spec: {
    form: {
      inputs: [],
      outputs: [],
      params: [
        { key: 'sql', label: 'SQL 语句', uiType: 'text', required: true, visible: true },
        { key: 'mode', label: '模式', uiType: 'select', required: false, visible: true, options: [{ label: '并行', value: 'parallel' }] },
      ],
      conditions: [],
      constraints: [],
      exclusions: [],
      refs: [],
      exports: [{ key: 'rows', from: 'log', type: 'int', logKey: 'row_count' }],
    },
    lineage: { assets: [{ role: 'source', pick: 'table', assetType: 'table' }] },
    render: { icon: '⚙', color: '#4C7CF0', summary: 'SQL 转换', ports: { inputs: [], outputs: [] } },
    dropPolicy: {},
    paletteVisible: true,
  },
  specHash: 'a'.repeat(64),
  checkReport: null,
  testRecords: [{ batch: 'B1', dataflow: 'ods→dwd', result: 'pass' }],
  updatedAt: '2026-09-28 10:00:00',
}

const OLD_DETAIL = {
  type: 'sql_transform', formFields: [
    { key: 'sql', label: 'SQL 语句', type: 'text', flags: {} },
    { key: 'mode', label: '模式', type: 'select', flags: {} },
    { key: 'legacy_only', label: '仅旧版', type: 'text', flags: {} },
  ],
}

const stubs = {
  /* emits 声明与真实 ElButton 对齐（EP2 声明了 click emit），避免 fallthrough 双触发 */
  ElButton: { emits: ['click'], template: '<button @click="$emit(\'click\')"><slot /></button>' },
  ElInput: { template: '<input />', props: ['modelValue'] },
  ElSwitch: { template: '<label class="stub-switch" />', props: ['modelValue'] },
  ElProgress: { props: ['percentage'], template: '<div class="stub-progress" />' },
}

function mountView() {
  setActivePinia(createPinia())
  return mount(BaselineWorkbenchView, { global: { components: stubs } })
}

async function selectRow(w: ReturnType<typeof mountView>, type: string): Promise<void> {
  const row = w.findAll('.crow').find((c) => c.text().includes(type))
  expect(row, `清单应包含 ${type}`).toBeTruthy()
  await row!.trigger('click')
  await flushPromises()
}

beforeEach(() => {
  vi.clearAllMocks()
  routeState.query = {}
  progressSpy.mockResolvedValue(structuredClone(PROGRESS))
  getDraftSpy.mockResolvedValue(structuredClone(DRAFT))
  getCompSpy.mockResolvedValue(structuredClone(OLD_DETAIL))
  lineageSpy.mockResolvedValue({ type: 'sql_transform', baselineState: 'unbaseline', lineage: {} })
})

describe('BaselineWorkbenchView（M-B0 基线化工作台）', () => {
  it('渲染冒烟：三区文案、清单分组、状态徽标、进度条与设计区空态', async () => {
    const w = mountView()
    await flushPromises()
    expect(progressSpy).toHaveBeenCalledTimes(1)
    // 三区关键文案
    expect(w.text()).toContain('清单看板')
    expect(w.text()).toContain('证据区')
    // 分组：sync 归「同步类」，etl 归「ETL / 计算类」，general 归「逻辑控制类」
    expect(w.text()).toContain('同步类')
    expect(w.text()).toContain('ETL / 计算类')
    expect(w.text()).toContain('逻辑控制类')
    // 状态徽标（中文映射）
    expect(w.text()).toContain('已发 v1')
    expect(w.text()).toContain('设计中')
    expect(w.text()).toContain('未开始')
    // 进度：published 1/3
    expect(w.text()).toContain('1/3')
    // 设计区空态（未选中组件）
    expect(w.text()).toContain('从清单选择组件')
    expect(getDraftSpy).not.toHaveBeenCalled()
  })

  it('选中组件：拉底稿渲染信息条/diff 折叠块/编辑器八段页签/保存按钮', async () => {
    const w = mountView()
    await flushPromises()
    await selectRow(w, 'sql_transform')
    expect(getDraftSpy).toHaveBeenCalledWith('sql_transform')
    expect(getCompSpy).toHaveBeenCalledWith('sql_transform')
    // 信息条：label + type + 执行模型
    expect(w.text()).toContain('SQL 转换')
    expect(w.text()).toContain('sql_transform')
    expect(w.text()).toContain('dag-engine')
    // 与旧声明 diff：旧 3 → 新 2；已迁移 sql/mode；待语义分析 legacy_only
    expect(w.text()).toContain('与旧声明 diff')
    expect(w.text()).toContain('已迁移')
    expect(w.text()).toContain('待语义分析')
    expect(w.text()).toContain('legacy_only')
    // 八段编辑器页签 + 配置抽屉预览
    expect(w.text()).toContain('输出变量')
    expect(w.text()).toContain('引用变量')
    expect(w.text()).toContain('配置抽屉预览')
    // 保存底稿按钮存在
    expect(w.findAll('button').some((b) => b.text() === '保存底稿')).toBe(true)
    // 证据区：血缘资产数量与实测记录（后端 1 条）
    expect(w.text()).toContain('血缘资产')
    expect(w.text()).toContain('B1')
  })

  it('深链定位：/meta/baseline?type=xxx 挂载后自动选中该组件拉底稿（目录页「修改」入口）', async () => {
    routeState.query = { type: 'sql_transform' }
    const w = mountView()
    await flushPromises()
    // progress 先行、随后自动 select → 拉底稿（无需点击清单行）
    expect(progressSpy).toHaveBeenCalledTimes(1)
    expect(getDraftSpy).toHaveBeenCalledWith('sql_transform')
    expect(w.text()).toContain('SQL 转换')
    // query.type 不在清单内（或为空）→ 保持设计区空态
  })

  it('深链兜底：query.type 不在清单内不选中、不拉底稿', async () => {
    routeState.query = { type: 'no_such_type' }
    const w = mountView()
    await flushPromises()
    expect(progressSpy).toHaveBeenCalledTimes(1)
    expect(getDraftSpy).not.toHaveBeenCalled()
    expect(w.text()).toContain('从清单选择组件')
  })

  it('保存底稿：携带 draftRev 与 spec；409 冲突自动重拉最新底稿', async () => {
    saveDraftSpy.mockRejectedValueOnce(Object.assign(new Error('conflict'), { code: 409, data: { currentRev: 9 } }))
    const w = mountView()
    await flushPromises()
    await selectRow(w, 'sql_transform')
    expect(getDraftSpy).toHaveBeenCalledTimes(1)
    const saveBtn = w.findAll('button').find((b) => b.text() === '保存底稿')
    await saveBtn!.trigger('click')
    await flushPromises()
    expect(saveDraftSpy).toHaveBeenCalledTimes(1)
    const [type, body] = saveDraftSpy.mock.calls[0] as [string, { draftRev: number; spec: Record<string, unknown> }]
    expect(type).toBe('sql_transform')
    expect(body.draftRev).toBe(2)
    expect(body.spec).toBeTruthy()
    // 409 → 重拉底稿合并（getDraft 第二次调用）
    expect(getDraftSpy).toHaveBeenCalledTimes(2)
  })

  it('认可发 v1：二次确认后调用 publishBaseline 并刷新进度；已发禁用', async () => {
    const confirmSpy = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({ value: 'confirm' } as any)
    publishSpy.mockResolvedValue({ type: 'sql_transform', publishedVersion: 1, specHash: 'e'.repeat(64), checkItems: [], confirmedAt: '2026-09-28 11:00:00' })
    const w = mountView()
    await flushPromises()
    // 未选中组件 → 发布按钮禁用
    const pubBtn0 = w.findAll('button').find((b) => b.text() === '认可发 v1')
    expect(pubBtn0).toBeTruthy()
    expect(pubBtn0!.attributes('disabled')).toBeDefined()
    await selectRow(w, 'sql_transform')
    const pubBtn = w.findAll('button').find((b) => b.text() === '认可发 v1')
    expect(pubBtn!.attributes('disabled')).toBeUndefined()
    await pubBtn!.trigger('click')
    await flushPromises()
    expect(confirmSpy).toHaveBeenCalledTimes(1)
    expect(publishSpy).toHaveBeenCalledWith('sql_transform')
    // 发布成功后刷新进度（progress 第二次调用）
    expect(progressSpy).toHaveBeenCalledTimes(2)
  })

  it('published 态（publishedVersion=1）：编辑器只读、显示「复制 v1 开修订」入口，无「保存底稿」/发布按钮', async () => {
    getDraftSpy.mockResolvedValue(structuredClone({ ...DRAFT, type: 'cdc_ds', status: 'published' }))
    const w = mountView()
    await flushPromises()
    await selectRow(w, 'cdc_ds')
    // spec §5：published 态编辑器只读（EightSectionEditor 根元素 readonly → ro class）
    expect(w.find('.ese').classes()).toContain('ro')
    const btns = w.findAll('button').map((b) => b.text())
    // 已发版底稿锁定（R3 409）→ 保存栏切开修订入口，发布按钮隐藏（后端必 409）
    expect(btns).toContain('复制 v1 开修订')
    expect(btns).not.toContain('保存底稿')
    expect(btns).not.toContain('认可发 v1')
    expect(btns).not.toContain('认可发 v2')
    expect(w.text()).toContain('registry 继续供给当前已发版')
    // 信息条/看板徽标动态版本号（publishedVersion=1，非兜底「已发版」）
    expect(w.text()).toContain('已发 v1')
    expect(w.find('.info-bar').text()).toContain('已发 v1')
  })

  it('修订中态（designing + publishedVersion=1）：编辑器可编辑，显示「放弃修订」与「认可发 v2」', async () => {
    const revising = structuredClone(PROGRESS)
    revising.items[1].publishedVersion = 1
    progressSpy.mockResolvedValue(revising)
    const w = mountView()
    await flushPromises()
    await selectRow(w, 'sql_transform')
    // 修订中底稿可编辑保存（编辑器无只读标记），可放弃修订（回已发版）
    expect(w.find('.ese').classes()).not.toContain('ro')
    const btns = w.findAll('button').map((b) => b.text())
    expect(btns).toContain('保存底稿')
    expect(btns).toContain('放弃修订')
    // 认可发下一版（publishedVersion+1）
    expect(btns).toContain('认可发 v2')
    expect(btns).not.toContain('认可发 v1')
    // 信息条修订中提示：当前供给 v1
    expect(w.text()).toContain('修订中（当前供给 v1）')
  })
})
