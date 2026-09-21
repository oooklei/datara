<script setup lang="ts">
/**
 * 标准管理 Hub（五页合并入口，F56a 同壳单入口）——
 * 权威路由 /std/element，页签走 query.tab 切换；
 * 旧路径 /std/code|naming|mapping|approval redirect 保书签（query 原样透传）。
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import StdElementView from './StdElementView.vue'
import StdCodeView from './StdCodeView.vue'
import StdNamingView from './StdNamingView.vue'
import StdMappingView from './StdMappingView.vue'
import StdApprovalView from './StdApprovalView.vue'

const route = useRoute()
type TabKey = 'element' | 'code' | 'naming' | 'mapping' | 'approval'
const tabs: { k: TabKey; label: string }[] = [
  { k: 'element', label: '数据元标准' },
  { k: 'code', label: '代码标准' },
  { k: 'naming', label: '命名规范' },
  { k: 'mapping', label: '标准映射与合规' },
  { k: 'approval', label: '标准审批' },
]
const tab = computed<TabKey>(() => {
  const t = String(route.query.tab ?? 'element')
  return (tabs.some((x) => x.k === t) ? t : 'element') as TabKey
})
</script>

<template>
  <div class="hub">
    <div class="hub-tabs">
      <router-link
        v-for="t in tabs" :key="t.k"
        class="hub-tab" :class="{ on: tab === t.k }"
        :to="{ query: { ...route.query, tab: t.k } }"
      >{{ t.label }}</router-link>
    </div>
    <div class="hub-body">
      <StdElementView v-if="tab === 'element'" />
      <StdCodeView v-else-if="tab === 'code'" />
      <StdNamingView v-else-if="tab === 'naming'" />
      <StdMappingView v-else-if="tab === 'mapping'" />
      <StdApprovalView v-else />
    </div>
  </div>
</template>

<style scoped>
.hub{display:flex;flex-direction:column;height:100%}
.hub-tabs{display:flex;align-items:center;gap:2px;padding:0 14px;background:#fff;border-bottom:1px solid var(--border);flex-shrink:0}
.hub-tab{padding:11px 16px;font-size:13px;color:var(--text-2);cursor:pointer;border-bottom:2px solid transparent;text-decoration:none;transition:color var(--dur-base) var(--ease),border-color var(--dur-base) var(--ease)}
.hub-tab:hover{color:var(--primary)}
.hub-tab.on{color:var(--primary);border-bottom-color:var(--primary);font-weight:600}
.hub-body{flex:1;min-height:0;overflow:auto;display:flex;flex-direction:column}
</style>
