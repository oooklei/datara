/**
 * R4-RESOURCE（脚本/SQL 资源版本）契约层 — GREEN 接线（接线计划 Task 4，R4 批次）。
 * 端点与映射依据：docs/increments/2026-10-17-R系列GREEN接线计划.md Task 4 +
 * A2 v2.1 冻结契约（R4-DEP-RES-API-contract-pending.md §2/§4，双线会签）；
 * 包络 {code,msg,data} 沿 R2/R7 批次固化。
 * uploadResource 真实实现为 multipart（project_id/kind/file）：contentBase64 → Blob，
 * 不手工设置 Content-Type（浏览器自动带 boundary）；服务端重验 kind/扩展名/大小并自行计算 sha256。
 * RES_* 错误码（RES_TYPE_NOT_ALLOWED/RES_SIZE_EXCEEDED/RES_KIND_UNKNOWN/RES_OBJECT_NOT_FOUND/
 * RES_VERSION_NOT_FOUND/RES_BINDING_CONFLICT）经包络解包后以 ContractApiError 透出。
 * R4_RESOURCE_NOT_WIRED 常量保留（View 横幅引用兼容）。
 */

import { camelToSnake, ContractApiError, snakeToCamel } from './adapterKit'
import { getToken } from '../http'

/* ---------- 资源身份与版本 ---------- */

export type ResourceKind = 'sql' | 'python' | 'shell'

export interface ResourceMeta {
  resourceId: number
  name: string
  kind: ResourceKind
  sizeBytes: number
  latestVersion: number
}

/** 不可变资源版本：一经上传不可改写（草案语义，后端冻结前不改） */
export interface ResourceVersion {
  resourceId: number
  version: number
  sizeBytes: number
  digest: string
  uploadedAt: string
}

/* ---------- 上传 / 绑定请求 ---------- */

export interface ResourceUploadRequest {
  projectId: number
  kind: ResourceKind
  filename: string
  sizeBytes: number
  /** 真实实现为 multipart 正文；契约层仅承载元数据描述 */
  contentBase64?: string
}

/** 显式版本绑定：resourceVersion 为具体数字，类型上排除 'latest' */
export interface ResourceBindRequest {
  projectId: number
  workflowId: number
  workflowVersion: number
  taskId: string
  resourceId: number
  resourceVersion: number
}

/* ---------- 前端预校验（草案常量：最终以服务端契约为权威） ---------- */

/** 大小上限草案 20MB（纠偏设计 §5.3 仅要求“有大小限制”，具体值待后端契约冻结） */
export const RESOURCE_MAX_SIZE_BYTES = 20 * 1024 * 1024

/** kind → 允许的扩展名（SQL 上传 .sql；Python/Shell 上传脚本） */
export const RESOURCE_ALLOWED_EXTENSIONS: Record<ResourceKind, string[]> = {
  sql: ['.sql'],
  python: ['.py'],
  shell: ['.sh'],
}

export interface ResourceDraftDiagnostic {
  field: 'filename' | 'sizeBytes' | 'kind'
  code: 'TYPE_NOT_ALLOWED' | 'SIZE_EXCEEDED' | 'KIND_UNKNOWN'
  message: string
}

/** 本地预校验：扩展名与大小限制（真实运行）；服务端保存时仍会重验（后端冻结前） */
export function validateUploadDraft(kind: ResourceKind, filename: string, sizeBytes: number): ResourceDraftDiagnostic[] {
  const diagnostics: ResourceDraftDiagnostic[] = []
  const dot = filename.lastIndexOf('.')
  const ext = dot >= 0 ? filename.slice(dot).toLowerCase() : ''
  if (!RESOURCE_ALLOWED_EXTENSIONS[kind].includes(ext)) {
    diagnostics.push({ field: 'filename', code: 'TYPE_NOT_ALLOWED', message: `${kind} 资源仅允许 ${RESOURCE_ALLOWED_EXTENSIONS[kind].join('/')} 扩展名` })
  }
  if (sizeBytes > RESOURCE_MAX_SIZE_BYTES) {
    diagnostics.push({ field: 'sizeBytes', code: 'SIZE_EXCEEDED', message: `超过大小上限 ${RESOURCE_MAX_SIZE_BYTES} 字节` })
  }
  return diagnostics
}

/* ---------- RED 哨兵 ---------- */

export const R4_RESOURCE_NOT_WIRED = 'R4_RESOURCE_NOT_WIRED: rebuild/resources contract not connected yet'

/** 契约方法清单（测试与 UI 横幅共用，保持单一事实源） */
export const R4_RESOURCE_CONTRACT_METHODS = [
  'uploadResource',
  'listResources',
  'listResourceVersions',
  'getResourceVersion',
  'bindResourceVersion',
] as const

export type R4ResourceContractMethod = (typeof R4_RESOURCE_CONTRACT_METHODS)[number]

export interface ResourceContract {
  uploadResource: (request: ResourceUploadRequest) => Promise<ResourceVersion>
  listResources: (projectId: number, kind?: ResourceKind) => Promise<ResourceMeta[]>
  listResourceVersions: (resourceId: number, projectId: number) => Promise<ResourceVersion[]>
  getResourceVersion: (resourceId: number, version: number, projectId: number) => Promise<ResourceVersion>
  bindResourceVersion: (request: ResourceBindRequest) => Promise<{ bound: true; bindingId: number }>
}

/* ---------- GREEN 统一原语（沿 R2/R7 固化版；BASE 换 resources 域，multipart 分支） ---------- */

/** 端点前缀（A2 v2.1 冻结契约） */
const BASE = '/api/v1/rebuild/resources'

const TIMEOUT_MS = 15000

/** 后端成功包络（rebuild 域全域实证形态） */
interface ApiEnvelope {
  code?: number | string
  msg?: string
  data?: unknown
}

/** 包络解包：rebuild 域全域 {code,msg,data}；非 2xx 但包络含 code（RES_* 错误码、4001/1001/1003/4041）时
 * 保码透出（A2 §2/§4 错误映射），httpStatus 同步保留；非 JSON/无 code 再退回 HTTP 状态码错误 */
async function unwrapEnvelope<T>(res: Response, path: string): Promise<T> {
  if (!res.ok) {
    const raw = await res.text().catch(() => '')
    let parsed: ApiEnvelope | undefined
    try {
      parsed = JSON.parse(raw) as ApiEnvelope
    } catch {
      parsed = undefined
    }
    if (parsed && parsed.code !== undefined) {
      throw new ContractApiError({ httpStatus: res.status, code: parsed.code, msg: parsed.msg ?? path, raw: parsed })
    }
    throw new ContractApiError({ httpStatus: res.status, code: res.status, msg: `HTTP ${res.status} ${path}`, raw })
  }
  const envelope = (await res.json()) as ApiEnvelope
  if (envelope.code !== undefined && envelope.code !== 0 && envelope.code !== 200) {
    throw new ContractApiError({ httpStatus: res.status, code: envelope.code, msg: envelope.msg ?? path, raw: envelope })
  }
  return (envelope.data ?? envelope) as T
}

/** 统一 JSON fetch 原语：15s AbortController 超时 + token header + 包络解包 + 归一错误 */
async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS)
  try {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    const token = getToken()
    if (token) headers.token = token
    const res = await fetch(`${BASE}${path}`, {
      ...init,
      method: init?.method ?? 'GET',
      headers: { ...headers, ...(init?.headers as Record<string, string>) },
      signal: ctrl.signal,
    })
    return await unwrapEnvelope<T>(res, path)
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new ContractApiError({ httpStatus: 0, code: 'TIMEOUT', msg: `请求超时（${TIMEOUT_MS / 1000}s）${path}` })
    }
    throw err
  } finally {
    clearTimeout(timer)
  }
}

/** multipart fetch 原语：不设 Content-Type（浏览器自动带 boundary），响应 snake→camel（上传版本载荷），其余与 requestJson 同构 */
async function requestMultipart<T>(path: string, form: FormData): Promise<T> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS)
  try {
    const headers: Record<string, string> = {}
    const token = getToken()
    if (token) headers.token = token
    const res = await fetch(`${BASE}${path}`, { method: 'POST', headers, body: form, signal: ctrl.signal })
    return snakeToCamel(await unwrapEnvelope<unknown>(res, path)) as T
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new ContractApiError({ httpStatus: 0, code: 'TIMEOUT', msg: `请求超时（${TIMEOUT_MS / 1000}s）${path}` })
    }
    throw err
  } finally {
    clearTimeout(timer)
  }
}

/** POST JSON：请求体深度 camel→snake，响应深度 snake→camel（bindings） */
async function sendJson<T>(path: string, body: unknown): Promise<T> {
  return snakeToCamel(await requestJson<unknown>(path, { method: 'POST', body: JSON.stringify(camelToSnake(body)) })) as T
}

/** GET：query 参数展开，响应深度 snake→camel（list/versions 三查询） */
async function getJson<T>(path: string, params: Record<string, string>): Promise<T> {
  const query = new URLSearchParams(params).toString()
  return snakeToCamel(await requestJson<unknown>(query ? `${path}?${query}` : path)) as T
}

/**
 * contentBase64 → 文件（multipart 正文）；非法 base64 由 atob 直接抛错（fail-visible）。
 * 直接构造 `File([bytes], filename)`：浏览器/Node/happy-dom 三载体均保留文件名
 * （`FormData.append(name, blob, filename)` 在 happy-dom 下不采纳 filename 实参）。
 */
function base64ToFile(base64: string, filename: string): File {
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  return new File([bytes], filename)
}

/**
 * R4-RESOURCE 契约工厂 — GREEN：5 方法接线至 A2 v2.1 冻结契约的后端实现（Task 4 契约面表），
 * 签名与返回类型不动，UI 层（ResourceUploadValidationView）不感知切换。
 * uploadResource 为真实 multipart：contentBase64 必填（缺失即 ContractApiError，不做任何静默降级）。
 */
export function createResourceContract(): ResourceContract {
  return {
    uploadResource: (request) => {
      if (request.contentBase64 === undefined) {
        return Promise.reject(
          new ContractApiError({
            httpStatus: 0,
            code: 'CONTRACT_VIOLATION',
            msg: 'uploadResource requires contentBase64 (real multipart upload; metadata-only calls are not wired)',
          }),
        )
      }
      const form = new FormData()
      form.append('project_id', String(request.projectId))
      form.append('kind', request.kind)
      form.append('file', base64ToFile(request.contentBase64, request.filename))
      return requestMultipart<ResourceVersion>('/uploads', form)
    },
    listResources: (projectId, kind) =>
      getJson<ResourceMeta[]>('', kind !== undefined ? { project_id: String(projectId), kind } : { project_id: String(projectId) }),
    listResourceVersions: (resourceId, projectId) =>
      getJson<ResourceVersion[]>(`/${resourceId}/versions`, { project_id: String(projectId) }),
    getResourceVersion: (resourceId, version, projectId) =>
      getJson<ResourceVersion>(`/${resourceId}/versions/${version}`, { project_id: String(projectId) }),
    bindResourceVersion: (request) => sendJson<{ bound: true; bindingId: number }>('/bindings', request),
  }
}
