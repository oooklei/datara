/**
 * useDraggable（D9/G10）契约测试：拖拽移动、越界钳制、位置记忆、禁用降级。
 * happy-dom 环境：原生 dispatchEvent 派发 pointer 事件；viewport 默认 1024×768；
 * getBoundingClientRect 经 stub 固定（happy-dom 不做布局计算，返回全零）。
 * options 用 reactive（非 ref）：expose 顶层 ref 会被 proxyRefs 解包，reactive 对象保持原样可直接变更。
 */
import { beforeEach, describe, expect, it } from 'vitest'
import { defineComponent, h, reactive, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { useDraggable } from '../useDraggable'

const Harness = defineComponent({
  setup(_, { expose }) {
    const panel = ref<HTMLElement | null>(null)
    const handle = ref<HTMLElement | null>(null)
    const options = reactive<{ storageKey: string; disabled?: boolean }>({ storageKey: 'test.panel' })
    const drag = useDraggable(panel, handle, options)
    expose({ drag, options })
    return () => h('div', { ref: panel, style: { position: 'fixed', left: '100px', top: '80px', width: '300px', height: '200px' } }, [
      h('div', { ref: handle, 'data-drag-handle': true, style: { width: '100%', height: '24px' }, onPointerdown: drag.onHandlePointerdown }, 'handle'),
    ])
  },
})

interface DragVm {
  drag: { x: { value: number | null }, y: { value: number | null }, dragging: { value: boolean } }
  options: { storageKey: string; disabled?: boolean }
}

async function mountHarness(): Promise<{ vm: DragVm; element: HTMLElement; unmount: () => void }> {
  const wrapper = mount(Harness, { attachTo: document.body })
  await wrapper.vm.$nextTick()
  // happy-dom getBoundingClientRect 返回全零：stub 固定为样式声明的 100/80/300×200
  wrapper.element.getBoundingClientRect = () => ({
    left: 100, top: 80, width: 300, height: 200, right: 400, bottom: 280, x: 100, y: 80,
    toJSON: () => ({}),
  } as DOMRect)
  return {
    vm: wrapper.vm as unknown as DragVm,
    element: wrapper.element,
    unmount: () => wrapper.unmount(),
  }
}

function findHandle(wrapper: { element: HTMLElement }): HTMLElement {
  return wrapper.element.querySelector('[data-drag-handle]') as HTMLElement
}

function pointerdown(handle: HTMLElement, clientX: number, clientY: number): void {
  handle.dispatchEvent(new MouseEvent('pointerdown', { clientX, clientY, button: 0, bubbles: true }))
}

beforeEach(() => {
  localStorage.clear()
})

describe('useDraggable', () => {
  it('拖拽移动：pointerdown 锚定当前位置 + pointermove 更新 x/y + pointerup 记忆', async () => {
    const wrapper = await mountHarness()
    pointerdown(findHandle(wrapper), 120, 100)
    expect(wrapper.vm.drag.dragging.value).toBe(true)

    window.dispatchEvent(new MouseEvent('pointermove', { clientX: 220, clientY: 160 }))
    expect(wrapper.vm.drag.x.value).toBe(200) // 100 + (220-120)
    expect(wrapper.vm.drag.y.value).toBe(140) // 80 + (160-100)

    window.dispatchEvent(new MouseEvent('pointerup'))
    expect(wrapper.vm.drag.dragging.value).toBe(false)
    expect(JSON.parse(localStorage.getItem('datara.drag.test.panel') ?? '{}')).toEqual({ x: 200, y: 140 })
    wrapper.unmount()
  })

  it('越界钳制：拖出视口时保留 40px 可见（viewport 1024×768）', async () => {
    const wrapper = await mountHarness()
    pointerdown(findHandle(wrapper), 120, 100)

    window.dispatchEvent(new MouseEvent('pointermove', { clientX: 5000, clientY: -3000 }))
    // x: 1024-40=984（右缘钳制）；y: 0（上缘钳制）
    expect(wrapper.vm.drag.x.value).toBe(984)
    expect(wrapper.vm.drag.y.value).toBe(0)
    window.dispatchEvent(new MouseEvent('pointerup'))
    wrapper.unmount()
  })

  it('位置记忆恢复：再次挂载读取 datara.drag.<key> 为初始位置', async () => {
    localStorage.setItem('datara.drag.test.panel', JSON.stringify({ x: 55, y: 66 }))
    const wrapper = await mountHarness()
    expect(wrapper.vm.drag.x.value).toBe(55)
    expect(wrapper.vm.drag.y.value).toBe(66)
    wrapper.unmount()
  })

  it('禁用拖拽：disabled 时不响应 pointerdown（移动端/受控降级）', async () => {
    const wrapper = await mountHarness()
    wrapper.vm.options.disabled = true
    pointerdown(findHandle(wrapper), 120, 100)
    expect(wrapper.vm.drag.dragging.value).toBe(false)
    expect(wrapper.vm.drag.x.value).toBeNull()
    wrapper.unmount()
  })
})
