// @vitest-environment happy-dom
/**
 * Task 12 右侧属性面板用例（happy-dom）：
 * - 选中 widget → 布局/样式/数据绑定 三段 tabs；未选中 → 画布段（宽度/高度/背景填充）
 * - text widget：value 槽 scalar 候选 select + 手动输入开关；切手动输入后 a-input 出现
 *   （placeholder=模板默认值文案）；blur 空值 → updateWidget patch bindings.value.fallback === placeholder（resolveFallback 语义）
 * - table widget：dataset 槽候选首项 value 为 ds:1（catalog 桩）
 * - kind 映射：ds:→query / $wf.$param.$system→variable（fallback 恒为槽默认文案）
 * el-* 桩为原生元素（与既有组件用例同法）。
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import PageInspector, { bindingOf } from '../inspector/PageInspector.vue'
import { normalizePage, type PageDSL } from '../designerModel'
import type { ResourceCatalog } from '../bindingCatalog'

const CATALOG: ResourceCatalog = {
  datasources: [{ id: 1, name: '主库', type: 'mysql', db: 'mysql' }],
  workflows: [{ code: 1, name: '演示流', vars: [{ path: '$wf.demo.v', label: '演示变量', type: 'string' }] }],
  globalParams: [],
  timeParams: [],
  components: [],
}

const stubs = {
  ElTabs: { template: '<div class="stub-tabs"><slot /></div>' },
  ElTabPane: { props: ['label', 'name'], template: '<div class="stub-pane"><div class="stub-pane-label">{{ label }}</div><slot /></div>' },
  ElSelect: { props: ['modelValue'], template: '<div class="stub-select"><slot /></div>' },
  ElOption: { props: ['label', 'value'], template: '<div class="stub-option" :value="value">{{ label }}</div>' },
  ElSwitch: {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<input type="checkbox" class="stub-switch" :checked="modelValue" @change="$emit(\'update:modelValue\', $event.target.checked)" />',
  },
  ElInput: {
    props: ['modelValue'],
    emits: ['update:modelValue', 'blur'],
    template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" @blur="$emit(\'blur\')" />',
  },
  ElInputNumber: {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<input type="number" :value="modelValue" @change="$emit(\'update:modelValue\', Number($event.target.value))" />',
  },
}

function makePage(kinds: string[]): PageDSL {
  return normalizePage({
    page: {
      version: 1,
      canvas: { width: 288, height: 520, background: { fill: '#ffffff' } },
      widgets: kinds.map((k, i) => ({ id: `w${i + 1}`, kind: k, rect: { x: 8, y: 8, w: 120, h: 32 }, props: {}, style: {}, bindings: {} })),
    },
  })
}

function mountInspector(props: Record<string, unknown> = {}) {
  return mount(PageInspector, {
    props: { page: makePage(['text']), catalog: CATALOG, ...props },
    global: { components: stubs },
  })
}

describe('PageInspector', () => {
  it('选中 widget：渲染 布局/样式/数据绑定 三段', () => {
    const w = mountInspector({ selectedId: 'w1' })
    const labels = w.findAll('.stub-pane-label').map((n) => n.text())
    expect(labels).toContain('布局')
    expect(labels).toContain('样式')
    expect(labels).toContain('数据绑定')
  })

  it('text widget：value 槽 scalar select + 手动输入开关；空值 blur 落 placeholder 默认', async () => {
    const w = mountInspector({ selectedId: 'w1' })
    expect(w.find('.stub-select').exists()).toBe(true)
    expect(w.find('.stub-switch').exists()).toBe(true)
    // 切手动输入 → a-input 出现，placeholder = 模板默认值文案
    await w.find('.stub-switch').setValue(true)
    const inp = w.find('.pd-insp-manual input')
    expect(inp.exists()).toBe(true)
    expect(inp.attributes('placeholder')).toBe('文本内容')
    // blur 空值 → fallback 落 placeholder 文案
    await inp.setValue('')
    await inp.trigger('blur')
    const evts = w.emitted('updateWidget')
    expect(evts).toBeTruthy()
    const [, patch] = evts![0] as [string, { bindings: Record<string, { fallback: string }> }]
    expect(patch.bindings.value.fallback).toBe('文本内容')
  })

  it('table widget：dataset 槽候选首项 value 为 ds:1', () => {
    const w = mountInspector({ page: makePage(['table']), selectedId: 'w1' })
    const opts = w.findAll('.stub-option')
    expect(opts.length).toBeGreaterThan(0)
    expect(opts[0].attributes('value')).toBe('ds:1')
  })

  it('绑定 kind 映射：ds:→query / $wf.$param.$system→variable（fallback 恒为槽默认文案）', () => {
    expect(bindingOf('ds:1', '默认')).toMatchObject({ kind: 'query', datasourceId: 1, fallback: '默认' })
    for (const v of ['$wf.a.b', '$param.a', '$system.date']) {
      const b = bindingOf(v, '默认')
      expect(b.kind).toBe('variable')
      expect(b.path).toBe(v)
      expect(b.fallback).toBe('默认')
    }
  })

  it('未选中：显示画布段（宽度/高度/背景填充输入）', () => {
    const w = mountInspector({ selectedId: undefined })
    expect(w.text()).toContain('画布')
    expect(w.text()).toContain('宽度')
    expect(w.text()).toContain('高度')
    expect(w.text()).toContain('背景填充')
  })
})
