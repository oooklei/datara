<template>
  <section class="resource-page" aria-label="资源管理">
    <header class="resource-head">
      <div><h1>资源管理</h1><p>管理 SQL、Python、Shell 资源及其不可变版本。</p></div>
      <select v-model="kind" aria-label="资源类型" @change="load"><option value="">全部类型</option><option value="sql">SQL</option><option value="python">Python</option><option value="shell">Shell</option></select>
    </header>
    <p v-if="error" class="error">{{ error }}</p>
    <table v-else><thead><tr><th>名称</th><th>类型</th><th>版本</th><th>状态</th><th>更新时间</th></tr></thead>
      <tbody><tr v-for="item in items" :key="item.resourceId"><td>{{ item.name }}</td><td>{{ item.kind }}</td><td>v{{ item.latestVersion }}</td><td>active</td><td>{{ item.sizeBytes }} bytes</td></tr><tr v-if="!loading && !items.length"><td colspan="5">暂无资源</td></tr></tbody>
    </table>
    <p v-if="loading">加载中…</p>
  </section>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { createResourceContract, type ResourceKind, type ResourceMeta } from '../../services/rebuild/resourceApi'

const props = defineProps<{ projectId: number }>()
const api = createResourceContract()
const kind = ref<ResourceKind | ''>('')
const items = ref<ResourceMeta[]>([])
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true; error.value = ''
  try { items.value = await api.listResources(props.projectId, kind.value || undefined) }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '资源加载失败' }
  finally { loading.value = false }
}
// Vue reuses the segment component when only :projectId changes.  Reload on
// prop changes as well as the initial mount so a deep-link switch never shows
// resources from the previous project.
watch(() => props.projectId, () => { void load() }, { immediate: true })
</script>

<style scoped>
.resource-page{padding:24px}.resource-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px}.resource-head h1{margin:0 0 6px}.resource-head p{margin:0;color:#64748b}.resource-head select{padding:8px 12px}table{width:100%;border-collapse:collapse;background:#fff}th,td{padding:10px 12px;border-bottom:1px solid #e2e8f0;text-align:left}.error{color:#b91c1c}
</style>
