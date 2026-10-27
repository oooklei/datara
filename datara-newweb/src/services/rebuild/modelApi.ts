import { deleteJson, getJson, postJson, putJson, request } from '../http'

const BASE = '/rebuild'

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
  status: 'draft' | 'published' | 'built' | string
  version: number
  owner: string
  builtAt: string | null
  updatedAt: string | null
  remark: string
}

export interface ModelListPage {
  list: ModelRow[]
  total: number
  layers: Array<{ code: string; count: number }>
  domains: Array<{ name: string; count: number }>
}

export interface ModelDicts {
  layers: Array<Record<string, unknown>>
  domains: Array<Record<string, unknown>>
  engines: Array<Record<string, unknown>>
}

export interface ModelCreateDraft {
  name: string
  code: string
  layer: string
  engine: string
  type?: string
  bizDomain?: string
}

export interface ModelUpdateDraft {
  name?: string
  remark?: string
  owner?: string
  securityLevel?: string
  dsId?: number | null
  dbName?: string | null
}

export interface ModelDdlPreview { engine: string; ddl: string; notes: string[] }

/** 字段行（BE `_field_row`：A6-6 详情内嵌 / A6-9 全量保存）。 */
export interface ModelFieldRow {
  name: string
  dataType: string
  length: number | null
  precision: number | null
  nullable: boolean
  defaultValue: string | null
  comment: string
  isPk: boolean
  isPartition: boolean
  dictRef: string | null
}

/** 模型详情（A6-6：ModelRow + `fields` 平铺内嵌，非 `{model, fields}` 包装）。 */
export interface ModelDetail extends ModelRow { fields: ModelFieldRow[] }

/** A6-9 字段全量保存入参：`rev` 乐观锁 + `fields` 全量。 */
export interface ModelFieldsPayload { rev: number; fields: ModelFieldRow[] }

/** 版本行（BE `_version_row`）。 */
export interface ModelVersionRow {
  id: number
  version: number
  changeNote: string
  createdBy: string
  createdAt: string
}

/** 版本快照创建入参（A6-13：`changeNote` 缺省空串）。 */
export interface ModelVersionDraft { changeNote?: string }

/** A6-14 版本 diff（`relationsChanged` 为全量关系列表相等性布尔，非数量）。 */
export interface ModelVersionDiff {
  added: ModelFieldRow[]
  removed: ModelFieldRow[]
  changed: Array<{ name: string; before: ModelFieldRow; after: ModelFieldRow }>
  relationsChanged: boolean
}

/** A6-15 回滚结果（`sourceVersion` 取快照行 version，非入参 versionId）。 */
export interface ModelRollbackResult { status: string; version: number; sourceVersion: number }

/** A6-21 血缘节点 / 边。 */
export interface ModelLineageNode { id: string; kind: string; label: string }
export interface ModelLineageEdge { from: string; to: string; kind: string; relType?: string }
export interface ModelLineageGraph {
  nodes: ModelLineageNode[]
  edges: ModelLineageEdge[]
  sources: { declared: number; runtime: number }
}

/** A6-22 下游影响清单。 */
export interface ModelImpactRow { modelId: number; code: string; name: string; path: string }
export interface ModelImpactResult { list: ModelImpactRow[] }

/** A6-4 ER 图节点（`erPos` 后端以 `m.er_pos or {}` 兜底）。 */
export interface ErNode {
  id: string
  model: ModelRow
  erPos: { x?: number; y?: number }
}

/** A6-4 ER 图边（模型间关系）。 */
export interface ErEdge {
  id: string
  source: string
  target: string
  relType: string
  srcFields: string
  tgtFields: string
  joinDesc: string
}

export interface ErGraph { nodes: ErNode[]; edges: ErEdge[] }

/** A6-5 ER 保存入参：`positions` 全量覆盖 + `relations` 三键增量 diff。 */
export interface ErRelationChange {
  removed: Array<Record<string, unknown>>
  added: ErEdge[]
  updated: ErEdge[]
}
export interface ErSavePayload {
  positions: Record<string, { x: number; y: number }>
  relations: ErRelationChange
}

/** A6-17 物理化入参（`mode` 缺省 `script`：exec 写库 / script 仅出脚本）。 */
export interface ModelPhysicalizePayload {
  engine: string
  dsId?: number | null
  dbName?: string | null
  mode?: string
  ddl?: string
}

/** A6-17 物理化出参：script 模式 `{script, notes}`；exec 模式 `{status, executed}`。 */
export interface ModelPhysicalizeResult { script?: string; notes?: string[]; status?: string; executed?: number }

/** A6-18 逆向扫描出参。 */
export interface ModelReverseScanTable { tb: string; comment: string; rows: number; cols: number }
export interface ModelReverseScanResult { db: string; tables: ModelReverseScanTable[] }

/** A6-19 逆向导入出参（逐表 `skipped` 带原因）。 */
export interface ModelReverseImportResult { imported: number; skipped: Array<{ tb: string; reason: string }> }

/** A6-19 逆向导入单表（`layer` 缺省 ODS、`name` 可空）。 */
export interface ModelReverseImportTable { tb: string; layer?: string; bizDomain?: string; name?: string }
export interface ModelReverseImportPayload { dsId: number; dbName?: string; tables: ModelReverseImportTable[] }

export const modelApi = {
  list(query: { layer?: string; status?: string; domain?: string; keyword?: string; page?: number; size?: number } = {}) {
    return getJson<ModelListPage>(`${BASE}/models`, query)
  },
  dicts() { return getJson<ModelDicts>(`${BASE}/model-dicts`) },
  create(draft: ModelCreateDraft) { return postJson<{ id: number }>(`${BASE}/models`, draft) },
  update(modelId: number, draft: ModelUpdateDraft) { return putJson<ModelRow>(`${BASE}/models/${modelId}`, draft) },
  remove(modelId: number) { return deleteJson<Record<string, unknown>>(`${BASE}/models/${modelId}`) },
  publish(modelId: number) { return postJson<{ status: string }>(`${BASE}/models/${modelId}/publish`) },
  redraft(modelId: number) { return postJson<ModelRow>(`${BASE}/models/${modelId}/redraft`) },
  ddl(modelId: number, engine?: string) { return getJson<ModelDdlPreview>(`${BASE}/models/${modelId}/ddl`, { engine }) },
  detail(modelId: number) { return getJson<ModelDetail>(`${BASE}/models/${modelId}`) },
  updateFields(modelId: number, payload: ModelFieldsPayload) {
    return putJson<number>(`${BASE}/models/${modelId}/fields`, payload)
  },
  listVersions(modelId: number) { return getJson<ModelVersionRow[]>(`${BASE}/models/${modelId}/versions`) },
  createVersion(modelId: number, payload: ModelVersionDraft = {}) {
    return postJson<{ id: number; version: number; changeNote: string }>(`${BASE}/models/${modelId}/versions`, payload)
  },
  diffVersion(modelId: number, versionId: number, base?: number) {
    return getJson<ModelVersionDiff>(`${BASE}/models/${modelId}/versions/${versionId}/diff`, { base })
  },
  rollbackVersion(modelId: number, versionId: number) {
    return postJson<ModelRollbackResult>(`${BASE}/models/${modelId}/versions/${versionId}/rollback`)
  },
  getEr(query: { layer?: string; domain?: string } = {}) { return getJson<ErGraph>(`${BASE}/models/er`, query) },
  putEr(payload: ErSavePayload) { return putJson<boolean>(`${BASE}/models/er`, payload) },
  lineage(modelId: number) { return getJson<ModelLineageGraph>(`${BASE}/models/${modelId}/lineage`) },
  impact(modelId: number) { return getJson<ModelImpactResult>(`${BASE}/models/${modelId}/impact`) },
  physicalize(modelId: number, payload: ModelPhysicalizePayload) {
    return postJson<ModelPhysicalizeResult>(`${BASE}/models/${modelId}/physicalize`, payload)
  },
  reverseScan(payload: { dsId: number; dbName?: string }) {
    return postJson<ModelReverseScanResult>(`${BASE}/models/reverse/scan`, payload)
  },
  reverseImport(payload: ModelReverseImportPayload) {
    return postJson<ModelReverseImportResult>(`${BASE}/models/reverse/import`, payload)
  },
  /**
   * A6-20 DDL 文件逆向导入（multipart，≤5MB）。
   * 不设 `Content-Type`（浏览器自动带 boundary），与 `resourceApi.requestMultipart` 同策。
   */
  reverseImportDdl(file: File | Blob) {
    const form = new FormData()
    form.append('file', file)
    return request<ModelReverseImportResult>(`${BASE}/models/reverse/import-ddl`, { method: 'POST', body: form })
  },
}
