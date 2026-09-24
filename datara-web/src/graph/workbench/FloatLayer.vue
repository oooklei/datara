<script setup lang="ts">
import { onBeforeUnmount } from 'vue'
import { useFloatStore, type FloatWin } from '../../stores/float'
import { useGraphStore } from '../../stores/graph'

const store = useFloatStore()
const graphStore = useGraphStore()

/**
 * C7：面板 emit('update', patch) → 写回当前文档选中节点 data 并置脏。
 * 沿用 Inspector 的"直接改 node.data + markDirty"契约，浮窗不改此约定：
 * 面板（SourceBasePanel/TargetBasePanel）需持有 node 或 selectedId 之一才能定位写入目标；
 * 未定位到节点时仅记日志（面板"保存"按钮已按 activeNode 置灰，正常不会触发）。
 */
function applyUpdate(f: FloatWin, patch: Record<string, unknown>) {
  const nodeId = String((f.props as any)?.selectedId ?? '')
  const doc = graphStore.doc
  const node = doc?.nodes.find((n) => n.id === nodeId)
  if (!node) {
    console.warn('[FloatLayer] update 未命中节点，忽略：', nodeId, patch)
    return
  }
  Object.assign(node.data, patch)
  graphStore.markDirty()
}

let dragging: { id: string; dx: number; dy: number } | null = null

function onMove(e: MouseEvent) {
  if (!dragging) return
  store.move(dragging.id, e.clientX - dragging.dx, e.clientY - dragging.dy)
}
function onUp() {
  dragging = null
  window.removeEventListener('mousemove', onMove)
  window.removeEventListener('mouseup', onUp)
}
function onDragStart(f: FloatWin, e: MouseEvent) {
  store.focus(f.id)
  dragging = { id: f.id, dx: e.clientX - f.x, dy: e.clientY - f.y }
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}
onBeforeUnmount(() => {
  window.removeEventListener('mousemove', onMove)
  window.removeEventListener('mouseup', onUp)
})
</script>

<template>
  <template v-for="f in store.floats" :key="f.id">
    <div
      class="float-win" :class="{ min: f.minimized }"
      :style="{ left: f.x + 'px', top: f.y + 'px', width: f.w + 'px', height: f.h + 'px', zIndex: f.z ?? 2500 }"
      @mousedown="store.focus(f.id)"
    >
      <div class="float-head" @mousedown="onDragStart(f, $event)">
        <span class="f-title">{{ f.title }}</span>
        <span class="f-act">
          <button class="f-btn" :title="f.minimized ? '展开' : '收起'" @click.stop="store.toggleMin(f.id)">{{ f.minimized ? '▣' : '—' }}</button>
          <button class="f-btn" title="关闭" @click.stop="store.close(f.id)">✕</button>
        </span>
      </div>
      <div class="float-body">
        <component
          :is="f.comp"
          v-bind="f.props ?? {}"
          @update="(patch: Record<string, unknown>) => applyUpdate(f, patch)"
          @close="store.close(f.id)"
        />
      </div>
    </div>
  </template>
</template>
