<script setup lang="ts">
/**
 * 组件页面设计器 Task 10：左侧组件库 Palette。
 * 数据源默认 templates.widgetGroups（六分组 43 项，props 可注入覆盖）；
 * 顶部搜索按 label/kind 过滤（空词显示全部分组，无 item 的分组隐藏）；
 * item 可拖出：dataTransfer 携带 kind（专用 MIME application/x-datara-widget，text/plain 兜底）。
 */
import { computed, ref } from 'vue'
import { widgetGroups, type WidgetGroup, type WidgetTemplate } from '../templates'

const props = defineProps<{ groups?: WidgetGroup[] }>()
const kw = ref('')

const visibleGroups = computed<WidgetGroup[]>(() => {
  const src = props.groups ?? widgetGroups
  const k = kw.value.trim()
  if (k === '') return src
  return src
    .map((g) => ({ ...g, items: g.items.filter((i) => i.label.includes(k) || i.kind.includes(k)) }))
    .filter((g) => g.items.length > 0)
})

function onDragStart(item: WidgetTemplate, e: DragEvent) {
  e.dataTransfer?.setData('application/x-datara-widget', item.kind)
  e.dataTransfer?.setData('text/plain', item.kind)
}
</script>

<template>
  <aside class="pd-pal">
    <div class="pd-pal-search">
      <el-input v-model="kw" placeholder="搜组件" clearable />
    </div>
    <div class="pd-pal-body">
      <section v-for="g in visibleGroups" :key="g.key" class="pd-pal-group">
        <div class="pd-pal-group-title">{{ g.label }}</div>
        <div class="pd-pal-grid">
          <div
            v-for="it in g.items" :key="it.kind" class="pd-pal-item" draggable="true"
            :title="`${it.label}（${it.kind}）`" @dragstart="onDragStart(it, $event)"
          >
            <span class="pd-pal-ico">{{ it.icon.slice(0, 1).toUpperCase() }}</span>
            <span class="pd-pal-label">{{ it.label }}</span>
          </div>
        </div>
      </section>
      <div v-if="visibleGroups.length === 0" class="pd-pal-empty">无匹配组件</div>
    </div>
  </aside>
</template>

<style scoped>
.pd-pal {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg);
  border-right: 1px solid var(--border);
  overflow: hidden;
}
.pd-pal-search {
  padding: 8px;
  border-bottom: 1px solid var(--border);
  background: var(--card);
}
.pd-pal-body {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}
.pd-pal-group {
  margin-bottom: 12px;
}
.pd-pal-group-title {
  font-size: 12px;
  color: var(--text-3);
  margin: 4px 2px 6px;
}
.pd-pal-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
}
.pd-pal-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border: 1px solid transparent;
  border-radius: var(--radius);
  background: var(--card);
  box-shadow: var(--shadow);
  cursor: grab;
  user-select: none;
}
.pd-pal-item:hover {
  border-color: var(--primary);
  color: var(--primary);
}
.pd-pal-ico {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: var(--radius-sm);
  background: var(--bg-deep);
  font-size: 12px;
  color: var(--text-2);
  flex: none;
}
.pd-pal-label {
  font-size: 12px;
  line-height: 16px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pd-pal-empty {
  padding: 24px 0;
  text-align: center;
  font-size: 12px;
  color: var(--text-3);
}
</style>
