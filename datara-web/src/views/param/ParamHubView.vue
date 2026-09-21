<script setup lang="ts">
/**
 * 参数配置 Hub（四页合并入口，F56a 同壳单入口）—— 权威路由 /param/global，
 * 页签走 query.tab 切换；旧路径 /param/builtin|env|tools redirect 保书签（query 原样透传）。
 * 各子页内保留 ParamTree 左侧树导航（树跳转走路由，与本壳 Tab 双向联动，query.tab 为唯一真相）。
 * 工作流变量已迁入任务中心 → 工作流 → 编排「变量」页签（管理与使用分离）。
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import ParamGlobalView from './ParamGlobalView.vue'
import ParamBuiltinView from './ParamBuiltinView.vue'
import ParamEnvView from './ParamEnvView.vue'
import ParamToolsView from './ParamToolsView.vue'

const route = useRoute()
type TabKey = 'global' | 'builtin' | 'env' | 'tools'
const tabs: { k: TabKey; label: string }[] = [
  { k: 'global', label: '全局参数' },
  { k: 'builtin', label: '内置时间参数' },
  { k: 'env', label: '环境参数组' },
  { k: 'tools', label: '引用检测与预览' },
]
const tab = computed<TabKey>(() => {
  const t = String(route.query.tab ?? 'global')
  return (tabs.some((x) => x.k === t) ? t : 'global') as TabKey
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
      <ParamGlobalView v-if="tab === 'global'" />
      <ParamBuiltinView v-else-if="tab === 'builtin'" />
      <ParamEnvView v-else-if="tab === 'env'" />
      <ParamToolsView v-else />
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
