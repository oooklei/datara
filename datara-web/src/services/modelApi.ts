/**
 * modelApi（I18 P0）：数仓建模真实后端实现。
 * 端点对齐 datara-backend/api/model.py（§3.2 契约唯一权威，datasourceApi 先例）：
 * - GET /model-dicts、GET/POST /models、GET/PUT/DELETE /models/{id}、PUT /models/{id}/fields
 * - POST /models/{id}/publish、GET /models/{id}/ddl、POST /models/{id}/physicalize
 * - POST /models/reverse/scan|import|import-ddl、GET /models/{id}/lineage|impact
 * isMock 分支保留（单测/离线演示；mock 读写 dataStore 演示文档并做形状适配）。
 */
import { http } from './http'
import { isMock } from './apiMode'
import { dataStore } from './mock/dataStore'

/* ---------- 契约类型 ---------- */

export interface ModelFieldRow {
  name: string
  dataType: string
  length: string
  precision: string
  nullable: boolean
  defaultValue: string
  comment: string
  isPk: boolean
  isPartition: boolean
  dictRef: string
}

export interface ModelRow {
  id: number
  code: string
  name: string
  layer: string
  type: string
  bizDomain: string
  engine: string
  engineXc: boolean
  dsId: number | null
  dbName: string | null
  securityLevel: string
  status: string
  version: number
  owner: string
  builtAt: string | null
  updatedAt: string
  remark: string
}

export interface ModelDetail extends ModelRow { fields: ModelFieldRow[] }
export interface LayerStat { code: string; count: number }
export interface DomainStat { name: string; count: number }
export interface ModelListResp { list: ModelRow[]; total: number; layers: LayerStat[]; domains: DomainStat[] }

export interface ModelDicts {
  layers: { code: string; name: string; rule: string; color: string; seq: number }[]
  domains: { name: string; remark: string }[]
  engines: { name: string; ddl: string; xc: boolean }[]
}

export interface ReverseTableItem { tb: string; comment: string; rows: number; cols: number }

export interface LineageNode { id: string; kind: 'model' | 'ext'; label: string }
export interface LineageEdgeRow { from: string; to: string; kind: 'declared' | 'runtime'; relType?: string }
export interface LineageResp { nodes: LineageNode[]; edges: LineageEdgeRow[]; sources: { declared: number; runtime: number } }
export interface ImpactItem { modelId: number; code: string; name: string; path: string }

/* ---------- mock 适配（演示文档形状 ↔ API 契约） ---------- */

/** demo Model 文档 → ModelRow（id 'MD001' → 数字序） */
function demoToRow(m: Record<string, unknown>): ModelRow {
  const id = Number(String(m.id ?? '').replace(/^\D+/, '')) || 0
  return {
    id, code: String(m.code ?? ''), name: String(m.name ?? ''), layer: String(m.layer ?? ''),
    type: String(m.type ?? '明细表'), bizDomain: String(m.bizDomain ?? ''),
    engine: String(m.engine ?? ''), engineXc: String(m.engine ?? '').includes('GreatDB'),
    dsId: null, dbName: null, securityLevel: '内部',
    status: String(m.status ?? 'draft'), version: Number(m.version ?? 1),
    owner: String(m.owner ?? ''), builtAt: null, updatedAt: String(m.updatedAt ?? ''),
    remark: '',
  }
}

/* ---------- API ---------- */

export async function getModelDicts(): Promise<ModelDicts> {
  if (isMock) {
    const [ls, ds, es] = await Promise.all([
      dataStore.list<Record<string, unknown>>('dwLayers'),
      dataStore.list<Record<string, unknown>>('bizDomains'),
      dataStore.list<Record<string, unknown>>('engineTypes'),
    ])
    return {
      layers: (ls ?? []).map((l) => ({ code: String(l.code), name: String(l.name), rule: String(l.rule ?? ''), color: String(l.color ?? '#64748b'), seq: Number(l.seq ?? 0) })),
      domains: (ds ?? []).map((d) => ({ name: String(d.name), remark: String(d.desc ?? '') })),
      engines: (es ?? []).map((e) => ({ name: String(e.name), ddl: String(e.ddl ?? 'mysql'), xc: !!e.xc })),
    }
  }
  return http.get<ModelDicts>('/model-dicts')
}

export async function listModels(params?: {
  layer?: string; status?: string; domain?: string; keyword?: string; page?: number; size?: number
}): Promise<ModelListResp> {
  if (isMock) {
    const ms = (await dataStore.list<Record<string, unknown>>('models')) ?? []
    const rows = ms.map(demoToRow)
    const layers = [...new Set(rows.map((r) => r.layer))].map((code) => ({ code, count: rows.filter((r) => r.layer === code).length }))
    const domains = [...new Set(rows.map((r) => r.bizDomain).filter(Boolean))].map((name) => ({ name, count: rows.filter((r) => r.bizDomain === name).length }))
    return { list: rows, total: rows.length, layers, domains }
  }
  const q = new URLSearchParams()
  if (params?.layer) q.set('layer', params.layer)
  if (params?.status) q.set('status', params.status)
  if (params?.domain) q.set('domain', params.domain)
  if (params?.keyword) q.set('keyword', params.keyword)
  if (params?.page) q.set('page', String(params.page))
  if (params?.size) q.set('size', String(params.size))
  const qs = q.toString()
  return http.get<ModelListResp>(`/models${qs ? `?${qs}` : ''}`)
}

export async function createModel(body: {
  name: string; code: string; layer: string; engine: string; type: string; bizDomain: string
}): Promise<{ id: number }> {
  return http.post<{ id: number }>('/models', body)
}

export async function getModel(id: number | string): Promise<ModelDetail> {
  return http.get<ModelDetail>(`/models/${encodeURIComponent(id)}`)
}

export async function updateModel(id: number | string, body: {
  name?: string; remark?: string; owner?: string; securityLevel?: string; dsId?: number; dbName?: string
}): Promise<ModelRow> {
  return http.put<ModelRow>(`/models/${encodeURIComponent(id)}`, body)
}

/** 删除模型（被下游血缘引用/已物理化 → 后端 409，http 层 throw Error） */
export async function deleteModel(id: number | string): Promise<void> {
  await http.delete<void>(`/models/${encodeURIComponent(id)}`)
}

/** 字段全量保存（乐观锁：rev≠当前 version → 后端 422 带 data.currentRev） */
export async function saveFields(id: number | string, body: { rev: number; fields: ModelFieldRow[] }): Promise<{ rev: number }> {
  return http.put<{ rev: number }>(`/models/${encodeURIComponent(id)}/fields`, body)
}

export async function publishModel(id: number | string): Promise<{ status: string }> {
  return http.post<{ status: string }>(`/models/${encodeURIComponent(id)}/publish`)
}

export async function getDdl(id: number | string, engine?: string): Promise<{ engine: string; ddl: string; notes: string[] }> {
  const q = engine ? `?engine=${encodeURIComponent(engine)}` : ''
  return http.get<{ engine: string; ddl: string; notes: string[] }>(`/models/${encodeURIComponent(id)}/ddl${q}`)
}

export async function physicalize(id: number | string, body: {
  engine: string; dsId?: number; dbName?: string; mode: 'exec' | 'script'; ddl?: string
}): Promise<{ status?: string; script?: string; notes?: string[]; executed?: number }> {
  return http.post(`/models/${encodeURIComponent(id)}/physicalize`, body)
}

export async function reverseScan(body: { dsId: number; dbName?: string }): Promise<{ db: string; tables: ReverseTableItem[] }> {
  return http.post('/models/reverse/scan', body)
}

export async function reverseImport(body: {
  dsId: number; dbName?: string; tables: { tb: string; layer: string; bizDomain?: string; name?: string }[]
}): Promise<{ imported: number; skipped: { tb: string; reason: string }[] }> {
  return http.post('/models/reverse/import', body)
}

/** DDL 文件导入（multipart；后端 400 时 http 层 throw Error(msg)） */
export async function reverseImportDdl(file: File): Promise<{ imported: number; skipped: { tb: string; reason: string }[] }> {
  const fd = new FormData()
  fd.append('file', file)
  const { getToken } = await import('./http')
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token) headers.token = token
  const res = await fetch('/api/v1/models/reverse/import-ddl', {
    method: 'POST',
    headers,
    body: fd,
  })
  const json = (await res.json()) as { code: number; msg: string; data: { imported: number; skipped: { tb: string; reason: string }[] } }
  if (json.code !== 0) throw new Error(json.msg || '导入失败')
  return json.data
}

export async function getModelLineage(id: number | string): Promise<LineageResp> {
  return http.get<LineageResp>(`/models/${encodeURIComponent(id)}/lineage`)
}

export async function getModelImpact(id: number | string): Promise<{ list: ImpactItem[] }> {
  return http.get<{ list: ImpactItem[] }>(`/models/${encodeURIComponent(id)}/impact`)
}
