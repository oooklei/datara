import { afterEach, describe, expect, it, vi } from 'vitest'
import { createSecAuditContract } from '../secAuditApi'

afterEach(() => vi.unstubAllGlobals())

describe('sec audit API contract', () => {
  it('serializes filters and maps snake-case access logs', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      code: 0,
      msg: 'success',
      data: {
        total: 1,
        facets: { allow: 1 },
        list: [{
          id: 9,
          user_name: 'admin',
          action: 'query',
          target: '/api/v1/rebuild/projects',
          rows_seen: 0,
          result: 'allow',
          reason: 'http_status_200',
          request_id: 'req-9',
          accessed_at: '2026-10-25T09:00:00',
        }],
      },
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)

    const page = await createSecAuditContract().listAccessLogs({
      userName: 'admin', action: 'query', result: 'allow', limit: 20, offset: 0,
    })

    const url = String(fetchMock.mock.calls[0]?.[0])
    expect(url).toContain('/api/v1/rebuild/sec/access-logs?')
    expect(url).toContain('user_name=admin')
    expect(page.list[0]).toMatchObject({
      userName: 'admin', rowsSeen: 0, requestId: 'req-9', accessedAt: '2026-10-25T09:00:00',
    })
  })
})
