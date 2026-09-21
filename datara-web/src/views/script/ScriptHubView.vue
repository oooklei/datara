<script setup lang="ts">
/**
 * 脚本任务 Hub（三页合并入口，F56a 同壳单入口）—— 权威路由 /script/list，
 * 页签走 query.tab 切换；旧路径 /script/env|remote redirect 保书签（query 原样透传）。
 * 远程执行(SSH) 节点配置以部署运维「运行时节点」为唯一权威源（页内仍可跳转）。
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import ScriptListView from './ScriptListView.vue'
import ScriptEnvView from './ScriptEnvView.vue'
import ScriptRemoteView from './ScriptRemoteView.vue'

const route = useRoute()
type TabKey = 'list' | 'env' | 'remote'
const tabs: { k: TabKey; label: string }[] = [
  { k: 'list', label: '脚本库' },
  { k: 'env', label: '环境与依赖' },
  { k: 'remote', label: '远程执行(SSH)' },
]
const tab = computed<TabKey>(() => {
  const t = String(route.query.tab ?? 'list')
  return (tabs.some((x) => x.k === t) ? t : 'list') as TabKey
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
      <ScriptListView v-if="tab === 'list'" />
      <ScriptEnvView v-else-if="tab === 'env'" />
      <ScriptRemoteView v-else />
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
