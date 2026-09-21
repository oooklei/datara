/**
 * syncApi（I6 F34）：同步任务监控两接口封装（datara-backend/api/sync.py）。
 * - GET /sync-tasks                      打「同步」标签的定义 + 最近实例读写统计聚合
 * - GET /sync-tasks/{wf_code}/instances  指定同步工作流实例明细（分页倒序）
 * 批次号 = 运行实例 instance_id（裁定③）；读写统计读 sync 节点 outputs 聚合。
 * 端点前缀 /api/v1 由 http.ts 统一拼接。
 */
import { http } from './http'

interface PageData<T> { total: number; list: T[] }

/** 同步任务列表行（定义 × 最近实例聚合视图） */
export interface SyncTaskRow {
  wfCode: number
  name: string
  tags: string[]
  instanceCount: number
  lastInstanceId: string | null
  lastState: string | null
  lastTime: string | null
  readRows: number
  writeRows: number
  badRows: number
  schemas: string[]
}

/** 同步实例明细行（批次号=instanceId） */
export interface SyncInstanceRow {
  instanceId: string
  state: string
  runMode: string
  startTime: string | null
  endTime: string | null
  batchId: string
  readRows: number
  writeRows: number
  badRows: number
  schemas: string[]
}

/** 同步任务列表（keyword 名称模糊 / state 最近实例状态筛选，后端过滤） */
export async function listSyncTasks(params?: {
  pageNo?: number
  pageSize?: number
  keyword?: string
  state?: string
}): Promise<PageData<SyncTaskRow>> {
  const q = new URLSearchParams()
  q.set('page_no', String(params?.pageNo ?? 1))
  q.set('page_size', String(params?.pageSize ?? 50))
  if (params?.keyword) q.set('keyword', params.keyword)
  if (params?.state) q.set('state', params.state)
  return http.get<PageData<SyncTaskRow>>(`/sync-tasks?${q.toString()}`)
}

/** 同步工作流实例明细（state 实例状态筛选；未打标定义返回 WF_PARAM_INVALID） */
export async function listSyncInstances(
  wfCode: number,
  params?: { pageNo?: number; pageSize?: number; state?: string },
): Promise<PageData<SyncInstanceRow>> {
  const q = new URLSearchParams()
  q.set('page_no', String(params?.pageNo ?? 1))
  q.set('page_size', String(params?.pageSize ?? 20))
  if (params?.state) q.set('state', params.state)
  return http.get<PageData<SyncInstanceRow>>(`/sync-tasks/${wfCode}/instances?${q.toString()}`)
}
