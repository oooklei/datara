<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  getComponentVersionSnapshot,
  getImpactedWorkflows,
  upgradeComponentRefs,
  type ImpactedWorkflow,
  type UpgradeRefResult,
} from '../../services/componentApi'
import { classifySpecChange, type ComponentSpec, type SpecChangeSummary } from '../../services/componentSpec'

type Step = 'select' | 'review' | 'results'
type Migration = 'map' | 'skip'

interface ReviewItem {
  row: ImpactedWorkflow
  referenceVersion: number
  change: SpecChangeSummary
  targetFields: string[]
  mapping: Record<string, string>
  migration?: Migration
}

const props = defineProps<{ componentType: string }>()
const emit = defineEmits<{ done: [results: UpgradeRefResult[]]; cancel: [] }>()

const loading = ref(true)
const submitting = ref(false)
const error = ref('')
const step = ref<Step>('select')
const rows = ref<ImpactedWorkflow[]>([])
const publishedVersion = ref<number | null>(null)
const selected = ref<Set<string>>(new Set())
const reviewItems = ref<ReviewItem[]>([])
const results = ref<UpgradeRefResult[] | null>(null)

const selectedRows = computed(() => rows.value.filter((row) => selected.value.has(row.id)))
const successful = computed(() => results.value?.filter((row) => row.ok) ?? [])
const failed = computed(() => results.value?.filter((row) => !row.ok) ?? [])
const skippedCount = computed(() => results.value?.filter((row) => row.ok && row.migration === 'skip').length ?? 0)
const canSubmit = computed(() => reviewItems.value.every((item) => {
  if (!item.change.removed.length) return true
  if (item.migration === 'skip') return true
  return item.migration === 'map' && item.change.removed.every((key) => Boolean(item.mapping[key]))
}))

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const impacted = await getImpactedWorkflows(props.componentType)
    rows.value = impacted.items
    publishedVersion.value = impacted.publishedVersion
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

function referenceVersion(row: ImpactedWorkflow): number | null {
  const versions = row.refVersions.filter((version) => version > 0)
  return versions.length ? Math.min(...versions) : null
}

async function beginReview(): Promise<void> {
  if (!selectedRows.value.length || !publishedVersion.value) return
  loading.value = true
  error.value = ''
  try {
    const target = await getComponentVersionSnapshot(props.componentType, publishedVersion.value)
    const items = await Promise.all(selectedRows.value.map(async (row): Promise<ReviewItem> => {
      const version = referenceVersion(row)
      if (version === null) throw new Error(`${row.name} 缺少可比较的组件版本`)
      const source = await getComponentVersionSnapshot(props.componentType, version)
      const change = classifySpecChange(source.spec as Partial<ComponentSpec>, target.spec as Partial<ComponentSpec>)
      return {
        row,
        referenceVersion: version,
        change,
        targetFields: ((target.spec as Partial<ComponentSpec>).fields ?? [])
          .map((field) => typeof field === 'object' && field !== null ? String((field as { key?: unknown }).key ?? '') : '')
          .filter(Boolean),
        mapping: {},
      }
    }))
    reviewItems.value = items
    step.value = 'review'
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause)
  } finally { loading.value = false }
}

function setMigration(item: ReviewItem, migration: Migration): void {
  item.migration = migration
}

function setMapping(item: ReviewItem, oldField: string, event: Event): void {
  setMigration(item, 'map')
  const value = (event.target as HTMLSelectElement | null)?.value ?? ''
  if (value) item.mapping[oldField] = value
  else delete item.mapping[oldField]
}

function fieldKeys(item: ReviewItem): string[] {
  return item.targetFields
}

async function submit(): Promise<void> {
  if (!canSubmit.value || !reviewItems.value.length) return
  submitting.value = true
  error.value = ''
  try {
    const response = await upgradeComponentRefs(props.componentType, reviewItems.value.map((item) => ({
      wfId: item.row.id,
      baseVersion: item.row.version,
      ...(item.migration ? { migration: item.migration } : {}),
      ...(item.migration === 'map' && Object.keys(item.mapping).length ? { fieldMapping: item.mapping } : {}),
    })))
    results.value = response.results
    step.value = 'results'
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause)
  } finally { submitting.value = false }
}

function backToSelect(): void {
  reviewItems.value = []
  step.value = 'select'
}

onMounted(load)
</script>

<template>
  <section class="upgrade-wizard">
    <header><b>批量升级引用</b><span>先确认影响面，再审阅字段兼容性并执行升级。</span></header>
    <p v-if="loading">正在加载升级信息…</p>
    <p v-else-if="error" class="error">{{ error }}</p>

    <template v-else-if="step === 'select'">
      <label v-for="row in rows" :key="row.id" class="target">
        <input type="checkbox" :checked="selected.has(row.id)" :disabled="!row.behind" @change="toggle(row.id)">
        <span><b>{{ row.name }}</b> · v{{ row.version }} · 当前引用 v{{ row.refVersions.join(', ') || '-' }}</span>
        <em :class="row.behind ? 'behind' : 'aligned'">{{ row.behind ? '待升级' : '已对齐' }}</em>
      </label>
      <footer>
        <button type="button" @click="emit('cancel')">取消</button>
        <button type="button" class="primary" data-testid="upgrade-next" :disabled="!selectedRows.length" @click="beginReview">
          审阅 {{ selectedRows.length }} 项
        </button>
      </footer>
    </template>

    <template v-else-if="step === 'review'">
      <p class="review-intro">字段变更需要明确处理；未移除字段可直接升级。</p>
      <article v-for="item in reviewItems" :key="item.row.id" class="review-item">
        <b>{{ item.row.name }}</b><span>组件 v{{ item.referenceVersion }} → v{{ publishedVersion }}</span>
        <p v-if="!item.change.breaking" class="aligned">未发现破坏性字段变化。</p>
        <template v-else>
          <p class="warning">检测到：移除 {{ item.change.removed.length }} 个字段、控件变化 {{ item.change.uiChanged.length }} 项、必填收紧 {{ item.change.requiredTightened.length }} 项。</p>
          <div v-if="item.change.removed.length" class="migration">
            <label class="decision"><input type="radio" :name="`migration-${item.row.id}`" :checked="item.migration === 'map'" @change="setMigration(item, 'map')"> 映射已移除字段</label>
            <label class="decision"><input :data-testid="`migration-skip-${item.row.id}`" type="radio" :name="`migration-${item.row.id}`" :checked="item.migration === 'skip'" @change="setMigration(item, 'skip')"> 明确跳过字段迁移</label>
            <label v-for="oldField in item.change.removed" :key="oldField" class="mapping">
              {{ oldField }} →
              <select :value="item.mapping[oldField] || ''" :disabled="item.migration === 'skip'" @change="setMapping(item, oldField, $event)">
                <option value="">选择目标字段</option>
                <option v-for="newField in fieldKeys(item)" :key="newField" :value="newField">{{ newField }}</option>
              </select>
            </label>
          </div>
        </template>
      </article>
      <footer>
        <button type="button" @click="backToSelect">上一步</button>
        <button type="button" class="primary" data-testid="upgrade-submit" :disabled="!canSubmit || submitting" @click="submit">
          {{ submitting ? '升级中…' : `确认升级 ${reviewItems.length} 项` }}
        </button>
      </footer>
    </template>

    <template v-else>
      <p>升级完成：成功 {{ successful.length }} 项，失败 {{ failed.length }} 项。<template v-if="skippedCount">明确跳过 {{ skippedCount }} 项字段迁移。</template></p>
      <p v-for="row in failed" :key="row.wfId" class="error">{{ row.wfId }}：{{ row.reason || '升级失败' }}</p>
      <footer><button type="button" class="primary" @click="emit('done', results!)">完成</button></footer>
    </template>
  </section>
</template>

<style scoped>
.upgrade-wizard{display:grid;gap:10px;min-width:480px;color:var(--text)}header{display:grid;gap:3px}header span,.review-item span{font-size:12px;color:var(--text-3)}.target,.review-item{display:grid;gap:7px;padding:9px;border:1px solid var(--border);border-radius:6px;font-size:12px}.target{grid-template-columns:auto 1fr auto;align-items:center}.target em{font-style:normal;font-size:11px}.review-intro{margin:0;font-size:12px;color:var(--text-2)}.warning{margin:0;color:var(--warn)}.migration{display:grid;gap:5px}.decision,.mapping{font-size:12px}.mapping{display:flex;align-items:center;gap:6px}select{min-width:150px;padding:3px;border:1px solid var(--border);border-radius:4px;background:var(--card);color:var(--text)}.behind{color:var(--warn)}.aligned{color:var(--success)}footer{display:flex;justify-content:flex-end;gap:8px}button{padding:5px 10px;border:1px solid var(--border);border-radius:5px;background:var(--card);cursor:pointer}button:disabled{cursor:not-allowed;opacity:.55}.primary{background:var(--primary);color:#fff;border-color:var(--primary)}.error{color:var(--danger);font-size:12px}
</style>
