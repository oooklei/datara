import { afterEach, describe, expect, it, vi } from 'vitest'
import { getWorkflowRunStat, listWorkflowRunStats } from '../executionStatsApi'

describe('execution stats API', () => {
  afterEach(() => vi.restoreAllMocks())
  it('queries the authoritative project-scoped run statistics route', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo) => new Response(JSON.stringify({ code: 0, msg: 'success', data: { total: 1, items: [] } }), { status: 200, headers: { 'content-type': 'application/json' } })))
    await expect(listWorkflowRunStats(7, { workflowId: 11 })).resolves.toEqual({ total: 1, items: [] })
    expect(String(vi.mocked(fetch).mock.calls[0][0])).toBe('/api/v1/rebuild/execution/run-stats?project_id=7&limit=50&workflow_id=11')
  })

  it('passes instance type, status, time range and pagination filters', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ code: 0, msg: 'success', data: { total: 0, items: [] } }), { status: 200, headers: { 'content-type': 'application/json' } })))
    await listWorkflowRunStats(7, {
      instanceType: 'STREAM', status: 'RUNNING', startedFrom: '2026-10-25T00:00:00Z',
      startedTo: '2026-10-26T00:00:00Z', offset: 50, limit: 25,
    })
    expect(String(vi.mocked(fetch).mock.calls[0][0])).toBe('/api/v1/rebuild/execution/run-stats?project_id=7&limit=25&instance_type=STREAM&status=RUNNING&started_from=2026-10-25T00%3A00%3A00Z&started_to=2026-10-26T00%3A00%3A00Z&offset=50')
  })

  it('loads one project-scoped run with table-level reconciliation details', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ code: 0, msg: 'success', data: { id: 5, details: [], detail_total: 0 } }), { status: 200, headers: { 'content-type': 'application/json' } })))
    await expect(getWorkflowRunStat(7, 5)).resolves.toMatchObject({ id: 5, detail_total: 0 })
    expect(String(vi.mocked(fetch).mock.calls[0][0])).toBe('/api/v1/rebuild/execution/run-stats/5?project_id=7&detail_limit=200')
  })
})
