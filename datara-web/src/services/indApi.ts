import { http } from './http'

export interface IndicatorRow { id: number; code: string; name: string; type: string; bizDef: string; techDef: string; srcRef: string; srcField: string; period: string; dims: string; unit: string; status: string; v: number; owner: string; domain: string; aggFn?: string; numField?: string; timeField?: string; dimField?: string; filterCond?: string }
export interface ConsistencyResult { metric: string; places: string[]; result: 'fail' | 'warn'; detail: string }
export const listIndicators = (params?: { type?: string; domain?: string; status?: string; keyword?: string; page?: number; size?: number }) => {
  const q = new URLSearchParams(); for (const k of ['type', 'domain', 'status', 'keyword', 'page', 'size'] as const) if (params?.[k] !== undefined && params[k] !== '') q.set(k, String(params[k]))
  return http.get<{ list: IndicatorRow[]; total: number }>(`/indicators${q.toString() ? `?${q}` : ''}`)
}
export const createIndicator = (body: Record<string, unknown>) => http.post<IndicatorRow>('/indicators', body)
export const publishIndicator = (id: number) => http.post(`/indicators/${id}/publish`)
export const changeIndicator = (id: number, body: Record<string, unknown>) => http.post(`/indicators/${id}/change`, body)
export const listIndicatorVersions = (id: number) => http.get('/indicators/' + id + '/versions')
export const getIndicatorTrend = (id: number, days = 8) => http.get(`/indicators/${id}/trend?days=${days}`)
export const getIndicatorBreakdown = (id: number, date?: string) => http.get(`/indicators/${id}/breakdown${date ? `?date=${encodeURIComponent(date)}` : ''}`)
export const getIndicatorConsistency = () => http.get<{ checked: number; pass: number; fail: number; items: ConsistencyResult[] }>('/indicators/consistency')
