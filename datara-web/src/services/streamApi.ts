/**
 * I8 流任务服务（F40/F41）：流任务列表/启停/日志 + 实时数据端点。
 * - REST 走统一 http 封装（header token）；
 * - SSE/EventSource 与 WebSocket 无法自定义 header → token 查询参数鉴权（后端同款兼容）。
 */
import { http, getToken } from './http'

/** 流任务行（t_stream_job + Redis 指标镜像合并） */
export interface StreamJobRow {
  id: number
  docId: string
  wfName: string
  name: string
  status: string // starting/running/reconnecting/stopped/failed
  lastError: string | null
  startedAt: string | null
  updatedAt: string
  /** datara:flink:metrics:{job} Hash（速率/累计/位点/错误/心跳/状态镜像），无则 null */
  metrics: Record<string, string> | null
}

/** 流任务实时数据页（C20 保留窗口 Last-N + schema 声明） */
export interface StreamDataPage {
  fields: string[]
  rows: Record<string, unknown>[]
  metrics: Record<string, string> | null
}

export async function listStreamJobs(params: { docId?: string; pageSize?: number } = {}): Promise<StreamJobRow[]> {
  const q = new URLSearchParams()
  if (params.docId) q.set('doc_id', params.docId)
  q.set('page_size', String(params.pageSize ?? 50))
  return http.get(`/stream-jobs?${q.toString()}`)
}

/** 流任务详情（含指标镜像；api/streamjob.py GET /stream-jobs/{id}，F56d 详情页用） */
export async function getStreamJob(id: number): Promise<StreamJobRow> {
  return http.get(`/stream-jobs/${id}`)
}

/** 启动/重启流任务（同文档已有运行任务先停再起，幂等） */
export async function startStreamJob(docId: string): Promise<{ id: number; name: string; restarted: boolean }> {
  return http.post('/stream-jobs/start', { doc_id: docId })
}

export async function stopStreamJob(id: number): Promise<true> {
  return http.post(`/stream-jobs/${id}/stop`)
}

/** 流任务日志尾（Redis List Last-500 中取尾部 lines 条，时间倒序返回） */
export async function getStreamLogs(id: number, lines = 60): Promise<string[]> {
  return http.get(`/stream-jobs/${id}/logs?lines=${lines}`)
}

/** 轮询模式取实时数据（C20 大屏联调主通道之一） */
export async function pollStreamData(id: number, limit = 100): Promise<StreamDataPage> {
  return http.get(`/stream-jobs/${id}/data?mode=poll&limit=${limit}`)
}

/** SSE 端点（EventSource 只支持 GET，token 走查询参数） */
export function streamSseUrl(id: number): string {
  return `/api/v1/stream-jobs/${id}/data?mode=sse&token=${encodeURIComponent(getToken())}`
}

/** WebSocket 端点（token 查询参数鉴权） */
export function streamWsUrl(id: number): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${location.host}/api/v1/stream-jobs/${id}/data/ws?token=${encodeURIComponent(getToken())}`
}
