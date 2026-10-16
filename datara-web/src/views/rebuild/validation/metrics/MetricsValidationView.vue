<!--
  I9：统计/质量/血缘报告验证页（RED/原型态）。
  权威范围：plan I9（docs/superpowers/plans/2026-10-14-datara-platform-rebuild.md）
  + docs/increments/I7-I9-前端消费面分析.md §1/§3。
  边界：独立验证页，不进正式菜单（I11 融合）；契约全部经 services/rebuild/metricsApi
  （后端接入前抛 R7_METRICS_NOT_WIRED，UI 统一横幅提示）；不触发增量 GREEN。
  legacy mock 页（IndBoardView/QcReportHubView）布局可参考，但其 mock 数据结构不进本契约。
-->
<template>
  <div class="i9-page">
    <el-alert
      type="warning"
      :closable="false"
      show-icon
      data-testid="i9-red-banner"
      title="I9 RED 骨架（原型态）— rebuild/metrics 后端契约未接入，所有 I/O 返回 R7_METRICS_NOT_WIRED"
    />

    <el-descriptions :column="3" size="small" border class="i9-context">
      <el-descriptions-item label="统计表面">workflow_result_stat / task_instance_data_stat / task_data_stat_segment / task_data_error_sample</el-descriptions-item>
      <el-descriptions-item label="口径透传">unknown（known=false）/ estimated 标记</el-descriptions-item>
      <el-descriptions-item label="契约方法">{{ contractMethodCount }} 项（全部未接线）</el-descriptions-item>
    </el-descriptions>

    <el-row :gutter="12">
      <el-col :span="12">
        <div class="i9-panel">
          <div class="i9-panel-head">
            <span>工作流结果统计</span>
            <el-button size="small" @click="onQueryStats('workflow')">加载</el-button>
          </div>
          <el-table :data="workflowStats" size="small" empty-text="（未接线）">
            <el-table-column prop="workflowId" label="工作流" width="80" />
            <el-table-column prop="runDate" label="日期" width="110" />
            <el-table-column prop="successCount" label="成功" width="70" />
            <el-table-column prop="failureCount" label="失败" width="70" />
            <el-table-column prop="skippedCount" label="跳过" width="70" />
            <el-table-column prop="retryCount" label="重试" width="70" />
          </el-table>
        </div>
      </el-col>
      <el-col :span="12">
        <div class="i9-panel">
          <div class="i9-panel-head">
            <span>实例数据量统计（unknown/estimated 透传）</span>
            <el-button size="small" @click="onQueryStats('instance')">加载</el-button>
          </div>
          <el-table :data="instanceStats" size="small" empty-text="（未接线）">
            <el-table-column prop="instanceId" label="实例" width="80" />
            <el-table-column prop="taskId" label="任务" width="120" />
            <el-table-column prop="rowsIn" label="rowsIn" />
            <el-table-column prop="rowsOut" label="rowsOut" />
            <el-table-column prop="errorRows" label="errorRows" />
          </el-table>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="12">
      <el-col :span="12">
        <div class="i9-panel">
          <div class="i9-panel-head">
            <span>分段统计 + 错误样本</span>
            <el-button size="small" @click="onQueryStats('segment')">加载</el-button>
            <el-button size="small" @click="onQueryStats('error')">样本</el-button>
          </div>
          <el-table :data="segmentStats" size="small" empty-text="（未接线）">
            <el-table-column prop="instanceId" label="实例" width="80" />
            <el-table-column prop="segmentKey" label="分段" />
            <el-table-column prop="rowCount" label="行数" />
          </el-table>
        </div>
      </el-col>
      <el-col :span="12">
        <div class="i9-panel">
          <div class="i9-panel-head">
            <span>质量规则结果链 + 血缘回写</span>
            <el-button size="small" @click="onQueryQuality">质量链</el-button>
            <el-button size="small" @click="onQueryLineage">血缘</el-button>
          </div>
          <el-table :data="qualityLinks" size="small" empty-text="（未接线）">
            <el-table-column prop="ruleName" label="规则" />
            <el-table-column prop="statRef" label="统计引用" width="150" />
            <el-table-column prop="alertSent" label="已告警" width="80" />
          </el-table>
        </div>
      </el-col>
    </el-row>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      data-testid="i9-status-bar"
      :title="statusText"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import {
  R7_CONTRACT_METHODS,
  R7_METRICS_NOT_WIRED,
  createMetricsContract,
  type LineageWritebackEntry,
  type QualityRuleResultLink,
  type TaskDataErrorSampleRow,
  type TaskDataStatSegmentRow,
  type TaskInstanceDataStatRow,
  type TimeWindowQuery,
  type WorkflowResultStatRow,
} from '../../../../services/rebuild/metricsApi'

defineOptions({ name: 'MetricsValidationView' })

const contract = createMetricsContract()
const contractMethodCount = R7_CONTRACT_METHODS.length

/* 时间窗（后端接入前为占位参数） */
const window: TimeWindowQuery = {
  from: '1970-01-01T00:00:00Z',
  to: '2030-01-01T00:00:00Z',
  offset: 0,
  limit: 50,
}

/* 观测面数据（后端接入前恒为空，展示空态） */
const workflowStats = ref<WorkflowResultStatRow[]>([])
const instanceStats = ref<TaskInstanceDataStatRow[]>([])
const segmentStats = ref<(TaskDataStatSegmentRow | TaskDataErrorSampleRow)[]>([])
const qualityLinks = ref<(QualityRuleResultLink | LineageWritebackEntry)[]>([])

/** NOT_WIRED 统一落状态栏语义：提示 + 不中断交互 */
function guard<T>(fn: () => Promise<T>, label: string): Promise<void> {
  statusText.value = `${label}…`
  return fn()
    .then(() => {
      statusText.value = `${label} 完成`
    })
    .catch((err: unknown) => {
      statusText.value =
        err instanceof Error && err.message.startsWith(R7_METRICS_NOT_WIRED)
          ? `${label}：后端未接线（${R7_METRICS_NOT_WIRED.split(':')[0]}）`
          : `${label} 失败：${err instanceof Error ? err.message : String(err)}`
    })
}

const statusText = ref('待操作')

function onQueryStats(which: 'workflow' | 'instance' | 'segment' | 'error') {
  return guard(async () => {
    if (which === 'workflow') workflowStats.value = await contract.queryWorkflowResultStats(window)
    else if (which === 'instance') instanceStats.value = await contract.queryTaskInstanceDataStats(window)
    else if (which === 'segment') segmentStats.value = await contract.queryTaskDataStatSegments(window)
    else segmentStats.value = await contract.queryTaskDataErrorSamples(window)
  }, '加载统计')
}

function onQueryQuality() {
  return guard(async () => {
    qualityLinks.value = await contract.listQualityRuleLinks(window)
  }, '加载质量规则结果链')
}

function onQueryLineage() {
  return guard(async () => {
    qualityLinks.value = await contract.listLineageWritebacks(window, 'all')
  }, '加载血缘回写')
}
</script>

<style scoped>
.i9-page {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.i9-panel {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 8px;
}

.i9-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
}
</style>
