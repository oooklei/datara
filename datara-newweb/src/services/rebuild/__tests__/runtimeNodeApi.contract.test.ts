import { afterEach, describe, expect, it, vi } from 'vitest'

import { RUNTIME_NODE_CONTRACT_METHODS, createRuntimeNodeContract } from '../runtimeNodeApi'

afterEach(() => vi.unstubAllGlobals())

describe('B6 runtimeNodeApi contract', () => {
  it('freezes the two read methods', () => {
    expect(RUNTIME_NODE_CONTRACT_METHODS).toEqual(['listRuntimeNodes', 'lsRuntimeNodeDir'])
    const contract = createRuntimeNodeContract()
    expect(typeof contract.listRuntimeNodes).toBe('function')
    expect(typeof contract.lsRuntimeNodeDir).toBe('function')
  })

  it('GETs the rebuild single-source list endpoint with the shared token transport', async () => {
    localStorage.setItem('datara_token', 'runtime-token')
    const data = [
      {
        id: 1,
        name: '1.9宿主机',
        kind: '远程',
        host: '192.168.1.9',
        port: 22,
        user: 'root',
        runtimeDir: '/opt/datara',
        status: 'offline',
        lastHeartbeat: null,
      },
    ]
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ code: 0, msg: 'success', data }), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)
    await expect(createRuntimeNodeContract().listRuntimeNodes()).resolves.toEqual(data)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/runtime-nodes')
    expect(init.method).toBe('GET')
    expect(new Headers(init.headers).get('token')).toBe('runtime-token')
  })

  it('GETs the ls endpoint with the snake path query and encodes the absolute path', async () => {
    localStorage.setItem('datara_token', 'runtime-token')
    const data = { path: '/opt/datara', entries: [{ name: 'logs', dir: true, size: 0, mtime: 1792700000 }] }
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ code: 0, msg: 'success', data }), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)
    await expect(createRuntimeNodeContract().lsRuntimeNodeDir(1, '/opt/datara')).resolves.toEqual(data)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/runtime-nodes/1/ls?path=%2Fopt%2Fdatara')
    expect(init.method).toBe('GET')
  })

  it('omits the query string when no path is given (remote home-dir semantics)', async () => {
    localStorage.setItem('datara_token', 'runtime-token')
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ code: 0, msg: 'success', data: { path: '/', entries: [] } }), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)
    await createRuntimeNodeContract().lsRuntimeNodeDir(1)
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/runtime-nodes/1/ls')
  })

  it('preserves the nine-field payload and never echoes credentials', async () => {
    const node = {
      id: 1,
      name: '1.9宿主机',
      kind: '远程',
      host: '192.168.1.9',
      port: 22,
      user: 'root',
      runtimeDir: '/opt/datara',
      status: 'offline',
      lastHeartbeat: null,
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 0, msg: 'success', data: [node] }), { status: 200 })))
    const result = await createRuntimeNodeContract().listRuntimeNodes()
    expect(Object.keys(result[0]).sort()).toEqual(
      ['host', 'id', 'kind', 'lastHeartbeat', 'name', 'port', 'runtimeDir', 'status', 'user'].sort(),
    )
    expect(JSON.stringify(result)).not.toContain('auth')
    expect(JSON.stringify(result)).not.toContain('password')
  })

  it('surfaces backend domain errors through the shared contract error (node not found)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 4101, msg: '运行时节点不存在', data: null }), { status: 404 })))
    await expect(createRuntimeNodeContract().lsRuntimeNodeDir(999)).rejects.toMatchObject({
      name: 'ContractApiError',
      httpStatus: 404,
      code: 4101,
    })
  })

  it('surfaces backend authentication errors through the shared contract error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 1001, msg: 'invalid token', data: null }), { status: 401 })))
    await expect(createRuntimeNodeContract().listRuntimeNodes()).rejects.toMatchObject({
      name: 'ContractApiError',
      httpStatus: 401,
      code: 1001,
    })
  })
})
