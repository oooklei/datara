<template>
  <main class="sync-page">
    <el-alert :type="bannerType" :closable="false" data-testid="r4-sync-green-banner" :title="bannerTitle" />
    <el-card shadow="never">
      <template #header>① 源/目标与工作流版本</template>
      <el-form inline label-position="top" size="small">
        <el-form-item label="项目 ID"><el-input-number v-model="form.projectId" :min="1" /></el-form-item>
        <el-form-item label="工作流 ID"><el-input-number v-model="form.workflowId" :min="1" /></el-form-item>
        <el-form-item label="工作流版本"><el-input-number v-model="form.workflowVersion" :min="1" /></el-form-item>
        <el-form-item label="任务 ID"><el-input v-model="form.taskId" /></el-form-item>
      </el-form>
      <el-divider content-position="left">源对象</el-divider>
      <el-form inline size="small">
        <el-form-item label="数据源 ID"><el-input-number v-model="source.datasource_id" :min="1" /></el-form-item>
        <el-form-item label="Schema"><el-input v-model="source.schema" /></el-form-item>
        <el-form-item label="表"><el-input v-model="source.object" /></el-form-item>
        <el-form-item><el-button data-testid="sync-explore-source" @click="exploreSource">探查源字段</el-button></el-form-item>
      </el-form>
      <el-divider content-position="left">目标对象</el-divider>
      <el-form inline size="small">
        <el-form-item label="数据源 ID"><el-input-number v-model="target.datasource_id" :min="1" /></el-form-item>
        <el-form-item label="Schema"><el-input v-model="target.schema" /></el-form-item>
        <el-form-item label="表"><el-input v-model="target.object" /></el-form-item>
        <el-form-item><el-button data-testid="sync-explore-target" @click="exploreTarget">探查目标字段</el-button></el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <span>② 映射</span>
        <el-button class="header-action" type="primary" size="small" :disabled="!sourceColumns.length || !targetColumns.length" data-testid="sync-auto-map" @click="autoMap">自动映射</el-button>
      </template>
      <el-row :gutter="16">
        <el-col :span="12"><strong>源字段</strong><el-table :data="sourceColumns" size="small" max-height="180" empty-text="尚未探查">
          <el-table-column prop="column_name" label="字段" /><el-table-column prop="data_type" label="类型" /><el-table-column prop="is_nullable" label="可空" />
        </el-table></el-col>
        <el-col :span="12"><strong>目标字段</strong><el-table :data="targetColumns" size="small" max-height="180" empty-text="尚未探查">
          <el-table-column prop="column_name" label="字段" /><el-table-column prop="data_type" label="类型" /><el-table-column prop="is_nullable" label="可空" />
        </el-table></el-col>
      </el-row>
      <el-table :data="mappings" size="small" class="mapping-table" empty-text="先探查两侧字段并生成映射">
        <el-table-column label="源字段"><template #default="{ row }"><el-input v-model="row.source_column" @change="markAdjusted(row)" /></template></el-table-column>
        <el-table-column label="目标字段"><template #default="{ row }"><el-input v-model="row.target_column" @change="markAdjusted(row)" /></template></el-table-column>
        <el-table-column prop="source_type" label="源类型" width="120" />
        <el-table-column prop="target_type" label="目标类型" width="120" />
        <el-table-column label="转换表达式" min-width="220"><template #default="{ row }"><el-input v-model="row.transform_expression" placeholder="例如 UPPER(customer_name)" @change="markAdjusted(row)" /></template></el-table-column>
        <el-table-column label="映射状态" width="135"><template #default="{ row }"><el-select v-model="row.mapping_status" size="small"><el-option label="自动" value="AUTO" /><el-option label="手动调整" value="ADJUSTED" /><el-option label="未匹配" value="UNMATCHED" /></el-select></template></el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never">
      <template #header>③ 转换、目标属性与版本计划</template>
      <el-form label-position="top" size="small">
        <el-form-item label="过滤条件"><el-input v-model="filterCondition" placeholder="可留空；例如 updated_at >= '2026-01-01'" /></el-form-item>
        <el-row :gutter="12">
          <el-col :span="6"><el-form-item label="分区字段"><el-input v-model="partitionField" /></el-form-item></el-col>
          <el-col :span="6"><el-form-item label="增量字段"><el-input v-model="incrementalField" /></el-form-item></el-col>
          <el-col :span="6"><el-form-item label="主键（逗号分隔）"><el-input v-model="primaryKeyText" /></el-form-item></el-col>
          <el-col :span="6"><el-form-item label="冲突策略"><el-select v-model="conflictStrategy"><el-option v-for="item in conflictStrategies" :key="item" :label="item" :value="item" /></el-select></el-form-item></el-col>
          <el-col :span="6"><el-form-item label="批大小（1–10000）"><el-input-number v-model="batchSize" :min="1" :max="10000" /></el-form-item></el-col>
          <el-col :span="6"><el-form-item label="并发度（1–32）"><el-input-number v-model="concurrency" :min="1" :max="32" /></el-form-item></el-col>
        </el-row>
      </el-form>
      <div class="actions">
        <el-button type="primary" data-testid="sync-save-plan" :disabled="!mappings.length" @click="savePlan">保存映射快照</el-button>
        <el-button data-testid="sync-list-plans" @click="listPlans">读取该版本计划</el-button>
        <el-button data-testid="sync-capabilities" @click="loadCapabilities">读取能力</el-button>
      </div>
      <el-descriptions v-if="saved" :column="3" border size="small" class="result">
        <el-descriptions-item label="保存结果">{{ saved.saved ? '成功' : '未保存' }}</el-descriptions-item>
        <el-descriptions-item label="工作流版本">{{ saved.workflow_version }}</el-descriptions-item>
        <el-descriptions-item label="任务 ID">{{ saved.task_id }}</el-descriptions-item>
      </el-descriptions>
      <el-table v-if="plans.length" :data="plans" size="small" class="result" data-testid="sync-saved-plans">
        <el-table-column prop="task_id" label="任务 ID" /><el-table-column prop="workflow_version" label="版本" />
        <el-table-column label="源 → 目标"><template #default="{ row }">{{ objectLabel(row.source) }} → {{ objectLabel(row.target) }}</template></el-table-column>
        <el-table-column label="映射数"><template #default="{ row }">{{ row.mappings.length }}</template></el-table-column>
      </el-table>
      <el-tag v-if="capabilities" class="result" type="info">表单字段 {{ capabilities.form_fields.length }} 项；映射字段 {{ capabilities.mapping_fields.length }} 项</el-tag>
    </el-card>
    <el-alert :type="error ? 'error' : 'info'" :closable="false" data-testid="sync-status" :title="status" />
    <el-alert v-if="error" type="warning" :closable="false" title="如后端返回字段诊断，详情如下" :description="JSON.stringify(error.diagnostics)" />
  </main>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { createSyncComponentContract, SyncApiError, type SyncCapabilities, type SyncColumn, type SyncMapping, type SyncObjectRef, type SyncPlan, type SyncPlanInput } from '../../../../services/rebuild/syncComponentApi'
import { bannerAlertType, bannerTitleFor } from '../../../../services/rebuild/bannerStatus'

defineOptions({ name: 'SyncFormValidationView' })

/* 横幅状态词表（FE-01 单一事实源）：GREEN 已接线；SyncContract 5 方法（getCapabilities/explore/autoMap/savePlan/listPlans） */
const bannerTitle = bannerTitleFor(
  { code: 'R4', contractName: 'sync', methodCount: 5 },
  'GREEN',
)
const bannerType = bannerAlertType('GREEN')

const api = createSyncComponentContract()
const form = reactive({ projectId: 1, workflowId: 1, workflowVersion: 1, taskId: 'sync-task' })
const source = reactive<SyncObjectRef>({ datasource_id: 1, schema: '', object: '' })
const target = reactive<SyncObjectRef>({ datasource_id: 1, schema: '', object: '' })
const sourceColumns = ref<SyncColumn[]>([])
const targetColumns = ref<SyncColumn[]>([])
const mappings = ref<SyncMapping[]>([])
const filterCondition = ref('')
const partitionField = ref('')
const incrementalField = ref('')
const primaryKeyText = ref('')
const conflictStrategies = ['insert', 'ignore', 'update', 'upsert'] as const
const conflictStrategy = ref<(typeof conflictStrategies)[number]>('insert')
const batchSize = ref(1000)
const concurrency = ref(1)
const saved = ref<{ saved: true; workflow_version: number; task_id: string } | null>(null)
const plans = ref<SyncPlan[]>([])
const capabilities = ref<SyncCapabilities | null>(null)
const status = ref('待操作')
const error = ref<SyncApiError | null>(null)

async function run(label: string, action: () => Promise<void>) {
  status.value = `${label}中…`
  error.value = null
  try {
    await action()
    status.value = `${label}成功`
  } catch (cause) {
    error.value = cause instanceof SyncApiError ? cause : null
    status.value = `${label}失败：${cause instanceof Error ? cause.message : String(cause)}`
  }
}

async function exploreSource() {
  await run('源字段探查', async () => { sourceColumns.value = (await api.explore(form.projectId, { ...source })).items })
}

async function exploreTarget() {
  await run('目标字段探查', async () => { targetColumns.value = (await api.explore(form.projectId, { ...target })).items })
}

async function autoMap() {
  await run('自动映射', async () => { mappings.value = await api.autoMap(form.projectId, { ...source }, { ...target }) })
}

function markAdjusted(row: SyncMapping) {
  row.mapping_status = row.source_column && row.target_column ? 'ADJUSTED' : 'UNMATCHED'
}

function makePlan(): SyncPlanInput {
  return {
    project_id: form.projectId,
    workflow_id: form.workflowId,
    workflow_version: form.workflowVersion,
    task_id: form.taskId,
    source: { ...source },
    target: { ...target },
    mappings: mappings.value,
    transform_config: {
      transform_expression: Object.fromEntries(
        mappings.value
          .filter((mapping) => mapping.target_column.trim() && mapping.transform_expression.trim())
          .map((mapping) => [mapping.target_column.trim(), mapping.transform_expression.trim()]),
      ),
      filter_condition: filterCondition.value,
    },
    target_properties: {
      partition_incremental: { partition_field: partitionField.value, incremental_field: incrementalField.value },
      primary_key_conflict: { primary_key: primaryKeyText.value.split(',').map((part) => part.trim()).filter(Boolean), conflict_strategy: conflictStrategy.value },
      batch_concurrency: { batch_size: batchSize.value, concurrency: concurrency.value },
    },
  }
}

async function savePlan() {
  await run('保存映射快照', async () => { saved.value = await api.savePlan(makePlan()) })
}

async function listPlans() {
  await run('读取版本计划', async () => { plans.value = await api.listPlans(form.projectId, form.workflowId, form.workflowVersion) })
}

async function loadCapabilities() {
  await run('读取能力', async () => { capabilities.value = await api.getCapabilities() })
}

function objectLabel(refValue: SyncObjectRef): string {
  return `${refValue.datasource_id}:${refValue.schema}.${refValue.object}`
}
</script>

<style scoped>
.sync-page { padding: 12px; display: flex; flex-direction: column; gap: 12px; }
.header-action { float: right; }
.mapping-table, .result { margin-top: 12px; }
.actions { display: flex; gap: 8px; }
</style>
