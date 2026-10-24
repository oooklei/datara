/**
 * 15-P0 开放 API 管理契约（RED 阶段，零 I/O）— IMPL-v4-08。
 *
 * 语义来源：docs/increments/2026-10-21-增量15.2-API管理新建模立项文档-监督员C.md（C1~C4 已批）
 *   + docs/increments/evidence/PRE/2026-10-20-增量15-系统管理与AI助手预研-Codex.md §4.3。
 *
 * 命名红线（立项 §一.5 / 预研 §7）：本域是产品「API 管理」，与 FastAPI `/openapi.json`
 *   schema 无关；后端包名建议 `api_management`，URL 前缀冻结为 `/api/v1/open`。
 *
 * RED 约定（同 scheduleApi #8 先例）：所有 I/O 方法在后端（15.2-A~D）接入前抛
 *   OPENAPI_ADMIN_NOT_WIRED 哨兵，不发出任何真实请求；未来 GREEN 接线必须经统一
 *   http 信封底座并开启 preserveEnvelopeCode。
 *
 * 安全红线（C4 / 验收 ④）：原始 key 仅签发/轮换响应一次性回显（KeyIssuance.plainKey），
 *   列表/详情记录（ApiKeyRecord）不含任何 key 明文或可逆形态；调用日志不落原始 key/
 *   敏感 body/完整 SQL——类型面即按此冻结，后端违反即 15.2-D 验收红。
 */

import { request } from '../http'
import { camelToSnake, snakeToCamel } from './adapterKit'

/* ---------- API 定义（rebuild_api_definition：method+path+version 唯一，受控 facade only） ---------- */

/** 受控 facade HTTP 方法白名单（C2：仅登记过的 Datara 受控 facade，禁任意 URL 代理）。 */
export type ApiDefinitionMethod = 'GET' | 'POST' | 'PUT' | 'DELETE'

/** 定义状态机（冻结）：draft→published（publish）；published→disabled（disable）；disabled→published（enable）。 */
export type ApiDefinitionStatus = 'draft' | 'published' | 'disabled'

export interface ApiDefinitionRecord {
  id: number
  name: string
  path: string
  method: ApiDefinitionMethod
  description: string
  /** 调用网关鉴权要求的权限点（identity Permission 词形，如 security:read）。 */
  requiredPermission: string
  status: ApiDefinitionStatus
  version: string
  createdBy: string
  createdAt: string
  updatedAt: string
}

export interface ApiDefinitionInput {
  name: string
  path: string
  method: ApiDefinitionMethod
  description: string
  requiredPermission: string
  version: string
}

/* ---------- API-Key（rebuild_api_key：hash-only 存储；原始 key 仅一次回显） ---------- */

/** Key 状态机（冻结）：active→revoked（revoke）；轮换=吊销旧 key+签发新 key（两步原子）。 */
export type ApiKeyStatus = 'active' | 'revoked'

export interface ApiKeyRecord {
  id: number
  name: string
  /** 展示用前缀（如 dk_live_abc123 的前 8 位），不可据此还原 key。 */
  keyPrefix: string
  /** C3 scope 粒度：permission allowlist + project allowlist（全局 key 仅 admin 可签发）。 */
  scopes: { permissions: string[]; projectIds: number[] }
  status: ApiKeyStatus
  expiresAt: string | null
  lastUsedAt: string | null
  createdBy: string
  revokedAt: string | null
  createdAt: string
  updatedAt: string
}

/** 签发/轮换响应：plainKey 仅在本响应出现一次，UI 关闭弹窗后不可再取。 */
export interface KeyIssuance {
  key: ApiKeyRecord
  /** 一次性明文 key；服务端只存 hash，刷新/重查不可再得。 */
  plainKey: string
}

export interface ApiKeyInput {
  name: string
  scopes: { permissions: string[]; projectIds: number[] }
  expiresAt: string | null
}

/* ---------- 调用日志（rebuild_api_call_log：脱敏，零敏感落盘） ---------- */

export interface ApiCallLogRecord {
  requestId: string
  apiId: number
  keyId: number
  /** 调用主体（principal 用户或项目标识）。 */
  principal: string
  projectId: number | null
  statusCode: number
  latencyMs: number
  result: 'success' | 'denied' | 'error'
  /** 后端稳定错误码（拒绝/失败时）；成功为 null。 */
  errorCode: string | null
  requestedAt: string
}

/** 日志查询过滤面（C1：API 管理页内页签，不设独立菜单）。 */
export interface ApiCallLogQuery {
  apiId?: number
  keyId?: number
  from?: string
  to?: string
  limit?: number
  offset?: number
}

export interface ApiCallLogPage {
  total: number
  list: ApiCallLogRecord[]
}

/* ---------- RED 哨兵与冻结清单 ---------- */

export const OPENAPI_ADMIN_NOT_WIRED =
  'OPENAPI_ADMIN_NOT_WIRED: api_management contract not connected yet (awaits 15.2-A~D)'

/** 契约方法清单（测试与 UI 横幅共用，单一事实源）。 */
export const OPENAPI_ADMIN_CONTRACT_METHODS = [
  'listApiDefinitions',
  'createApiDefinition',
  'updateApiDefinition',
  'deleteApiDefinition',
  'publishApiDefinition',
  'disableApiDefinition',
  'enableApiDefinition',
  'listApiKeys',
  'issueApiKey',
  'rotateApiKey',
  'revokeApiKey',
  'listCallLogs',
] as const

export type OpenapiAdminContractMethod = (typeof OPENAPI_ADMIN_CONTRACT_METHODS)[number]

/**
 * 权限矩阵（冻结）：管理面复用 identity 既有权限点（G 系统管理组，零新增枚举）——
 * 写面 security:manage、读面 security:read；不引入新权限词形（越出 C1~C4 即停票上报）。
 */
export const OPENAPI_ADMIN_PERMISSION_MATRIX = {
  listApiDefinitions: 'security:read',
  createApiDefinition: 'security:manage',
  updateApiDefinition: 'security:manage',
  deleteApiDefinition: 'security:manage',
  publishApiDefinition: 'security:manage',
  disableApiDefinition: 'security:manage',
  enableApiDefinition: 'security:manage',
  listApiKeys: 'security:read',
  issueApiKey: 'security:manage',
  rotateApiKey: 'security:manage',
  revokeApiKey: 'security:manage',
  listCallLogs: 'security:read',
} as const satisfies Record<OpenapiAdminContractMethod, 'security:read' | 'security:manage'>

/**
 * 后端稳定错误码（冻结；未来 GREEN 接线统一 preserveEnvelopeCode 保码透出）。
 * 1001/1003 为 identity 共用码；40xx/50xx 为本域专属段。
 */
export const OPENAPI_ADMIN_ERROR_CODES = {
  invalidToken: 1001,
  permissionDenied: 1003,
  invalidInput: 4001,
  apiNotFound: 4041,
  keyNotFound: 4042,
  duplicateDefinition: 4091,
  invalidStatusTransition: 4092,
  keyExpired: 4093,
  keyRevoked: 4094,
  insufficientScope: 4095,
  facadeUnavailable: 5041,
} as const

/** 冻结 URL 前缀（立项 §一.5：本票定稿 /api/v1/open）。 */
export const OPENAPI_ADMIN_URL_PREFIX = '/api/v1/open'

export interface OpenapiAdminContract {
  listApiDefinitions: () => Promise<ApiDefinitionRecord[]>
  createApiDefinition: (input: ApiDefinitionInput) => Promise<ApiDefinitionRecord>
  updateApiDefinition: (id: number, input: ApiDefinitionInput) => Promise<ApiDefinitionRecord>
  deleteApiDefinition: (id: number) => Promise<void>
  publishApiDefinition: (id: number) => Promise<ApiDefinitionRecord>
  disableApiDefinition: (id: number) => Promise<ApiDefinitionRecord>
  enableApiDefinition: (id: number) => Promise<ApiDefinitionRecord>
  listApiKeys: () => Promise<ApiKeyRecord[]>
  issueApiKey: (input: ApiKeyInput) => Promise<KeyIssuance>
  rotateApiKey: (id: number) => Promise<KeyIssuance>
  revokeApiKey: (id: number) => Promise<ApiKeyRecord>
  listCallLogs: (query?: ApiCallLogQuery) => Promise<ApiCallLogPage>
}

/** API-Key GREEN facade.  Keys are never persisted by the browser; plaintext is
 * held only by the caller until the issuance dialog is closed. */
export interface OpenapiAdminKeyApi {
  list: () => Promise<ApiKeyRecord[]>
  issue: (input: ApiKeyInput) => Promise<KeyIssuance>
  rotate: (id: number) => Promise<KeyIssuance>
  revoke: (id: number) => Promise<ApiKeyRecord>
}

async function keyRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const raw = await request<unknown>(`${OPENAPI_ADMIN_URL_PREFIX.replace('/api/v1', '')}${path}`, {
    ...init,
    ...(init?.body ? { body: JSON.stringify(camelToSnake(JSON.parse(String(init.body)))) } : {}),
    headers: { 'Content-Type': 'application/json', ...(init?.headers as Record<string, string> | undefined) },
  })
  return snakeToCamel(raw) as T
}

export const openapiAdminKeyApi: OpenapiAdminKeyApi = {
  async list() { return keyRequest<ApiKeyRecord[]>('/api-keys') },
  async issue(input) { return keyRequest<KeyIssuance>('/api-keys', { method: 'POST', body: JSON.stringify(input) }) },
  async rotate(id) { return keyRequest<KeyIssuance>(`/api-keys/${id}/rotate`, { method: 'POST' }) },
  async revoke(id) { return keyRequest<ApiKeyRecord>(`/api-keys/${id}/revoke`, { method: 'POST' }) },
}

export interface OpenapiAdminApi {
  list: () => Promise<ApiDefinitionRecord[]>
  create: (input: ApiDefinitionInput) => Promise<ApiDefinitionRecord>
  update: (id: number, input: ApiDefinitionInput) => Promise<ApiDefinitionRecord>
  remove: (id: number) => Promise<void>
  publish: (id: number) => Promise<ApiDefinitionRecord>
  disable: (id: number) => Promise<ApiDefinitionRecord>
  enable: (id: number) => Promise<ApiDefinitionRecord>
  callLogs: (query?: ApiCallLogQuery) => Promise<ApiCallLogPage>
}
export const openapiAdminApi: OpenapiAdminApi = {
  async list() { return keyRequest<ApiDefinitionRecord[]>('/definitions') },
  async create(input) { return keyRequest<ApiDefinitionRecord>('/definitions', { method: 'POST', body: JSON.stringify(input) }) },
  async update(id, input) { return keyRequest<ApiDefinitionRecord>(`/definitions/${id}`, { method: 'PUT', body: JSON.stringify(input) }) },
  async remove(id) { await keyRequest<unknown>(`/definitions/${id}`, { method: 'DELETE' }) },
  async publish(id) { return keyRequest<ApiDefinitionRecord>(`/definitions/${id}/publish`, { method: 'POST' }) },
  async disable(id) { return keyRequest<ApiDefinitionRecord>(`/definitions/${id}/disable`, { method: 'POST' }) },
  async enable(id) { return keyRequest<ApiDefinitionRecord>(`/definitions/${id}/enable`, { method: 'POST' }) },
  async callLogs(query) {
    const q = query ? '?' + Object.entries(query).filter(([, v]) => v !== undefined).map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`).join('&') : ''
    return keyRequest<ApiCallLogPage>(`/call-logs${q}`)
  },
}

/* ---------- RED 实现（后端接入前统一抛哨兵；方法清单见 OPENAPI_ADMIN_CONTRACT_METHODS） ---------- */

/** 异步契约方法统一实现：rejected promise（同步 throw 会在调用点直接炸出，无法被 rejects 断言捕获）。 */
const notWired = async (): Promise<never> => {
  throw new Error(OPENAPI_ADMIN_NOT_WIRED)
}

/**
 * 15-P0 契约工厂（RED 原型态）：签名与类型已冻结，实现在 15.2-A~D 后端就绪后逐方法替换，
 * UI 层不感知切换。
 */
export function createOpenapiAdminContract(): OpenapiAdminContract {
  return {
    listApiDefinitions: notWired,
    createApiDefinition: notWired,
    updateApiDefinition: notWired,
    deleteApiDefinition: notWired,
    publishApiDefinition: notWired,
    disableApiDefinition: notWired,
    enableApiDefinition: notWired,
    listApiKeys: notWired,
    issueApiKey: notWired,
    rotateApiKey: notWired,
    revokeApiKey: notWired,
    listCallLogs: notWired,
  }
}
