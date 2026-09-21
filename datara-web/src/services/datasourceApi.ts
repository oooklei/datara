/**
 * datasourceApi（I4 F10~F14）：数据源中心真实后端实现。
 * 端点对齐 datara-backend/api/datasource.py（§3.2 契约唯一权威，graphApi 先例）：
 * - GET/POST /datasources、PUT/DELETE /datasources/{id}、POST /datasources/{id}/test
 * - GET /datasources/{id}/tree（连接型三级树 / 文件型 schema+抽样）
 * - GET /datasources/files（共享卷文件清单，路径选择器）
 * - GET /tmp-data?instance_id=、DELETE /tmp-data/{id}（实例临时数据）
 * 密码明文存储与回显（09-18 裁定：内部系统）。
 */
import { http } from './http'

/* ---------- 数据源 ---------- */

export type DsType = 'mysql' | 'greatdb' | 'file'

/** 后端数据源行（_payload 形状；db/group 为前端名，落库 db_name/group_name） */
export interface DsRow {
  id: number
  name: string
  type: DsType | string
  host: string | null
  port: number | null
  db: string | null
  user: string | null
  pwd: string
  env: string | null
  group: string | null
  tags: string[]
  params: Record<string, unknown> | null
  /** online / offline / null（未测试） */
  status: string | null
  owner: string
  createdAt: string
  updateTime: string
}

/** 新建/编辑请求体（DsBody；全量覆盖语义） */
export interface DsBody {
  name: string
  type: string
  host?: string | null
  port?: number | null
  db?: string | null
  user?: string | null
  pwd?: string
  env?: string | null
  group?: string | null
  tags?: string[]
  params?: Record<string, unknown> | null
}

export interface DsTestResult {
  status: 'online' | 'offline'
  elapsedMs: number
  message: string
  /** 文件型附带：解析列数 */
  columns?: number
}

/* ---------- 库表树 ---------- */

export interface TreeColumn { name: string; type: string }
export interface TreeTable { name: string; columns: TreeColumn[] }
export interface TreeDatabase { name: string; tables: TreeTable[] }

export interface FileSchemaColumn { name: string; type: string; nullRate: number }
export interface FileSchema { columns: FileSchemaColumn[]; sampledRows: number }

export type DsTree =
  | { kind: 'connection'; databases: TreeDatabase[] }
  | { kind: 'file'; file: string; schema: FileSchema; sample: string[][] }

/* ---------- 实例临时数据 ---------- */

export interface TmpRow {
  id: number
  instanceId: string
  taskId: number | null
  nodeId: string | null
  name: string
  /** table / file / resultset */
  kind: string
  ref: string
  targetDsId: number | null
  rowsCount: number | null
  schema: FileSchema | null
  /** worker file.py 落库形状：{columns: 表头[], rows: 抽样二维数组} */
  preview: { columns: string[]; rows: string[][] } | null
  /** immediate / days / keep */
  retention: string
  expireAt: string | null
  /** active / cleaned / consumed */
  status: string
  createTime: string
}

/* ---------- API ---------- */

export async function listDataSources(params?: {
  keyword?: string
  env?: string
  group?: string
  type?: string
}): Promise<DsRow[]> {
  const q = new URLSearchParams()
  if (params?.keyword) q.set('keyword', params.keyword)
  if (params?.env) q.set('env', params.env)
  if (params?.group) q.set('group', params.group)
  if (params?.type) q.set('type', params.type)
  const qs = q.toString()
  return http.get<DsRow[]>(`/datasources${qs ? `?${qs}` : ''}`)
}

export async function createDataSource(body: DsBody): Promise<DsRow> {
  return http.post<DsRow>('/datasources', body)
}

export async function updateDataSource(id: number | string, body: DsBody): Promise<void> {
  await http.put<void>(`/datasources/${encodeURIComponent(id)}`, body)
}

/** 删除数据源（被工作流引用时后端 409，http 层 throw Error(msg)） */
export async function deleteDataSource(id: number | string): Promise<void> {
  await http.delete<void>(`/datasources/${encodeURIComponent(id)}`)
}

export async function testDataSource(id: number | string): Promise<DsTestResult> {
  return http.post<DsTestResult>(`/datasources/${encodeURIComponent(id)}/test`)
}

export async function getDataSourceTree(id: number | string, dbFilter?: string): Promise<DsTree> {
  const q = dbFilter ? `?db=${encodeURIComponent(dbFilter)}` : ''
  return http.get<DsTree>(`/datasources/${encodeURIComponent(id)}/tree${q}`)
}

/** 共享卷 /datara/files 文件清单（相对 posix 路径） */
export async function listDataFiles(): Promise<string[]> {
  return http.get<string[]>('/datasources/files')
}

/* ---- 实例临时数据（C22 预览网格 / 实例详情区块） ---- */

export async function listTmpData(instanceId: string): Promise<TmpRow[]> {
  return http.get<TmpRow[]>(`/tmp-data?instance_id=${encodeURIComponent(instanceId)}`)
}

/** 手动清理临时数据（实体清扫 + status=cleaned） */
export async function deleteTmpData(tmpId: number): Promise<void> {
  await http.delete<void>(`/tmp-data/${tmpId}`)
}
