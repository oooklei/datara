/**
 * I12 T11（C24/C25/C26）新组件注册留痕：
 * - file_sync/assert/notify 三组件 schema 存在、编号与分类归属锁定；
 *   同步编排重构后 file_sync 降级为编排链内执行节点（palette 不提供，categories 收敛为 ['sync']）；
 * - required 必填在各分型下的缺失口径（W1 requiredMissing 共用判定）；
 * - C25 assert 双出口（success/failure 固定 ports，复用 conditions/switch 分支边机制）；
 * - page_board 让号：不再占用 C24 编号（Inspector 编号徽标 v-if 容忍无 code）；
 * - palette 可拖：assert/notify 分别落位 数据计算/通用 组，无灰置；
 * - 同步编排端点合一：C37 endpoint_select 必填三分型口径（src_base/tgt_base/file_sync）+
 *   runtimeOnly 执行组件（sync/file_sync）排除：不进 palette、W1 必填校验与分支完整性校验均跳过。
 * 防回归锁点：编号回填漂移（page_board 重占 C24）、分类漂移、required/showIf 分型漂移、runtimeOnly 排除漂移。
 */
import { describe, it, expect } from 'vitest'
import type { GraphDocument } from '../../model'
import type { ConditionDef, NodeSchema } from '../types'
import { dagProfile } from '../dag'
import { requiredMissing } from '../formLinkage'

const schemaOf = (type: string) => {
  const s = dagProfile.nodeTypes[type]
  expect(s, `${type} 应已在 dagProfile.nodeTypes 注册`).toBeDefined()
  return s!
}

/* ================= 八段 DSL conditions 求值辅助（M-B2 迁移后分型显隐/必填口径的测试侧等价求值） ================= */

/** 单条 when 是否满足（op 口径对齐 dag.ts 迁移声明：eq/ne/notEq/in/notIn/empty/notEmpty） */
function whenMet(when: ConditionDef['when'], d: Record<string, unknown>): boolean {
  const v = d[when.field]
  const empty = v === undefined || v === null || String(v) === ''
  switch (when.op) {
    case 'eq': return v === when.value
    case 'ne':
    case 'notEq': return v !== when.value
    case 'in': return Array.isArray(when.value) && (when.value as unknown[]).includes(v)
    case 'notIn': return Array.isArray(when.value) && !(when.value as unknown[]).includes(v)
    case 'empty': return empty
    case 'notEmpty': return !empty
    default: return false
  }
}

/** 按 conditions 段求值字段可见性：同字段被多条条件引用时取交集（与迁移前 AND 复合 showIf 等价），未被引用恒显示 */
function condVisible(schema: { conditions?: ConditionDef[] }, key: string, d: Record<string, unknown>): boolean {
  const refs = (schema.conditions ?? []).filter((c) => c.show.includes(key))
  return refs.length === 0 || refs.every((c) => whenMet(c.when, d))
}

/**
 * W1 必填口径 × conditions 分型显隐：与生产 requiredMissing 同判定（required 且可见且值为空），
 * 叠加八段 conditions 可见性——生产求值器尚未消费 conditions 段，迁移组件（assert/notify 等）暂以此等价求值。
 */
function requiredMissingDsl(schema: NodeSchema, data: Record<string, unknown>): string[] {
  return (schema.form ?? [])
    .filter((f) => f.required && f.type !== 'hint' && condVisible(schema, f.key, data))
    .filter((f) => {
      const v = data[f.key]
      if (Array.isArray(v)) return v.length === 0
      return v === undefined || v === null || v === ''
    })
    .map((f) => f.label || f.key)
}

describe('I12 T11 C24/C25/C26 组件注册', () => {
  it('三组件已注册且编号/分类锁定（R1 归属约定）', () => {
    expect(schemaOf('file_sync').code).toBe('C24')
    expect(schemaOf('file_sync').categories).toEqual(['sync'])
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

  it('palette 归属：file_sync 降级链内执行不再入 palette；assert→数据计算、notify→通用（无灰置）', () => {
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
  it('file_sync 降级链内执行节点：业务读写配置经编排链细项合并，表单无必填项', () => {
    const s = schemaOf('file_sync')
    expect(requiredMissing(s, { ...(s.defaults ?? {}) })).toEqual([])
    // 键名统一 camelCase：无 snake_case 表单键残留
    for (const f of s.form) expect(f.key).not.toMatch(/_[a-z]/)
  })

  it('file_sync 表单契约：标识列 showIf 依赖 src_flag 写入模式；无旧直连键残留', () => {
    const form = schemaOf('file_sync').form
    const byKey = (k: string) => form.find((f) => f.key === k)!
    expect(byKey('flagColumn').showIf!({ writeMode: 'append' })).toBe(false)
    expect(byKey('flagColumn').showIf!({ writeMode: 'src_flag' })).toBe(true)
    // 同步编排重构后旧直连键（文件来源/目标端）不再出现在执行节点表单
    for (const k of ['filePath', 'stagedPath', 'ddl', 'targetDs', 'targetTable']) {
      expect(byKey(k), `${k} 应已移除`).toBeUndefined()
    }
  })

  it('C25 上游节点引用（resource·upstreamNodes）仅上游模式展示；规则列参考仅手选模式展示（I12 T11 修）', () => {
    const schema = schemaOf('assert')
    const form = schema.form
    const byKey = (k: string) => form.find((f) => f.key === k)!
    expect(byKey('assertUpstream')?.type).toBe('resource')
    expect(byKey('assertUpstream')?.cap?.mode).toBe('upstreamNodes')
    expect(byKey('ruleColumns')?.type).toBe('resource')
    expect(byKey('ruleColumns')?.cap?.mode).toBe('column')
    // 分型显隐迁移至 conditions 段：assertSrc=upstream 显示 assertUpstream；assertSrc=manual 显示手选族
    expect(schema.conditions?.find((c) => c.show.includes('assertUpstream'))).toMatchObject({
      when: { field: 'assertSrc', op: 'eq', value: 'upstream' },
    })
    expect(schema.conditions?.find((c) => c.show.includes('ruleColumns'))).toMatchObject({
      when: { field: 'assertSrc', op: 'eq', value: 'manual' },
    })
    // 分型显隐按声明等价求值
    expect(condVisible(schema, 'assertUpstream', { assertSrc: 'upstream' })).toBe(true)
    expect(condVisible(schema, 'assertUpstream', { assertSrc: 'manual' })).toBe(false)
    expect(condVisible(schema, 'ruleColumns', { assertSrc: 'manual' })).toBe(true)
    expect(condVisible(schema, 'ruleColumns', { assertSrc: 'upstream' })).toBe(false)
    // 显式引用与规则列参考均非必填（W1 口径不受影响）
    expect(byKey('assertUpstream').required).toBeFalsy()
    expect(byKey('ruleColumns').required).toBeFalsy()
  })

  it('assert 上游模式不强制手选项；手选模式必填数据源与表', () => {
    const s = schemaOf('assert')
    // 必填口径 = required × conditions 分型显隐 × 空值（生产 requiredMissing 尚未消费 conditions 段，
    // 迁移组件以 requiredMissingDsl 按八段声明等价求值，保持 W1 原语义）
    expect(requiredMissingDsl(s, { ...(s.defaults ?? {}) })).toEqual([])
    expect(requiredMissingDsl(s, { ...(s.defaults ?? {}), assertSrc: 'manual' }))
      .toEqual(['校验数据源', '校验表（schema → 表）'])
  })

  it('notify 仅日志无必填；webhook 分型必填 URL', () => {
    const s = schemaOf('notify')
    // url 必填 + conditions 分型（channel=webhook 才显示）双声明
    expect(s.conditions?.find((c) => c.show.includes('url'))).toMatchObject({
      when: { field: 'channel', op: 'eq', value: 'webhook' },
    })
    expect(requiredMissingDsl(s, { ...(s.defaults ?? {}) })).toEqual([])
    expect(requiredMissingDsl(s, { ...(s.defaults ?? {}), channel: 'webhook' })).toEqual(['Webhook URL'])
  })

  it('endpoint_select 三分型必填口径：src_base 缺 3 项 / tgt_base 仅缺目标表 / file_sync 缺 2 项', () => {
    const s = schemaOf('endpoint_select')
    const d = (over: Record<string, unknown>) => ({ ...(s.defaults ?? {}), ...over })
    // src_base：srcDs/srcTable/tgtDs 必填；tgtTable 该分型留空合法（按源表同名/文件表头新建）
    expect(requiredMissing(s, d({ baseMode: 'src_base' }))).toEqual(['源数据源', '源表', '目标数据源'])
    // tgt_base：填好源/目标数据源后仅缺目标表（probeResult 留空 = 探测全部匹配，合法不报缺）
    expect(requiredMissing(s, d({ baseMode: 'tgt_base', srcDs: 'src1', tgtDs: 'tgt1' }))).toEqual(['目标表'])
    // file_sync：文件路径 + 目标数据源必填（src 侧字段不适用；tgtTable 留空按文件表头新建）
    expect(requiredMissing(s, d({ baseMode: 'file_sync' }))).toEqual(['文件路径（/datara/files 相对）', '目标数据源'])
  })
})

describe('同步编排端点合一：runtimeOnly 执行组件排除', () => {
  it('sync/file_sync 标记 runtimeOnly 且不进 palette 任何分组', () => {
    expect(dagProfile.nodeTypes.sync?.runtimeOnly).toBe(true)
    expect(dagProfile.nodeTypes.file_sync?.runtimeOnly).toBe(true)
    const types = dagProfile.palette.flatMap((g) => (g.items ?? []).map((i) => i.type))
    expect(types).not.toContain('sync')
    expect(types).not.toContain('file_sync')
  })

  it('runtimeOnly 排除（阳性对照）：空配置 endpoint_select 必报必填，且全部告警落在对照节点（sync/file_sync 不被 W1 误报）', () => {
    /* n5 为非 runtimeOnly 对照节点（endpoint_select 空配置，默认 src_base 分型缺 3 项必填）：
       对照节点必报 → 证明 W1 校验器活着；全部告警均落在 n5 → sync/file_sync 未被 W1 误报（runtimeOnly 排除生效）。
       注：分支完整性校验的 runtimeOnly 守卫因 runtimeOnly schema 均无 ports（!schema.ports 先行早退）
       而无法行为级敏感化，此处仅覆盖 W1 排除。 */
    const doc = {
      id: 'wf_rt', name: 'rt', version: 1, meta: {},
      nodes: [
        { id: 'n1', type: 'start', position: { x: 0, y: 0 }, data: { name: '开始' } },
        { id: 'n2', type: 'sync', position: { x: 200, y: 0 }, data: { name: '同步执行' } },
        { id: 'n3', type: 'file_sync', position: { x: 400, y: 0 }, data: { name: '文件入仓执行' } },
        { id: 'n4', type: 'end', position: { x: 600, y: 0 }, data: { name: '结束' } },
        { id: 'n5', type: 'endpoint_select', position: { x: 800, y: 0 }, data: { name: '端点选择' } },
      ],
      edges: [
        { id: 'e1', source: 'n1', target: 'n2', kind: 'flow' },
        { id: 'e2', source: 'n2', target: 'n3', kind: 'flow' },
        { id: 'e4', source: 'n3', target: 'n5', kind: 'flow' },
        { id: 'e5', source: 'n5', target: 'n4', kind: 'flow' },
      ],
    } as unknown as GraphDocument
    const issues = dagProfile.validators.flatMap((v) => v(doc))
    expect(issues.length).toBeGreaterThan(0)
    expect(issues.every((i) => i.nodeId === 'n5' && i.msg.includes('必填项未配置'))).toBe(true)
  })
})
