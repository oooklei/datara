<script setup lang="ts">
/**
 * 页签组织范式组件（增量 2 / 票 2-07）
 *
 * 蓝本：权威设计 §4.1（页面布局骨架=§4 抄袭范畴；§5D 三层调和）；预研 §2.4——
 * 增量 2 交付「范式」通用交互壳（页签增删/激活/容器语义），不提前实现 DAG 专用页签内容
 * （MAX_DAG_TABS=5、localStorage 持久化键、视角页签等归增量 4.2 照抄 §5A.1 蓝本，边界见预研 §2.4）。
 * 纪律：受控组件（tabs/modelValue 由消费方持有）；页签增删为事件上报（close），列表变更归消费方；
 *      内容区仅容器插槽（KeepAlive 缓存语义由消费方按页面需要包裹，本组件不强制）。
 */
export interface TabItem {
  /** 稳定键（禁中文标签） */
  id: string
  label: string
  /** 可关闭标记（不可关闭页签不渲染关闭钮） */
  closable?: boolean
}

const props = defineProps<{
  tabs: readonly TabItem[]
  /** 当前激活页签 id（v-model） */
  modelValue: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', id: string): void
  (e: 'close', id: string): void
}>()

function onActivate(id: string): void {
  if (id !== props.modelValue) emit('update:modelValue', id)
}

function onClose(id: string): void {
  emit('close', id)
}
</script>

<template>
  <div class="tabs-view">
    <div class="tabs-bar" role="tablist">
      <button
        v-for="t in tabs"
        :key="t.id"
        type="button"
        role="tab"
        class="tab"
        :class="{ active: t.id === modelValue }"
        :aria-selected="t.id === modelValue"
        :data-tab-id="t.id"
        @click="onActivate(t.id)"
      >
        <span class="tab-label">{{ t.label }}</span>
        <span
          v-if="t.closable"
          class="tab-close"
          role="button"
          aria-label="关闭页签"
          @click.stop="onClose(t.id)"
        >×</span>
      </button>
    </div>
    <div class="tabs-content" role="tabpanel"><slot /></div>
  </div>
</template>

<style scoped>
.tabs-view{display:flex;flex-direction:column;min-height:0}
.tabs-bar{display:flex;gap:2px;border-bottom:1px solid #e5e5e5}
.tab{display:inline-flex;align-items:center;gap:6px;padding:6px 14px;border:none;background:none;cursor:pointer;border-bottom:2px solid transparent}
.tab.active{border-bottom-color:var(--app-primary,#2f6fed);font-weight:600}
.tab-close{cursor:pointer;font-size:14px;line-height:1}
.tabs-content{flex:1;min-height:0}
</style>
