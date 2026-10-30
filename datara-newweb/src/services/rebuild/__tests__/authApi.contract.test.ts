/**
 * I1 认证域契约测试（node 语义，纯契约层无组件挂载；范式沿 projectApi GREEN 批次）。
 * 端点实证：datara-backend/rebuild/api/app.py
 *   POST /api/v1/rebuild/login  body {username, password}
 *     → {code:0, msg:'success', data:{token, user:{id, username, role}}}
 *     401 {code:1001} 凭据无效；403 {code:1006} 账号停用（不签发 token）
 *   POST /api/v1/rebuild/logout → {code:0, msg:'success', data:null}
 * 登记簿 #23（2026-10-24 18R2-i 补登记时标注「测试缺位」缺口，本文件即补测）。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as authApi from '../authApi'
import { login, logout } from '../authApi'
import { clearToken, getToken, setToken } from '../../http'

function stubFetchWith(status: number, body: unknown): ReturnType<typeof vi.fn> {
  return vi
    .fn()
    .mockResolvedValue(new Response(JSON.stringify(body), { status }))
}

afterEach(() => {
  vi.unstubAllGlobals()
  clearToken()
  authApi.authAccount.value = null
})

describe('I1 authApi contract (POST /api/v1/rebuild/login)', () => {
  it('restores the current account from the authenticated session endpoint', async () => {
    const api = authApi as unknown as Record<string, unknown>
    expect(typeof api.currentSession).toBe('function')
    const fetchMock = stubFetchWith(200, {
      code: 0,
      msg: 'success',
      data: { id: 7, username: 'analyst', role: 'operator' },
    })
    vi.stubGlobal('fetch', fetchMock)
    setToken('tok-session-1')

    const account = await (api.currentSession as () => Promise<unknown>)()

    expect(account).toEqual({ id: 7, username: 'analyst', role: 'operator' })
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/rebuild/session', expect.objectContaining({ method: 'GET' }))
  })

  it('旧账号会话查询晚于 admin 登录返回时，不覆盖 admin 权限身份', async () => {
    let finishOldSession!: (response: Response) => void
    const fetchMock = vi.fn()
      .mockImplementationOnce(() => new Promise<Response>((resolve) => { finishOldSession = resolve }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        code: 0,
        data: { token: 'admin-token', user: { id: 1, username: 'admin', role: 'admin' } },
      }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    setToken('zhangsan-token')
    const staleSession = authApi.currentSession()
    await login('admin', 'secret')
    finishOldSession(new Response(JSON.stringify({
      code: 0,
      data: { id: 7, username: 'zhangsan', role: 'developer' },
    }), { status: 200 }))

    await expect(staleSession).rejects.toThrow('会话已切换')
    expect(authApi.authAccount.value).toEqual({ id: 1, username: 'admin', role: 'admin' })
    expect(getToken()).toBe('admin-token')
  })

  it('login POSTs anonymous {username,password}, keeps token in memory only, unwraps account', async () => {
    const fetchMock = stubFetchWith(200, {
      code: 0,
      msg: 'success',
      data: {
        token: 'tok-login-1',
        user: { id: 7, username: 'admin', role: 'admin' },
      },
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await login('admin', 'secret-1')

    expect(result).toEqual({
      token: 'tok-login-1',
      account: { id: 7, username: 'admin', role: 'admin' },
    })
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/login')
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toEqual({ username: 'admin', password: 'secret-1' })
    expect(getToken()).toBe('tok-login-1')
    expect(globalThis.localStorage?.getItem('datara_token')).toBeNull()
  })

  it('invalid credentials (401) maps to ContractApiError with httpStatus as code (1.2 冻结：非 2xx 不解析包络), no token stored', async () => {
    vi.stubGlobal(
      'fetch',
      stubFetchWith(401, { code: 1001, msg: 'invalid credentials', data: null }),
    )

    await expect(login('admin', 'wrong')).rejects.toMatchObject({
      httpStatus: 401,
      code: 401,
      name: 'ContractApiError',
    })
    expect(globalThis.localStorage?.getItem('datara_token')).toBeNull()
  })

  it('disabled account (403) maps to ContractApiError with httpStatus as code (1.2 冻结), no token stored', async () => {
    vi.stubGlobal(
      'fetch',
      stubFetchWith(403, { code: 1006, msg: 'account disabled', data: null }),
    )

    await expect(login('stale-user', 'secret-1')).rejects.toMatchObject({
      httpStatus: 403,
      code: 403,
      name: 'ContractApiError',
    })
    expect(globalThis.localStorage?.getItem('datara_token')).toBeNull()
  })
})

describe('I1 authApi contract (POST /api/v1/rebuild/logout)', () => {
  it('logout POSTs with token header then clears datara_token', async () => {
    setToken('tok-out-1')
    const fetchMock = stubFetchWith(200, { code: 0, msg: 'success', data: null })
    vi.stubGlobal('fetch', fetchMock)

    await expect(logout()).resolves.toBeUndefined()

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/logout')
    expect(init.method).toBe('POST')
    expect((init.headers as Record<string, string>).token).toBe('tok-out-1')
    expect(getToken()).toBe('')
    expect(globalThis.localStorage?.getItem('datara_token')).toBeNull()
  })

  it('backend revoke failure does not block local token cleanup (local state must converge)', async () => {
    setToken('tok-out-2')
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('boom', { status: 500 })),
    )

    await expect(logout()).resolves.toBeUndefined()
    expect(getToken()).toBe('')
    expect(globalThis.localStorage?.getItem('datara_token')).toBeNull()
  })
})
