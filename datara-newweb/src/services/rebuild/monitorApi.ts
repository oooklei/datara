/** B3 cluster-monitoring contract migrated to the rebuild API. */

import { request } from '../http'

export type MonitorHeartbeat = 'online' | 'offline' | 'unknown'
export type MonitorMetricState = 'fresh' | 'stale' | 'unsupported'

export interface MonitorNode {
  module: 'master' | 'worker' | 'ssh'
  node: string
  cpu: number | null
  mem: number | null
  memUsedMb: number | null
  memTotalMb: number | null
  disk: number | null
  heartbeat: MonitorHeartbeat
  metricState: MonitorMetricState
  lastSeen: string | null
  tags: string[]
}

export interface MonitorSnapshot {
  zkAvailable: boolean
  generatedAt: string
  nodes: MonitorNode[]
}

export const MONITOR_CONTRACT_METHODS = ['fetchMonitorNodes'] as const

export interface MonitorContract {
  fetchMonitorNodes: () => Promise<MonitorSnapshot>
}

export function createMonitorContract(): MonitorContract {
  return {
    fetchMonitorNodes: () => request<MonitorSnapshot>('/rebuild/monitor/nodes', { preserveEnvelopeCode: true }),
  }
}
