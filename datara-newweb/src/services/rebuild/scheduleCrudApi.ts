/** Rebuild schedule CRUD contract. Runtime observation stays in scheduleApi.ts. */
import { request } from '../http'

const BASE = '/rebuild'

export type ScheduleState = 'offline' | 'online'
export type ScheduleMisfirePolicy = 'FIRE_ONCE' | 'SKIP' | 'FIRE_ALL_LIMITED'
export type ScheduleConcurrencyPolicy = 'ALLOW' | 'FORBID' | 'QUEUE'

export interface ScheduleRow {
  id: number
  wfCode: number
  name: string
  crontab: string
  startTime: string | null
  endTime: string | null
  state: ScheduleState
  priority: number
  workerGroup: string | null
  failRetryTimes: number
  failRetryInterval: number
  misfirePolicy: ScheduleMisfirePolicy
  concurrencyPolicy: ScheduleConcurrencyPolicy
  maxRunningInstances: number
  timezone: string
  createTime: string | null
  updateTime: string | null
}

export interface ScheduleInput {
  name?: string
  crontab: string
  startTime?: string | null
  endTime?: string | null
  priority?: number
  workerGroup?: string | null
  failRetryTimes?: number
  failRetryInterval?: number
  misfirePolicy?: ScheduleMisfirePolicy
  concurrencyPolicy?: ScheduleConcurrencyPolicy
  maxRunningInstances?: number
  timezone?: string
}

export interface CrontabPreview {
  valid: boolean
  nextFireTimes: string[]
}

export interface ScheduleCrudContract {
  listSchedules: (wf: number | string) => Promise<ScheduleRow[]>
  createSchedule: (wf: number | string, input: ScheduleInput) => Promise<ScheduleRow>
  updateSchedule: (scheduleId: number, input: ScheduleInput) => Promise<ScheduleRow>
  deleteSchedule: (scheduleId: number) => Promise<void>
  onlineSchedule: (scheduleId: number) => Promise<ScheduleRow>
  offlineSchedule: (scheduleId: number) => Promise<ScheduleRow>
  previewCrontab: (crontab: string, timezone?: string) => Promise<CrontabPreview>
}

const key = (value: number | string) => encodeURIComponent(String(value))

export function createScheduleCrudContract(projectId: number): ScheduleCrudContract {
  return {
    listSchedules: (wf) => request<ScheduleRow[]>(`${BASE}/workflow-definitions/${key(wf)}/schedules`),
    createSchedule: (wf, input) => request<ScheduleRow>(`${BASE}/workflow-definitions/${key(wf)}/schedules`, { method: 'POST', json: input }),
    updateSchedule: (id, input) => request<ScheduleRow>(`${BASE}/schedules/${id}`, { method: 'PUT', json: input }),
    deleteSchedule: async (id) => { await request(`${BASE}/schedules/${id}`, { method: 'DELETE' }) },
    onlineSchedule: (id) => request<ScheduleRow>(`${BASE}/schedules/${id}/online`, { method: 'POST' }),
    offlineSchedule: (id) => request<ScheduleRow>(`${BASE}/schedules/${id}/offline`, { method: 'POST' }),
    previewCrontab: (crontab, timezone = 'Asia/Shanghai') => request<CrontabPreview>(`${BASE}/crontab-preview`, {
      method: 'POST',
      json: { projectId, crontab, timezone },
    }),
  }
}
