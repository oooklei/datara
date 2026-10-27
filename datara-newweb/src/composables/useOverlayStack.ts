/**
 * D9/G08 单一受控 overlay 栈：多浮窗 zIndex 递增、栈顶判定、Esc 关闭栈顶、
 * 卸载/关闭状态一致（无遮罩残留）。
 *
 * 契约（2026-10-28 方案 D9 冻结）：
 *  - open() 幂等；close() 幂等；组件卸载自动出栈；
 *  - zIndex = 2000 + 开启序 ×10（后开者覆盖先开者）；
 *  - isOpened 按栈成员身份判定（供 v-if）；isTop 判定栈顶（供 Esc）；
 *  - 栈顶 overlay 持有 Esc 监听（Escape 关闭自己），非栈顶不响应。
 *
 * 实现注记：stack 必须用 shallowRef——条目为扁平普通对象、以对象身份做成员/比对；
 * 若用深层 ref，`stack.value = [...stack.value, entry]` 展开时元素会被 reactive 重新
 * 包装为代理，导致 includes/filter 的 raw 身份比对失配（元素"丢失"假象）。
 */
import { computed, onBeforeUnmount, shallowRef, watch } from 'vue'

interface OverlayEntry {
  id: string
  zIndex: number
}

const stack = shallowRef<OverlayEntry[]>([])
let openSequence = 0
const BASE_Z_INDEX = 2000

export function useOverlayStack(id: string) {
  const entry: OverlayEntry = { id, zIndex: 0 }
  let opened = false

  const zIndex = computed(() => stack.value.find((item) => item === entry)?.zIndex ?? 0)
  const isOpened = computed(() => stack.value.includes(entry))
  const isTop = computed(() => {
    const top = stack.value[stack.value.length - 1]
    return top !== undefined && top.id === id && opened
  })

  function open(): void {
    if (opened) return
    opened = true
    openSequence += 1
    entry.zIndex = BASE_Z_INDEX + openSequence * 10
    stack.value = [...stack.value, entry]
  }

  function close(): void {
    if (!opened) return
    opened = false
    stack.value = stack.value.filter((item) => item !== entry)
  }

  function onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Escape' && isTop.value) close()
  }

  watch(isTop, (top) => {
    if (top) window.addEventListener('keydown', onKeydown)
    else window.removeEventListener('keydown', onKeydown)
  }, { immediate: true })

  onBeforeUnmount(() => {
    window.removeEventListener('keydown', onKeydown)
    close()
  })

  return { open, close, zIndex, isOpened, isTop }
}
