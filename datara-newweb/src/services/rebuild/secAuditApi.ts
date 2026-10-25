/**
 * G11 访问审计查询契约（后端已就绪：rebuild/sec/api.py → /api/v1/rebuild/sec/access-logs）。
 *
 * 语义来源：rebuild/sec/service.py access_logs()
 *   + rebuild/sec/models.py SecAccessLogRecord（字段语义）
 *
 * 权限：admin-only（后端 audit view 权限检查 _AUDIT_VIEW_ROLES）
 */

import { getJson, type QueryParams } from '../http'

export type AccessLogResult = 'allow' | 'deny'

export interface AccessLogRecord {
  id: number
  userName: string
  action: string
  target: string
  rowsSeen: number
  result: AccessLogResult
  reason: string
  requestId: string
  accessedAt: string | null
}

export interface AccessLogFacets {
  /** 按结果值分组的计数（allow / deny）。 */
  allow?: number
  deny?: number
}

export interface AccessLogPage {
  list: AccessLogRecord[]
  total: number
  facets: AccessLogFacets
}

interface AccessLogWireRecord {
  id: number
  user_name: string
  action: string
  target: string
  rows_seen: number
  result: AccessLogResult
  reason: string
  request_id: string
  accessed_at: string | null
}

interface AccessLogWirePage {
  list: AccessLogWireRecord[]
  total: number
  facets: AccessLogFacets
}

export interface AccessLogQuery extends QueryParams {
  userName?: string | null
  action?: string | null
  result?: AccessLogResult | null
  limit?: number
  offset?: number
}

export const SEC_AUDIT_CONTRACT_METHODS = ['listAccessLogs'] as const

export interface SecAuditContract {
  listAccessLogs: (query?: AccessLogQuery) => Promise<AccessLogPage>
}

/**
 * 访问审计查询契约（admin-only）。
 *
 * 后端真实路径：GET /api/v1/rebuild/sec/access-logs
 * 前端 BASE = /api/v1 → 相对路径 /rebuild/sec/access-logs
 */
export function createSecAuditContract(): SecAuditContract {
  return {
    listAccessLogs: async (query) => {
      const page = await getJson<AccessLogWirePage>('/rebuild/sec/access-logs', query)
      return {
        total: page.total,
        facets: page.facets,
        list: page.list.map((row) => ({
          id: row.id,
          userName: row.user_name,
          action: row.action,
          target: row.target,
          rowsSeen: row.rows_seen,
          result: row.result,
          reason: row.reason,
          requestId: row.request_id,
          accessedAt: row.accessed_at,
        })),
      }
    },
  }
}
