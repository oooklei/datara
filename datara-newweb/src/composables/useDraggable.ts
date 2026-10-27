/**
 * D9/G10 全局拖拽 composable：浮窗/弹窗统一拖拽移动、越界钳制、位置记忆、移动端降级。
 *
 * 契约（2026-10-28 方案 D9 冻结）：
 *  - 位置记忆键 `datara.drag.<storageKey>`（localStorage，跨会话恢复）；
 *  - 越界钳制：拖动中浮窗任意时刻至少保留 40px 可见（viewport 内）；
 *  - 移动端降级：`pointer: coarse` 设备禁用拖拽（浮窗保持 CSS 默认定位）；
 *  - 首次拖动锚定浮窗当前位置（无需调用方提供初始值）；禁用拖拽时不写样式。
 *
 * 用法：panel 为被移动元素 ref，handle 为拖拽把手 ref；
 * 模板绑定 `:style="dragStyle"`（一旦定位即强制 position:fixed，viewport 坐标）与 `@pointerdown="onHandlePointerdown"`。
 */
import { computed, ref, type CSSProperties, type Ref } from 'vue'

const STORAGE_PREFIX = 'datara.drag.'
const MIN_VISIBLE = 40

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}

function readSavedPosition(storageKey: string): { x: number; y: number } | null {
  try {
    const raw = localStorage.getItem(STORAGE_PREFIX + storageKey)
    if (!raw) return null
    const saved = JSON.parse(raw) as { x?: unknown; y?: unknown }
    if (typeof saved?.x !== 'number' || typeof saved?.y !== 'number') return null
    return { x: saved.x, y: saved.y }
  } catch {
    return null
  }
}

function savePosition(storageKey: string, x: number, y: number): void {
  try {
    localStorage.setItem(STORAGE_PREFIX + storageKey, JSON.stringify({ x, y }))
  } catch {
    /* 位置记忆失败不影响拖拽 */
  }
}

export interface DraggableOptions {
  storageKey: string
  /** 动态禁用（移动端降级内置 pointer:coarse 判定，此项为调用方附加条件） */
  disabled?: Ref<boolean> | boolean
}

export function useDraggable(panel: Ref<HTMLElement | null>, handle: Ref<HTMLElement | null>, options: DraggableOptions) {
  /** null = 未定位（保持 CSS 默认）；一旦拖动/恢复记忆即有值 */
  const x = ref<number | null>(readSavedPosition(options.storageKey)?.x ?? null)
  const y = ref<number | null>(readSavedPosition(options.storageKey)?.y ?? null)
  const dragging = ref(false)
  let offsetX = 0
  let offsetY = 0

  const coarsePointer = typeof window !== 'undefined' && window.matchMedia?.('(pointer: coarse)').matches === true

  function isDisabled(): boolean {
    if (coarsePointer) return true
    const extra = options.disabled
    return extra === true || (typeof extra === 'object' && extra !== null && extra.value === true)
  }

  function onHandlePointerdown(event: PointerEvent): void {
    if (isDisabled() || event.button !== 0) return
    const el = panel.value
    if (!el) return
    const rect = el.getBoundingClientRect()
    if (x.value === null || y.value === null) {
      // 首次拖动锚定当前位置，避免从 (0,0) 跳变
      x.value = rect.left
      y.value = rect.top
    }
    offsetX = event.clientX - x.value
    offsetY = event.clientY - y.value
    dragging.value = true
    event.preventDefault()
    window.addEventListener('pointermove', onPointerMove)
    window.addEventListener('pointerup', onPointerUp, { once: true })
  }

  function onPointerMove(event: PointerEvent): void {
    const el = panel.value
    if (!el || x.value === null || y.value === null) return
    const rect = el.getBoundingClientRect()
    x.value = clamp(event.clientX - offsetX, MIN_VISIBLE - rect.width, window.innerWidth - MIN_VISIBLE)
    y.value = clamp(event.clientY - offsetY, 0, window.innerHeight - MIN_VISIBLE)
  }

  function onPointerUp(): void {
    dragging.value = false
    window.removeEventListener('pointermove', onPointerMove)
    if (x.value !== null && y.value !== null) savePosition(options.storageKey, x.value, y.value)
  }

  const dragStyle = computed<CSSProperties>(() => (
    x.value === null || y.value === null
      ? {}
      : { position: 'fixed', left: `${x.value}px`, top: `${y.value}px`, margin: '0' }
  ))

  return { x, y, dragging, dragStyle, onHandlePointerdown }
}
