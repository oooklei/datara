/**
 * INC4-FE-7（WBS 4.5 / s269 派令）：trial 试运行面板 store（options 表单态 + 运行结果 + 输出面）。
 *
 * 职责（真源：trialApi 七端点 + runner.TrialRunOptions WF-15~WF-20 + promote WF-21/WF-26）：
 *  - open：进入试运行会话（projectId/definitionId 绑定），全量清态（跨 definition 防串写）；
 *    loadSeq 递增使全部在飞响应过期丢弃；
 *  - createSnapshot：POST snapshot → 快照权威锚定（深拷贝落地）；幂等同 digest 直返既有行；
 *  - options 表单态：八能力草稿（nodeCodes/startNode/testVariables/dependencyMock/
 *    dryRun/sqlPrecheck），面板直改 reactive 态；run 提交时经 effectiveOptions 归一化
 *    （空集合/空串/未勾选键不携带，全空则 body 不含 options 键）；
 *  - run：POST run → runResult；loadSeq 时序守卫（KeepAlive 复活/切 Tab 竞态下仅最新
 *    响应落地，过期响应与过期错误一并丢弃）；running 仅 run 置位，任一更晚落地动作复位；
 *  - refreshOutput：GET /runs/{runResult.instanceId} 输出面 → output（stats {} 兜底 0、
 *    缺 instance_type/status → null 由 trialApi mapOutput 承接）；DRY_RUN instance_id=0
 *    无输出面，面板侧跳过；
 *  - promote：POST /runs/{id}/promote（WF-26 按 run_id，definition 由后端自实例解析）
 *    → promoteResult（幂等 idempotent 直返）。
 */
import { defineStore } from 'pinia'

import {
  createTrialSnapshot,
  getTrialRunOutput,
  promoteRunById,
  runTrial,
  type TrialDependencyMockStatus,
  type TrialPromoteResult,
  type TrialRunOptions,
  type TrialRunOutput,
  type TrialRunResult,
  type TrialSnapshot,
} from '../services/rebuild/trialApi'

/** 试运行 options 表单态（面板直改；提交时经 effectiveOptions 归一化） */
export interface TrialRunFormOptions {
  /** WF-15：指定节点子集（空数组 = 不限） */
  nodeCodes: string[]
  /** WF-16：起始节点（空串 = 不限） */
  startNode: string
  /** WF-17：变量覆盖（变量名 → 覆盖值） */
  testVariables: Record<string, unknown>
  /** WF-18：依赖模拟（dependency_id → 模拟结果） */
  dependencyMock: Record<string, TrialDependencyMockStatus>
  /** WF-19：仅出执行计划不落副作用 */
  dryRun: boolean
  /** WF-20：执行前 SQL 预检 */
  sqlPrecheck: boolean
}

function emptyFormOptions(): TrialRunFormOptions {
  return {
    nodeCodes: [],
    startNode: '',
    testVariables: {},
    dependencyMock: {},
    dryRun: false,
    sqlPrecheck: false,
  }
}

/** 表单 → TrialRunOptions 归一化：空集合/空串/未勾选键不携带；全空 → undefined（body 无 options 键） */
function effectiveOptions(form: TrialRunFormOptions): TrialRunOptions | undefined {
  const out: TrialRunOptions = {}
  if (form.nodeCodes.length > 0) out.nodeCodes = [...form.nodeCodes]
  if (form.startNode !== '') out.startNode = form.startNode
  if (Object.keys(form.testVariables).length > 0) out.testVariables = { ...form.testVariables }
  if (Object.keys(form.dependencyMock).length > 0) out.dependencyMock = { ...form.dependencyMock }
  if (form.dryRun) out.dryRun = true
  if (form.sqlPrecheck) out.sqlPrecheck = true
  return Object.keys(out).length > 0 ? out : undefined
}

export const useTrialRunStore = defineStore('trialRun', {
  state: () => ({
    projectId: null as number | null,
    definitionId: null as number | null,
    snapshot: null as TrialSnapshot | null,
    options: emptyFormOptions(),
    runResult: null as TrialRunResult | null,
    output: null as TrialRunOutput | null,
    promoteResult: null as TrialPromoteResult | null,
    running: false,
    loadSeq: 0,
    lastError: null as string | null,
  }),

  actions: {
    /** 进入试运行会话：绑定上下文并全量清态（跨 definition 防串写）；loadSeq 递增使在飞响应全部过期 */
    open(projectId: number, definitionId: number): void {
      this.projectId = projectId
      this.definitionId = definitionId
      this.snapshot = null
      this.options = emptyFormOptions()
      this.runResult = null
      this.output = null
      this.promoteResult = null
      this.loadSeq++
      this.running = false
      this.lastError = null
    },

    /** 生成/刷新草稿快照（POST snapshot；幂等同 digest 直返既有行）；loadSeq 守卫过期响应丢弃 */
    async createSnapshot(): Promise<TrialSnapshot | null> {
      if (this.projectId === null || this.definitionId === null) return null
      const seq = ++this.loadSeq
      this.lastError = null
      try {
        const snap = await createTrialSnapshot(this.projectId, this.definitionId)
        if (seq !== this.loadSeq) return null
        // 权威锚定：深拷贝落地（JSON 安全值），隔离 reactive 代理串写
        this.snapshot = JSON.parse(JSON.stringify(snap)) as TrialSnapshot
        this.running = false
        return this.snapshot
      } catch (error) {
        if (seq !== this.loadSeq) return null
        this.lastError = error instanceof Error ? error.message : String(error)
        this.running = false
        return null
      }
    },

    /** 发起试运行（表单归一化）→ runResult；loadSeq 守卫，仅最新响应落地 */
    async run(): Promise<TrialRunResult | null> {
      if (this.projectId === null || this.definitionId === null || this.snapshot === null) return null
      const seq = ++this.loadSeq
      this.running = true
      this.lastError = null
      try {
        const result = await runTrial(
          this.projectId,
          this.definitionId,
          this.snapshot.snapshotId,
          effectiveOptions(this.options),
        )
        if (seq !== this.loadSeq) return null
        this.runResult = result
        return result
      } catch (error) {
        if (seq !== this.loadSeq) return null
        this.lastError = error instanceof Error ? error.message : String(error)
        return null
      } finally {
        if (seq === this.loadSeq) this.running = false
      }
    },

    /** 拉取输出面（GET /runs/{runResult.instanceId}）；无 run 结果 → null 不发请求 */
    async refreshOutput(): Promise<TrialRunOutput | null> {
      if (this.projectId === null || this.runResult === null) return null
      const seq = ++this.loadSeq
      this.lastError = null
      try {
        const out = await getTrialRunOutput(this.projectId, this.runResult.instanceId)
        if (seq !== this.loadSeq) return null
        this.output = out
        this.running = false
        return out
      } catch (error) {
        if (seq !== this.loadSeq) return null
        this.lastError = error instanceof Error ? error.message : String(error)
        this.running = false
        return null
      }
    },

    /** 转正式（POST /runs/{id}/promote；WF-26 按 run_id）→ promoteResult */
    async promote(remark?: string): Promise<TrialPromoteResult | null> {
      if (this.projectId === null || this.runResult === null) return null
      const seq = ++this.loadSeq
      this.lastError = null
      try {
        const result = await promoteRunById(this.projectId, this.runResult.instanceId, remark)
        if (seq !== this.loadSeq) return null
        this.promoteResult = result
        this.running = false
        return result
      } catch (error) {
        if (seq !== this.loadSeq) return null
        this.lastError = error instanceof Error ? error.message : String(error)
        this.running = false
        return null
      }
    },
  },
})
