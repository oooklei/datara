import { createDbxContract } from './dbxApi'
import { listWorkflowRunStats, type WorkflowRunStat } from './executionStatsApi'
import { governanceApi } from './governanceApi'
import { createMetricsContract, type WorkflowResultStatRow } from './metricsApi'
import { createResourceContract } from './resourceApi'
import { listWorkflowDefinitions, type WorkflowDefSummary } from './workflowApi'

/* §4.3 切换点预留：后端聚合端点一旦就绪，设 true 即可跳过 fan-out 全走单端点 */
const WORKBENCH_SUMMARY_ENABLED = false
const WORKBENCH_SUMMARY_PATH = '/projects/:pid/workbench-summary'

/** §2 裁决 2：fan-out 并发上限（默认 ≤4） */
const FAN_OUT_CONCURRENCY_LIMIT = 4

/**
 * 分批并发闸：保持任务顺序但每批最多 `limit` 个同时在飞。
 * signal 触发后跳过尚未开始的批次（协作式取消；已在跑的等自然返回）。
 */
async function runConcurrent<T>(items: (() => Promise<T>)[], limit: number, signal?: AbortSignal): Promise<T[]> {
  const out: T[] = new Array(items.length)
  for (let i = 0; i < items.length; i += limit) {
    if (signal?.aborted) break
    const slice = items.slice(i, i + limit)
    const results = await Promise.all(
      slice.map((fn, k) => fn().then((v) => ({ v, idx: i + k })).catch((_) => null))
    )
    for (const r of results) if (r) out[r.idx] = r.v
  }
  return out
}

export interface ProjectDashboardSource {
  workflows: WorkflowDefSummary[]
  dailyStats: WorkflowResultStatRow[]
  recentRuns: WorkflowRunStat[]
  datasourceCount: number
  resourceCount: number
  assetCount: number
  standardCount: number
  metricCount: number
  qualityRuleCount: number
  openExceptionCount: number
}

export interface ProjectDashboardModel {
  workflowTypes: { normal: number; sync: number; stream: number }
  runTotals: { success: number; failure: number; skipped: number; retry: number; running: number }
  governance: {
    datasources: number
    resources: number
    assets: number
    standards: number
    metrics: number
    qualityRules: number
    openExceptions: number
  }
  dailyStats: WorkflowResultStatRow[]
  recentRuns: WorkflowRunStat[]
  partialFailures: string[]
}

export function aggregateProjectDashboard(source: ProjectDashboardSource): ProjectDashboardModel {
  const workflowTypes = { normal: 0, sync: 0, stream: 0 }
  for (const workflow of source.workflows) {
    if (workflow.workflowType === 'SYNC') workflowTypes.sync += 1
    else if (workflow.workflowType === 'STREAM') workflowTypes.stream += 1
    else workflowTypes.normal += 1
  }
  const runTotals = source.dailyStats.reduce((totals, row) => ({
    success: totals.success + row.successCount,
    failure: totals.failure + row.failureCount,
    skipped: totals.skipped + row.skippedCount,
    retry: totals.retry + row.retryCount,
    running: totals.running,
  }), { success: 0, failure: 0, skipped: 0, retry: 0, running: 0 })
  runTotals.running = source.recentRuns.filter((run) => run.status.toUpperCase() === 'RUNNING').length
  return {
    workflowTypes,
    runTotals,
    governance: {
      datasources: source.datasourceCount,
      resources: source.resourceCount,
      assets: source.assetCount,
      standards: source.standardCount,
      metrics: source.metricCount,
      qualityRules: source.qualityRuleCount,
      openExceptions: source.openExceptionCount,
    },
    dailyStats: [...source.dailyStats].sort((a, b) => a.runDate.localeCompare(b.runDate)),
    recentRuns: [...source.recentRuns].sort((a, b) => b.started_at.localeCompare(a.started_at)).slice(0, 8),
    partialFailures: [],
  }
}

function sevenDayWindow() {
  const to = new Date()
  const from = new Date(to.getTime() - 7 * 24 * 60 * 60 * 1000)
  return { from: from.toISOString(), to: to.toISOString(), offset: 0, limit: 100 }
}

export async function loadProjectDashboard(projectId: number, signal?: AbortSignal): Promise<ProjectDashboardModel> {
  // §4.3 切换点：后端聚合端点就绪时单请求替代 10 路 fan-out
  if (WORKBENCH_SUMMARY_ENABLED) {
    // 预留占位（TODO: 实现后替换 fan-out 全部逻辑）
    throw new Error(`workbench-summary 端点未就绪：${WORKBENCH_SUMMARY_PATH.replace(':pid', String(projectId))}`)
  }

  const failures: string[] = []
  const window = sevenDayWindow()
  const dbx = createDbxContract(projectId)
  const resources = createResourceContract()
  const metrics = createMetricsContract()

  // §2 裁决 2：fan-out 并发 ≤4（10 任务 → 4+4+2 三批串批内并发）
  const tasks: Array<() => Promise<{ label: string; ok: boolean; data: any }>> = [
    () => listWorkflowDefinitions(projectId).then((v) => ({ label: '工作流', ok: true, data: v })).catch(() => ({ label: '工作流', ok: false, data: [] })),
    () => metrics.queryWorkflowResultStats(projectId, window).then((v) => ({ label: '运行趋势', ok: true, data: v })).catch(() => ({ label: '运行趋势', ok: false, data: [] })),
    () => listWorkflowRunStats(projectId, { startedFrom: window.from, limit: 50 }).then((v) => ({ label: '最近运行', ok: true, data: v })).catch(() => ({ label: '最近运行', ok: false, data: { total: 0, items: [] } })),
    () => dbx.listConnections().then((items) => ({ label: 'dbx 连接', ok: true, data: { items } })).catch(() => ({ label: 'dbx 连接', ok: false, data: { items: [] } })),
    () => resources.listResources(projectId).then((v) => ({ label: '资源', ok: true, data: v })).catch(() => ({ label: '资源', ok: false, data: [] })),
    () => governanceApi.listAssets(projectId, { page: 1, pageSize: 1 }).then((v) => ({ label: '资产', ok: true, data: v })).catch(() => ({ label: '资产', ok: false, data: { total: 0, page: 1, pageSize: 1, list: [] } })),
    () => governanceApi.listStandards(projectId, 1, 1).then((v) => ({ label: '标准', ok: true, data: v })).catch(() => ({ label: '标准', ok: false, data: { total: 0, list: [] } })),
    () => governanceApi.listMetrics(projectId, 1, 1).then((v) => ({ label: '指标', ok: true, data: v })).catch(() => ({ label: '指标', ok: false, data: { total: 0, list: [] } })),
    () => governanceApi.listRules(projectId, 1, 1).then((v) => ({ label: '质量规则', ok: true, data: v })).catch(() => ({ label: '质量规则', ok: false, data: { total: 0, list: [] } })),
    () => governanceApi.listExceptions(projectId, 1, 1, 'open').then((v) => ({ label: '异常', ok: true, data: v })).catch(() => ({ label: '异常', ok: false, data: { total: 0, list: [] } })),
  ]
  // 协作式取消：signal.aborted 时 runConcurrent 跳过剩余批次
  const results = await runConcurrent(tasks, FAN_OUT_CONCURRENCY_LIMIT, signal)
  for (const r of results) if (r && !r.ok) failures.push(r.label)
  if (signal?.aborted) failures.push('已取消')

  // 结果按原始索引解构（保持与原 Promise.all 解构一致）
  const [
    workflowsResult, dailyStatsResult, runPageResult, datasourceResult, resourceResult,
    assetsResult, standardsResult, metricResult, rulesResult, exceptionsResult,
  ] = results
  const workflows = workflowsResult?.ok ? workflowsResult.data : []
  const dailyStats = dailyStatsResult?.ok ? dailyStatsResult.data : []
  const runPage = runPageResult?.ok ? runPageResult.data : { total: 0, items: [] }
  const datasourcePage = datasourceResult?.ok ? datasourceResult.data : { items: [] }
  const resourceRows = resourceResult?.ok ? resourceResult.data : []
  const assets = assetsResult?.ok ? assetsResult.data : { total: 0, page: 1, pageSize: 1, list: [] }
  const standards = standardsResult?.ok ? standardsResult.data : { total: 0, list: [] }
  const metricPage = metricResult?.ok ? metricResult.data : { total: 0, list: [] }
  const rules = rulesResult?.ok ? rulesResult.data : { total: 0, list: [] }
  const exceptions = exceptionsResult?.ok ? exceptionsResult.data : { total: 0, list: [] }

  // safe 作用域已迁到 runConcurrent；以下聚合逻辑不变
  const model = aggregateProjectDashboard({
    workflows,
    dailyStats,
    recentRuns: runPage.items,
    datasourceCount: datasourcePage.items.length,
    resourceCount: resourceRows.length,
    assetCount: assets.total,
    standardCount: standards.total,
    metricCount: metricPage.total,
    qualityRuleCount: rules.total,
    openExceptionCount: exceptions.total,
  })
  model.partialFailures = failures
  return model
}
