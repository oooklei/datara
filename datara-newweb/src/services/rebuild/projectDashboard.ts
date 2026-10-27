import { createDatasourceContract } from './datasourceApi'
import { listWorkflowRunStats, type WorkflowRunStat } from './executionStatsApi'
import { governanceApi } from './governanceApi'
import { createMetricsContract, type WorkflowResultStatRow } from './metricsApi'
import { createResourceContract } from './resourceApi'
import { listWorkflowDefinitions, type WorkflowDefSummary } from './workflowApi'

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

export async function loadProjectDashboard(projectId: number): Promise<ProjectDashboardModel> {
  const failures: string[] = []
  async function safe<T>(label: string, task: Promise<T>, fallback: T): Promise<T> {
    try { return await task } catch { failures.push(label); return fallback }
  }
  const window = sevenDayWindow()
  const datasource = createDatasourceContract(projectId)
  const resources = createResourceContract()
  const metrics = createMetricsContract()
  const [workflows, dailyStats, runPage, datasourcePage, resourceRows, assets, standards, metricPage, rules, exceptions] = await Promise.all([
    safe('工作流', listWorkflowDefinitions(projectId), []),
    safe('运行趋势', metrics.queryWorkflowResultStats(projectId, window), []),
    safe('最近运行', listWorkflowRunStats(projectId, { startedFrom: window.from, limit: 50 }), { total: 0, items: [] }),
    safe('数据源', datasource.listDatasources(), { items: [] }),
    safe('资源', resources.listResources(projectId), []),
    safe('资产', governanceApi.listAssets(projectId, { page: 1, pageSize: 1 }), { total: 0, page: 1, pageSize: 1, list: [] }),
    safe('标准', governanceApi.listStandards(projectId, 1, 1), { total: 0, list: [] }),
    safe('指标', governanceApi.listMetrics(projectId, 1, 1), { total: 0, list: [] }),
    safe('质量规则', governanceApi.listRules(projectId, 1, 1), { total: 0, list: [] }),
    safe('异常', governanceApi.listExceptions(projectId, 1, 1, 'open'), { total: 0, list: [] }),
  ])
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
