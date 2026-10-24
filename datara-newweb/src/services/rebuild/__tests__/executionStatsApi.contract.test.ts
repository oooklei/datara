import { afterEach, describe, expect, it, vi } from 'vitest'
import { listWorkflowRunStats } from '../executionStatsApi'

describe('execution stats API', () => {
  afterEach(() => vi.restoreAllMocks())
  it('queries the authoritative project-scoped run statistics route', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo) => new Response(JSON.stringify({ code: 0, msg: 'success', data: { total: 1, items: [] } }), { status: 200, headers: { 'content-type': 'application/json' } })))
    await expect(listWorkflowRunStats(7, { workflowId: 11 })).resolves.toEqual({ total: 1, items: [] })
    expect(String(vi.mocked(fetch).mock.calls[0][0])).toContain('/api/v1/rebuild/execution/run-stats?project_id=7&limit=50&workflow_id=11')
  })
})
