// @vitest-environment happy-dom
/**
 * D3 DataNode 版本角标用例：n-ref 徽标复用 n-miss/n-attempt 视觉语言，
 * componentRef.version（正整数）才显示——存量文档无 ref / 非法值一律不渲染，
 * 避免把「未注入」误展示成 v0。Handle（vue-flow）与路由无画布上下文依赖，桩掉即可挂载。
 * Task 15（§4.3/§4.4）：spec 骨架 publishedVersion 高于引用版本 → 黄标（有新版本可用），
 * 服务降级/未加载/旧骨架不亮；specMap 整体替换（发布广播失效重建）→ 角标随 nextTick 刷新。
 */
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { nextTick } from 'vue'

vi.mock('@vue-flow/core', () => ({
  Handle: { template: '<div class="stub-handle" />' },
  Position: { Left: 'left', Right: 'right' },
}))

import DataNode from '../DataNode.vue'
import type { NodeSchema } from '../../profiles/types'
import type { GNode } from '../../model'
import { useComponentStore } from '../../../stores/componentStore'
import type { ComponentSpec } from '../../../services/componentSpec'

const schema: NodeSchema = {
  type: 'user_demo', label: '演示组件', icon: '⚙', color: '#000', form: [],
}

function gnode(data: GNode['data']): GNode {
  return { id: 'n1', type: 'user_demo', position: { x: 0, y: 0 }, data }
}

function mountNode(g: GNode, ports?: NodeSchema['ports']) {
  return mount(DataNode, {
    props: { id: 'n1', gnode: g, schema: ports ? { ...schema, ports } : schema },
    global: { plugins: [createPinia()] },
  })
}

/* 黄标用例挂载：pinia 由外部持有（可预置 specMap/loaded/degraded 状态） */
function mountWithStore(g: GNode) {
  const pinia = createPinia()
  const w = mount(DataNode, {
    props: { id: 'n1', gnode: g, schema },
    global: { plugins: [pinia] },
  })
  return { w, store: useComponentStore(pinia) }
}

/* 最小合法 ComponentSpec（角标链路只消费 publishedVersion；其余要素给合法空值） */
function spec(publishedVersion?: number): ComponentSpec {
  return {
    icon: '', color: '', summary: '',
    ports: { inputs: [], outputs: [] },
    fields: [],
    dropPolicy: {
      snapToGrid: false, autoName: '{type}_{n}', prefillFromUpstream: [],
      autoConnect: { upstream: 'none', downstream: 'none' }, maxInstances: 0,
    },
    paletteVisible: true,
    ...(publishedVersion === undefined ? {} : { publishedVersion }),
  }
}

describe('DataNode 组件版本角标（D3 n-ref）', () => {
  it('普通形态：componentRef.version=3 → 渲染 v3 角标（title 含说明）', () => {
    const w = mountNode(gnode({ name: '节点A', componentRef: { type: 'user_demo', version: 3 } }))
    const ref = w.find('.n-ref')
    expect(ref.exists()).toBe(true)
    expect(ref.text()).toBe('v3')
    expect(ref.attributes('title')).toContain('组件版本 v3')
  })

  it('分支形态（动态 ports）同样渲染版本角标', () => {
    const w = mountNode(
      gnode({ name: '分支节点', componentRef: { type: 'user_demo', version: 12 } }),
      () => [{ id: 'out', label: '输出' }],
    )
    expect(w.find('.gnode-branch').exists()).toBe(true)
    expect(w.find('.n-ref').text()).toBe('v12')
  })

  it('无 ref / version=0 / 负数 / 非整数 / 非数值 → 一律不渲染（未注入不误展示）', () => {
    const cases: GNode['data'][] = [
      { name: 'x' },
      { name: 'x', componentRef: { type: 'user_demo', version: 0 } },
      { name: 'x', componentRef: { type: 'user_demo', version: -2 } },
      { name: 'x', componentRef: { type: 'user_demo', version: 1.5 } },
      { name: 'x', componentRef: { type: 'user_demo', version: '3' } },
    ]
    for (const data of cases) {
      const w = mountNode(gnode(data))
      expect(w.find('.n-ref').exists()).toBe(false)
    }
  })
})

describe('DataNode 引用角标黄标（Task 15 §4.3/§4.4）', () => {
  it('spec publishedVersion=5 高于引用版本 v3 → .n-ref-behind 黄标 + title 含「有新版本 v5」', async () => {
    const { w, store } = mountWithStore(gnode({ name: 'n', componentRef: { type: 'user_demo', version: 3 } }))
    store.loaded = true
    store.specMap = new Map([['user_demo', spec(5)]])
    await nextTick()
    const ref = w.find('.n-ref')
    expect(ref.exists()).toBe(true)
    expect(ref.classes()).toContain('n-ref-behind')
    expect(ref.attributes('title')).toContain('组件版本 v3')
    expect(ref.attributes('title')).toContain('有新版本 v5')
  })

  it('publishedVersion 等于引用版本 → 不亮黄标（title 为基础说明）', () => {
    const { w, store } = mountWithStore(gnode({ name: 'n', componentRef: { type: 'user_demo', version: 3 } }))
    store.loaded = true
    store.specMap = new Map([['user_demo', spec(3)]])
    const ref = w.find('.n-ref')
    expect(ref.classes()).not.toContain('n-ref-behind')
    expect(ref.attributes('title')).toBe('组件版本 v3（componentRef）')
  })

  it('store 未加载 / 服务降级 / 旧骨架缺 publishedVersion → 守卫不亮黄标', () => {
    // loaded=false（store 默认态）
    const a = mountWithStore(gnode({ name: 'n', componentRef: { type: 'user_demo', version: 3 } }))
    a.store.specMap = new Map([['user_demo', spec(5)]])
    expect(a.w.find('.n-ref-behind').exists()).toBe(false)
    // degraded=true（服务不可用 → profile 兜底，无版本比对基准）
    const b = mountWithStore(gnode({ name: 'n', componentRef: { type: 'user_demo', version: 3 } }))
    b.store.loaded = true
    b.store.degraded = true
    b.store.specMap = new Map([['user_demo', spec(5)]])
    expect(b.w.find('.n-ref-behind').exists()).toBe(false)
    // 旧骨架（spec 无 publishedVersion 键）
    const c = mountWithStore(gnode({ name: 'n', componentRef: { type: 'user_demo', version: 3 } }))
    c.store.loaded = true
    c.store.specMap = new Map([['user_demo', spec()]])
    expect(c.w.find('.n-ref-behind').exists()).toBe(false)
  })

  it('pinned 引用落后 → 仍亮黄标，title 追加「（已钉住）」', async () => {
    const { w, store } = mountWithStore(
      gnode({ name: 'n', componentRef: { type: 'user_demo', version: 3, pinned: true } }))
    store.loaded = true
    store.specMap = new Map([['user_demo', spec(5)]])
    await nextTick()
    const ref = w.find('.n-ref')
    expect(ref.classes()).toContain('n-ref-behind')
    expect(ref.attributes('title')).toContain('有新版本 v5')
    expect(ref.attributes('title')).toContain('（已钉住）')
  })

  it('specMap 整体替换（发布广播 → invalidate 重建）→ 角标随 nextTick 亮黄（§4.4 实时刷新闭环）', async () => {
    const { w, store } = mountWithStore(gnode({ name: 'n', componentRef: { type: 'user_demo', version: 3 } }))
    store.loaded = true
    store.specMap = new Map([['user_demo', spec(3)]])
    await nextTick()
    expect(w.find('.n-ref-behind').exists()).toBe(false)
    // 模拟组件发布新版本 v5 后的失效重建（整体替换 specMap，与 ensureSpecs 同模式）
    store.specMap = new Map([['user_demo', spec(5)]])
    await nextTick()
    expect(w.find('.n-ref-behind').exists()).toBe(true)
  })
})

describe('DataNode 临时表虚线（Task 7 血缘 tmp 标记）', () => {
  it('data.tmp=true → 普通节点挂 .tmp class（虚线边框样式钩子）', () => {
    const w = mountNode(gnode({ name: '临时表', tmp: true }))
    expect(w.find('.gnode.tmp').exists()).toBe(true)
  })

  it('tmp=false / 缺省 → 无 .tmp class（实线不变）', () => {
    expect(mountNode(gnode({ name: 'a', tmp: false })).find('.gnode.tmp').exists()).toBe(false)
    expect(mountNode(gnode({ name: 'b' })).find('.gnode.tmp').exists()).toBe(false)
  })
})
