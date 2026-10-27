import { afterEach, describe, expect, it, vi } from 'vitest'
import { governanceApi } from '../governanceApi'

afterEach(() => vi.unstubAllGlobals())

const envelope = (data: unknown) => new Response(JSON.stringify({ code: 0, msg: 'success', data }), {
  status: 200,
  headers: { 'Content-Type': 'application/json' },
})

describe('quality read-only views API', () => {
  it('connects exceptions, reports, and alarms to project-scoped endpoints', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(envelope({ total: 1, list: [{ id: 1, target: 'orders', hit_count: 2, status: 'open' }] }))
      .mockResolvedValueOnce(envelope({ total: 1, list: [{ id: 2, title: '日报', created_by: 'admin', content: {} }] }))
      .mockResolvedValueOnce(envelope({ total: 1, list: [{ id: 3, name: '失败率', last_fired_at: null, enabled: true }] }))
    vi.stubGlobal('fetch', fetchMock)

    const exceptions = await governanceApi.listExceptions(7, 1, 50, 'open')
    const reports = await governanceApi.listReports(7)
    const alarms = await governanceApi.listAlarmPolicies(7)

    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('/projects/7/quality-exceptions?page=1&page_size=50&status=open')
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain('/projects/7/quality-reports?page=1&page_size=50')
    expect(String(fetchMock.mock.calls[2]?.[0])).toContain('/projects/7/quality-alarm-policies?page=1&page_size=50')
    expect(exceptions.list[0]).toMatchObject({ hitCount: 2 })
    expect(reports.list[0]).toMatchObject({ createdBy: 'admin' })
    expect(alarms.list[0]).toMatchObject({ lastFiredAt: null })
  })

  it('connects exception disposition, report generation, and alarm policy writes', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(envelope({ id: 1, status: 'resolved', fix_note: 'fixed', handled_by: 'dev' }))
      .mockResolvedValueOnce(envelope({ id: 2, title: '日报', content: { run_count: 0 } }))
      .mockResolvedValueOnce(envelope({ id: 3, name: '失败行', enabled: true }))
      .mockResolvedValueOnce(envelope({ id: 3, name: '失败行', enabled: false }))
    vi.stubGlobal('fetch', fetchMock)

    await governanceApi.disposeException(7, 1, { status: 'resolved', fixNote: 'fixed' })
    await governanceApi.createReport(7, { title: '日报', scope: 'project', period: 'daily' })
    await governanceApi.createAlarmPolicy(7, {
      name: '失败行', scope: 'project', metric: 'failed_rows', operator: '>', threshold: 0, enabled: true,
    })
    await governanceApi.setAlarmPolicyEnabled(7, 3, false)

    expect(fetchMock.mock.calls.map((call) => String(call[0]))).toEqual([
      expect.stringContaining('/projects/7/quality-exceptions/1'),
      expect.stringContaining('/projects/7/quality-reports'),
      expect.stringContaining('/projects/7/quality-alarm-policies'),
      expect.stringContaining('/projects/7/quality-alarm-policies/3/enabled'),
    ])
    expect(fetchMock.mock.calls.map((call) => (call[1] as RequestInit).method)).toEqual([
      'PATCH', 'POST', 'POST', 'PATCH',
    ])
    expect(JSON.parse(String((fetchMock.mock.calls[0]?.[1] as RequestInit).body))).toEqual({
      status: 'resolved', fix_note: 'fixed',
    })
  })
})
