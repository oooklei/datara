<script setup lang="ts">
/**
 * TargetBasePanel 目标端基础信息（target_base 面板）。
 * 语义（与源端 SourceBasePanel 对称，同为"中心数据源表单"模式）：
 *  - 目标表必须存在（区别于源端可开拓新表）
 *  - 目标表从中心数据源下拉选择 → 探表列出 schema/字段清单（只读）
 *  - 血缘载体字段（血缘来源字段 / 目标备注字段）由后端 schema 探测清单回填
 * 探表走 datasourceApi.listSchemas，只读不写库。
 */
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { listDataSources, listSchemas } from '../../../services/datasourceApi'
import type { DsRow, DatasourceSchema } from '../../../services/datasourceApi'
import { useGraphStore } from '../../../stores/graph'
import type { GNode } from '../../model'

const props = withDefaults(
  defineProps<{
    node?: GNode | null
    selectedId?: string | null
    profile?: any
    schema?: any
    readonly?: boolean
  }>(),
  { node: null, selectedId: null, readonly: false },
)

const graphStore = useGraphStore()

/** 活跃节点：显式 node 优先，否则按 selectedId 从当前文档解析（浮窗 propsOf 只传 selectedId） */
const activeNode = computed<GNode | null>(() => {
  if (props.node) return props.node
  if (!props.selectedId || !graphStore.doc) return null
  return graphStore.doc.nodes.find((n) => n.id === props.selectedId) ?? null
})

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'update', patch: Record<string, unknown>): void
}>()

/** 中心数据源下拉 */
const datasources = ref<DsRow[]>([])
const loadingDs = ref(false)

/** 目标数据中心 ID → 探表 */
const targetCenterId = ref('')
const probing = ref(false)
const schemaTree = ref<DatasourceSchema[] | null>(null)
const probeError = ref('')

/** 血缘载体字段（探表后从 schema 探测清单回填可选项） */
const carrierFields = ref<string[]>([])
const carrierField = ref('')

const displayName = computed(() => activeNode.value?.data?.name ?? '目标端基础信息')
const readonly_ = computed(() => props.readonly ?? false)

async function loadDs() {
  loadingDs.value = true
  try {
    datasources.value = await listDataSources()
  } catch (e) {
    console.error('[TargetBasePanel] 数据源列表加载失败', e)
  } finally {
    loadingDs.value = false
  }
}

async function probe() {
  if (!targetCenterId.value) {
    probeError.value = '请先选择目标数据中心'
    return
  }
  probing.value = true
  probeError.value = ''
  schemaTree.value = null
  try {
    const res = await listSchemas(targetCenterId.value)
    schemaTree.value = res ?? null
    // 血缘载体字段：从探测到的 schema 首表列清单回填（只读展示）
    const tables = res ?? []
    const first = tables.length > 0 ? tables[0] : null
    const cols = first && first.tables.length > 0 ? (first.tables[0].columns ?? []) : []
    carrierFields.value = cols.map((c) => c.name ?? String(c))
  } catch (e: any) {
    probeError.value = String(e?.message ?? e)
  } finally {
    probing.value = false
  }
}

function patch(p: Record<string, unknown>) {
  if (readonly_.value) return
  emit('update', p)
}

/** 保存写回活跃节点 data（target_center / 血缘载体字段），host 经 onUpdate 接线 markDirty */
function save() {
  if (readonly_.value || !activeNode.value) return
  const node = activeNode.value
  const p: Record<string, unknown> = { target_center: targetCenterId }
  if (carrierField.value) p.target_carrier_field = carrierField.value
  Object.assign(node.data, p)
  patch(p)
}

function emitClose() {
  emit('close')
}

/** 初始化回填已保存配置后再响应用户变更（避免首次赋值清空探测结果/载体字段） */
const initialized = ref(false)
onMounted(async () => {
  await loadDs()
  const nd = activeNode.value?.data
  if (nd) {
    targetCenterId.value = String(nd.target_center ?? '')
    carrierField.value = String(nd.target_carrier_field ?? '')
  }
  await nextTick()
  initialized.value = true
  if (targetCenterId.value) await probe()
})
watch(targetCenterId, () => {
  if (!initialized.value) return
  carrierFields.value = []
  carrierField.value = ''
  schemaTree.value = null
  probeError.value = ''
})
</script>

<template>
  <div class="tb-panel">
    <div class="tb-hd">
      <span class="tb-title">{{ displayName }}</span>
      <div class="tb-tools">
        <button v-if="!readonly_" class="btn-link" type="button" :disabled="!activeNode" @click="save">保存</button>
        <button class="btn-link" type="button" @click="emitClose">关闭</button>
      </div>
    </div>

    <div class="tb-bd">
      <!-- 目标数据中心（目标表必须存在，来源必须是中心数据源中已注册的表目录） -->
      <label class="m-field">
        <span class="m-field-label">目标数据中心（目标表必须存在）</span>
        <select
          v-model="targetCenterId"
          class="m-input"
          :disabled="readonly_"
        >
          <option value="">请选择中心数据源…</option>
          <option v-for="ds in datasources" :key="ds.id" :value="ds.id">{{ ds.name }}</option>
        </select>
      </label>

      <!-- 探表（只读）：列出 schema/表/字段 血缘载体候选 -->
      <div class="tb-probe">
        <div class="tb-probe-tools">
          <span class="tb-probe-hint">探表（只读，不写库）</span>
          <button class="btn-link" type="button" :disabled="probing || !targetCenterId" @click="probe">
            {{ probing ? '探测中…' : '探测' }}
          </button>
        </div>
        <p v-if="probeError" class="tb-probe-error">{{ probeError }}</p>

        <div v-if="schemaTree" class="tb-tree">
          <div v-for="db in schemaTree" :key="db.db" class="tb-db">
            <div class="tb-db-name">{{ db.db }}</div>
            <div v-for="t in (db.tables ?? [])" :key="t.name" class="tb-row">
              <span class="tb-table">{{ t.name }}</span>
              <div v-if="t.columns?.length" class="tb-cols">
                <span v-for="c in t.columns" :key="c.name" class="tb-col">{{ c.name }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 血缘载体字段（探表回填，只读） -->
      <label class="m-field">
        <span class="m-field-label">血缘载体字段</span>
        <select v-model="carrierField" class="m-input" :disabled="readonly_">
          <option value="">无（不写血缘载体）</option>
          <option v-for="f in carrierFields" :key="f" :value="f">{{ f }}</option>
        </select>
      </label>
    </div>
  </div>
</template>

<style scoped>
.tb-panel { display: flex; flex-direction: column; height: 100%; min-width: 320px; }
.tb-hd { display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; border-bottom: 1px solid var(--m-border, #e5e7eb); }
.tb-title { font-size: 13px; font-weight: 600; color: var(--m-text, #1f2937); }
.tb-tools { display: flex; gap: 8px; }
.btn-link { background: none; border: none; color: var(--m-primary, #2563eb); cursor: pointer; font-size: 12px; }
.btn-link:disabled { color: var(--m-text-muted, #9ca3af); cursor: not-allowed; }
.tb-bd { flex: 1; overflow: auto; padding: 12px; display: flex; flex-direction: column; gap: 12px; }
.m-field { display: flex; flex-direction: column; gap: 4px; }
.m-field-label { font-size: 12px; color: var(--m-text-muted, #6b7280); }
.m-input { box-sizing: border-box; width: 100%; padding: 6px 8px; border: 1px solid var(--m-border, #e5e7eb); border-radius: 4px; font-size: 13px; background: var(--m-bg, #fff); color: var(--m-text, #1f2937); }
.m-input:disabled { opacity: 0.6; cursor: not-allowed; }
.tb-probe { border-top: 1px dashed var(--m-border, #e5e7eb); padding-top: 10px; }
.tb-probe-tools { display: flex; align-items: center; justify-content: space-between; }
.tb-probe-hint { font-size: 12px; color: var(--m-text-muted, #6b7280); }
.tb-probe-error { font-size: 12px; color: var(--m-danger, #dc2626); margin: 4px 0 0; }
.tb-tree { margin-top: 6px; max-height: 200px; overflow: auto; border: 1px solid var(--m-border, #e5e7eb); border-radius: 4px; padding: 6px; background: var(--m-bg-muted, #f8fafc); font-size: 11px; }
.tb-db { margin-bottom: 6px; }
.tb-db-name { font-weight: 600; color: var(--m-text, #1f2937); margin-bottom: 2px; }
.tb-row { margin-left: 10px; }
.tb-table { color: var(--m-text-2, #374151); display: inline-block; min-width: 120px; }
.tb-cols { display: flex; flex-wrap: wrap; gap: 3px; margin: 2px 0 4px 10px; }
.tb-col { background: var(--m-bg, #fff); border: 1px solid var(--m-border, #e5e7eb); border-radius: 3px; padding: 1px 5px; color: var(--m-text-3, #6b7280); }
</style>
