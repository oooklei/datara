/**
 * INC4-FE-1（4.2a）验收测试：任务中心顶部视角页签框架（s260 派令）。
 *
 * 覆盖（蓝本 TaskCenterView.vue 照抄语义 + §5A.1 内容门控）：
 *  1. 四视角页签照抄渲染：任务编排/模板中心/运行监控/告警与SLA（顺序+icon+label）；
 *  2. 默认 edit 主视角 + 非法 ?tab= 回落 edit（蓝本初始化语义）；
 *  3. ?tab= 激活分流：edit=画布占位区（INC4-FE-2 接驳位）、runs=页签占位
 *     （内容归增量 8）、templates/alarm=框架保留不渲染占位内容；
 *  4. switchTab → router.replace 合并既有 query（保书签，蓝本语义照抄）。
 *
 * 依赖 mock：vue-router（useRoute.query / useRouter.replace；/dag 路由注册
 * 与路由表负断言归 router/__tests__/routes.contract.test.ts，本文件不重复）。
 */
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { replaceSpy, routeQuery } = vi.hoisted(() => ({
  replaceSpy: vi.fn(() => Promise.resolve()),
  routeQuery: { value: {} as Record<string, unknown> },
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: routeQuery.value }),
  useRouter: () => ({ replace: replaceSpy }),
}))

import TaskCenterView from '../TaskCenterView.vue'

function mountView() {
  return mount(TaskCenterView)
}

beforeEach(() => {
  routeQuery.value = {}
  replaceSpy.mockClear()
})

/** 蓝本 tabs 数组原文（顺序 + icon + label） */
const BLUEPRINT_TABS = [
  { k: 'edit', label: '任务编排', icon: '⑃' },
  { k: 'templates', label: '模板中心', icon: '▦' },
  { k: 'runs', label: '运行监控', icon: '▶' },
  { k: 'alarm', label: '告警与SLA', icon: '🖂' },
]

describe('INC4-FE-1 任务中心顶部视角页签框架（/dag，s260 派令）', () => {
  it('四视角页签照抄渲染：顺序 + icon + label 与蓝本一致，页签条单实例', () => {
    const w = mountView()
    expect(w.find('[data-tc-tabs]').exists()).toBe(true)
    const els = w.findAll('[data-tc-tabs] .tc-tab')
    expect(els).toHaveLength(BLUEPRINT_TABS.length)
    BLUEPRINT_TABS.forEach((t, i) => {
      expect(els[i].attributes('data-tab')).toBe(t.k)
      expect(els[i].text()).toBe(`${t.icon}${t.label}`)
    })
  })

  it('默认 edit 主视角：edit 页签 .on 态 + 画布占位区渲染（INC4-FE-2 接驳位）', () => {
    const w = mountView()
    expect(w.find('[data-tab="edit"]').classes()).toContain('on')
    expect(w.find('[data-tc-canvas-slot]').exists()).toBe(true)
    expect(w.find('[data-tc-canvas-slot]').text()).toContain('任务编排画布')
  })

  it('非法 ?tab= 回落 edit（蓝本初始化语义照抄）', () => {
    routeQuery.value = { tab: 'nope' }
    const w = mountView()
    expect(w.find('[data-tab="edit"]').classes()).toContain('on')
    expect(w.find('[data-tc-canvas-slot]').exists()).toBe(true)
  })

  it('?tab=runs：runs 页签激活 + 占位注记渲染（内容归增量 8），画布占位不渲染', () => {
    routeQuery.value = { tab: 'runs' }
    const w = mountView()
    expect(w.find('[data-tab="runs"]').classes()).toContain('on')
    expect(w.find('[data-tab="edit"]').classes()).not.toContain('on')
    expect(w.find('[data-tc-runs-slot]').exists()).toBe(true)
    expect(w.find('[data-tc-runs-slot]').text()).toContain('增量 8')
    expect(w.find('[data-tc-canvas-slot]').exists()).toBe(false)
  })

  it('?tab=templates / ?tab=alarm：页签激活态正确，框架保留且 body 不渲染占位内容', () => {
    for (const k of ['templates', 'alarm']) {
      routeQuery.value = { tab: k }
      const w = mountView()
      expect(w.find(`[data-tab="${k}"]`).classes()).toContain('on')
      expect(w.find('[data-tc-canvas-slot]').exists()).toBe(false)
      expect(w.find('[data-tc-runs-slot]').exists()).toBe(false)
      expect(w.find('[data-tc-body]').text()).toBe('')
    }
  })

  it('点击页签 → switchTab → router.replace 合并既有 query（保书签，蓝本语义）', async () => {
    routeQuery.value = { tab: 'edit', foo: 'bar' }
    const w = mountView()
    await w.find('[data-tab="runs"]').trigger('click')
    expect(replaceSpy).toHaveBeenCalledTimes(1)
    expect(replaceSpy).toHaveBeenCalledWith({ query: { tab: 'runs', foo: 'bar' } })
    // 本地激活态即时切换（不等路由响应）
    expect(w.find('[data-tab="runs"]').classes()).toContain('on')
  })
})
