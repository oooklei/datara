<script setup lang="ts">
/**
 * 详情抽屉范式组件（增量 2 / 票 2-06）
 *
 * 蓝本：权威设计 §4.1（页面布局骨架=§4 抄袭范畴；§5D 三层调和——复刻遮罩+右侧滑出
 * 抽屉+标题栏+关闭钮+内容区+底部操作区布局语义，不复制旧业务组件实现代码）。
 * 纪律：纯布局范式壳（受控开合 v-model），零业务逻辑；宽体内容/操作经插槽注入。
 */
import { computed, ref, type CSSProperties } from 'vue'
import { useDraggable } from '../composables/useDraggable'

const props = defineProps<{
  /** 受控开合（v-model:modelValue） */
  modelValue: boolean
  title?: string
  /** 抽屉宽度（默认 480px） */
  width?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'close'): void
}>()

/* D9：抽屉可由标题栏拖动；CSS 为 top:0/right:0/height:100%，
   拖拽定位后解除 right 约束并把高度按 top 反推，避免抽屉溢出视口。 */
const drawerRef = ref<HTMLElement | null>(null)
const headerRef = ref<HTMLElement | null>(null)
const { dragStyle: drawerDragStyle, onHandlePointerdown } = useDraggable(drawerRef, headerRef, { storageKey: 'drawer.detail' })
const drawerStyle = computed<CSSProperties>(() => {
  const base = drawerDragStyle.value
  const width = props.width ?? '480px'
  if (!base.position) return { width }
  return { ...base, width, right: 'auto', height: `calc(100vh - ${base.top})` }
})

function onClose(): void {
  emit('update:modelValue', false)
  emit('close')
}
</script>

<template>
  <Teleport to="body">
    <div v-if="modelValue" class="detail-drawer-mask" data-part="mask" @click.self="onClose">
      <aside ref="drawerRef" class="detail-drawer" role="dialog" aria-modal="true" :style="drawerStyle">
        <header ref="headerRef" class="drawer-header drag-handle" data-part="header" @pointerdown="onHandlePointerdown">
          <span class="drawer-title">{{ title }}</span>
          <button type="button" class="drawer-close" aria-label="关闭" @pointerdown.stop @click="onClose">×</button>
        </header>
        <div class="drawer-body" data-part="body"><slot /></div>
        <footer v-if="$slots.footer" class="drawer-footer" data-part="footer"><slot name="footer" /></footer>
      </aside>
    </div>
  </Teleport>
</template>

<style scoped>
.detail-drawer-mask{position:fixed;inset:0;background:rgba(0,0,0,.35);z-index:1000}
.detail-drawer{position:absolute;top:0;right:0;height:100%;background:var(--app-bg,#fff);box-shadow:-4px 0 16px rgba(0,0,0,.15);display:flex;flex-direction:column}
.drawer-header{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;border-bottom:1px solid #eee}
.drawer-close{border:none;background:none;font-size:18px;cursor:pointer}
.drawer-body{flex:1;overflow:auto;padding:16px}
.drawer-footer{padding:12px 16px;border-top:1px solid #eee}
.drag-handle{cursor:grab;user-select:none}
.drag-handle:active{cursor:grabbing}
</style>
