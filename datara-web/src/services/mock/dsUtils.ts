/**
 * dsUtils — M03 数据源纯函数工具（todo 6）
 * 筛选/引擎图标派生均为确定性纯函数，便于单测与视图复用。
 */
import type { DataSource } from '../types'

export interface DsFilter {
  keyword?: string
  env?: string
  group?: string
  status?: string
}

/** 关键字 + 环境 + 分组 + 状态 组合筛选（关键字命中 name/type/host/db/id/group） */
export function filterDataSources(rows: DataSource[], f: DsFilter): DataSource[] {
  const kw = (f.keyword ?? '').trim().toLowerCase()
  return rows.filter((r) => {
    if (kw) {
      const hay = [r.name, r.type, r.host, r.db, r.id, r.group].join(' ').toLowerCase()
      if (!hay.includes(kw)) return false
    }
    if (f.env && r.env !== f.env) return false
    if (f.group && r.group !== f.group) return false
    if (f.status && r.status !== f.status) return false
    return true
  })
}

/** 引擎类型 → 品牌色（与 dataStore.dsTypes[].color 一致；未知类型回退主色） */
const DS_TYPE_COLORS: Record<string, string> = {
  '万里 GreatDB': '#c2410c',
  '华为 GaussDB': '#9333ea',
  '达梦 DM8': '#dc2626',
  'MySQL': '#0891b2',
  'Oracle': '#e11d48',
  'Apache Doris': '#2563eb',
  'Hive': '#f59e0b',
  'Kafka': '#0d9488',
  'PostgreSQL': '#336791',
  'SQL Server': '#a91d22',
  '人大金仓 Kingbase': '#c8102e',
  'HBase': '#f97316',
  'StarRocks': '#4f46e5',
  'MongoDB': '#47a248',
  'Redis': '#d82c20',
  'Elasticsearch': '#f5bd4f',
  'RocketMQ': '#f59e0b',
  'RabbitMQ': '#ff6600',
  'CSV文件': '#64748b',
  'JSON文件': '#64748b',
  'Parquet文件': '#64748b',
  'Excel文件': '#217346',
  'TXT文件': '#64748b',
  'RESTful API': '#7c3aed',
  'WebService': '#7c3aed',
}

export function dsTypeColor(type: string): string {
  return DS_TYPE_COLORS[type] ?? '#1668dc'
}

/** 引擎图标文字：类型名前 2 字符大写（原型同款） */
export function dsTypeShort(type: string): string {
  return (type || '?').slice(0, 2).toUpperCase()
}

/* ===== M03 连接测试/诊断（todo 7 · F3） ===== */

export interface ConnTestResult {
  ok: boolean
  latency: number
  diagnostics: string[]
}

/**
 * 模拟连接测试（确定性，无随机）：
 * - host 含 `local` → 连接超时 + 驱动缺失
 * - pwd === 'bad'  → 认证失败 + 驱动缺失
 * - 其余 → 成功，延迟 = 8 + (host.length * 7) % 40（8~47ms 确定性）
 */
export function testConnection(host: string, pwd: string): ConnTestResult {
  const diagnostics: string[] = []
  if (host.includes('local')) {
    diagnostics.push(`连接超时：目标库 ${host} 无响应（模拟诊断）`)
  }
  if (pwd === 'bad') {
    diagnostics.push('认证失败：账号或密码错误（模拟诊断）')
  }
  if (host.includes('local') || pwd === 'bad') {
    diagnostics.push('驱动缺失：未找到对应 JDBC 驱动（模拟诊断）')
    return { ok: false, latency: 0, diagnostics }
  }
  const latency = 8 + (host.length * 7) % 40
  return { ok: true, latency, diagnostics: [] }
}

/* ===== M03 连接池模拟计数（todo 8 · F2） ===== */

export interface PoolCounts {
  active: number
  idle: number
  waiting: number
}

/**
 * 连接池活跃/空闲/等待模拟计数（确定性，无随机）：
 * - 活跃 = min(floor(max * 0.4), max - minIdle)，至少 0
 * - 空闲 = minIdle
 * - 等待 = 0
 */
export function simulatePoolCounts(pool: { max: number; minIdle: number }): PoolCounts {
  const active = Math.max(0, Math.min(Math.floor(pool.max * 0.4), pool.max - pool.minIdle))
  return { active, idle: pool.minIdle, waiting: 0 }
}