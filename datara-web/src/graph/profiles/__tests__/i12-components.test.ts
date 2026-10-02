/**
 * I12 T11（C24/C25/C26）组件注册留痕：
 * - file_sync/assert/notify 三组件 schema 存在、编号与分类归属锁定；
 * - 同步编排端点合一后，file_sync(C24) 为 runtimeOnly 执行节点，不再进入设计态 palette/必填校验；
 * - required 必填在各分型下的缺失口径（W1 requiredMissing 共用判定）；
 * - C25 assert 双出口（success/failure 固定 ports，复用 conditions/switch 分支边机制）；
 * - page_board 让号：不再占用 C24 编号（Inspector 编号徽标 v-if 容忍无 code）；
 * - palette 可拖：assert→数据计算、notify→通用；file_sync 只供运行图/实例详情渲染。
 * 防回归锁点：编号回填漂移（page_board 重占 C24）、分类/runtimeOnly 漂移、required/showIf 分型漂移。
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
    expect(schemaOf('file_sync').categories).toEqual(['sync'])
    expect(schemaOf('file_sync').runtimeOnly).toBe(true)
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

  it('palette 只暴露设计态组件：assert→数据计算、notify→通用；file_sync runtimeOnly 不可拖', () => {
    const groupOf = (type: string) =>
      dagProfile.palette.find((g) => (g.items ?? []).some((i) => i.type === type))
    expect(groupOf('file_sync')).toBeUndefined()
    expect(groupOf('assert')?.name).toBe('数据计算')
    expect(groupOf('notify')?.name).toBe('通用')
    for (const t of ['assert', 'notify']) {
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
  it('file_sync 为运行态执行组件：设计态不承担业务必填，兜底参数不阻断保存', () => {
    const s = schemaOf('file_sync')
    expect(s.runtimeOnly).toBe(true)
    expect(requiredMissing(s, { ...(s.defaults ?? {}) })).toEqual([])
  })

  it('文件同步业务表单集中在 C37 端点选择 file_sync 分型，C24 仅保留运行兜底', () => {
    const form = schemaOf('endpoint_select').form
    const byKey = (k: string) => form.find((f) => f.key === k)!
    expect(byKey('filePath').showIf!({ baseMode: 'file_sync' })).toBe(true)
    expect(byKey('filePath').showIf!({ baseMode: 'src_base' })).toBe(false)
    expect(byKey('tgtDs').showIf).toBeUndefined()
    expect(form.filter((f) => f.key === 'tgtTable').some((f) => f.showIf?.({ baseMode: 'file_sync' }))).toBe(true)
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
