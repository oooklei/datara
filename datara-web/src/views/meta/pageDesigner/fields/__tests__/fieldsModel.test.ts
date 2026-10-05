/**
 * fieldsModel 纯函数单测（组件初始化「表单定义模式」）：
 * - 判型：detectPageMode / detectFieldsSource（page DSL vs spec.fields vs 八段 form.params）
 * - 加载：loadFieldsState 双源解析 + 空声明骨架
 * - 回写：toFieldsSpec 原位写回 + baseSpec 其余段保留 + dropPolicy 覆写
 * - 初始化：rowsFromCatalogFormFields（目录 formFields → 9 基元行）+ initWithCatalogRows 仅空态物化
 * - 规范化：normFieldRow 未知键保留 / normDropPolicy / makeFieldRow 八段 visible
 */
import { describe, expect, it } from 'vitest'
import {
  applyDeclSpec, detectFieldsSource, detectPageMode, initWithCatalogRows, loadDeclState, loadFieldsState,
  makeFieldRow, normDropPolicy, normFieldRow, rowsFromCatalogFormFields, toFieldsSpec,
} from '../fieldsModel'

describe('detectPageMode / detectFieldsSource（spec 判型）', () => {
  it("spec.page 键存在 → page 模式（即使同携带 fields）", () => {
    expect(detectPageMode({ page: { widgets: [] }, fields: [] }, 'dag-engine')).toBe(true)
  })
  it("fields 数组 / form 对象 → fields 模式", () => {
    expect(detectPageMode({ fields: [] }, 'dag-engine')).toBe(false)
    expect(detectPageMode({ form: { params: [] } }, 'dag-engine')).toBe(false)
  })
  it('两者皆无 → executionModel=page 兜底判 page，否则 fields', () => {
    expect(detectPageMode({}, 'page')).toBe(true)
    expect(detectPageMode({}, 'dag-engine')).toBe(false)
    expect(detectPageMode(null, 'page')).toBe(true)
  })
  it('来源判定：fields 优先，其次 form.params，空声明兜底 fields', () => {
    expect(detectFieldsSource({ fields: [], form: { params: [] } })).toBe('fields')
    expect(detectFieldsSource({ form: { params: [] } })).toBe('form.params')
    expect(detectFieldsSource({})).toBe('fields')
    expect(detectFieldsSource(null)).toBe('fields')
  })
})

describe('loadFieldsState（双源加载 + 空声明骨架）', () => {
  it('spec.fields 源：行规范化 + dropPolicy 归一化 + baseSpec 深拷贝', () => {
    const spec = {
      fields: [{ key: 'sql', label: 'SQL', uiType: 'text', required: true, showIf: 'x>1' }],
      dropPolicy: { autoName: '{n}', maxInstances: 3 },
      other: 1,
    }
    const st = loadFieldsState(spec)
    expect(st.source).toBe('fields')
    expect(st.rows).toHaveLength(1)
    expect(st.rows[0]).toMatchObject({ key: 'sql', required: true })
    expect(st.dropPolicy).toMatchObject({ autoName: '{n}', maxInstances: 3 })
    expect(st.baseSpec).toEqual(spec)
    expect(st.baseSpec).not.toBe(spec)
  })
  it('八段 form.params 源：行取自 form.params', () => {
    const st = loadFieldsState({ form: { title: '参数', params: [{ key: 'a', label: 'A', uiType: 'number' }] } })
    expect(st.source).toBe('form.params')
    expect(st.rows[0].key).toBe('a')
  })
  it('空声明 {} → 可编辑骨架（rows 空，source=fields）', () => {
    const st = loadFieldsState({})
    expect(st.source).toBe('fields')
    expect(st.rows).toEqual([])
    expect(st.baseSpec).toEqual({})
  })
})

describe('toFieldsSpec（保存回写：原源写回 + 其余段保留）', () => {
  it('fields 源：写 out.fields，其余 spec 段与 dropPolicy 原样/覆写', () => {
    const st = loadFieldsState({ fields: [{ key: 'a', label: 'A', uiType: 'text', required: false }], other: { x: 1 } })
    st.rows.push({ ...makeFieldRow('fields'), key: 'b', label: 'B' })
    st.dropPolicy = { ...st.dropPolicy, autoName: '{type}_{n}' }
    const out = toFieldsSpec(st)
    expect(out.other).toEqual({ x: 1 })
    expect((out.fields as { key: string }[]).map((r) => r.key)).toEqual(['a', 'b'])
    expect((out.dropPolicy as { autoName: string }).autoName).toBe('{type}_{n}')
  })
  it('八段源：写 form.params，form.title 等其余段与八段其他键保留，不新增顶层 fields', () => {
    const st = loadFieldsState({
      form: { title: '参数', group: '基础', params: [{ key: 'a', label: 'A', uiType: 'text', visible: true }] },
      lineage: { out: 't1' },
    })
    st.rows[0].label = 'A2'
    const out = toFieldsSpec(st)
    const form = out.form as { title: string; group: string; params: { key: string; label: string; visible: boolean }[] }
    expect(form.title).toBe('参数')
    expect(form.group).toBe('基础')
    expect(form.params[0].label).toBe('A2')
    expect(out.lineage).toEqual({ out: 't1' })
    expect(out.fields).toBeUndefined()
  })
})

describe('rowsFromCatalogFormFields（组件初始化：目录 formFields → 行）', () => {
  it('type 已 9 基元恒等映射；defaultValue→default、placeholder→desc、options 拷贝', () => {
    const rows = rowsFromCatalogFormFields([
      { key: 'srcDs', label: '源', type: 'resource', required: true },
      { key: 'n', label: '阈值', type: 'number', defaultValue: 10 },
      { key: 'hint1', label: '提示', type: 'hint', placeholder: '填写说明' },
      { key: 'm', label: '方式', type: 'select', options: [{ label: '全量', value: 'full' }, { label: '增量', value: 2 }] },
    ])
    expect(rows).toHaveLength(4)
    expect(rows[0]).toMatchObject({ key: 'srcDs', uiType: 'resource', required: true })
    expect(rows[1].default).toBe(10)
    expect(rows[2].desc).toBe('填写说明')
    expect(rows[3].options).toEqual([{ label: '全量', value: 'full' }, { label: '增量', value: 2 }])
  })
  it('type 越界兜底 text；无 key 且无 label 行过滤；非数组入参返回空', () => {
    expect(rowsFromCatalogFormFields([{ key: 'x', label: 'X', type: 'magic' }])[0].uiType).toBe('text')
    expect(rowsFromCatalogFormFields([{ key: '', label: '' }, { type: 'text' }])).toEqual([])
    expect(rowsFromCatalogFormFields(undefined)).toEqual([])
  })
})

describe('initWithCatalogRows（仅空态物化——组件初始化语义）', () => {
  it('rows 为空 → 物化目录行；已有行 → 原样返回；目录行空 → 原样', () => {
    const blank = loadFieldsState({})
    const rows = rowsFromCatalogFormFields([{ key: 'a', label: 'A', type: 'text' }])
    expect(initWithCatalogRows(blank, rows).rows).toHaveLength(1)
    const nonBlank = loadFieldsState({ fields: [{ key: 'b', label: 'B', uiType: 'text', required: false }] })
    expect(initWithCatalogRows(nonBlank, rows)).toBe(nonBlank)
    expect(initWithCatalogRows(blank, [])).toBe(blank)
  })
})

describe('normFieldRow / normDropPolicy / makeFieldRow（规范化）', () => {
  it('normFieldRow：已知键归一化（required 严格布尔），未知键（showIf/cap/visible）浅拷贝保留', () => {
    const row = normFieldRow({ key: 'a', label: 1, uiType: 9, required: true, showIf: 'x', cap: { min: 0 }, visible: true })
    expect(row).toMatchObject({ key: 'a', label: '1', uiType: '9', required: true, showIf: 'x', cap: { min: 0 }, visible: true })
    expect(normFieldRow({ required: 1 }).required).toBe(false)
    expect(normFieldRow(null)).toMatchObject({ key: '', label: '', uiType: '', required: false })
  })
  it('normDropPolicy：布尔/字符串/数组/autoConnect 归一化，maxInstances 0=不限，未知键保留', () => {
    const dp = normDropPolicy({
      snapToGrid: true, autoName: 5, prefillFromUpstream: ['a'], autoConnect: { upstream: 'none' },
      maxInstances: 2.9, custom: 'keep',
    })
    expect(dp).toMatchObject({
      snapToGrid: true, autoName: '5', prefillFromUpstream: ['a'],
      autoConnect: { upstream: 'none', downstream: 'nearest' }, maxInstances: 2, custom: 'keep',
    })
    /* 非法形态收紧为缺省：非布尔→false / 非数组→[] */
    const dpBad = normDropPolicy({ snapToGrid: 1, prefillFromUpstream: 'a' })
    expect(dpBad.snapToGrid).toBe(false)
    expect(dpBad.prefillFromUpstream).toEqual([])
    const dp0 = normDropPolicy({ maxInstances: 0 })
    expect(dp0.maxInstances).toBe(0)
    const dpNeg = normDropPolicy({ maxInstances: -1 })
    expect(dpNeg.maxInstances).toBe(0)
  })
  it('makeFieldRow：fields 源无 visible；form.params 源补 visible:true', () => {
    expect(makeFieldRow('fields')).toEqual({ key: '', label: '', uiType: 'text', required: false })
    expect(makeFieldRow('form.params')).toEqual({ key: '', label: '', uiType: 'text', required: false, visible: true })
  })
})

describe('loadDeclState / applyDeclSpec（decl 分片往返）', () => {
  it('V2 缺位键不落 JSON：optional 全 undefined → delete 旧键；summary/icon/color 恒写', () => {
    const d = loadDeclState({ summary: '简介', icon: '⬢', color: '#1677ff' })
    expect(d).toEqual({ summary: '简介', icon: '⬢', color: '#1677ff' })
    const out: Record<string, unknown> = {
      summary: '旧', icon: '旧', color: '旧',
      displayName: '旧显示名', outputs: [{ name: 'x', type: 'table' }], specVersion: '2.0',
    }
    applyDeclSpec(out, JSON.parse(JSON.stringify(d)) as ReturnType<typeof loadDeclState>)
    /* 一级必有键始终覆写；V2 optional 键 undefined 即删除（缺位键不落 JSON 契约） */
    expect(out).toEqual({ summary: '简介', icon: '⬢', color: '#1677ff' })
  })

  it('合法声明往返一致：load → apply → load 深度相等（含 outputs/badge/behaviors/extensions/initTemplate）', () => {
    const spec = {
      summary: '汇总算子', displayName: '汇总', aliases: ['agg', '汇总'], description: '描述', category: '转换', docUrl: 'https://x',
      icon: 'Σ', color: '#409eff',
      outputs: [{ name: 'out', type: 'table', desc: '结果表' }],
      badge: { key: 'state', colorMap: { ok: '#67c23a', fail: '#f56c6c' } },
      behaviors: {
        onChange: [{ field: 'ds', action: 'refreshOptions', target: ['t1', 't2'], remote: 'r1' }],
        prefillFromUpstream: [{ field: 'sql', from: 'input.table' }],
        pick: [{ field: 'cron', picker: 'cron' }],
      },
      extensions: { hiddenInputs: ['tenantId', 'runId'], capabilities: { testable: true, previewLimit: 50 } },
      initTemplate: { srcDs: 1, nested: { a: [1, 2] } },
      specVersion: '2.0',
    }
    const out: Record<string, unknown> = {}
    applyDeclSpec(out, loadDeclState(spec as Record<string, unknown>))
    expect(loadDeclState(out)).toEqual(loadDeclState(spec as Record<string, unknown>))
  })

  it('非法形状缺位兜底：outputs 元素/badge/behaviors/extensions/initTemplate 形状非法 → 不炸且键缺位', () => {
    const d = loadDeclState({
      summary: 's', icon: 'i', color: 'c',
      outputs: ['scalar', null, 42, { name: 'x', type: 'table' }],
      badge: { key: 7, colorMap: 'no' },
      behaviors: { onChange: 'no', pick: [{ field: 'f', picker: 'table' }] },
      extensions: { hiddenInputs: 'no', capabilities: 'no' },
      initTemplate: 'no',
      aliases: 'no',
    })
    expect(d.outputs).toEqual([{ name: 'x', type: 'table' }])
    expect(d.badge).toBeUndefined()
    expect(d.behaviors).toEqual({ pick: [{ field: 'f', picker: 'table' }] })
    expect(d.extensions).toBeUndefined()
    expect(d.initTemplate).toBeUndefined()
    expect(d.aliases).toBeUndefined()
  })

  it('枚举白名单收敛：outputs.type 非法整行丢弃（全灭不落键）；action/from/picker 非法行丢弃；hiddenInputs 脏值过滤', () => {
    const d = loadDeclState({
      summary: 's', icon: 'i', color: 'c',
      outputs: [{ name: 'bad', type: 'bogus' }, { name: 'noType' }],
      behaviors: {
        onChange: [{ field: 'f', action: 'bogus' }, { field: 'f', action: 'resetFields' }],
        prefillFromUpstream: [{ field: 'f', from: 'bogus' }, { field: 'f', from: 'input.columns' }],
        pick: [{ field: 'f', picker: 'bogus' }, { field: 'f', picker: 'sshHost' }],
      },
      extensions: { hiddenInputs: ['tenantId', 'hacker', 42, null, 'nodeId'] },
    })
    expect(d.outputs).toBeUndefined() // 全部被收敛 → 不落键（避免 outputs:[] 落 JSON）
    expect(d.behaviors).toEqual({
      onChange: [{ field: 'f', action: 'resetFields' }],
      prefillFromUpstream: [{ field: 'f', from: 'input.columns' }],
      pick: [{ field: 'f', picker: 'sshHost' }],
    })
    expect(d.extensions).toEqual({ hiddenInputs: ['tenantId', 'nodeId'] })
  })
})
