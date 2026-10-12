import { http } from './http'

export interface MetaTag { id: number; name: string; cat: string; color: string; desc: string; cnt: number }
export interface MetaCatalogRow { key: string; type: 'table' | 'model'; id?: number; code: string; name: string; layer: string; domain: string; status?: string }
export interface MetaTagging { id: number; tagId: number; targetType: 'table' | 'field' | 'model'; targetKey: string }

export const listMetaTags = (params?: { keyword?: string; cat?: string }) => {
  const q = new URLSearchParams(); if (params?.keyword) q.set('keyword', params.keyword); if (params?.cat) q.set('cat', params.cat)
  return http.get<MetaTag[]>(`/meta/tags${q.toString() ? `?${q}` : ''}`)
}
export const createMetaTag = (body: Omit<MetaTag, 'id' | 'cnt'>) => http.post<MetaTag>('/meta/tags', body)
export const updateMetaTag = (id: number, body: Omit<MetaTag, 'id' | 'cnt'>) => http.put<MetaTag>(`/meta/tags/${id}`, body)
export const deleteMetaTag = (id: number) => http.delete<boolean>(`/meta/tags/${id}`)
export const listMetaTaggings = (params?: { tagId?: number; targetType?: string; targetKey?: string }) => {
  const q = new URLSearchParams(); if (params?.tagId) q.set('tag_id', String(params.tagId)); if (params?.targetType) q.set('target_type', params.targetType); if (params?.targetKey) q.set('target_key', params.targetKey)
  return http.get<MetaTagging[]>(`/meta/taggings${q.toString() ? `?${q}` : ''}`)
}
export const setMetaTaggings = (body: { tagIds: number[]; targetType: string; targetKey: string }) => http.post('/meta/taggings', body)
export const listMetaCatalog = (params?: { keyword?: string; layer?: string; domain?: string }) => {
  const q = new URLSearchParams(); if (params?.keyword) q.set('keyword', params.keyword); if (params?.layer) q.set('layer', params.layer); if (params?.domain) q.set('domain', params.domain)
  return http.get<{ list: MetaCatalogRow[]; total: number }>(`/meta/catalog/tables${q.toString() ? `?${q}` : ''}`)
}
export const saveMetaTableExt = (key: string, body: { bizDomain: string; securityLevel: string; owner: string; remark: string }) => http.put(`/meta/catalog/table/${encodeURIComponent(key)}/ext`, body)
export interface MetaMapProjection { stats: { dataSources: number; databases: number; tables: number; models: number; tags: number }; nodes: { id: string; type: string; label: string; code: string; layer: string; domain: string; status: string }[]; edges: { source: string; target: string; kind: string; relType?: string }[]; truncated: boolean }
export const getMetaMap = (params?: { view?: string; layer?: string; domain?: string; limit?: number }) => {
  const q = new URLSearchParams(); if (params?.view) q.set('view', params.view); if (params?.layer) q.set('layer', params.layer); if (params?.domain) q.set('domain', params.domain); if (params?.limit) q.set('limit', String(params.limit))
  return http.get<MetaMapProjection>(`/meta/map${q.toString() ? `?${q}` : ''}`)
}
