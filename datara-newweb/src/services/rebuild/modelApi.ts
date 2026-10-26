import { deleteJson, getJson, postJson, putJson } from '../http'

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

export interface ModelDetail extends ModelRow { fields: ModelFieldRow[] }
export interface ModelFieldsPayload { rev: number; fields: ModelFieldRow[] }

export interface ModelVersionRow {
  id: number
  version: number
  changeNote: string
  createdBy: string
  createdAt: string
}

export interface ModelVersionDraft { changeNote?: string }
export interface ModelVersionDiff {
  added: ModelFieldRow[]
  removed: ModelFieldRow[]
  changed: Array<{ name: string; before: ModelFieldRow; after: ModelFieldRow }>
  relationsChanged: boolean
}
export interface ModelRollbackResult { status: string; version: number; sourceVersion: number }

export interface ModelLineageNode { id: string; kind: string; label: string }
export interface ModelLineageEdge { from: string; to: string; kind: string; relType?: string }
export interface ModelLineageGraph {
  nodes: ModelLineageNode[]
  edges: ModelLineageEdge[]
  sources: { declared: number; runtime: number }
}
export interface ModelImpactRow { modelId: number; code: string; name: string; path: string }
export interface ModelImpactResult { list: ModelImpactRow[] }

export interface ErNode {
  id: string
  model: ModelRow
  erPos: { x?: number; y?: number }
}
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
export interface ErRelationChange {
  removed: Array<Record<string, unknown>>
  added: ErEdge[]
  updated: ErEdge[]
}
export interface ErSavePayload {
  positions: Record<string, { x: number; y: number }>
  relations: ErRelationChange
}

export interface ModelPhysicalizePayload {
  engine: string
  dsId?: number | null
  dbName?: string | null
  mode?: string
  ddl?: string
}
export interface ModelPhysicalizeResult { script?: string; notes?: string[]; status?: string; executed?: number }

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
    return putJson<{ rev: number }>(`${BASE}/models/${modelId}/fields`, payload).then((result) => result.rev)
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
}
