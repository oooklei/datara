/**
 * I12 T6（R1）分类模型留痕：
 * - dag profile nodeTypes 每个条目都有非空 categories，值域限于 sync/etl/stream/general 四类；
 * - 关键归属锁点：sync 含 'sync'、sql 含 'etl'、流三件纯 'stream'、demo_pipeline 纯 'general'。
 * 防回归锁点：新增组件漏标 categories、归属漂移（常量 satisfies 对齐 ComponentCategory 单源）。
 */
import { describe, it, expect } from 'vitest'
import { dagProfile } from '../dag'
import type { ComponentCategory } from '../types'

const VALID_CATEGORIES = ['sync', 'etl', 'stream', 'general'] as const satisfies readonly ComponentCategory[]

describe('I12 NodeSchema.categories 组件归属', () => {
  it('nodeTypes 每个条目都有非空 categories，且每个值均为合法分类', () => {
    const entries = Object.entries(dagProfile.nodeTypes)
    expect(entries.length).toBeGreaterThan(0)
    entries.forEach(([type, schema]) => {
      const cats = schema.categories
      expect(Array.isArray(cats) && cats.length > 0, `${type} 的 categories 缺失或为空`).toBe(true)
      cats?.forEach((c) => {
        expect(VALID_CATEGORIES, `${type} 含非法分类值 ${c}`).toContain(c)
      })
    })
  })

  it('关键归属：sync 条目含 sync，sql 条目含 etl', () => {
    const syncCats = dagProfile.nodeTypes.sync.categories
    expect(syncCats, 'sync 条目缺 categories').toBeDefined()
    expect(syncCats).toContain('sync')
    const sqlCats = dagProfile.nodeTypes.sql.categories
    expect(sqlCats, 'sql 条目缺 categories').toBeDefined()
    expect(sqlCats).toContain('etl')
  })

  it('流三件（stream_input/fuse/output）归属精确为 stream（单分类）', () => {
    ;['stream_input', 'stream_fuse', 'stream_output'].forEach((t) => {
      const cats = dagProfile.nodeTypes[t].categories
      expect(cats, `${t} 缺 categories`).toBeDefined()
      expect(cats).toEqual(['stream'])
    })
  })

  it('demo_pipeline 归属精确为 general', () => {
    const cats = dagProfile.nodeTypes.demo_pipeline.categories
    expect(cats, 'demo_pipeline 缺 categories').toBeDefined()
    expect(cats).toEqual(['general'])
  })
})
