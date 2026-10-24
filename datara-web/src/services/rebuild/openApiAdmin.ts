import { camelToSnake, snakeToCamel, ContractApiError } from './adapterKit'
import { getToken } from '../http'
export interface ApiDefinition { id: number; name: string; path: string; method: string; version: string; description: string; requiredPermission: string; status: string; createdAt: string }
export interface ApiCallLog { requestId: string; apiId: number; keyId: number; principal: string; projectId?: number | null; statusCode: number; latencyMs: number; result: string; errorCode?: string | null; requestedAt: string }
async function request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const token = getToken(); const headers: Record<string, string> = {}; if (token) headers.token = token
  const response = await fetch(`/api/v1/open${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(camelToSnake(body)) })
  const raw = await response.json().catch(() => null) as { code?: number; msg?: string; data?: unknown } | null
  if (!response.ok || !raw || (raw.code !== undefined && raw.code !== 0 && raw.code !== 200)) throw new ContractApiError({ httpStatus: response.status, code: raw?.code ?? response.status, msg: raw?.msg ?? `HTTP ${response.status}`, raw })
  return snakeToCamel((raw.data ?? raw) as unknown) as T
}
export function createOpenApiAdminContract() {
  const mutate = async (path: string, method = 'POST', body?: unknown) => request<ApiDefinition>(path, method, body)
  return {
    listDefinitions: () => request<ApiDefinition[]>('/definitions'),
    listCallLogs: (limit = 200) => request<{ list: ApiCallLog[]; total: number }>(`/call-logs?limit=${limit}`),
    createDefinition: (body: unknown) => mutate('/definitions', 'POST', body),
    updateDefinition: (id: number, body: unknown) => mutate(`/definitions/${id}`, 'PUT', body),
    deleteDefinition: (id: number) => mutate(`/definitions/${id}`, 'DELETE'),
    publish: (id: number) => mutate(`/definitions/${id}/publish`),
    disable: (id: number) => mutate(`/definitions/${id}/disable`),
    enable: (id: number) => mutate(`/definitions/${id}/enable`),
  }
}
