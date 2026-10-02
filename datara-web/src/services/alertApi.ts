import { http } from './http'

export interface AlertNotification {
  id: number
  icon: string
  cls: string
  title: string
  desc: string
  time: string
  target: string
  state: string
}

interface AlertRow {
  id: number
  title: string
  content: string
  state: string
  createTime: string
  target: string
}

export async function listAlertNotifications(limit = 20): Promise<AlertNotification[]> {
  const rows = await http.get<AlertRow[]>(`/alerts?limit=${limit}`)
  return rows.map((row) => ({
    id: row.id,
    icon: row.state === 'fail' ? '!' : '⚠',
    cls: row.state === 'fail' ? 'danger' : 'warn',
    title: row.title,
    desc: row.content,
    time: row.createTime,
    target: row.target,
    state: row.state,
  }))
}
