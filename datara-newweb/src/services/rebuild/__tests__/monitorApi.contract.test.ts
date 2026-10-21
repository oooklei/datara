import { afterEach, describe, expect, it, vi } from 'vitest'

import { MONITOR_CONTRACT_METHODS, createMonitorContract } from '../monitorApi'

afterEach(() => vi.unstubAllGlobals())

describe('B3 monitorApi contract', () => {
  it('freezes the single read method', () => {
    expect(MONITOR_CONTRACT_METHODS).toEqual(['fetchMonitorNodes'])
    expect(typeof createMonitorContract().fetchMonitorNodes).toBe('function')
  })

  it('GETs the rebuild single-source endpoint with the shared token transport', async () => {
    localStorage.setItem('datara_token', 'monitor-token')
    const data = { zkAvailable: false, generatedAt: '2026-10-21 08:00:00', nodes: [] }
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ code: 0, msg: 'success', data }), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)
    await expect(createMonitorContract().fetchMonitorNodes()).resolves.toEqual(data)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/monitor/nodes')
    expect(init.method).toBe('GET')
    expect(new Headers(init.headers).get('token')).toBe('monitor-token')
  })

  it('preserves all three metric states and all three heartbeat states', async () => {
    const nodes = [
      { module: 'master', node: 'm1', cpu: 1, mem: 2, memUsedMb: 3, memTotalMb: 4, disk: 5, heartbeat: 'online', metricState: 'fresh', lastSeen: 't1', tags: [] },
      { module: 'worker', node: 'w1', cpu: null, mem: null, memUsedMb: null, memTotalMb: null, disk: null, heartbeat: 'offline', metricState: 'stale', lastSeen: null, tags: [] },
      { module: 'ssh', node: 's1', cpu: null, mem: null, memUsedMb: null, memTotalMb: null, disk: null, heartbeat: 'unknown', metricState: 'unsupported', lastSeen: null, tags: ['ops'] },
    ]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 0, msg: 'success', data: { zkAvailable: true, generatedAt: 't', nodes } }), { status: 200 })))
    const result = await createMonitorContract().fetchMonitorNodes()
    expect(result.nodes.map((row) => row.metricState)).toEqual(['fresh', 'stale', 'unsupported'])
    expect(result.nodes.map((row) => row.heartbeat)).toEqual(['online', 'offline', 'unknown'])
  })

  it('surfaces backend authentication errors through the shared contract error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 1001, msg: 'invalid token', data: null }), { status: 401 })))
    await expect(createMonitorContract().fetchMonitorNodes()).rejects.toMatchObject({
      name: 'ContractApiError',
      httpStatus: 401,
      code: 1001,
    })
  })
})
