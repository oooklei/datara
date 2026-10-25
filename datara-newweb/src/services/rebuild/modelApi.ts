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
}
