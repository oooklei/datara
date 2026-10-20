/**
 * FE 单 BASE 底座（WBS 1.2 / 权威设计 §7.1 / 0.7 方案 §5.3）。
 *
 * 职责（唯一上游，红线 1 / §7.1 单 BASE 拓扑）：
 *   - 单一 BASE `'/api/v1'`：nginx（prod）与 vite proxy（dev）统一反代到 `datara-rebuild-api:8001`；
 *   - token 自动携带（header `'token'`，与后端既有鉴权头同源）；
 *   - 包络三态统一解包（复用 adapterKit 冻结原语 `unwrapEnvelope` / `ContractApiError`，§5.4 冻结结论）；
 *   - 1xxx 跳登录（BE `common/resp.py` 1xxx = 用户/鉴权段：1001/1002/1003/1004/1005）；
 *   - 15s 超时（AbortController，超时归一为 `ContractApiError{code:'TIMEOUT'}`）。
 *
 * 明确不做（§7.1 红线 / 单 BASE 纪律）：
 *   - 不设 `LEGACY_BASE`、不做第二后端分派（旧后端 8000 完全不进新前端调用链路）；
 *   - 不做包络解包之外的语义加工（命名映射 / id 归一归契约层 adapterKit）；
 *   - 不接管登录页跳转之后的会话流程（仅触发跳转，会话重建归登录域）。
 *
 * 依赖方向：本底座 → `./rebuild/adapterKit`（冻结原语，不含 fetch，无环）。
 */

import { camelToSnakeKey, ContractApiError, unwrapEnvelope } from './rebuild/adapterKit'
import type { ApiEnvelope } from './rebuild/adapterKit'

export type { ApiEnvelope, ContractApiErrorInit } from './rebuild/adapterKit'
export { ContractApiError, unwrapEnvelope } from './rebuild/adapterKit'

/* ---------- 单 BASE（§7.1：唯一上游 rebuild-api:8001） ---------- */

/** 单一 BASE；nginx / vite 统一反代到 datara-rebuild-api(8001)。无第二 BASE、无 LEGACY_BASE。 */
export const BASE = '/api/v1' as const

/** BASE 别名（API 一源口径）。 */
export const API_BASE = BASE

/* ---------- token ---------- */

export const TOKEN_KEY = 'datara_token' as const

/** 后端鉴权头（与 rebuild 域既有鉴权读取同源）。 */
export const TOKEN_HEADER = 'token' as const

export function getToken(): string {
  return globalThis.localStorage?.getItem(TOKEN_KEY) ?? ''
}

export function setToken(token: string): void {
  if (!token) {
    clearToken()
    return
  }
  globalThis.localStorage?.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  globalThis.localStorage?.removeItem(TOKEN_KEY)
}

/* ---------- 15s 超时 ---------- */

export const HTTP_TIMEOUT_MS = 15_000 as const

/* ---------- 1xxx 跳登录 ---------- */

export const LOGIN_PATH = '/login' as const

/** BE `common/resp.py` 1xxx 段 = 用户/鉴权（1001 用户不存在 / 1002 密码错误 / 1003 会话失效 / 1004 无权限 / 1005 账号禁用）。 */
export const AUTH_ERROR_CODE_MIN = 1000
export const AUTH_ERROR_CODE_MAX = 1999

export type LoginRedirector = (target: string) => void

const defaultRedirector: LoginRedirector = (target) => {
  if (typeof window !== 'undefined' && window.location) {
    window.location.assign(target)
  }
}

let loginRedirector: LoginRedirector = defaultRedirector

/**
 * 注入 / 重置登录跳转器（SPA 路由接管或测试用）。
 * 传 `null` 恢复默认 `window.location.assign`。
 */
export function setLoginRedirector(fn: LoginRedirector | null): void {
  loginRedirector = fn ?? defaultRedirector
}

/** 是否 1xxx 鉴权错误码（BE 1xxx 段）。 */
export function isAuthErrorCode(code: number | string | undefined): boolean {
  if (typeof code !== 'number') return false
  return code >= AUTH_ERROR_CODE_MIN && code <= AUTH_ERROR_CODE_MAX
}

/* ---------- 请求选项 ---------- */

export type QueryParams = Record<string, string | number | boolean | undefined | null>

export interface RequestOptions {
  /** HTTP 方法（默认 GET）。 */
  method?: string
  /** 查询串；键经 `camelToSnakeKey` 转 wire 词形（幂等），undefined/null 剔除。 */
  query?: QueryParams
  /** JSON 请求体（plain DTO）；给定后自动置 `Content-Type: application/json` 并序列化。 */
  json?: unknown
  /** 原始请求体（BodyInit，如 FormData / Blob）；与 `json` 互斥，`json` 优先。 */
  body?: BodyInit | null
  headers?: Record<string, string>
  /** 匿名请求：不携带 token（登录等匿名端点）。 */
  anonymous?: boolean
  /** 超时覆盖（毫秒）；默认 `HTTP_TIMEOUT_MS`(15s)。传 `null` 表示**不设超时**（长耗时域：stream/sql-ide/ai-tools）。 */
  timeoutMs?: number | null
  /**
   * 非 2xx 时解析响应体包络并保留后端 `code`/`msg`（默认 `false`）。
   * 1.2 冻结行为（默认）：非 2xx 一律抛 `ContractApiError{httpStatus: res.status, code: res.status}`，不解析包络。
   * 契约层部分域（dependency/resources 等，A2 §2/§4 错误映射）需「非 2xx 但包络含 code 时保码透出」，
   * 故开放此开关；开启且包络无 `code` 时仍退回 HTTP 状态码错误。
   */
  preserveEnvelopeCode?: boolean
  /** 透传 fetch 其余参数（method / credentials / mode / cache 等）。
   *  `headers` / `body` / `signal` 由本底座独占（分别用于 token+JSON、请求体、超时控制），不从此处透传。 */
  init?: Omit<RequestInit, 'headers' | 'body' | 'signal'>
}

/* ---------- URL 组装 ---------- */

/** 拼 BASE + path（path 缺前导斜杠时补），查询串 camel→snake 序列化。 */
function buildUrl(path: string, query?: QueryParams): string {
  const base = `${BASE}${path.startsWith('/') ? path : `/${path}`}`
  if (!query) return base
  const qs = Object.entries(query)
    .filter(([, value]) => value !== undefined && value !== null)
    .map(([key, value]) => `${encodeURIComponent(camelToSnakeKey(key))}=${encodeURIComponent(String(value))}`)
    .join('&')
  return qs ? `${base}?${qs}` : base
}

/* ---------- 错误归一辅助 ---------- */

function isAbortError(err: unknown): boolean {
  return typeof err === 'object' && err !== null && (err as { name?: unknown }).name === 'AbortError'
}

/** 宽松解析响应文本为包络（非 JSON / 非对象 → undefined）；仅供 `preserveEnvelopeCode` 保码透出使用。 */
function parseEnvelope(text: string): ApiEnvelope | undefined {
  if (text.trim() === '') return undefined
  try {
    const parsed = JSON.parse(text) as unknown
    if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) return parsed as ApiEnvelope
    return undefined
  } catch {
    return undefined
  }
}

/* ---------- 底座核心 ---------- */

/**
 * 单 BASE 请求底座：token 携带 + 15s 超时 + 非 2xx 抛错 + 包络三态解包 + 1xxx 跳登录。
 * 返回已解包的 `data`（`code === 0 / 200 / undefined`）；业务错误与系统错误均以 rejected promise
 * 携带 `ContractApiError`（与 RED 契约方法形态一致，UI 捕获方式不因接线改变）。
 */
export async function request<T = unknown>(path: string, options: RequestOptions = {}): Promise<T> {
  const {
    query,
    json,
    body,
    headers,
    anonymous = false,
    timeoutMs,
    preserveEnvelopeCode = false,
    init: fetchInit,
  } = options
  const url = buildUrl(path, query)
  const effectiveTimeout = timeoutMs === null ? null : (timeoutMs ?? HTTP_TIMEOUT_MS)
  const ctrl = new AbortController()
  const timer = effectiveTimeout === null ? null : setTimeout(() => ctrl.abort(), effectiveTimeout)
  try {
    const finalHeaders: Record<string, string> = { ...headers }
    if (json !== undefined) finalHeaders['Content-Type'] = 'application/json'
    if (!anonymous) {
      const token = getToken()
      if (token) finalHeaders[TOKEN_HEADER] = token
    }

    const init: RequestInit = {
      ...fetchInit,
      method: options.method ?? 'GET',
      headers: finalHeaders,
      signal: ctrl.signal,
      ...(json !== undefined ? { body: JSON.stringify(json) } : body !== undefined ? { body } : {}),
    }
    const res = await fetch(url, init)

    // 系统错误：非 2xx 在解包前抛错（包络三态之第三态）
    if (!res.ok) {
      const raw = await res.text().catch(() => '')
      // 保码透出（preserveEnvelopeCode）：非 2xx 但包络含 code 时保留后端码（A2 §2/§4 错误映射）；
      // 包络无 code 或非 JSON 时退回 HTTP 状态码错误（与默认行为一致）。
      if (preserveEnvelopeCode) {
        const parsed = parseEnvelope(raw)
        if (parsed && parsed.code !== undefined) {
          throw new ContractApiError({ httpStatus: res.status, code: parsed.code, msg: parsed.msg ?? path, raw: parsed })
        }
      }
      throw new ContractApiError({ httpStatus: res.status, code: res.status, msg: `HTTP ${res.status} ${path}`, raw })
    }

    const text = await res.text()
    // 空响应体（如 204）：无包络可解包，返回 undefined
    if (text.trim() === '') return undefined as T

    const envelope = JSON.parse(text) as ApiEnvelope
    try {
      return unwrapEnvelope<T>(envelope, res.status)
    } catch (err) {
      // 业务错误：1xxx 段触发跳登录后继续抛出（UI 仍按 ContractApiError 捕获）
      if (err instanceof ContractApiError && isAuthErrorCode(err.code)) {
        loginRedirector(LOGIN_PATH)
      }
      throw err
    }
  } catch (err) {
    if (isAbortError(err)) {
      throw new ContractApiError({ httpStatus: 0, code: 'TIMEOUT', msg: `请求超时（${(effectiveTimeout ?? 0) / 1000}s）${path}` })
    }
    throw err
  } finally {
    if (timer !== null) clearTimeout(timer)
  }
}

/* ---------- 原始响应通道（无包络解包 / 无错误归一） ---------- */

export type RawRequestOptions = Omit<RequestOptions, 'preserveEnvelopeCode'>

/**
 * 原始响应通道：token 携带 + 超时（可 `null` 不设）+ 非 2xx **不**抛错 + 响应体按 JSON 原样返回。
 * 供非 `{code,msg,data}` 包络形态的域使用（如 R8A ai-tools 的领域包络）。
 * 与 `request` 共享同一传输核心（同 BASE / 同 token / 同超时机制），仅去掉包络解包与错误归一。
 */
export async function requestRaw<T = unknown>(path: string, options: RawRequestOptions = {}): Promise<T> {
  const { query, json, body, headers, anonymous = false, timeoutMs, init: fetchInit } = options
  const url = buildUrl(path, query)
  const effectiveTimeout = timeoutMs === null ? null : (timeoutMs ?? HTTP_TIMEOUT_MS)
  const ctrl = new AbortController()
  const timer = effectiveTimeout === null ? null : setTimeout(() => ctrl.abort(), effectiveTimeout)
  try {
    const finalHeaders: Record<string, string> = { ...headers }
    if (json !== undefined) finalHeaders['Content-Type'] = 'application/json'
    if (!anonymous) {
      const token = getToken()
      if (token) finalHeaders[TOKEN_HEADER] = token
    }
    const init: RequestInit = {
      ...fetchInit,
      method: options.method ?? 'GET',
      headers: finalHeaders,
      signal: ctrl.signal,
      ...(json !== undefined ? { body: JSON.stringify(json) } : body !== undefined ? { body } : {}),
    }
    const res = await fetch(url, init)
    const text = await res.text()
    if (text.trim() === '') return undefined as T
    return JSON.parse(text) as T
  } catch (err) {
    if (isAbortError(err)) {
      throw new ContractApiError({ httpStatus: 0, code: 'TIMEOUT', msg: `请求超时（${(effectiveTimeout ?? 0) / 1000}s）${path}` })
    }
    throw err
  } finally {
    if (timer !== null) clearTimeout(timer)
  }
}

/* ---------- 动词便捷方法 ---------- */

export type VerbOptions = Omit<RequestOptions, 'json' | 'body' | 'method'>

/** GET：查询串 camel→snake 序列化，响应包络解包。 */
export function getJson<T = unknown>(path: string, query?: QueryParams, options?: VerbOptions): Promise<T> {
  return request<T>(path, { ...options, method: 'GET', query })
}

/** POST：JSON 请求体，响应包络解包。 */
export function postJson<T = unknown>(path: string, json?: unknown, options?: VerbOptions): Promise<T> {
  return request<T>(path, { ...options, method: 'POST', json })
}

/** PUT：JSON 请求体，响应包络解包。 */
export function putJson<T = unknown>(path: string, json?: unknown, options?: VerbOptions): Promise<T> {
  return request<T>(path, { ...options, method: 'PUT', json })
}

/** PATCH：JSON 请求体，响应包络解包。 */
export function patchJson<T = unknown>(path: string, json?: unknown, options?: VerbOptions): Promise<T> {
  return request<T>(path, { ...options, method: 'PATCH', json })
}

/** DELETE：响应包络解包。 */
export function deleteJson<T = unknown>(path: string, options?: VerbOptions): Promise<T> {
  return request<T>(path, { ...options, method: 'DELETE' })
}
