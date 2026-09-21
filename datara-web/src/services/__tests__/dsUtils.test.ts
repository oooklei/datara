/**
 * dsUtils 纯函数单测（todo 6）
 * 覆盖：组合筛选（关键字/环境/分组/状态）、引擎色映射、引擎图标缩写。
 */
import { describe, it, expect } from 'vitest'
import { filterDataSources, dsTypeColor, dsTypeShort, testConnection, simulatePoolCounts } from '../mock/dsUtils'
import type { DataSource } from '../types'

const rows: DataSource[] = [
  {
    id: 'DS001', name: '万里GreatDB-生产业务库', type: '万里 GreatDB', host: '192.168.30.11', port: 9030,
    db: 'biz', user: 'root', pwd: '******', env: '生产', group: '交易域', tags: ['核心', '高优先'],
    pool: { max: 20, minIdle: 2, idle: 5, timeout: 30 }, status: 'enabled', owner: '张伟', createdAt: '2025-01-10', latency: 12, health: '健康',
  },
  {
    id: 'DS002', name: '华为GaussDB-测试库', type: '华为 GaussDB', host: '192.168.30.12', port: 8000,
    db: 'test', user: 'root', pwd: '******', env: '测试', group: '经营域', tags: ['测试'],
    pool: { max: 10, minIdle: 1, idle: 3, timeout: 30 }, status: 'enabled', owner: '李娜', createdAt: '2025-02-01', latency: 45, health: '健康',
  },
  {
    id: 'DS003', name: 'MySQL-开发库', type: 'MySQL', host: '192.168.30.13', port: 3306,
    db: 'dev', user: 'dev', pwd: '******', env: '开发', group: '数仓', tags: [],
    pool: { max: 5, minIdle: 1, idle: 2, timeout: 30 }, status: 'disabled', owner: '王强', createdAt: '2025-03-01', latency: 0, health: '异常',
  },
]

describe('filterDataSources', () => {
  it('无筛选返回全部', () => {
    expect(filterDataSources(rows, {})).toHaveLength(3)
  })

  it('关键字命中名称', () => {
    expect(filterDataSources(rows, { keyword: 'GaussDB' }).map((r) => r.id)).toEqual(['DS002'])
  })

  it('关键字命中主机', () => {
    expect(filterDataSources(rows, { keyword: '192.168.30.13' }).map((r) => r.id)).toEqual(['DS003'])
  })

  it('关键字命中库名', () => {
    expect(filterDataSources(rows, { keyword: 'biz' }).map((r) => r.id)).toEqual(['DS001'])
  })

  it('关键字大小写不敏感', () => {
    expect(filterDataSources(rows, { keyword: 'mysql' }).map((r) => r.id)).toEqual(['DS003'])
  })

  it('环境筛选', () => {
    expect(filterDataSources(rows, { env: '生产' }).map((r) => r.id)).toEqual(['DS001'])
  })

  it('分组筛选', () => {
    expect(filterDataSources(rows, { group: '经营域' }).map((r) => r.id)).toEqual(['DS002'])
  })

  it('状态筛选', () => {
    expect(filterDataSources(rows, { status: 'disabled' }).map((r) => r.id)).toEqual(['DS003'])
  })

  it('组合筛选（关键字+环境）', () => {
    expect(filterDataSources(rows, { keyword: '库', env: '测试' }).map((r) => r.id)).toEqual(['DS002'])
  })

  it('无匹配返回空数组', () => {
    expect(filterDataSources(rows, { keyword: '不存在的名字' })).toEqual([])
  })
})

describe('dsTypeColor', () => {
  it('已知类型返回品牌色', () => {
    expect(dsTypeColor('万里 GreatDB')).toBe('#c2410c')
    expect(dsTypeColor('Apache Doris')).toBe('#2563eb')
    expect(dsTypeColor('MySQL')).toBe('#0891b2')
  })

  it('未知类型回退主色', () => {
    // PostgreSQL 已注册为已知类型（品牌色 #336791），回退场景改用真正未登记的类型名
    expect(dsTypeColor('UnknownDB')).toBe('#1668dc')
  })
})

describe('dsTypeShort', () => {
  it('取类型名前 2 字符大写', () => {
    expect(dsTypeShort('MySQL')).toBe('MY')
    expect(dsTypeShort('Apache Doris')).toBe('AP')
    expect(dsTypeShort('Oracle')).toBe('OR')
  })

  it('空类型回退 ?', () => {
    expect(dsTypeShort('')).toBe('?')
    expect(dsTypeShort(undefined as unknown as string)).toBe('?')
  })
})

describe('testConnection', () => {
  it('正常主机与密码 → 成功且无诊断', () => {
    const r = testConnection('192.168.30.21', 'secret')
    expect(r.ok).toBe(true)
    expect(r.diagnostics).toEqual([])
    expect(r.latency).toBeGreaterThan(0)
  })

  it('host 含 local → 失败且含连接超时诊断', () => {
    const r = testConnection('localhost:3306', 'secret')
    expect(r.ok).toBe(false)
    expect(r.latency).toBe(0)
    expect(r.diagnostics.some((d) => d.includes('连接超时'))).toBe(true)
  })

  it('pwd 为 bad → 失败且含认证失败诊断', () => {
    const r = testConnection('192.168.30.21', 'bad')
    expect(r.ok).toBe(false)
    expect(r.latency).toBe(0)
    expect(r.diagnostics.some((d) => d.includes('认证失败'))).toBe(true)
  })

  it('host 含 local 且 pwd 为 bad → 多条诊断（>1）', () => {
    const r = testConnection('local', 'bad')
    expect(r.ok).toBe(false)
    expect(r.diagnostics.length).toBeGreaterThan(1)
  })

  it('延迟为确定性值（同输入同输出）', () => {
    expect(testConnection('192.168.30.21', 'secret').latency).toBe(
      testConnection('192.168.30.21', 'secret').latency,
    )
  })
})

describe('simulatePoolCounts', () => {
  it('活跃 = min(floor(max*0.4), max-minIdle)，空闲 = minIdle，等待 = 0', () => {
    const c = simulatePoolCounts({ max: 20, minIdle: 2 })
    expect(c).toEqual({ active: 8, idle: 2, waiting: 0 })
  })

  it('max 较小且 minIdle 较大时活跃被 max-minIdle 截断', () => {
    const c = simulatePoolCounts({ max: 5, minIdle: 4 })
    expect(c.active).toBe(1)
    expect(c.idle).toBe(4)
  })

  it('minIdle 为 0 时活跃 = floor(max*0.4)', () => {
    const c = simulatePoolCounts({ max: 10, minIdle: 0 })
    expect(c.active).toBe(4)
    expect(c.idle).toBe(0)
  })

  it('确定性：同输入同输出', () => {
    expect(simulatePoolCounts({ max: 20, minIdle: 2 })).toEqual(
      simulatePoolCounts({ max: 20, minIdle: 2 }),
    )
  })
})