/**
 * http.ts 单 BASE 底座单元测试（WBS 1.2 / 权威设计 §7.1）。
 * 覆盖：单 BASE 常量化 + 无 LEGACY_BASE/无 8000 旧后端旁路（红线 1 负断言）、
 * token 携带（含 anonymous 跳过）、包络三态解包（成功 0/200/undefined、业务错误、非 2xx 系统错误）、
 * 1xxx 跳登录（BE 1xxx 鉴权段）、15s 超时归一、查询串 camel→snake 序列化、
 * JSON 请求体 / 原始请求体透传、动词便捷方法 method 正确性。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import httpSource from '../http.ts?raw'
import {
  API_BASE,
  AUTH_ERROR_CODE_MAX,
  AUTH_ERROR_CODE_MIN,
  BASE,
  ContractApiError,
  HTTP_TIMEOUT_MS,
  LOGIN_PATH,
  TOKEN_KEY,
  clearToken,
  deleteJson,
  getJson,
  getToken,
  isAuthErrorCode,
  patchJson,
  postJson,
  putJson,
  request,
  requestRaw,
  setLoginRedirector,
  setToken,
} from '../http'
import * as httpModule from '../http'

/* ---------- 测试夹具 ---------- */

type FetchStub = ReturnType<typeof vi.fn>

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => (typeof body === 'string' ? body : JSON.stringify(body)),
  } as unknown as Response
}

function envelopeResponse(status: number, envelope: unknown): Response {
  return jsonResponse(status, envelope)
}

let fetchStub: FetchStub

beforeEach(() => {
  fetchStub = vi.fn()
  vi.stubGlobal('fetch', fetchStub)
  localStorage.clear()
  setLoginRedirector(null)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
  setLoginRedirector(null)
})

/* ---------- 1. 单 BASE 与一源红线（§7.1） ---------- */

describe('单 BASE 底座与一源红线（§7.1 / 红线 1）', () => {
  it('BASE 常量化为 /api/v1，API_BASE 与之一致', () => {
    expect(BASE).toBe('/api/v1')
    expect(API_BASE).toBe(BASE)
  })

  it('模块不导出 LEGACY_BASE（无双源）', () => {
    expect('LEGACY_BASE' in httpModule).toBe(false)
  })

  it('底座代码不含 LEGACY_BASE / 旧后端 8000 / 旧 datara-api 反代（红线负断言）', () => {
    const raw = httpSource
    // 仅断言代码（剥离注释；注释中说明「不设 LEGACY_BASE」属正当表述）
    const code = raw.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '')
    expect(code).not.toContain('LEGACY_BASE')
    expect(code).not.toContain('8000')
    expect(code).not.toContain('datara-api')
    // 唯一 BASE 事实源：BASE 赋值仅出现一次
    const baseMarker = "export const BASE = '/api/v1'"
    expect(code.split(baseMarker)).toHaveLength(2)
  })
})

/* ---------- 2. token 携带 ---------- */

describe('token 携带', () => {
  it('localStorage 有 token 时自动携带 token 头', async () => {
    setToken('tok-abc')
    fetchStub.mockResolvedValue(envelopeResponse(200, { code: 0, msg: 'success', data: { ok: true } }))

    await request('/rebuild/ping')

    const [, init] = fetchStub.mock.calls[0] as [string, RequestInit]
    expect((init.headers as Record<string, string>).token).toBe('tok-abc')
  })

  it('无 token 时不携带 token 头', async () => {
    fetchStub.mockResolvedValue(envelopeResponse(200, { code: 0, data: {} }))

    await request('/rebuild/ping')

    const [, init] = fetchStub.mock.calls[0] as [string, RequestInit]
    expect((init.headers as Record<string, string>).token).toBeUndefined()
  })

  it('anonymous: true 跳过 token 携带（登录等匿名端点）', async () => {
    setToken('tok-abc')
    fetchStub.mockResolvedValue(envelopeResponse(200, { code: 0, data: {} }))

    await request('/rebuild/login', { anonymous: true })

    const [, init] = fetchStub.mock.calls[0] as [string, RequestInit]
    expect((init.headers as Record<string, string>).token).toBeUndefined()
  })

  it('setToken / getToken / clearToken 与 TOKEN_KEY 落位一致', () => {
    expect(TOKEN_KEY).toBe('datara_token')
    expect(getToken()).toBe('')
    setToken('tok-1')
    expect(getToken()).toBe('tok-1')
    setToken('')
    expect(getToken()).toBe('')
    setToken('tok-2')
    clearToken()
    expect(getToken()).toBe('')
  })
})

/* ---------- 3. 包络三态解包（§5.4 冻结） ---------- */

describe('包络三态解包', () => {
  it('code === 0 → resolve(data)', async () => {
    fetchStub.mockResolvedValue(envelopeResponse(200, { code: 0, msg: 'success', data: { rowsTotal: 3 } }))
    await expect(request('/rebuild/x')).resolves.toEqual({ rowsTotal: 3 })
  })

  it('code === 200 → resolve(data)', async () => {
    fetchStub.mockResolvedValue(envelopeResponse(200, { code: 200, msg: 'success', data: [1, 2] }))
    await expect(request('/rebuild/x')).resolves.toEqual([1, 2])
  })

  it('code === undefined（裸 JSON）→ resolve(整个载荷)', async () => {
    fetchStub.mockResolvedValue(envelopeResponse(200, { items: [{ id: 1 }] }))
    await expect(request('/rebuild/x')).resolves.toEqual({ items: [{ id: 1 }] })
  })

  it('data 键存在且为 null → resolve(null)', async () => {
    fetchStub.mockResolvedValue(envelopeResponse(200, { code: 0, data: null }))
    await expect(request('/rebuild/x')).resolves.toBeNull()
  })

  it('code ≠ 0/200（业务错误）→ throw ContractApiError{httpStatus, code, msg}', async () => {
    fetchStub.mockResolvedValue(envelopeResponse(200, { code: 4001, msg: '数据源不存在', data: null }))

    const err = await request('/rebuild/x').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ContractApiError)
    expect(err).toMatchObject({ httpStatus: 200, code: 4001, msg: '数据源不存在' })
  })

  it('非 2xx（系统错误）→ 解包前抛 ContractApiError{httpStatus: 500}', async () => {
    fetchStub.mockResolvedValue(jsonResponse(500, 'boom'))

    const err = await request('/rebuild/x').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ContractApiError)
    expect(err).toMatchObject({ httpStatus: 500, code: 500 })
  })

  it('非 2xx 时 raw 保留原始响应文本（诊断用）', async () => {
    fetchStub.mockResolvedValue(jsonResponse(503, 'service unavailable'))

    const err = await request('/rebuild/x').catch((e: unknown) => e)
    expect((err as ContractApiError).raw).toBe('service unavailable')
  })

  it('preserveEnvelopeCode（默认关）：非 2xx 包络含 code 也不保码，仍抛 HTTP 状态码（1.2 冻结行为）', async () => {
    fetchStub.mockResolvedValue(envelopeResponse(400, { code: 'DEP_INVALID_WINDOW', msg: 'bad window', data: null }))

    const err = await request('/rebuild/x').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ContractApiError)
    expect(err).toMatchObject({ httpStatus: 400, code: 400 })
  })

  it('preserveEnvelopeCode: 非 2xx 但包络含 code → 保码透出（httpStatus 同步保留，契约层 A2 §2/§4）', async () => {
    fetchStub.mockResolvedValue(envelopeResponse(400, { code: 'DEP_INVALID_WINDOW', msg: 'bad window', data: null }))

    const err = await request('/rebuild/x', { preserveEnvelopeCode: true }).catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ContractApiError)
    expect(err).toMatchObject({ httpStatus: 400, code: 'DEP_INVALID_WINDOW', msg: 'bad window' })
    expect((err as ContractApiError).raw).toMatchObject({ code: 'DEP_INVALID_WINDOW' })
  })

  it('preserveEnvelopeCode: 包络为数值码（4001/1001/1003/4041）同样保码', async () => {
    fetchStub.mockResolvedValue(envelopeResponse(404, { code: 4041, msg: 'not found', data: null }))

    const err = await request('/rebuild/x', { preserveEnvelopeCode: true }).catch((e: unknown) => e)
    expect(err).toMatchObject({ httpStatus: 404, code: 4041 })
  })

  it('preserveEnvelopeCode: 包络无 code（非 JSON / 无 code 字段）→ 退回 HTTP 状态码错误', async () => {
    fetchStub.mockResolvedValue(jsonResponse(500, 'boom'))
    const errA = await request('/rebuild/x', { preserveEnvelopeCode: true }).catch((e: unknown) => e)
    expect(errA).toMatchObject({ httpStatus: 500, code: 500 })

    fetchStub.mockResolvedValue(envelopeResponse(500, { msg: 'no code here' }))
    const errB = await request('/rebuild/x', { preserveEnvelopeCode: true }).catch((e: unknown) => e)
    expect(errB).toMatchObject({ httpStatus: 500, code: 500 })
  })

  it('空响应体（204）→ resolve(undefined)', async () => {
    fetchStub.mockResolvedValue(jsonResponse(204, ''))
    await expect(request('/rebuild/x')).resolves.toBeUndefined()
  })
})

/* ---------- 4. 1xxx 跳登录 ---------- */

describe('1xxx 跳登录（BE 1xxx=用户/鉴权段）', () => {
  it('1003 会话失效 → 跳转 /login 且仍抛 ContractApiError', async () => {
    const redirects: string[] = []
    setLoginRedirector((target) => redirects.push(target))
    fetchStub.mockResolvedValue(envelopeResponse(200, { code: 1003, msg: '未登录或会话已过期', data: null }))

    const err = await request('/rebuild/x').catch((e: unknown) => e)
    expect(redirects).toEqual([LOGIN_PATH])
    expect(err).toBeInstanceOf(ContractApiError)
    expect(err).toMatchObject({ code: 1003 })
  })

  it('1xxx 全段（1001/1002/1004/1005）均跳登录', async () => {
    for (const code of [1001, 1002, 1003, 1004, 1005]) {
      const redirects: string[] = []
      setLoginRedirector((target) => redirects.push(target))
      fetchStub.mockResolvedValue(envelopeResponse(200, { code, msg: 'auth', data: null }))
      await request('/rebuild/x').catch(() => undefined)
      expect(redirects).toEqual([LOGIN_PATH])
    }
  })

  it('非 1xxx 业务错误（4xxx/5xxx）不跳登录', async () => {
    const redirects: string[] = []
    setLoginRedirector((target) => redirects.push(target))
    fetchStub.mockResolvedValue(envelopeResponse(200, { code: 4002, msg: '参数错误', data: null }))

    await request('/rebuild/x').catch(() => undefined)
    expect(redirects).toEqual([])
  })

  it('默认跳转器调用 window.location.assign（SPA History 路由）', async () => {
    const assign = vi.fn()
    vi.stubGlobal('window', { ...window, location: { ...window.location, assign } })
    fetchStub.mockResolvedValue(envelopeResponse(200, { code: 1003, msg: 'expired', data: null }))

    await request('/rebuild/x').catch(() => undefined)
    expect(assign).toHaveBeenCalledWith('/login')
  })

  it('isAuthErrorCode 边界：1000/1999 命中，999/2000/字符串不命中', () => {
    expect(AUTH_ERROR_CODE_MIN).toBe(1000)
    expect(AUTH_ERROR_CODE_MAX).toBe(1999)
    expect(isAuthErrorCode(1000)).toBe(true)
    expect(isAuthErrorCode(1999)).toBe(true)
    expect(isAuthErrorCode(999)).toBe(false)
    expect(isAuthErrorCode(2000)).toBe(false)
    expect(isAuthErrorCode('1003')).toBe(false)
    expect(isAuthErrorCode(undefined)).toBe(false)
  })
})

/* ---------- 5. 15s 超时 ---------- */

describe('15s 超时（AbortController）', () => {
  it('HTTP_TIMEOUT_MS 常量化为 15000', () => {
    expect(HTTP_TIMEOUT_MS).toBe(15000)
  })

  it('默认超时 → ContractApiError{code:"TIMEOUT"}', async () => {
    vi.useFakeTimers()
    fetchStub.mockImplementation(
      (_url: string, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => {
            const err = new Error('aborted')
            err.name = 'AbortError'
            reject(err)
          })
        }),
    )

    const pending = request('/rebuild/slow').catch((e: unknown) => e)
    await vi.advanceTimersByTimeAsync(15_000)

    const err = await pending
    expect(err).toBeInstanceOf(ContractApiError)
    expect(err).toMatchObject({ httpStatus: 0, code: 'TIMEOUT' })
  })

  it('timeoutMs 覆盖生效（5s）', async () => {
    vi.useFakeTimers()
    const abortSignals: Array<AbortSignal | undefined> = []
    fetchStub.mockImplementation(
      (_url: string, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          abortSignals.push(init?.signal ?? undefined)
          init?.signal?.addEventListener('abort', () => {
            const err = new Error('aborted')
            err.name = 'AbortError'
            reject(err)
          })
        }),
    )

    const pending = request('/rebuild/slow', { timeoutMs: 5_000 }).catch((e: unknown) => e)
    await vi.advanceTimersByTimeAsync(5_000)

    const err = await pending
    expect(err).toBeInstanceOf(ContractApiError)
    expect((err as ContractApiError).code).toBe('TIMEOUT')
    expect(abortSignals[0]?.aborted).toBe(true)
  })

  it('请求成功时清除定时器（无悬挂 abort）', async () => {
    fetchStub.mockResolvedValue(envelopeResponse(200, { code: 0, data: {} }))
    await request('/rebuild/x')
    // 若 finally 未清除定时器，advance 后信号会 abort（此处断言信号未 abort）
    const [, init] = fetchStub.mock.calls[0] as [string, RequestInit]
    expect((init.signal as AbortSignal).aborted).toBe(false)
  })
})

/* ---------- 6. URL 与查询串 ---------- */

describe('URL 组装与查询串序列化', () => {
  it('BASE + path 拼接，缺前导斜杠时补', async () => {
    fetchStub.mockResolvedValue(envelopeResponse(200, { code: 0, data: {} }))
    await request('rebuild/x')
    expect(fetchStub.mock.calls[0]?.[0]).toBe('/api/v1/rebuild/x')
  })

  it('查询键 camel→snake，undefined/null 剔除', async () => {
    fetchStub.mockResolvedValue(envelopeResponse(200, { code: 0, data: {} }))
    await request('/rebuild/x', { query: { rowsTotal: 10, orderBy: 'createdAt', skip: undefined, drop: null } })
    expect(fetchStub.mock.calls[0]?.[0]).toBe('/api/v1/rebuild/x?rows_total=10&order_by=createdAt')
  })

  it('布尔与数值查询值转字符串', async () => {
    fetchStub.mockResolvedValue(envelopeResponse(200, { code: 0, data: {} }))
    await request('/rebuild/x', { query: { onlyActive: true, limit: 200 } })
    expect(fetchStub.mock.calls[0]?.[0]).toBe('/api/v1/rebuild/x?only_active=true&limit=200')
  })

  it('特殊字符查询值经 encodeURIComponent', async () => {
    fetchStub.mockResolvedValue(envelopeResponse(200, { code: 0, data: {} }))
    await request('/rebuild/x', { query: { name: 'a b&c' } })
    expect(fetchStub.mock.calls[0]?.[0]).toBe('/api/v1/rebuild/x?name=a%20b%26c')
  })
})

/* ---------- 7. 请求体 ---------- */

describe('请求体处理', () => {
  it('json 给定 → Content-Type: application/json 且体为序列化 JSON', async () => {
    fetchStub.mockResolvedValue(envelopeResponse(200, { code: 0, data: {} }))
    await request('/rebuild/x', { method: 'POST', json: { name: 'n', rowsTotal: 2 } })

    const [, init] = fetchStub.mock.calls[0] as [string, RequestInit]
    expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json')
    expect(init.body).toBe(JSON.stringify({ name: 'n', rowsTotal: 2 }))
    expect(init.method).toBe('POST')
  })

  it('原始 body（FormData/Blob）透传且不强制 Content-Type', async () => {
    fetchStub.mockResolvedValue(envelopeResponse(200, { code: 0, data: {} }))
    const form = new FormData()
    await request('/rebuild/x', { method: 'POST', body: form })

    const [, init] = fetchStub.mock.calls[0] as [string, RequestInit]
    expect(init.body).toBe(form)
    expect((init.headers as Record<string, string>)['Content-Type']).toBeUndefined()
  })

  it('json 与 body 同时给定时 json 优先', async () => {
    fetchStub.mockResolvedValue(envelopeResponse(200, { code: 0, data: {} }))
    await request('/rebuild/x', { method: 'POST', json: { a: 1 }, body: 'raw' })

    const [, init] = fetchStub.mock.calls[0] as [string, RequestInit]
    expect(init.body).toBe(JSON.stringify({ a: 1 }))
  })

  it('init 透传 credentials / mode，signal 由底座独占', async () => {
    fetchStub.mockResolvedValue(envelopeResponse(200, { code: 0, data: {} }))
    await request('/rebuild/x', { init: { credentials: 'include', mode: 'cors' } })

    const [, init] = fetchStub.mock.calls[0] as [string, RequestInit]
    expect(init.credentials).toBe('include')
    expect(init.mode).toBe('cors')
    expect(init.signal).toBeInstanceOf(AbortSignal)
  })

  it('默认 method 为 GET', async () => {
    fetchStub.mockResolvedValue(envelopeResponse(200, { code: 0, data: {} }))
    await request('/rebuild/x')
    const [, init] = fetchStub.mock.calls[0] as [string, RequestInit]
    expect(init.method).toBe('GET')
  })
})

/* ---------- 8. 动词便捷方法 ---------- */

describe('动词便捷方法', () => {
  const cases: Array<[string, (p: string) => Promise<unknown>, string]> = [
    ['getJson', getJson, 'GET'],
    ['postJson', (p) => postJson(p, { a: 1 }), 'POST'],
    ['putJson', (p) => putJson(p, { a: 1 }), 'PUT'],
    ['patchJson', (p) => patchJson(p, { a: 1 }), 'PATCH'],
    ['deleteJson', deleteJson, 'DELETE'],
  ]

  for (const [name, call, method] of cases) {
    it(`${name} 使用 ${method} 且解包 data`, async () => {
      fetchStub.mockResolvedValue(envelopeResponse(200, { code: 0, data: { via: name } }))
      await expect(call('/rebuild/x')).resolves.toEqual({ via: name })
      const [, init] = fetchStub.mock.calls[0] as [string, RequestInit]
      expect(init.method).toBe(method)
    })
  }
})

/* ---------- 9. timeoutMs: null（不设超时） ---------- */

describe('timeoutMs: null（长耗时域不设超时）', () => {
  it('timeoutMs: null → 不挂 abort 定时器（挂起请求不因超时归一 TIMEOUT）', async () => {
    vi.useFakeTimers()
    try {
      fetchStub.mockImplementation((_url: string, init?: RequestInit) => new Promise((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => {
          const e = new Error('aborted') as Error & { name?: string }
          e.name = 'AbortError'
          reject(e)
        })
      }))
      const pending = request('/rebuild/stream/jobs', { timeoutMs: null })
      await vi.advanceTimersByTimeAsync(60_000)
      // 未 abort：promise 仍挂起（不是 TIMEOUT 拒绝）
      let settled = false
      void pending.catch(() => { settled = true })
      await Promise.resolve()
      expect(settled).toBe(false)
    } finally {
      vi.useRealTimers()
    }
  })

  it('timeoutMs 缺省仍为 15s（HTTP_TIMEOUT_MS 常量不变）', () => {
    expect(HTTP_TIMEOUT_MS).toBe(15000)
  })
})

/* ---------- 10. requestRaw（原始响应通道） ---------- */

describe('requestRaw（无包络解包 / 无错误归一）', () => {
  it('返回响应体 JSON 原样（不做 {code,msg,data} 解包）', async () => {
    fetchStub.mockResolvedValue(jsonResponse(200, { status: 'ERROR', error: { code: 'TOOL_NOT_FOUND' } }))
    await expect(requestRaw('/rebuild/ai/tool-calls')).resolves.toEqual({
      status: 'ERROR',
      error: { code: 'TOOL_NOT_FOUND' },
    })
  })

  it('非 2xx 也不抛错（与 request 的系统错误态相反）', async () => {
    fetchStub.mockResolvedValue(jsonResponse(500, { status: 'ERROR', error: { code: 'BOOM' } }))
    await expect(requestRaw('/rebuild/ai/tools')).resolves.toMatchObject({ status: 'ERROR' })
  })

  it('token 携带与超时机制与 request 同源（同底座传输核心）', async () => {
    setToken('t-raw')
    fetchStub.mockResolvedValue(jsonResponse(200, { ok: true }))
    await requestRaw('/rebuild/ai/tools', { method: 'POST', json: { a: 1 } })
    const [url, init] = fetchStub.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/ai/tools')
    expect((init.headers as Record<string, string>).token).toBe('t-raw')
    expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json')
    expect(init.method).toBe('POST')
    clearToken()
  })

  it('timeoutMs: null 时不挂超时定时器', async () => {
    vi.useFakeTimers()
    try {
      fetchStub.mockImplementation((_url: string, init?: RequestInit) => new Promise((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => {
          const e = new Error('aborted') as Error & { name?: string }
          e.name = 'AbortError'
          reject(e)
        })
      }))
      const pending = requestRaw('/rebuild/ai/tools', { timeoutMs: null })
      await vi.advanceTimersByTimeAsync(60_000)
      let settled = false
      void pending.catch(() => { settled = true })
      await Promise.resolve()
      expect(settled).toBe(false)
    } finally {
      vi.useRealTimers()
    }
  })
})
