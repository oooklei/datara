<script setup lang="ts">
/**
 * 组件页面设计器 Task 11：画布。
 * - 手机规格画布卡在 .pd-stage 内 flex 居中，柔和阴影；背景填充/图片随 page.canvas
 * - 拖入落点：drop 读 dataTransfer（专用 MIME → text/plain 兜底），emit add(kind, 卡内相对坐标)
 * - 拖尺寸：e/s/se grip mousedown 记起点 → window mousemove 实时 emit canvasSize（钳制 宽140-520/高320-1200）
 *   → mouseup 解绑（GraphWorkbench 面板拖宽同款模式）；持久化由宿主 PageDesignerView 统一承担，本组件只 emit
 */
import { computed, onBeforeUnmount } from 'vue'
import { CANVAS_H, CANVAS_W, type PageDSL } from '../designerModel'
import type { PreviewResult } from '../pageApi'
import WidgetRenderer from './WidgetRenderer.vue'

const props = defineProps<{
  page: PageDSL
  selectedId?: string
  /** 多选集合（shift+点击累积）：提供时按集合高亮，缺省回退 selectedId 单选判断（兼容） */
  selectedIds?: string[]
  preview?: Record<string, PreviewResult>
}>()
const emit = defineEmits<{
  add: [kind: string, x: number, y: number]
  select: [id: string, additive: boolean]
  move: [id: string, dx: number, dy: number]
  resize: [id: string, dw: number, dh: number]
  canvasSize: [w: number, h: number]
}>()

/** stage 居中用内联样式承载（测试断言 + 观感不依赖外部 css 加载） */
const stageStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: '100%',
  height: '100%',
  overflow: 'auto',
}

const canvasStyle = computed<Record<string, string>>(() => {
  const c = props.page.canvas
  const out: Record<string, string> = {
    width: `${c.width}px`,
    height: `${c.height}px`,
    background: c.background?.fill ?? 'var(--card)',
    boxShadow: 'var(--shadow-lg)',
  }
  if (c.background?.image) {
    out.backgroundImage = `url(${c.background.image})`
    out.backgroundSize = c.background.size ?? 'cover'
  }
  return out
})

/* ---------- 拖入落点 ---------- */
function onDrop(e: DragEvent) {
  const dt = e.dataTransfer
  if (!dt) return
  const kind = dt.getData('application/x-datara-widget') || dt.getData('text/plain') || dt.getData('text')
  if (!kind) return
  const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
  const x = Math.round(e.clientX - rect.left)
  const y = Math.round(e.clientY - rect.top)
  emit('add', kind, x, y)
}

/* ---------- 画布尺寸拖拽（钳制与 designerModel CANVAS_W/H 同口径） ---------- */
const clampW = (v: number) => Math.min(CANVAS_W.max, Math.max(CANVAS_W.min, v))
const clampH = (v: number) => Math.min(CANVAS_H.max, Math.max(CANVAS_H.min, v))
let resizeDir: 'e' | 's' | 'se' | null = null
let startX = 0
let startY = 0
let startW = 0
let startH = 0
function startResize(dir: 'e' | 's' | 'se', e: MouseEvent) {
  resizeDir = dir
  startX = e.clientX
  startY = e.clientY
  startW = props.page.canvas.width
  startH = props.page.canvas.height
  document.body.style.userSelect = 'none'
  window.addEventListener('mousemove', onCanvasResizeMove)
  window.addEventListener('mouseup', stopResize)
  e.preventDefault()
}
function onCanvasResizeMove(e: MouseEvent) {
  if (!resizeDir) return
  const w = resizeDir.includes('e') ? clampW(startW + (e.clientX - startX)) : startW
  const h = resizeDir.includes('s') ? clampH(startH + (e.clientY - startY)) : startH
  emit('canvasSize', w, h)
}
function stopResize() {
  resizeDir = null
  document.body.style.userSelect = ''
  window.removeEventListener('mousemove', onCanvasResizeMove)
  window.removeEventListener('mouseup', stopResize)
}
onBeforeUnmount(stopResize)
</script>

<template>
  <div class="pd-stage" :style="stageStyle">
    <div class="pd-canvas" :style="canvasStyle" @drop.prevent="onDrop" @dragover.prevent>
      <WidgetRenderer
        v-for="wd in page.widgets" :key="wd.id" :widget="wd" :preview="preview?.[wd.id]"
        :selected="selectedIds ? selectedIds.includes(wd.id) : wd.id === selectedId"
        @select="(additive) => $emit('select', wd.id, additive)"
        @move="(dx, dy) => $emit('move', wd.id, dx, dy)"
        @resize="(dw, dh) => $emit('resize', wd.id, dw, dh)"
      />
      <div class="pd-grip pd-grip-e" title="拖拽调宽" @mousedown="startResize('e', $event)" />
      <div class="pd-grip pd-grip-s" title="拖拽调高" @mousedown="startResize('s', $event)" />
      <div class="pd-grip pd-grip-se" title="拖拽调尺寸" @mousedown="startResize('se', $event)" />
    </div>
  </div>
</template>

<style scoped>
.pd-stage {
  min-height: 100%;
  padding: 24px;
  background: var(--bg-deep);
}
.pd-canvas {
  position: relative;
  flex: none;
  border-radius: var(--radius-xl);
  overflow: hidden;
}
/* 画布卡拖尺寸手柄 */
.pd-grip {
  position: absolute;
  background: var(--primary);
  opacity: 0;
  z-index: 10;
  transition: opacity var(--dur-fast) var(--ease);
}
.pd-canvas:hover .pd-grip {
  opacity: 0.9;
}
.pd-grip-e {
  top: 50%;
  right: -3px;
  width: 6px;
  height: 32px;
  margin-top: -16px;
  border-radius: var(--radius-sm);
  cursor: ew-resize;
}
.pd-grip-s {
  bottom: -3px;
  left: 50%;
  width: 32px;
  height: 6px;
  margin-left: -16px;
  border-radius: var(--radius-sm);
  cursor: ns-resize;
}
.pd-grip-se {
  right: -3px;
  bottom: -3px;
  width: 12px;
  height: 12px;
  border-radius: var(--radius-sm);
  cursor: nwse-resize;
}
</style>
