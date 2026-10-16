/**
 * R4-RESOURCE（脚本/SQL 资源版本）契约层 — RED 阶段。
 * 端点前缀为草案（/api/v1/rebuild/resources/*），最终以后端契约为权威；
 * 本文件语义源自 docs/increments/2026-10-16-纠偏重构方案设计.md §2.2 客户要求 #4 与 §5.3：
 * 上传文件成为有身份、有版本、有大小/类型限制和权限边界的资源；
 * 工作流版本引用确定资源版本；运行时禁止隐式绑定 latest。
 * RED 约定：所有 I/O 方法在后端接入前抛 R4_RESOURCE_NOT_WIRED，不发出任何真实请求；
 * 类型/大小前端预校验等纯前端逻辑可真实运行（见 ResourceUploadValidationView）。
 */

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

/* ---------- RED 实现（后端接入前统一抛哨兵；方法清单见 R4_RESOURCE_CONTRACT_METHODS） ---------- */

/** 异步契约方法统一实现：rejected promise（同步 throw 会在调用点直接炸出，无法被 rejects 断言捕获） */
const notWired = async (): Promise<never> => {
  throw new Error(R4_RESOURCE_NOT_WIRED)
}

/**
 * R4-RESOURCE 契约工厂（原型态）：签名与类型已冻结，实现在后端就绪后按本接口逐方法替换，
 * UI 层（ResourceUploadValidationView）不感知切换。
 */
export function createResourceContract(): ResourceContract {
  return {
    uploadResource: notWired,
    listResources: notWired,
    listResourceVersions: notWired,
    getResourceVersion: notWired,
    bindResourceVersion: notWired,
  }
}
