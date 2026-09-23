/**
 * I12 T11（C24/C25/C26）新组件注册留痕：
 * - file_sync/assert/notify 三组件 schema 存在、编号与分类归属锁定（R1 归属约定）；
 * - required 必填在各分型下的缺失口径（W1 requiredMissing 共用判定）；
 * - C25 assert 双出口（success/failure 固定 ports，复用 conditions/switch 分支边机制）；
 * - page_board 让号：不再占用 C24 编号（Inspector 编号徽标 v-if 容忍无 code）；
 * - palette 可拖：三组件分别落位 数据同步/数据计算/通用 组，无灰置。
 * 防回归锁点：编号回填漂移（page_board 重占 C24）、分类漂移、required/showIf 分型漂移。
 */
import { describe, it, expect } from 'vitest'
import { dagProfile } from '../dag'
import { requiredMissing } from '../formLinkage'

const schemaOf = (type: string) => {
  const s = dagProfile.nodeTypes[type]
  expect(s, `${type} 应已在 dagProfile.nodeTypes 注册`).toBeDefined()
  return s!
}

describe('I12 T11 C24/C25/C26 组件注册', () => {
  it('三组件已注册且编号/分类锁定（R1 归属约定）', () => {
    expect(schemaOf('file_sync').code).toBe('C24')
    expect(schemaOf('file_sync').categories).toEqual(['sync', 'general'])
    expect(schemaOf('assert').code).toBe('C25')
    expect(schemaOf('assert').categories).toEqual(['etl', 'general'])
    expect(schemaOf('notify').code).toBe('C26')
    expect(schemaOf('notify').categories).toEqual(['general', 'stream', 'etl'])
  })

  it('page_board 让号：不再占用 C24 编号', () => {
    expect(dagProfile.nodeTypes.page_board.code).toBeUndefined()
  })

  it('C25 assert 双出口 ports 固定为 success/failure', () => {
    const ports = schemaOf('assert').ports!({})
    expect(ports.map((p) => p.id)).toEqual(['success', 'failure'])
    expect(ports.map((p) => p.label)).toEqual(['通过', '不通过'])
  })

  it('palette 三组可拖：file_sync→数据同步、assert→数据计算、notify→通用（无灰置）', () => {
    const groupOf = (type: string) =>
      dagProfile.palette.find((g) => (g.items ?? []).some((i) => i.type === type))
    expect(groupOf('file_sync')?.name).toBe('数据同步')
    expect(groupOf('assert')?.name).toBe('数据计算')
    expect(groupOf('notify')?.name).toBe('通用')
    for (const t of ['file_sync', 'assert', 'notify']) {
      const item = groupOf(t)!.items!.find((i) => i.type === t)!
      expect(item.disabled, `${t} 不应灰置`).toBeFalsy()
    }
    /* palette 引用完整性：所有条目都能在 nodeTypes 找到定义（防拖入未知类型） */
    dagProfile.palette.forEach((g) => (g.items ?? []).forEach((i) => {
      expect(dagProfile.nodeTypes[i.type], `${i.type} 应在 nodeTypes`).toBeDefined()
    }))
  })
})

describe('I12 T11 required 必填分型口径（requiredMissing 共用判定）', () => {
  it('file_sync 缺省全空 → 来源目录与上传暂存二选一均缺失 + 目标端两项；补齐任一来源后清零', () => {
    const s = schemaOf('file_sync')
    expect(requiredMissing(s, { ...(s.defaults ?? {}) }))
      .toEqual(['文件来源目录/路径', '上传暂存路径（/datara/files 相对）', '目标数据源', '目标 schema → 表'])
    // 补齐文件路径来源（targetTable 为 table-picker schemaTable 对象形态；键 camelCase 对齐 I12 T11 修）
    expect(requiredMissing(s, {
      ...(s.defaults ?? {}),
      filePath: 'samples/orders', fileName: 'orders.csv',
      targetDs: '内置数仓-datara_dw', targetTable: { schema: 'ods', table: 'orders' },
    })).toEqual([])
    // 仅填上传暂存（I12 T11 修：二选一备选来源）→ 来源侧不再缺失
    expect(requiredMissing(s, {
      ...(s.defaults ?? {}),
      stagedPath: 'staging/orders.csv',
      targetDs: '内置数仓-datara_dw', targetTable: { schema: 'ods', table: 'orders' },
    })).toEqual([])
  })

  it('file_sync 来源互斥 showIf 与 DDL 预览（I12 T11 修）', () => {
    const form = schemaOf('file_sync').form
    const byKey = (k: string) => form.find((f) => f.key === k)!
    // 二选一：任一来源已填 → 另一侧字段隐藏（showIf 互斥）
    expect(byKey('filePath').showIf!({ stagedPath: 'a.csv' })).toBe(false)
    expect(byKey('filePath').showIf!({ stagedPath: '' })).toBe(true)
    expect(byKey('stagedPath').showIf!({ filePath: 'samples' })).toBe(false)
    expect(byKey('stagedPath').showIf!({ filePath: '' })).toBe(true)
    // DDL 预览：仅在 autoCreate 开启时展示
    expect(byKey('ddl').showIf!({ autoCreate: true })).toBe(true)
    expect(byKey('ddl').showIf!({ autoCreate: false })).toBe(false)
    // 键名统一 camelCase（I12 T11 修）：无 snake_case 表单键残留
    for (const f of form) expect(f.key).not.toMatch(/_[a-z]/)
  })

  it('C25 上游节点引用（upstream-ref）仅上游模式展示；规则列参考仅手选模式展示（I12 T11 修）', () => {
    const form = schemaOf('assert').form
    const byKey = (k: string) => form.find((f) => f.key === k)!
    expect(byKey('assertUpstream')?.type).toBe('upstream-ref')
    expect(byKey('assertUpstream').showIf!({ assertSrc: 'upstream' })).toBe(true)
    expect(byKey('assertUpstream').showIf!({ assertSrc: 'manual' })).toBe(false)
    expect(byKey('ruleColumns')?.type).toBe('field-select')
    expect(byKey('ruleColumns').showIf!({ assertSrc: 'manual' })).toBe(true)
    expect(byKey('ruleColumns').showIf!({ assertSrc: 'upstream' })).toBe(false)
    // 显式引用与规则列参考均非必填（W1 口径不受影响）
    expect(byKey('assertUpstream').required).toBeFalsy()
    expect(byKey('ruleColumns').required).toBeFalsy()
  })

  it('assert 上游模式不强制手选项；手选模式必填数据源与表', () => {
    const s = schemaOf('assert')
    expect(requiredMissing(s, { ...(s.defaults ?? {}) })).toEqual([])
    expect(requiredMissing(s, { ...(s.defaults ?? {}), assertSrc: 'manual' }))
      .toEqual(['校验数据源', '校验表（schema → 表）'])
  })

  it('notify 仅日志无必填；webhook 分型必填 URL', () => {
    const s = schemaOf('notify')
    expect(requiredMissing(s, { ...(s.defaults ?? {}) })).toEqual([])
    expect(requiredMissing(s, { ...(s.defaults ?? {}), channel: 'webhook' })).toEqual(['Webhook URL'])
  })
})
