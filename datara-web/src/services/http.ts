/**
 * fetch 封装（F6 REST 规范前端侧）：
 * - base '/api/v1'；自动携带 header token（localStorage 'datara_token'）
 * - 统一解包 {code,msg,data}，code!==0 时 throw Error(msg)
 * - 1xxx 错误段视为鉴权错 → 清 token 并跳登录（路由为 hash 模式 → location.hash='#/login'）
 * - 超时 15s（AbortController）
 */
import { localTime } from './mock/timeUtil'

const BASE = '/api/v1'
export const TOKEN_KEY = 'datara_token'
const TIMEOUT_MS = 15000

export function getToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? ''
  } catch {
    return ''
  }
}

export function setToken(token: string): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch { /* 私有模式等忽略 */ }
}

/** 鉴权失效跳登录（hash 路由既有裁定） */
function redirectToLogin(): void {
  setToken('')
  if (!location.hash.startsWith('#/login')) location.hash = '#/login'
}

export interface ApiEnvelope<T> { code: number; msg: string; data: T }

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS)
  try {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    const token = getToken()
    if (token) headers.token = token
    const res = await fetch(BASE + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: ctrl.signal,
    })
    const json = (await res.json().catch(() => null)) as ApiEnvelope<T> | null
    if (!json) throw new Error(`响应解析失败（HTTP ${res.status}）`)
    if (json.code !== 0) {
      // 1xxx 段 = 用户/鉴权错误（§6.3 错误码分段）
      if (json.code >= 1000 && json.code < 2000) redirectToLogin()
      /* I12-D2：挂 code 供调用方识别业务错误类型（如 2005 保存并发冲突） */
      const err = new Error(json.msg || `请求失败（code=${json.code}）`) as Error & { code?: number }
      err.code = json.code
      throw err
    }
    return json.data
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new Error('请求超时（15s），请检查后端服务')
    }
    throw err
  } finally {
    clearTimeout(timer)
  }
}

export const http = {
  get<T>(path: string): Promise<T> { return request<T>('GET', path) },
  post<T>(path: string, body?: unknown): Promise<T> { return request<T>('POST', path, body) },
  put<T>(path: string, body?: unknown): Promise<T> { return request<T>('PUT', path, body) },
  delete<T>(path: string): Promise<T> { return request<T>('DELETE', path) },
}

/** 后端时间 'YYYY-MM-DD HH:mm:ss' → 前端本地格式 'YYYY-MM-DD HH:mm'（禁止 toISOString 教训） */
export function toLocalMinute(s: string | undefined | null): string {
  const raw = String(s ?? '')
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(raw)) return raw.slice(0, 16)
  return raw || localTime()
}
