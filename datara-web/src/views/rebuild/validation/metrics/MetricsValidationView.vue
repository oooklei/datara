<!--
  I9：统计/质量/血缘报告验证页（RED/原型态）。
  权威范围：plan I9（docs/superpowers/plans/2026-10-14-datara-platform-rebuild.md）
  + docs/increments/I7-I9-前端消费面分析.md §1/§3。
  边界：独立验证页，不进正式菜单（I11 融合）；契约全部经 services/rebuild/metricsApi
  （后端接入前抛 I9_METRICS_NOT_WIRED，UI 统一横幅提示）；不触发增量 GREEN。
  legacy mock 页（IndBoardView/QcReportHubView）布局可参考，但其 mock 数据结构不进本契约。
-->
<template>
  <div class="i9-page">
    <el-alert
      type="warning"
      :closable="false"
      show-icon
      data-testid="i9-red-banner"
      title="I9 RED 骨架（原型态）— rebuild/metrics 后端契约未接入，所有 I/O 返回 I9_METRICS_NOT_WIRED"
    />

    <el-descriptions :column="3" size="small" border class="i9-context">
      <el-descriptions-item label="统计表面">workflow_result_stat / task_instance_data_stat / task_data_stat_segment / task_data_error_sample</el-descriptions-item>
      <el-descriptions-item label="口径透传">unknown（known=false）/ estimated 标记</el-descriptions-item>
      <el-descriptions-item label="契约方法">{{ contractMethodCount }} 项（全部未接线）</el-descriptions-item>
    </el-descriptions>

    <!-- R7 深化：时间窗筛选（四表查询共用，真实可编辑） -->
    <div class="i9-panel">
      <div class="i9-panel-head"><span>时间窗筛选（四表 + 质量链/血缘共用）</span></div>
      <el-form inline size="small" class="i9-filter">
        <el-form-item label="From"><el-input v-model="queryWindow.from" style="width: 180px" /></el-form-item>
        <el-form-item label="To"><el-input v-model="queryWindow.to" style="width: 180px" /></el-form-item>
        <el-form-item label="Offset"><el-input v-model.number="queryWindow.offset" style="width: 80px" /></el-form-item>
        <el-form-item label="Limit"><el-input v-model.number="queryWindow.limit" style="width: 80px" /></el-form-item>
      </el-form>
    </div>

    <el-row :gutter="12">
      <el-col :span="12">
        <div class="i9-panel">
          <div class="i9-panel-head">
            <span>工作流结果统计（成功/失败/跳过筛选）</span>
            <el-button size="small" @click="onQueryStats('workflow')">加载</el-button>
          </div>
          <el-table :data="workflowStats" size="small" empty-text="（未接线）" data-testid="i9-workflow-stats">
            <el-table-column prop="workflowId" label="工作流" width="80" />
            <el-table-column prop="runDate" label="日期" width="110" />
            <el-table-column prop="successCount" label="成功" width="70" :filters="[{ text: '成功>0', value: 'success' }, { text: '失败>0', value: 'failure' }, { text: '跳过>0', value: 'skipped' }]" :filter-method="filterWorkflowRow" />
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
            <el-table-column prop="rowsIn" label="rowsIn" :formatter="metricFormatter" />
            <el-table-column prop="rowsOut" label="rowsOut" :formatter="metricFormatter" />
            <el-table-column prop="errorRows" label="errorRows" :formatter="metricFormatter" />
            <el-table-column label="实例" width="90">
              <template #default="{ row }">
                <el-link type="primary" :underline="false" @click="goInstance(row.instanceId)">运行实例</el-link>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="12">
      <el-col :span="12">
        <div class="i9-panel">
          <div class="i9-panel-head">
            <span>分段统计</span>
            <el-button size="small" @click="onQueryStats('segment')">加载</el-button>
          </div>
          <el-table :data="segmentStats" size="small" empty-text="（未接线）">
            <el-table-column prop="instanceId" label="实例" width="80" />
            <el-table-column prop="segmentKey" label="分段" />
            <el-table-column prop="rowCount" label="行数" :formatter="metricFormatter" />
          </el-table>
        </div>
      </el-col>
      <el-col :span="12">
        <div class="i9-panel">
          <div class="i9-panel-head">
            <span>错误样本（可跳转实例）</span>
            <el-button size="small" @click="onQueryStats('error')">样本</el-button>
          </div>
          <el-table :data="errorSamples" size="small" empty-text="（未接线）" data-testid="i9-error-samples">
            <el-table-column prop="instanceId" label="实例" width="80" />
            <el-table-column prop="taskId" label="任务" width="110" />
            <el-table-column prop="errorType" label="错误类型" width="120" />
            <el-table-column prop="sampleData" label="样本" show-overflow-tooltip />
            <el-table-column label="实例" width="90">
              <template #default="{ row }">
                <el-link type="primary" :underline="false" @click="goInstance(row.instanceId)">运行实例</el-link>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="12">
      <el-col :span="24">
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
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  I9_CONTRACT_METHODS,
  I9_METRICS_NOT_WIRED,
  createMetricsContract,
  type LineageWritebackEntry,
  type MetricValue,
  type QualityRuleResultLink,
  type TaskDataErrorSampleRow,
  type TaskDataStatSegmentRow,
  type TaskInstanceDataStatRow,
  type TimeWindowQuery,
  type WorkflowResultStatRow,
} from '../../../../services/rebuild/metricsApi'

defineOptions({ name: 'MetricsValidationView' })

const router = useRouter()
const contract = createMetricsContract()
const contractMethodCount = I9_CONTRACT_METHODS.length

/* 时间窗筛选（R7 深化：真实可编辑，四表 + 质量链/血缘共用） */
const queryWindow = reactive<TimeWindowQuery>({
  from: '1970-01-01T00:00:00Z',
  to: '2030-01-01T00:00:00Z',
  offset: 0,
  limit: 50,
})

/* 观测面数据（后端接入前恒为空，展示空态） */
const workflowStats = ref<WorkflowResultStatRow[]>([])
const instanceStats = ref<TaskInstanceDataStatRow[]>([])
const segmentStats = ref<TaskDataStatSegmentRow[]>([])
const errorSamples = ref<TaskDataErrorSampleRow[]>([])
const qualityLinks = ref<(QualityRuleResultLink | LineageWritebackEntry)[]>([])

/** MetricValue 渲染：known=false 标 unknown、estimated=true 标估算（A7 Step 1 口径透传） */
function metricFormatter(row: Record<string, unknown>, _column: unknown, cellValue: unknown): string {
  const metric = cellValue as MetricValue
  if (!metric || typeof metric !== 'object') return String(cellValue ?? '—')
  const flags = [!metric.known ? 'unknown' : '', metric.estimated ? 'estimated' : ''].filter(Boolean).join('/')
  return flags ? `${metric.value}（${flags}）` : String(metric.value)
}

/** 成功/失败/跳过记录筛选（客户 #9 监控语义） */
function filterWorkflowRow(value: string, row: WorkflowResultStatRow): boolean {
  if (value === 'success') return row.successCount > 0
  if (value === 'failure') return row.failureCount > 0
  if (value === 'skipped') return row.skippedCount > 0
  return true
}

/** 实例/错误样本 → 正式运行实例页跳转（/dag/instances 已有路由） */
function goInstance(instanceId: number) {
  void router.push({ path: '/dag/instances', query: { instanceId: String(instanceId) } })
}

/** NOT_WIRED 统一落状态栏语义：提示 + 不中断交互 */
function guard<T>(fn: () => Promise<T>, label: string): Promise<void> {
  statusText.value = `${label}…`
  return fn()
    .then(() => {
      statusText.value = `${label} 完成`
    })
    .catch((err: unknown) => {
      statusText.value =
        err instanceof Error && err.message.startsWith(I9_METRICS_NOT_WIRED)
          ? `${label}：后端未接线（${I9_METRICS_NOT_WIRED.split(':')[0]}）`
          : `${label} 失败：${err instanceof Error ? err.message : String(err)}`
    })
}

const statusText = ref('待操作')

function onQueryStats(which: 'workflow' | 'instance' | 'segment' | 'error') {
  return guard(async () => {
    if (which === 'workflow') workflowStats.value = await contract.queryWorkflowResultStats(queryWindow)
    else if (which === 'instance') instanceStats.value = await contract.queryTaskInstanceDataStats(queryWindow)
    else if (which === 'segment') segmentStats.value = await contract.queryTaskDataStatSegments(queryWindow)
    else errorSamples.value = await contract.queryTaskDataErrorSamples(queryWindow)
  }, '加载统计')
}

function onQueryQuality() {
  return guard(async () => {
    qualityLinks.value = await contract.listQualityRuleLinks(queryWindow)
  }, '加载质量规则结果链')
}

function onQueryLineage() {
  return guard(async () => {
    qualityLinks.value = await contract.listLineageWritebacks(queryWindow, 'all')
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

.i9-filter {
  margin-bottom: 0;
}
</style>
