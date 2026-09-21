<script setup lang="ts">
import { onBeforeUnmount } from 'vue'
import { useFloatStore, type FloatWin } from '../../stores/float'

const store = useFloatStore()

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
        <component :is="f.comp" v-bind="f.props ?? {}" />
      </div>
    </div>
  </template>
</template>
