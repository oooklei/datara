<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { createSyncComponentContract, type SyncMapping, type SyncObjectRef } from '../services/rebuild/syncComponentApi'

const props = defineProps<{ projectId: number; workflowId: number; workflowVersion: number; taskId: string; modelValue?: Record<string, unknown> }>()
const emit = defineEmits<{ 'update:modelValue': [value: Record<string, unknown>]; saved: [] }>()
const api = createSyncComponentContract()
const busy = ref(false)
const source = reactive<SyncObjectRef>({ ...(props.modelValue?.source as SyncObjectRef | undefined ?? { datasource_id: 0, schema: '', object: '' }) })
const target = reactive<SyncObjectRef>({ ...(props.modelValue?.target as SyncObjectRef | undefined ?? { datasource_id: 0, schema: '', object: '' }) })
const mappings = ref<SyncMapping[]>((props.modelValue?.mappings as SyncMapping[] | undefined) ?? [])
const sourceColumns = ref<string[]>([])
const targetColumns = ref<string[]>([])

function snapshot(): Record<string, unknown> {
  return { source: { ...source }, target: { ...target }, mappings: mappings.value }
}
function syncModel() { emit('update:modelValue', snapshot()) }
async function explore() {
  busy.value = true
  try {
    const [src, tgt] = await Promise.all([
      api.explore(props.projectId, source),
      api.explore(props.projectId, target),
    ])
    sourceColumns.value = src.items.map((item) => item.column_name)
    targetColumns.value = tgt.items.map((item) => item.column_name)
    mappings.value = await api.autoMap(props.projectId, source, target)
    syncModel()
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '同步字段探查失败') }
  finally { busy.value = false }
}
async function save() {
  busy.value = true
  try {
    await api.savePlan({
      project_id: props.projectId, workflow_id: props.workflowId, workflow_version: props.workflowVersion,
      task_id: props.taskId, source: { ...source }, target: { ...target }, mappings: mappings.value,
      transform_config: {}, target_properties: {},
    })
    syncModel(); emit('saved'); ElMessage.success('同步映射已保存')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '同步映射保存失败') }
  finally { busy.value = false }
}
</script>

<template>
  <section class="sync-editor" data-sync-mapping-editor>
    <strong>同步组件表单 · 探查映射</strong>
    <div class="sync-ref-grid">
      <label>源数据源 <input v-model.number="source.datasource_id" type="number" min="1" /></label>
      <label>源 Schema <input v-model="source.schema" /></label>
      <label>源对象 <input v-model="source.object" /></label>
      <label>目标数据源 <input v-model.number="target.datasource_id" type="number" min="1" /></label>
      <label>目标 Schema <input v-model="target.schema" /></label>
      <label>目标对象 <input v-model="target.object" /></label>
    </div>
    <div class="sync-actions"><button :disabled="busy" @click="explore">探查并自动映射</button><button :disabled="busy || !mappings.length" @click="save">保存映射</button></div>
    <p v-if="sourceColumns.length || targetColumns.length" class="sync-meta">源字段 {{ sourceColumns.length }} · 目标字段 {{ targetColumns.length }} · 映射 {{ mappings.length }}</p>
    <table v-if="mappings.length"><thead><tr><th>源字段</th><th>目标字段</th><th>状态</th></tr></thead><tbody><tr v-for="(mapping, index) in mappings" :key="`${mapping.target_column}-${index}`"><td><input v-model="mapping.source_column" @change="syncModel" /></td><td>{{ mapping.target_column }}</td><td>{{ mapping.mapping_status }}</td></tr></tbody></table>
  </section>
</template>

<style scoped>
.sync-editor { display: grid; gap: 10px; padding: 12px; border: 1px solid #d9e2ef; border-radius: 8px; background: #fff; }
.sync-ref-grid { display: grid; grid-template-columns: repeat(3, minmax(120px, 1fr)); gap: 8px; }
.sync-ref-grid label { display: grid; gap: 4px; font-size: 12px; color: #526173; }
input { min-width: 0; padding: 5px 7px; border: 1px solid #c8d3e0; border-radius: 4px; }
.sync-actions { display: flex; gap: 8px; }
button { padding: 6px 10px; border: 0; border-radius: 4px; background: #2463eb; color: #fff; cursor: pointer; }
button:disabled { opacity: .5; cursor: default; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th, td { padding: 5px; border-bottom: 1px solid #e7edf5; text-align: left; }
.sync-meta { margin: 0; color: #64748b; font-size: 12px; }
</style>
