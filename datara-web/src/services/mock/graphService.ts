/**
 * graphService mock：图定义持久化（localStorage + 内存）与版本管理。
 * 未来替换为真实后端 REST 实现，契约不变。
 * - get 返回深克隆，避免调用方直接改动污染 seed / 内存缓存（seed 数据隔离）
 * - save 记录版本快照（内存 + localStorage，保留最近 20 份），rollback 真实恢复历史文档
 */
import type { GraphDocument } from '../../graph/model'
import { cloneDoc } from '../../graph/model'
import type { IGraphService, VersionMeta } from '../types'
import { getSeedDoc } from './seed'
import { localTime } from './timeUtil'

const KEY = (id: string) => `datara.graph.${id}`
const VER = (id: string) => `datara.graph.${id}.versions`
const SNAP = (id: string) => `datara.graph.${id}.snaps`

const MAX_SNAPS = 20

interface Snapshot { version: number; doc: GraphDocument }

const memStore = new Map<string, GraphDocument>()
const memVersions = new Map<string, VersionMeta[]>()
const memSnaps = new Map<string, Snapshot[]>()

function lsGet<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : null
  } catch {
    return null
  }
}

function lsSet(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* 内存兜底已覆盖 */
  }
}

function emptyDoc(id: string): GraphDocument {
  return { id, name: '', version: 0, meta: { profile: '' }, nodes: [], edges: [] }
}

export const graphService: IGraphService = {
  async get(id) {
    const local = lsGet<GraphDocument>(KEY(id))
    if (local) return cloneDoc(local)
    const mem = memStore.get(id)
    if (mem) return cloneDoc(mem)
    const seed = getSeedDoc(id)
    return cloneDoc(seed ?? emptyDoc(id))
  },

  async save(doc, remark) {
    const next: GraphDocument = {
      ...doc,
      version: doc.version + 1,
      meta: { ...doc.meta, updatedAt: localTime() },
    }
    memStore.set(doc.id, next)
    lsSet(KEY(doc.id), next)
    const versions = memVersions.get(doc.id) ?? lsGet<VersionMeta[]>(VER(doc.id)) ?? []
    versions.unshift({ version: next.version, updatedAt: next.meta.updatedAt!, operator: '王工', remark })
    memVersions.set(doc.id, versions)
    lsSet(VER(doc.id), versions)
    const snaps = memSnaps.get(doc.id) ?? lsGet<Snapshot[]>(SNAP(doc.id)) ?? []
    snaps.unshift({ version: next.version, doc: cloneDoc(next) })
    if (snaps.length > MAX_SNAPS) snaps.length = MAX_SNAPS // 控制持久化体积
    memSnaps.set(doc.id, snaps)
    lsSet(SNAP(doc.id), snaps)
    return { version: next.version }
  },

  async listVersions(id) {
    return memVersions.get(id) ?? lsGet<VersionMeta[]>(VER(id)) ?? []
  },

  async rollback(id, version) {
    const cur = await this.get(id)
    if (!cur) throw new Error(`图不存在: ${id}`)
    const snaps = memSnaps.get(id) ?? lsGet<Snapshot[]>(SNAP(id)) ?? []
    const snap = snaps.find((s) => s.version === version)
    const seed = getSeedDoc(id)
    // 优先恢复历史快照；与种子版本一致时回落种子；旧数据（修复前仅存版本号）退化为仅重置版本
    const restored = snap
      ? cloneDoc(snap.doc)
      : seed && seed.version === version
        ? cloneDoc(seed)
        : { ...cur, version }
    const rolled: GraphDocument = {
      ...restored,
      version,
      meta: { ...restored.meta, updatedAt: localTime() },
    }
    memStore.set(id, rolled)
    lsSet(KEY(id), rolled)
    return cloneDoc(rolled)
  },
}

export type { IGraphService }
