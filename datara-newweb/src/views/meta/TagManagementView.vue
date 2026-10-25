<template>
  <main class="pg" aria-label="标签管理">
    <header class="pg-head">
      <h1 class="sec-head">标签管理</h1>
      <p class="pg-desc">创建项目标签并挂载到资产（tags / assets/{id}/tags）。</p>
    </header>

    <div class="toolbar">
      <label class="field"><span>项目</span>
        <select v-model="selectedProject" class="kw" data-project-select :disabled="loading || creating" @change="reloadAssets">
          <option value="">请选择项目</option>
          <option v-for="p in projects" :key="p.id" :value="String(p.id)">{{ p.name }}</option>
        </select>
      </label>
      <span class="spacer"></span>
      <span v-if="projectId !== null" class="hint">资产 {{ assets.length }} 个 · 本次创建 {{ created.length }} 个</span>
    </div>

    <div v-if="error" class="err-box" role="alert" data-error>
      <span>{{ error }}</span>
      <button type="button" class="op-btn retry" :disabled="loading || creating || assigning" @click="retry">重试</button>
    </div>

    <div v-if="loading" class="panel" role="status" aria-live="polite">
      <div class="skeleton sk-row" style="width:40%"></div>
      <div class="skeleton sk-row" style="width:68%"></div>
    </div>

    <div v-else-if="projectId === null" class="panel empty" data-no-project>
      <div class="e-title">请先选择项目</div>
      <div class="e-hint">在上方下拉框选择项目后，即可创建标签并挂载资产。</div>
    </div>

    <!-- 左筛选面板 + 右内容（对标旧前端 ListFilterPanel 两栏范式） -->
    <div v-if="projectId !== null" class="split filter">
      <FilterPanel
        v-model:keyword="keyword"
        v-model:filters="filters"
        :facets="facets"
        placeholder="搜索资产"
        :result-count="filteredAssets.length"
        :total-count="assets.length"
      />

      <div class="page-main">
        <section v-if="assets.length === 0" class="panel empty" data-no-assets>
          <div class="e-title">暂无资产</div>
          <div class="e-hint">当前项目下没有资产，无法挂载标签；仍可在下方创建标签。</div>
        </section>
        <section v-else class="panel">
          <div class="tbl-toolbar">
            <span class="sec-head">资产标签</span>
            <span class="pill info">{{ filteredAssets.length }} / {{ assets.length }}</span>
            <span class="spacer"></span>
            <button type="button" class="op-btn" :disabled="loading || assigning" @click="reloadAssets">刷新</button>
          </div>
          <table class="tbl" data-tag-assets>
            <thead>
              <tr>
                <th>资产</th><th>所属域</th><th>类型</th><th>已挂载标签</th><th style="width:150px">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="a in filteredAssets" :key="a.id">
                <td>
                  <span class="mono" style="font-size:12px">{{ a.databaseName }}.{{ a.assetName }}</span>
                  <div style="color:var(--text-3);font-size:11px">{{ a.displayName || a.assetName }}</div>
                </td>
                <td><span class="pill info">{{ a.domainName || '—' }}</span></td>
                <td>{{ a.assetType }}</td>
                <td>
                  <template v-if="(a.tags ?? []).length">
                    <span v-for="t in a.tags" :key="t.id" class="tag">{{ t.displayName || t.tagKey }}</span>
                  </template>
                  <span v-else class="hint">未打标</span>
                </td>
                <td>
                  <button type="button" class="op-btn primary" :disabled="loading || assigning" @click="focusAssign(a)">打标</button>
                  <button
                    type="button"
                    class="op-btn danger"
                    :disabled="loading || assigning || clearingId !== null || (a.tags ?? []).length === 0"
                    @click="clearTags(a)"
                  >{{ clearingId === a.id ? '清空中…' : '清空' }}</button>
                </td>
              </tr>
              <tr v-if="filteredAssets.length === 0">
                <td class="empty" colspan="5">未找到匹配的资产</td>
              </tr>
            </tbody>
          </table>
        </section>

        <div class="split even">
          <form class="create panel" @submit.prevent="create">
            <div class="panel-hd">新建标签</div>
            <div class="form-grid">
              <label class="f-item"><span>命名空间</span><input v-model.trim="form.namespace" placeholder="default" :disabled="creating"></label>
              <label class="f-item"><span>标签键</span><input v-model.trim="form.tagKey" required :disabled="creating"></label>
              <label class="f-item"><span>显示名</span><input v-model.trim="form.displayName" required :disabled="creating"></label>
              <label class="f-item"><span>描述</span><input v-model="form.description" :disabled="creating"></label>
            </div>
            <div class="form-hint">创建成功后可在右侧资产挂载面板引用该标签 ID。</div>
            <div class="dlg-ft">
              <button type="button" class="op-btn" :disabled="creating" @click="resetForm">清空</button>
              <button type="submit" class="tb-new" :disabled="loading || creating || form.tagKey === '' || form.displayName === ''">
                {{ creating ? '创建中…' : '创建' }}
              </button>
            </div>
          </form>

          <section class="assign panel">
            <div class="panel-hd">资产挂载</div>
            <label class="field"><span>资产</span>
              <select v-model="selectedAsset" class="kw" data-asset-select :disabled="loading || assigning || creating">
                <option value="">请选择资产</option>
                <option v-for="a in assets" :key="a.id" :value="String(a.id)">{{ a.databaseName }}.{{ a.assetName }}</option>
              </select>
            </label>
            <p v-if="selectedAsset === ''" class="hint">先选择资产再填写标签 ID。</p>
            <label v-else class="field"><span>标签 ID</span>
              <input v-model.trim="tagIds" class="kw" placeholder="1,2,3" :disabled="assigning || creating">
            </label>
            <p v-if="assignHint" class="hint" data-assign-hint>{{ assignHint }}</p>
            <div class="dlg-ft">
              <button type="button" class="tb-new" :disabled="loading || selectedAsset === '' || tagIds === '' || assigning || creating" @click="assign">
                {{ assigning ? '挂载中…' : '挂载' }}
              </button>
            </div>
            <p v-if="lastResult" class="result-line" data-assign-result><span class="pill ok">{{ lastResult }}</span></p>
          </section>
        </div>

        <section class="panel">
          <div class="panel-hd">本次创建<span class="pill info">{{ created.length }}</span></div>
          <p v-if="created.length === 0" class="hint">尚未创建标签，创建成功后会在此列出。</p>
          <ul v-else class="recent-list">
            <li v-for="t in created" :key="t.key">
              <strong>#{{ t.id }}</strong>
              <span class="mono">{{ t.namespace }}:{{ t.tagKey }}</span>
              <span>{{ t.displayName }}</span>
              <span class="r-time">{{ t.time }}</span>
            </li>
          </ul>
        </section>
      </div>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useRoute } from 'vue-router'
import FilterPanel, { type Facet } from '../../components/FilterPanel.vue'
import { governanceApi, type AssetRecord, type GovernanceTagDefinition } from '../../services/rebuild/governanceApi'
import { listProjects, type ProjectSummary } from '../../services/rebuild/projectApi'

interface CreatedTag extends GovernanceTagDefinition { key: string; time: string }

const route = useRoute()
const projects = ref<ProjectSummary[]>([])
const selectedProject = ref('')
const assets = ref<AssetRecord[]>([])
const selectedAsset = ref('')
const tagIds = ref('')
const lastResult = ref('')
const assignHint = ref('')
const loading = ref(false)
const creating = ref(false)
const assigning = ref(false)
/** 行内「清空」的进行中资产 id（null=空闲），避免多行并发写冲突 */
const clearingId = ref<number | null>(null)
const error = ref('')
/** 错误框「重试」绑定操作：按错误来源设定（默认重载资产，创建/挂载/清空失败时重试对应操作） */
const retry = ref<() => void>(() => reloadAssets)
const created = ref<CreatedTag[]>([])
const form = reactive({ namespace: 'default', tagKey: '', displayName: '', description: '' })
/** 左筛选面板：关键字 + 各 facet 当前值（'' = 全部） */
const keyword = ref('')
const filters = ref<Record<string, string>>({})

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

/** facet 由真实资产数据派生：标签键（来自资产已挂载标签）+ 资产类型（不造选项）。 */
const facets = computed<Facet[]>(() => {
  const tagMap = new Map<string, string>()
  for (const a of assets.value) {
    for (const t of a.tags ?? []) if (t.tagKey) tagMap.set(t.tagKey, t.displayName || t.tagKey)
  }
  const tagOptions = [...tagMap.entries()]
    .map(([v, t]) => ({ v, t }))
    .sort((x, y) => x.t.localeCompare(y.t))
  const types = [...new Set(assets.value.map((a) => a.assetType).filter(Boolean))].sort()
  return [
    { key: 'tag', label: '标签', options: tagOptions },
    { key: 'assetType', label: '类型', options: types.map((t) => ({ v: t, t })) },
  ]
})

/** 客户端筛选（关键字 + 标签键 + 类型）；数据源为后端资产列表，标签取自资产 tags 字段。 */
const filteredAssets = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return assets.value.filter((a) => {
    if (filters.value.assetType && a.assetType !== filters.value.assetType) return false
    if (filters.value.tag && !(a.tags ?? []).some((t) => t.tagKey === filters.value.tag)) return false
    if (!kw) return true
    return `${a.assetName} ${a.displayName ?? ''} ${a.description ?? ''}`.toLowerCase().includes(kw)
  })
})

const message = (e: unknown): string => (e instanceof Error ? e.message : String(e))

async function init(): Promise<void> {
  try {
    const p = await listProjects()
    projects.value = p.list
    if (routeProjectId.value !== null) selectedProject.value = String(routeProjectId.value)
    if (selectedProject.value) await reloadAssets()
  } catch (e) {
    error.value = message(e)
    retry.value = init
  }
}
onMounted(init)

let assetSeq = 0
let loadedProjectId: number | null = null
/** 拉取资产列表；reset=true 用于切换项目（清空选择/结果），false 用于挂载后刷新（保留选择与结果）。 */
async function loadAssets(reset: boolean): Promise<void> {
  const pid = projectId.value
  if (pid !== loadedProjectId) {
    created.value = []
    loadedProjectId = pid
  }
  if (reset) {
    assets.value = []
    selectedAsset.value = ''
    tagIds.value = ''
    assignHint.value = ''
    lastResult.value = ''
  }
  if (pid === null) { assets.value = []; return }
  const seq = ++assetSeq
  loading.value = true
  error.value = ''
  try {
    const page = await governanceApi.listAssets(pid)
    if (seq !== assetSeq) return
    assets.value = page.list
  } catch (e) {
    if (seq === assetSeq) {
      error.value = message(e)
      retry.value = () => loadAssets(false)
    }
  } finally { if (seq === assetSeq) loading.value = false }
}
function reloadAssets(): Promise<void> {
  return loadAssets(true)
}

function resetForm(): void {
  Object.assign(form, { namespace: 'default', tagKey: '', displayName: '', description: '' })
}

async function create(): Promise<void> {
  if (projectId.value === null || loading.value || creating.value) return
  creating.value = true
  error.value = ''
  try {
    const tag = await governanceApi.createTag(projectId.value, { ...form })
    lastResult.value = `已创建标签 #${tag.id} ${tag.namespace}:${tag.tagKey}`
    created.value.unshift({
      ...tag,
      key: `${tag.id}-${Date.now()}`,
      time: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
    })
    resetForm()
  } catch (e) {
    error.value = message(e)
    retry.value = create
  } finally { creating.value = false }
}

async function assign(): Promise<void> {
  if (loading.value || assigning.value) return
  assignHint.value = ''
  const id = Number(selectedAsset.value)
  const raw = tagIds.value.split(',').map((s) => s.trim()).filter((s) => s !== '')
  const ids = raw.map((s) => Number(s)).filter((n) => Number.isInteger(n) && n > 0)
  if (!Number.isInteger(id) || id <= 0 || raw.length === 0 || ids.length !== raw.length) {
    assignHint.value = '标签 ID 需为逗号分隔的正整数（如 1,2），请检查后重试。'
    return
  }
  assigning.value = true
  error.value = ''
  try {
    const res = await governanceApi.assignAssetTags(id, ids)
    lastResult.value = `资产 #${res.assetId} 已挂载标签：${res.tagIds.join(', ')}`
    await loadAssets(false)
  } catch (e) {
    error.value = message(e)
    retry.value = assign
  } finally { assigning.value = false }
}

/** 行操作：把该资产带入挂载面板（复用既有挂载流程，不重复造写接口）。 */
function focusAssign(a: AssetRecord): void {
  if (loading.value) return
  selectedAsset.value = String(a.id)
  assignHint.value = ''
}

/** 行操作：清空该资产全部标签（assignAssetTags(id, []) 为后端既有替换语义）。 */
async function clearTags(a: AssetRecord): Promise<void> {
  if (loading.value || assigning.value || clearingId.value !== null) return
  try {
    await ElMessageBox.confirm(`确认清空资产“${a.displayName || a.assetName}”的全部标签？`, '清空标签', { type: 'warning' })
  } catch {
    return
  }
  clearingId.value = a.id
  error.value = ''
  try {
    await governanceApi.assignAssetTags(a.id, [])
    lastResult.value = `资产 #${a.id} 已清空标签`
    await loadAssets(false)
  } catch (e) {
    error.value = message(e)
    retry.value = () => clearTags(a)
  } finally { clearingId.value = null }
}
</script>

<style scoped>
.tag{display:inline-block;border-radius:4px;padding:1px 8px;font-size:11.5px;font-weight:600;margin:0 4px 2px 0;background:var(--primary-light);color:var(--primary)}
</style>
