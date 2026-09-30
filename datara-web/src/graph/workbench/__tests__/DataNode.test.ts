// @vitest-environment happy-dom
/**
 * D3 DataNode 版本角标用例：n-ref 徽标复用 n-miss/n-attempt 视觉语言，
 * componentRef.version（正整数）才显示——存量文档无 ref / 非法值一律不渲染，
 * 避免把「未注入」误展示成 v0。Handle（vue-flow）与路由无画布上下文依赖，桩掉即可挂载。
 */
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'

vi.mock('@vue-flow/core', () => ({
  Handle: { template: '<div class="stub-handle" />' },
  Position: { Left: 'left', Right: 'right' },
}))

import DataNode from '../DataNode.vue'
import type { NodeSchema } from '../../profiles/types'
import type { GNode } from '../../model'

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
