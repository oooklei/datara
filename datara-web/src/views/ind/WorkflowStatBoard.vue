<script setup lang="ts">
/**
 * 统计 15 项字段展示层骨架（FE-12 / B6-b 批次，可先行骨架）。
 * 字段面对齐设计正本 §9「统一工作流统计表 workflow_result_stat 至少记录」15 字段清单：
 *   input/output/success/failed/skipped/rejected/filtered/duplicate/inserted/updated/
 *   deleted/read_bytes/write_bytes/batch_count/data_quality_status（+extra_metrics 扩展位）。
 * 覆盖状态（诚实标注，不伪造通道）：
 *  - R7 契约已覆盖（metricsApi.queryWorkflowResultStats，GREEN）：successCount/failureCount/
 *    skippedCount + retryCount（契约扩展项，§9 十五项无对应）；
 *  - 待后端契约扩展：其余 12 项 + extra_metrics——占位展示，不造本地假数据、不做计数推导
 *    （adapterKit 语义加工负面清单）。
 * 嵌入方式：独立组件，可在指标看板 /ind/board 中嵌入；回写链路 1.9 实测后可见真实数据（大盘 #9）。
 */
import { reactive, ref } from 'vue'
import {
  createMetricsContract,
  type TimeWindowQuery,
  type WorkflowResultStatRow,
} from '../../services/rebuild/metricsApi'

defineOptions({ name: 'WorkflowStatBoard' })

const contract = createMetricsContract()

/* §9 十五项字段清单（设计正本原文顺序）+ camelCase 映射 + R7 契约覆盖状态 */
interface StatField {
  /** §9 原文 snake_case 字段名 */
  snake: string
  /** FE camelCase 字段名（metricsApi 词形） */
  camel: string
  /** R7 契约覆盖状态 */
  covered: 'r7' | 'pending'
  /** R7 契约覆盖时对应 WorkflowResultStatRow 的取值键（covered='r7' 时有效） */
  valueKey?: keyof WorkflowResultStatRow
}

const STAT_FIELDS: StatField[] = [
  { snake: 'input_record_count', camel: 'inputRecordCount', covered: 'pending' },
  { snake: 'output_record_count', camel: 'outputRecordCount', covered: 'pending' },
  { snake: 'success_record_count', camel: 'successCount', covered: 'r7', valueKey: 'successCount' },
  { snake: 'failed_record_count', camel: 'failureCount', covered: 'r7', valueKey: 'failureCount' },
  { snake: 'skipped_record_count', camel: 'skippedCount', covered: 'r7', valueKey: 'skippedCount' },
  { snake: 'rejected_record_count', camel: 'rejectedCount', covered: 'pending' },
  { snake: 'filtered_record_count', camel: 'filteredCount', covered: 'pending' },
  { snake: 'duplicate_record_count', camel: 'duplicateCount', covered: 'pending' },
  { snake: 'inserted_record_count', camel: 'insertedCount', covered: 'pending' },
  { snake: 'updated_record_count', camel: 'updatedCount', covered: 'pending' },
  { snake: 'deleted_record_count', camel: 'deletedCount', covered: 'pending' },
  { snake: 'read_bytes', camel: 'readBytes', covered: 'pending' },
  { snake: 'write_bytes', camel: 'writeBytes', covered: 'pending' },
  { snake: 'batch_count', camel: 'batchCount', covered: 'pending' },
  { snake: 'data_quality_status', camel: 'dataQualityStatus', covered: 'pending' },
  /* extra_metrics：§9 第 16 项（JSON 扩展位），R7 契约未覆盖 */
  { snake: 'extra_metrics', camel: 'extraMetrics', covered: 'pending' },
]

const R7_COVERED_COUNT = STAT_FIELDS.filter((f) => f.covered === 'r7').length

/* ---------- 时间窗（TimeWindowQuery 四字段，契约原样透传不加工） ---------- */
const queryWindow = reactive<TimeWindowQuery>({
  from: '1970-01-01T00:00:00Z',
  to: '2030-01-01T00:00:00Z',
  offset: 0,
  limit: 50,
})

const rows = ref<WorkflowResultStatRow[]>([])
const statusText = ref('待操作')

/** GREEN 契约请求；失败统一落状态栏（不中断交互） */
function guard<T>(fn: () => Promise<T>, label: string): Promise<void> {
  statusText.value = `${label}…`
  return fn()
    .then(() => {
      statusText.value = `${label} 完成`
    })
    .catch((err: unknown) => {
      statusText.value = `${label} 失败：${err instanceof Error ? err.message : String(err)}`
    })
}

function onLoad() {
  return guard(async () => {
    rows.value = await contract.queryWorkflowResultStats(1, queryWindow)
  }, '加载工作流结果统计')
}

/**
 * 字段对齐表值列：仅当主表恰为 1 行时取该行字段值作示例（不做计数推导，多行/空显示占位）。
 * R7 未覆盖字段恒为占位「待契约扩展」。
 */
function fieldValue(f: StatField): string {
  if (f.covered !== 'r7' || !f.valueKey) return '待契约扩展'
  const row = rows.value[0]
  if (!row || rows.value.length !== 1) return rows.value.length > 1 ? '多行见主表' : '暂无数据'
  const v = row[f.valueKey]
  return v == null ? '—' : String(v)
}
</script>

<template>
  <div class="wsb-root" data-testid="workflow-stat-board">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      data-testid="wsb-banner"
      :title="`统计字段展示层（设计 §9 workflow_result_stat ${STAT_FIELDS.length} 项字段面对齐）— R7 契约已覆盖 ${R7_COVERED_COUNT} 项（真实数据）；其余待后端契约扩展（占位，不伪造通道）`"
    />

    <div class="wsb-filter">
      <el-form inline size="small">
        <el-form-item label="From"><el-input v-model="queryWindow.from" data-testid="wsb-from" style="width: 180px" /></el-form-item>
        <el-form-item label="To"><el-input v-model="queryWindow.to" data-testid="wsb-to" style="width: 180px" /></el-form-item>
        <el-form-item label="Offset"><el-input v-model.number="queryWindow.offset" data-testid="wsb-offset" style="width: 80px" /></el-form-item>
        <el-form-item label="Limit"><el-input v-model.number="queryWindow.limit" data-testid="wsb-limit" style="width: 80px" /></el-form-item>
        <el-form-item>
          <el-button size="small" type="primary" data-testid="wsb-load" @click="onLoad">加载</el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- 面板 1：工作流结果统计（R7 契约真实数据，按工作流 × 日期行） -->
    <div class="wsb-panel">
      <div class="wsb-panel-head"><span>工作流结果统计（R7 契约：success/failure/skipped/retry）</span></div>
      <el-table :data="rows" size="small" empty-text="（暂无数据）" data-testid="wsb-main-table">
        <el-table-column prop="workflowId" label="工作流" width="90" />
        <el-table-column prop="runDate" label="日期" width="120" />
        <el-table-column prop="successCount" label="成功" width="80" />
        <el-table-column prop="failureCount" label="失败" width="80" />
        <el-table-column prop="skippedCount" label="跳过" width="80" />
        <el-table-column prop="retryCount" label="重试（契约扩展）" width="130" />
      </el-table>
    </div>

    <!-- 面板 2：§9 十五项字段对齐表（展示层 vs 统计契约字段核对） -->
    <div class="wsb-panel">
      <div class="wsb-panel-head">
        <span>§9 统计字段对齐表（{{ STAT_FIELDS.length }} 项）</span>
      </div>
      <el-table :data="STAT_FIELDS" size="small" data-testid="wsb-align-table">
        <el-table-column prop="snake" label="§9 字段（snake）" width="220" />
        <el-table-column prop="camel" label="FE 字段（camel）" width="200" />
        <el-table-column label="契约覆盖" width="150">
          <template #default="{ row }">
            <span :class="row.covered === 'r7' ? 'wsb-tag--r7' : 'wsb-tag--pending'">
              {{ row.covered === 'r7' ? 'R7 已覆盖（真实）' : '待后端契约扩展' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="当前值">
          <template #default="{ row }">{{ fieldValue(row) }}</template>
        </el-table-column>
      </el-table>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      data-testid="wsb-status-bar"
      :title="statusText"
    />
  </div>
</template>

<style scoped>
.wsb-root {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.wsb-filter {
  margin: 0;
}
.wsb-panel {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 8px;
}
.wsb-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
}
.wsb-tag--r7 {
  color: #16a34a;
}
.wsb-tag--pending {
  color: var(--el-text-color-secondary);
}
</style>
