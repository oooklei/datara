/** B6 runtime-node contract migrated to the rebuild API. */

import { request } from '../http'

/**
 * 九字段冻结载荷（B6-1，与后端 `runtime_node/api.py` `_payload` 逐字段对齐）。
 * 凭据列（auth）永不回显，故不在前端类型面。
 */
export interface RuntimeNode {
  id: number
  name: string
  kind: string
  host: string | null
  port: number | null
  user: string | null
  runtimeDir: string | null
  status: string
  lastHeartbeat: string | null
}

/** 目录条目（`service.ls` 逐字段透出；mtime 为 unix 秒）。 */
export interface RuntimeNodeDirEntry {
  name: string
  dir: boolean
  size: number
  mtime: number
}

/** 目录浏览结果（缺省路径按远端 SFTP 家目录语义解析）。 */
export interface RuntimeNodeDirListing {
  path: string
  entries: RuntimeNodeDirEntry[]
}

export const RUNTIME_NODE_CONTRACT_METHODS = ['listRuntimeNodes', 'lsRuntimeNodeDir'] as const

export interface RuntimeNodeContract {
  listRuntimeNodes: () => Promise<RuntimeNode[]>
  lsRuntimeNodeDir: (nodeId: number, path?: string) => Promise<RuntimeNodeDirListing>
}

export function createRuntimeNodeContract(): RuntimeNodeContract {
  return {
    listRuntimeNodes: () =>
      request<RuntimeNode[]>('/rebuild/runtime-nodes', { preserveEnvelopeCode: true }),
    lsRuntimeNodeDir: (nodeId, path = '') =>
      request<RuntimeNodeDirListing>(`/rebuild/runtime-nodes/${nodeId}/ls`, {
        preserveEnvelopeCode: true,
        query: path ? { path } : undefined,
      }),
  }
}
