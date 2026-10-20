/**
 * L3-02 契约测试（node 语义，纯契约层无组件挂载；范式沿 metricsApi GREEN 批次）。
 * 端点实证：datara-backend/rebuild/api/app.py `GET /api/v1/rebuild/projects`
 *   → {code:0, msg:'success', data:{total, list:[{id, name}]}}。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { listProjects } from '../projectApi'

/** 后端成功包络形态（rebuild 域全域实证：{code:0,msg:'success',data}） */
function stubFetchWithEnvelope(data: unknown): ReturnType<typeof vi.fn> {
  return vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 0, msg: 'success', data }), { status: 200 }))
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('L3-02 projectApi contract (GET /api/v1/rebuild/projects)', () => {
  it('GETs /api/v1/rebuild/projects with token header and unwraps {total, list}', async () => {
    globalThis.localStorage?.setItem('datara_token', 'tok-1')
    const fetchMock = stubFetchWithEnvelope({
      total: 2,
      list: [
        { id: 1, name: '数据中台' },
        { id: 2, name: '风控治理' },
      ],
    })
    vi.stubGlobal('fetch', fetchMock)

    const page = await listProjects()

    expect(page).toEqual({
      total: 2,
      list: [
        { id: 1, name: '数据中台' },
        { id: 2, name: '风控治理' },
      ],
    })
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/projects')
    expect(init.method).toBe('GET')
    expect((init.headers as Record<string, string>).token).toBe('tok-1')
  })

  it('passes optional ownOrJoined through when backend delivers it (S243 注记 3.2 最小补兼容位)', async () => {
    const fetchMock = stubFetchWithEnvelope({
      total: 2,
      list: [
        { id: 7, name: '网关治理', ownOrJoined: 'owner' },
        { id: 8, name: '标签平台', ownOrJoined: 'joined' },
      ],
    })
    vi.stubGlobal('fetch', fetchMock)

    const page = await listProjects()

    expect(page.list[0]).toEqual({ id: 7, name: '网关治理', ownOrJoined: 'owner' })
    expect(page.list[1]).toEqual({ id: 8, name: '标签平台', ownOrJoined: 'joined' })
  })

  it('empty list unwraps to {total:0, list:[]}', async () => {
    const fetchMock = stubFetchWithEnvelope({ total: 0, list: [] })
    vi.stubGlobal('fetch', fetchMock)

    await expect(listProjects()).resolves.toEqual({ total: 0, list: [] })
  })

  it('non-2xx maps to ContractApiError with httpStatus preserved', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('boom', { status: 500 })))
    await expect(listProjects()).rejects.toMatchObject({
      httpStatus: 500,
      name: 'ContractApiError',
    })
  })

  it('envelope business error (code !== 0) maps to ContractApiError with the backend code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 1004, msg: '无权限', data: null }), { status: 200 })),
    )
    await expect(listProjects()).rejects.toMatchObject({
      httpStatus: 200,
      code: 1004,
      name: 'ContractApiError',
    })
  })
})
