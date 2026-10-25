import { afterEach, describe, expect, it, vi } from 'vitest'
import { getWorkflowRunStat, listWorkflowRunStats } from '../executionStatsApi'

describe('execution stats API', () => {
  afterEach(() => vi.restoreAllMocks())
  it('queries the authoritative project-scoped run statistics route', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo) => new Response(JSON.stringify({ code: 0, msg: 'success', data: { total: 1, items: [] } }), { status: 200, headers: { 'content-type': 'application/json' } })))
    await expect(listWorkflowRunStats(7, { workflowId: 11 })).resolves.toEqual({ total: 1, items: [] })
    expect(String(vi.mocked(fetch).mock.calls[0][0])).toContain('/api/v1/rebuild/execution/run-stats?project_id=7&limit=50&workflow_id=11')
  })

  it('loads one project-scoped run with table-level reconciliation details', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ code: 0, msg: 'success', data: { id: 5, details: [], detail_total: 0 } }), { status: 200, headers: { 'content-type': 'application/json' } })))
    await expect(getWorkflowRunStat(7, 5)).resolves.toMatchObject({ id: 5, detail_total: 0 })
    expect(String(vi.mocked(fetch).mock.calls[0][0])).toContain('/api/v1/rebuild/execution/run-stats/5?project_id=7&detail_limit=200')
  })
})
