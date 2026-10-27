import { describe, expect, it } from 'vitest'
import { aggregateProjectDashboard } from '../projectDashboard'

describe('UX v3：项目工作台真实聚合', () => {
  it('聚合工作流类型、治理计数、运行趋势与最近实例', () => {
    const dashboard = aggregateProjectDashboard({
      workflows: [
        { id: 1, name: '离线', tags: [], workflowType: 'NORMAL' },
        { id: 2, name: '同步', tags: [], workflowType: 'SYNC' },
        { id: 3, name: '实时', tags: [], workflowType: 'STREAM' },
      ],
      dailyStats: [
        { workflowId: 1, runDate: '2026-10-26', successCount: 8, failureCount: 1, skippedCount: 2, retryCount: 1 },
        { workflowId: 2, runDate: '2026-10-27', successCount: 5, failureCount: 0, skippedCount: 0, retryCount: 0 },
      ],
      recentRuns: [
        { id: 8, workflow_id: 1, workflow_instance_id: 18, instance_type: 'FORMAL', status: 'SUCCESS', success_count: 8, failure_count: 0, skipped_count: 0, total_count: 8, started_at: '2026-10-27T09:00:00Z', dag_name: '离线' },
        { id: 9, workflow_id: 3, workflow_instance_id: 19, instance_type: 'STREAM', status: 'RUNNING', success_count: 3, failure_count: 0, skipped_count: 0, total_count: 3, started_at: '2026-10-27T10:00:00Z', dag_name: '实时' },
      ],
      datasourceCount: 4,
      resourceCount: 7,
      assetCount: 20,
      standardCount: 6,
      metricCount: 9,
      qualityRuleCount: 5,
      openExceptionCount: 2,
    })

    expect(dashboard.workflowTypes).toEqual({ normal: 1, sync: 1, stream: 1 })
    expect(dashboard.runTotals).toEqual({ success: 13, failure: 1, skipped: 2, retry: 1, running: 1 })
    expect(dashboard.governance).toEqual({ datasources: 4, resources: 7, assets: 20, standards: 6, metrics: 9, qualityRules: 5, openExceptions: 2 })
    expect(dashboard.recentRuns.map((run) => run.id)).toEqual([9, 8])
  })
})
