/**
 * 增量 10 / 10A：正式 rebuild datasource 契约（R-47）。
 *
 * 唯一后端事实源：`datara-backend/rebuild/api/app.py` 的 11 个 rebuild datasource 端点。
 * 本契约不调用旧 `/datasources` API；项目数据始终由 URL 中的 projectId 隔离。
 * password 只允许出现在写请求中，任何读取/写入响应类型均不包含凭据字段。
 */

import { deleteJson, getJson, postJson, putJson } from '../http'
import { camelToSnake, snakeToCamel } from './adapterKit'

export type DatasourceKind = 'mysql' | 'postgresql'
export type DatasourcePermission = 'authenticated' | 'admin' | 'VIEW_ALL' | 'EDIT_DEFINITION'

export interface DatasourceDraft {
  name: string
  kind: DatasourceKind
  host: string
  port: number
  database: string
  username: string
  /** 仅请求方向存在；服务端响应禁止回显。 */
  password?: string
}

export interface DatasourceRecord {
  id: number
  projectId: number
  name: string
  kind: DatasourceKind
  host: string
  port: number
  database: string
  username: string
  createdAt: string
  updatedAt: string
}

export interface DatasourceValidation {
  name: string
  kind: DatasourceKind
  capabilities: string[]
}

export interface DatasourceProbe {
  connected: true
  database: string
  serverVersion: string
  capabilities: string[]
}

export interface DatasourceObject {
  schema: string
  name: string
  type: 'table' | 'view'
}

export interface DatasourceColumn {
  schema: string
  object: string
  name: string
  dataType: string
  databaseType: string
  nullable: boolean
  primaryKey: boolean
  comment: string
}

export interface DatasourcePage<T> {
  items: T[]
  nextAfter: string | null
  limit: number
}

export const DATASOURCE_CONTRACT_METHODS = [
  'validateDraft',
  'probeProfile',
  'listDatasources',
  'createDatasource',
  'getDatasource',
  'updateDatasource',
  'deleteDatasource',
  'testDatasource',
  'listSchemas',
  'listObjects',
  'listColumns',
] as const

/** 与后端 `project_permission_error` 和 profile probe 的鉴权逐端点对齐。 */
export const DATASOURCE_PERMISSION_MATRIX = {
  validateDraft: 'authenticated',
  probeProfile: 'admin',
  listDatasources: 'VIEW_ALL',
  createDatasource: 'EDIT_DEFINITION',
  getDatasource: 'VIEW_ALL',
  updateDatasource: 'EDIT_DEFINITION',
  deleteDatasource: 'EDIT_DEFINITION',
  testDatasource: 'EDIT_DEFINITION',
  listSchemas: 'VIEW_ALL',
  listObjects: 'VIEW_ALL',
  listColumns: 'VIEW_ALL',
} as const satisfies Record<(typeof DATASOURCE_CONTRACT_METHODS)[number], DatasourcePermission>

/** 后端稳定错误码；请求统一开启 preserveEnvelopeCode，UI 可按 code 精确分流。 */
export const DATASOURCE_ERROR_CODES = {
  invalidToken: 1001,
  permissionDenied: 1003,
  invalidInput: 4001,
  registerBeforeTest: 4002,
  projectNotFound: 4041,
  datasourceNotFound: 4042,
  duplicateName: 4091,
  connectionFailed: 5021,
  metadataBrowseFailed: 5022,
  profileUnavailable: 5031,
} as const

const PROJECT_BASE = (projectId: number) => `/rebuild/projects/${projectId}/datasources`
const PRESERVE_ERROR = { preserveEnvelopeCode: true } as const

function toWireDraft(input: DatasourceDraft): Record<string, unknown> {
  return camelToSnake(input) as unknown as Record<string, unknown>
}

function fromWire<T>(value: unknown): T {
  return snakeToCamel(value) as T
}

export interface DatasourceContract {
  validateDraft(input: DatasourceDraft): Promise<DatasourceValidation>
  probeProfile(profileId: string): Promise<DatasourceProbe>
  listDatasources(): Promise<{ items: DatasourceRecord[] }>
  createDatasource(input: DatasourceDraft): Promise<DatasourceRecord>
  getDatasource(datasourceId: number): Promise<DatasourceRecord>
  updateDatasource(datasourceId: number, input: DatasourceDraft): Promise<DatasourceRecord>
  deleteDatasource(datasourceId: number): Promise<{ deleted: true; id: number }>
  testDatasource(datasourceId: number): Promise<DatasourceProbe>
  listSchemas(datasourceId: number, after?: string, limit?: number): Promise<DatasourcePage<string>>
  listObjects(datasourceId: number, schema: string, after?: string, limit?: number): Promise<DatasourcePage<DatasourceObject>>
  listColumns(datasourceId: number, schema: string, objectName: string, limit?: number): Promise<DatasourcePage<DatasourceColumn>>
}

/** 创建绑定单一项目的 datasource 契约，避免调用方遗漏 projectId。 */
export function createDatasourceContract(projectId: number): DatasourceContract {
  const base = PROJECT_BASE(projectId)
  return {
    validateDraft: async (input) =>
      fromWire(await postJson('/rebuild/datasources/validate', { ...toWireDraft(input), probe: false }, PRESERVE_ERROR)),
    probeProfile: async (profileId) =>
      fromWire(await postJson(`/rebuild/datasources/profiles/${encodeURIComponent(profileId)}/probe`, undefined, PRESERVE_ERROR)),
    listDatasources: async () => fromWire(await getJson(base, undefined, PRESERVE_ERROR)),
    createDatasource: async (input) => fromWire(await postJson(base, toWireDraft(input), PRESERVE_ERROR)),
    getDatasource: async (datasourceId) => fromWire(await getJson(`${base}/${datasourceId}`, undefined, PRESERVE_ERROR)),
    updateDatasource: async (datasourceId, input) =>
      fromWire(await putJson(`${base}/${datasourceId}`, toWireDraft(input), PRESERVE_ERROR)),
    deleteDatasource: async (datasourceId) =>
      fromWire(await deleteJson(`${base}/${datasourceId}`, PRESERVE_ERROR)),
    testDatasource: async (datasourceId) =>
      fromWire(await postJson(`${base}/${datasourceId}/test`, undefined, PRESERVE_ERROR)),
    listSchemas: async (datasourceId, after, limit = 100) =>
      fromWire(await getJson(`${base}/${datasourceId}/schemas`, { after, limit }, PRESERVE_ERROR)),
    listObjects: async (datasourceId, schema, after, limit = 100) =>
      fromWire(await getJson(`${base}/${datasourceId}/objects`, { schema, after, limit }, PRESERVE_ERROR)),
    listColumns: async (datasourceId, schema, objectName, limit = 200) =>
      fromWire(await getJson(`${base}/${datasourceId}/columns`, { schema, objectName, limit }, PRESERVE_ERROR)),
  }
}
