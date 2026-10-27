/**
 * useOverlayStack（D9/G08）契约测试：zIndex 递增、栈顶判定、Esc 关栈顶、幂等、卸载自动出栈、
 * owner 前台过滤（§7.1.4 护栏 2）。
 * 模块级栈跨用例共享：每用例结束时 unmount 全部 overlay 保证隔离；
 * zIndex 断言用相对关系（差值 10），不依赖 openSequence 绝对值。
 * 挂载须 attachTo document：owner 过滤以根 DOM isConnected 为据（真实环境恒在文档内）。
 */
import { afterEach, describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { useOverlayStack } from '../useOverlayStack'

interface OverlayVm {
  ov: { open: () => void; close: () => void; zIndex: { value: number }; isOpened: { value: boolean }; isTop: { value: boolean } }
}

const Harness = defineComponent({
  props: { id: { type: String, required: true } },
  setup(props, { expose }) {
    const ov = useOverlayStack(props.id)
    expose({ ov })
    return () => h('div', { 'data-id': props.id })
  },
})

function mountOverlay(id: string) {
  return mount(Harness, { props: { id }, attachTo: document.body }) as unknown as {
    vm: OverlayVm
    unmount: () => void
    element: HTMLElement
  }
}

function pressEscape(): void {
  window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
}

describe('useOverlayStack', () => {
  afterEach(() => {
    document.body.replaceChildren()
  })

  it('open 幂等 + zIndex 按 2000+序×10 递增 + 栈顶判定', () => {
    const a = mountOverlay('a')
    const b = mountOverlay('b')
    a.vm.ov.open()
    a.vm.ov.open() // 幂等：重复 open 不叠加
    b.vm.ov.open()
    expect(a.vm.ov.zIndex.value).toBeGreaterThanOrEqual(2010)
    expect(b.vm.ov.zIndex.value - a.vm.ov.zIndex.value).toBe(10)
    expect(a.vm.ov.isOpened.value).toBe(true)
    expect(b.vm.ov.isOpened.value).toBe(true)
    expect(b.vm.ov.isTop.value).toBe(true)
    expect(a.vm.ov.isTop.value).toBe(false)
    a.unmount()
    b.unmount()
  })

  it('close 幂等 + 关闭栈顶后下一个成为栈顶', () => {
    const a = mountOverlay('a')
    const b = mountOverlay('b')
    a.vm.ov.open()
    b.vm.ov.open()
    b.vm.ov.close()
    b.vm.ov.close() // 幂等：重复 close 无副作用
    expect(a.vm.ov.isOpened.value).toBe(true)
    expect(b.vm.ov.isOpened.value).toBe(false)
    expect(a.vm.ov.isTop.value).toBe(true)
    expect(b.vm.ov.isTop.value).toBe(false)
    a.unmount()
    b.unmount()
  })

  it('Esc 关闭栈顶（非栈顶不响应、栈空无副作用）', async () => {
    const a = mountOverlay('a')
    const b = mountOverlay('b')
    a.vm.ov.open()
    b.vm.ov.open()
    await nextTick() // flush watch：栈顶挂 Esc 监听、非栈顶卸监听
    pressEscape() // b 为栈顶：b 关闭，a 不受影响
    expect(b.vm.ov.isTop.value).toBe(false)
    expect(a.vm.ov.isTop.value).toBe(true)
    await nextTick()
    pressEscape() // a 为栈顶：a 关闭
    expect(a.vm.ov.isTop.value).toBe(false)
    await nextTick()
    pressEscape() // 栈空：无副作用
    expect(a.vm.ov.isTop.value).toBe(false)
    a.unmount()
    b.unmount()
  })

  it('组件卸载自动出栈：unmount 栈顶后前一个回退为栈顶', () => {
    const a = mountOverlay('a')
    const b = mountOverlay('b')
    a.vm.ov.open()
    b.vm.ov.open()
    expect(b.vm.ov.isTop.value).toBe(true)
    b.unmount()
    expect(a.vm.ov.isTop.value).toBe(true)
    a.unmount()
  })

  it('owner 过滤：KeepAlive 后台实例（DOM 离开文档）的浮窗不响应 Esc，复活后恢复（§7.1.4 护栏 2）', async () => {
    const a = mountOverlay('a')
    a.vm.ov.open()
    await nextTick()
    // 模拟 KeepAlive deactivated：宿主 DOM 被移出文档
    a.element.remove()
    pressEscape()
    expect(a.vm.ov.isOpened.value).toBe(true) // 后台不关闭
    // 复活（activated）：DOM 重新插入文档
    document.body.appendChild(a.element)
    pressEscape()
    expect(a.vm.ov.isOpened.value).toBe(false)
    a.unmount()
  })
})
