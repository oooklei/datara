import { describe, expect, it } from 'vitest'

import { createScheduleCrudContract } from '../scheduleCrudApi'

describe('scheduleCrudApi split contract', () => {
  it('uses the rebuild 8001 seven-endpoint surface and keeps policy fields camelCase', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: String(input), init })
      return new Response(JSON.stringify({ code: 0, msg: 'success', data: { valid: true, nextFireTimes: [] } }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }) as typeof fetch

    const api = createScheduleCrudContract(7)
    await api.previewCrontab('0 0 1 * * *', 'UTC')

    expect(calls[0].url).toBe('/api/v1/rebuild/crontab-preview')
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ projectId: 7, crontab: '0 0 1 * * *', timezone: 'UTC' })
    expect(Object.keys(api).sort()).toEqual([
      'createSchedule', 'deleteSchedule', 'listSchedules', 'offlineSchedule',
      'onlineSchedule', 'previewCrontab', 'updateSchedule',
    ].sort())
  })
})
