import { getJson } from '../http'

export interface AlertNotification {
  id: number
  title: string
  content: string
  state: string
  createTime: string
  target?: string
}

/** 读取当前用户可见的站内预警；权限由后端按会话裁剪。 */
export function listAlertNotifications(limit = 20): Promise<AlertNotification[]> {
  return getJson<AlertNotification[]>('/alerts', { limit })
}
