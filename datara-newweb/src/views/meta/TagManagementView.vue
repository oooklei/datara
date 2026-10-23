<template>
  <main class="meta-page" aria-label="标签管理">
    <header class="meta-head">
      <div>
        <h1>标签管理</h1>
        <p>创建项目标签并挂载到资产（tags / assets/{id}/tags）。</p>
      </div>
      <div class="meta-actions">
        <label>项目
          <select v-model="selectedProject" data-project-select @change="reloadAssets">
            <option value="">请选择项目</option>
            <option v-for="p in projects" :key="p.id" :value="String(p.id)">{{ p.name }}</option>
          </select>
        </label>
      </div>
    </header>

    <p v-if="error" role="alert" data-error>{{ error }}</p>
    <p v-if="loading" role="status">加载中…</p>
    <p v-else-if="projectId === null" data-no-project>请先选择项目</p>

    <div v-else class="split">
      <form class="create" @submit.prevent="create">
        <h2>新建标签</h2>
        <label>命名空间<input v-model.trim="form.namespace" placeholder="default"></label>
        <label>标签键<input v-model.trim="form.tagKey" required></label>
        <label>显示名<input v-model.trim="form.displayName" required></label>
        <label>描述<input v-model="form.description"></label>
        <button type="submit">创建</button>
      </form>

      <section class="assign">
        <h2>资产挂载</h2>
        <label>资产
          <select v-model="selectedAsset" data-asset-select>
            <option value="">请选择资产</option>
            <option v-for="a in assets" :key="a.id" :value="String(a.id)">{{ a.databaseName }}.{{ a.assetName }}</option>
          </select>
        </label>
        <p v-if="selectedAsset === ''" class="hint">先选择资产再填写标签 ID。</p>
        <label v-else>标签 ID（逗号分隔）
          <input v-model.trim="tagIds" placeholder="1,2,3">
        </label>
        <button type="button" :disabled="selectedAsset === '' || tagIds === ''" @click="assign">挂载</button>
        <p v-if="lastResult" data-assign-result>{{ lastResult }}</p>
      </section>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { governanceApi, type AssetRecord } from '../../services/rebuild/governanceApi'
import { listProjects, type ProjectSummary } from '../../services/rebuild/projectApi'

const route = useRoute()
const projects = ref<ProjectSummary[]>([])
const selectedProject = ref('')
const assets = ref<AssetRecord[]>([])
const selectedAsset = ref('')
const tagIds = ref('')
const lastResult = ref('')
const loading = ref(false)
const error = ref('')
const form = reactive({ namespace: 'default', tagKey: '', displayName: '', description: '' })

const routeProjectId = computed<number | null>(() => {
  const raw = route.params.projectId ?? route.query.projectId
  const value = Array.isArray(raw) ? raw[0] : raw
  const n = Number(value)
  return value !== undefined && value !== '' && Number.isInteger(n) && n > 0 ? n : null
})
const projectId = computed<number | null>(() => {
  const fromRoute = routeProjectId.value
  if (fromRoute !== null) return fromRoute
  const n = Number(selectedProject.value)
  return selectedProject.value !== '' && Number.isInteger(n) && n > 0 ? n : null
})

const message = (e: unknown): string => (e instanceof Error ? e.message : String(e))

onMounted(async () => {
  try {
    const p = await listProjects()
    projects.value = p.list
    if (routeProjectId.value !== null) selectedProject.value = String(routeProjectId.value)
    if (selectedProject.value) await reloadAssets()
  } catch (e) { error.value = message(e) }
})

async function reloadAssets(): Promise<void> {
  selectedAsset.value = ''
  tagIds.value = ''
  if (projectId.value === null) { assets.value = []; return }
  loading.value = true
  error.value = ''
  try {
    const page = await governanceApi.listAssets(projectId.value)
    assets.value = page.list
  } catch (e) { error.value = message(e) } finally { loading.value = false }
}

async function create(): Promise<void> {
  if (projectId.value === null) return
  error.value = ''
  try {
    const tag = await governanceApi.createTag(projectId.value, { ...form })
    lastResult.value = `已创建标签 #${tag.id} ${tag.namespace}:${tag.tagKey}`
    Object.assign(form, { namespace: 'default', tagKey: '', displayName: '', description: '' })
  } catch (e) { error.value = message(e) }
}

async function assign(): Promise<void> {
  const id = Number(selectedAsset.value)
  const ids = tagIds.value.split(',').map((s) => Number(s.trim())).filter((n) => Number.isInteger(n) && n > 0)
  if (!Number.isInteger(id) || id <= 0 || ids.length === 0) return
  error.value = ''
  try {
    const res = await governanceApi.assignAssetTags(id, ids)
    lastResult.value = `资产 #${res.assetId} 已挂载标签：${res.tagIds.join(', ')}`
  } catch (e) { error.value = message(e) }
}
</script>

<style scoped>
.meta-page{max-width:1100px;margin:auto;padding:24px}
.meta-head{display:flex;flex-wrap:wrap;gap:16px;align-items:flex-end;justify-content:space-between}
.meta-actions{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end}
.split{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px}
.create,.assign{border:1px solid #e2e8f0;border-radius:6px;padding:12px;display:grid;gap:8px;align-content:start}
label{display:grid;gap:4px;font-size:13px}
.hint{color:#64748b;font-size:12px}
</style>
