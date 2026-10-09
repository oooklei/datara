<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getImpactedWorkflows, upgradeComponentRefs, type ImpactedWorkflow, type UpgradeRefResult } from '../../services/componentApi'

const props = defineProps<{ componentType: string }>()
const emit = defineEmits<{ done: [results: UpgradeRefResult[]]; cancel: [] }>()

const loading = ref(true)
const submitting = ref(false)
const error = ref('')
const rows = ref<ImpactedWorkflow[]>([])
const selected = ref<Set<string>>(new Set())
const results = ref<UpgradeRefResult[] | null>(null)

const selectedRows = computed(() => rows.value.filter((row) => selected.value.has(row.id)))
const successful = computed(() => results.value?.filter((row) => row.ok) ?? [])
const failed = computed(() => results.value?.filter((row) => !row.ok) ?? [])

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const impacted = await getImpactedWorkflows(props.componentType)
    rows.value = impacted.items
    selected.value = new Set(impacted.items.filter((row) => row.behind).map((row) => row.id))
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause)
  } finally { loading.value = false }
}

function toggle(id: string): void {
  const next = new Set(selected.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selected.value = next
}

async function submit(): Promise<void> {
  if (!selectedRows.value.length) return
  submitting.value = true
  error.value = ''
  try {
    const response = await upgradeComponentRefs(props.componentType, selectedRows.value.map((row) => ({
      wfId: row.id, baseVersion: row.version,
    })))
    results.value = response.results
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause)
  } finally { submitting.value = false }
}

onMounted(load)
</script>

<template>
  <section class="upgrade-wizard">
    <header><b>批量升级引用</b><span>选择需要升至已发布组件版本的工作流</span></header>
    <p v-if="loading">正在加载影响面…</p>
    <p v-else-if="error" class="error">{{ error }}</p>
    <template v-else-if="results === null">
      <label v-for="row in rows" :key="row.id" class="target">
        <input type="checkbox" :checked="selected.has(row.id)" :disabled="!row.behind" @change="toggle(row.id)">
        <span><b>{{ row.name }}</b> · v{{ row.version }} · 当前引用 v{{ row.refVersions.join(', ') || '-' }}</span>
        <em :class="row.behind ? 'behind' : 'aligned'">{{ row.behind ? '待升级' : '已对齐' }}</em>
      </label>
      <footer>
        <button type="button" @click="emit('cancel')">取消</button>
        <button type="button" class="primary" :disabled="!selectedRows.length || submitting" @click="submit">
          {{ submitting ? '升级中…' : `升级 ${selectedRows.length} 项` }}
        </button>
      </footer>
    </template>
    <template v-else>
      <p>升级完成：成功 {{ successful.length }} 项，失败 {{ failed.length }} 项。</p>
      <p v-for="row in failed" :key="row.wfId" class="error">{{ row.wfId }}：{{ row.reason || '升级失败' }}</p>
      <footer><button type="button" class="primary" @click="emit('done', results!)">完成</button></footer>
    </template>
  </section>
</template>

<style scoped>
.upgrade-wizard{display:grid;gap:10px;min-width:440px;color:var(--text)} header{display:grid;gap:3px} header span{font-size:12px;color:var(--text-3)}.target{display:flex;align-items:center;gap:8px;padding:8px;border:1px solid var(--border);border-radius:6px;font-size:12px}.target span{flex:1}.target em{font-style:normal;font-size:11px}.behind{color:var(--warn)}.aligned{color:var(--success)}footer{display:flex;justify-content:flex-end;gap:8px}.primary{background:var(--primary);color:#fff;border-color:var(--primary)}button{padding:5px 10px;border:1px solid var(--border);border-radius:5px;background:var(--card);cursor:pointer}.error{color:var(--danger);font-size:12px}
</style>
