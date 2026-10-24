import { camelToSnake, snakeToCamel, ContractApiError } from './adapterKit'
import { getToken } from '../http'

export interface ApiKeyRow { id: number; name: string; keyPrefix: string; scopes: { permissions?: string[]; projectIds?: number[] }; status: string; expiresAt?: string | null; lastUsedAt?: string | null; createdBy?: string; createdAt: string }
export interface IssuedApiKey { key: ApiKeyRow; plainKey: string }
const BASE = '/api/v1/open'
async function request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = getToken(); if (token) headers.token = token
  const res = await fetch(`${BASE}${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(camelToSnake(body)) })
  const raw = await res.json().catch(() => null) as { code?: number; msg?: string; data?: unknown } | null
  if (!res.ok || !raw || (raw.code !== undefined && raw.code !== 0 && raw.code !== 200)) throw new ContractApiError({ httpStatus: res.status, code: raw?.code ?? res.status, msg: raw?.msg ?? `HTTP ${res.status}`, raw })
  return snakeToCamel((raw.data ?? raw) as unknown) as T
}
export function createApiKeyContract() {
  return {
    list: () => request<ApiKeyRow[]>('/api-keys'),
    issue: (name: string, scopes: { permissions?: string[]; projectIds?: number[] } = {}) => request<IssuedApiKey>('/api-keys', 'POST', { name, scopes }),
    rotate: (id: number) => request<IssuedApiKey>(`/api-keys/${id}/rotate`, 'POST'),
    revoke: (id: number) => request<ApiKeyRow>(`/api-keys/${id}/revoke`, 'POST'),
  }
}
