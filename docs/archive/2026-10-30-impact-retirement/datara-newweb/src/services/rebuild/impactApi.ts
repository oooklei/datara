import { getJson, postJson } from '../http'

export interface DailyImpactItem {
  history_id: string
  connection_id: string
  database: string
  executed_at: string
  success: boolean
  status: string
  reads: string[]
  writes: string[]
}

export interface DailyImpactResult {
  day: string
  collected: boolean
  items: DailyImpactItem[]
}

export function createImpactContract(projectId: number) {
  const base = `/rebuild/projects/${projectId}/impact/daily`
  return {
    listDaily: (day: string) => getJson<DailyImpactResult>(base, { day }),
    refreshDaily: (day: string) => postJson<{ day: string; row_count: number }>(`${base}/refresh?day=${encodeURIComponent(day)}`, {}),
  }
}
