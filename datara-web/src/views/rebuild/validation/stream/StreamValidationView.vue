<!--
  I8：流处理观摩/运行时验证页（GREEN 已接线，FE-01 修订 2026-10-19）。
  权威范围：plan I8（docs/superpowers/plans/2026-10-14-datara-platform-rebuild.md，R8 承接）
  + docs/increments/I7-I9-前端消费面分析.md §1/§3
  + 权威设计 §8.4 观摩查询接口结构基线（f475c76）。
  边界：独立验证页，不进正式菜单（I11 融合）；契约全部经 services/rebuild/streamApi
  （P1 冻结词形 I8_CONTRACT_METHODS，6 方法接线，包络 {code,msg,data}）；
  横幅状态词表见 services/rebuild/bannerStatus.ts。
-->
<template>
  <div class="i8-page">
    <el-alert
      :type="bannerType"
      :closable="false"
      show-icon
      data-testid="i8-green-banner"
      :title="bannerTitle"
    />

    <el-descriptions :column="3" size="small" border class="i8-context">
      <el-descriptions-item label="观摩结构（§8.4）">生产速率 / 消费速率 / 积压 / 偏移 / 窗口结果 / 成功失败跳过 / 错误样本</el-descriptions-item>
      <el-descriptions-item label="运行时面">job / attempt / checkpoint / metric + 故障恢复与漂移注入事件</el-descriptions-item>
      <el-descriptions-item label="契约方法">{{ contractMethodCount }} 项（已接线）</el-descriptions-item>
    </el-descriptions>

    <el-row :gutter="12">
      <el-col :span="12">
        <div class="i8-panel">
          <div class="i8-panel-head">
            <span>流作业与尝试（长驻进程面）</span>
            <el-button size="small" @click="onQueryRuntime('jobs')">作业</el-button>
            <el-button size="small" @click="onQueryRuntime('attempts')">尝试</el-button>
          </div>
          <el-table :data="runtimeRows" size="small" empty-text="暂无流作业">
            <el-table-column prop="jobId" label="作业" width="120" />
            <el-table-column prop="kind" label="角色" width="90" />
            <el-table-column prop="state" label="状态" width="90" />
            <el-table-column prop="startedAt" label="开始" />
          </el-table>
        </div>
      </el-col>
      <el-col :span="12">
        <div class="i8-panel">
          <div class="i8-panel-head">
            <span>位点/检查点 + 指标序列（恢复面）</span>
            <el-button size="small" @click="onQueryCheckpoints">位点</el-button>
            <el-button size="small" @click="onQueryMetrics">指标</el-button>
          </div>
          <el-table :data="metricRows" size="small" empty-text="暂无位点或指标">
            <el-table-column prop="key" label="作业/分区" width="130" />
            <el-table-column prop="name" label="指标/位点" width="110" />
            <el-table-column prop="value" label="值" />
            <el-table-column prop="at" label="时间" width="150" />
          </el-table>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="12">
      <el-col :span="12">
        <div class="i8-panel">
          <div class="i8-panel-head">
            <span>观摩查询（§8.4 结构）</span>
            <el-button size="small" @click="onQueryObservation">观摩</el-button>
          </div>
          <el-table :data="observationRows" size="small" empty-text="暂无观摩数据">
            <el-table-column prop="item" label="观测项" width="140" />
            <el-table-column prop="value" label="值" />
          </el-table>
        </div>
      </el-col>
      <el-col :span="12">
        <div class="i8-panel">
          <div class="i8-panel-head">
            <span>故障恢复 / 漂移注入事件</span>
            <el-button size="small" @click="onQueryRecovery">事件</el-button>
          </div>
          <el-table :data="recoveryRows" size="small" empty-text="暂无恢复事件">
            <el-table-column prop="jobId" label="作业" width="120" />
            <el-table-column prop="kind" label="类型" width="110" />
            <el-table-column prop="detail" label="详情" />
            <el-table-column prop="occurredAt" label="时间" width="150" />
          </el-table>
        </div>
      </el-col>
    </el-row>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      data-testid="i8-status-bar"
      :title="statusText"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import {
  I8_CONTRACT_METHODS,
  I8_STREAM_NOT_WIRED,
  createStreamContract,
  type StreamAttemptRow,
  type StreamJobRow,
  type StreamRecoveryEventRow,
  type TimeWindowQuery,
} from '../../../../services/rebuild/streamApi'
import { bannerAlertType, bannerTitleFor } from '../../../../services/rebuild/bannerStatus'

defineOptions({ name: 'StreamValidationView' })

const contract = createStreamContract()
const contractMethodCount = I8_CONTRACT_METHODS.length

/* 横幅状态词表（FE-01 单一事实源）：GREEN 已接线 */
const bannerTitle = bannerTitleFor(
  { code: 'I8', contractName: 'stream', methodCount: contractMethodCount },
  'GREEN',
)
const bannerType = bannerAlertType('GREEN')

/* 最近 24 小时的观摩时间窗。 */
const now = new Date()
const dayAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000)
const window: TimeWindowQuery = {
  from: dayAgo.toISOString(),
  to: now.toISOString(),
  offset: 0,
  limit: 50,
}

/* 观测面数据。 */
const runtimeRows = ref<(StreamJobRow | StreamAttemptRow | Record<string, unknown>)[]>([])
const metricRows = ref<{ key: string; name: string; value: string; at: string }[]>([])
const observationRows = ref<{ item: string; value: string }[]>([])
const recoveryRows = ref<(StreamRecoveryEventRow | Record<string, unknown>)[]>([])

/** NOT_WIRED 统一落状态栏语义：提示 + 不中断交互 */
function guard<T>(fn: () => Promise<T>, label: string): Promise<void> {
  statusText.value = `${label}…`
  return fn()
    .then(() => {
      statusText.value = `${label} 完成`
    })
    .catch((err: unknown) => {
      statusText.value =
        err instanceof Error && err.message.startsWith(I8_STREAM_NOT_WIRED)
          ? `${label}：后端未接线（${I8_STREAM_NOT_WIRED.split(':')[0]}）`
          : `${label} 失败：${err instanceof Error ? err.message : String(err)}`
    })
}

const statusText = ref('待操作')

function onQueryRuntime(which: 'jobs' | 'attempts') {
  return guard(async () => {
    if (which === 'jobs') runtimeRows.value = await contract.listStreamJobs(window)
    else runtimeRows.value = await contract.listStreamAttempts(window)
  }, '加载流作业运行时')
}

function onQueryCheckpoints() {
  return guard(async () => {
    const rows = await contract.listStreamCheckpoints(window)
    metricRows.value = rows.map((row) => ({
      key: `${row.jobId}/${row.partition}`,
      name: 'checkpoint',
      value: `committed=${row.committedOffset.value} current=${row.currentOffset.value}`,
      at: row.checkpointedAt,
    }))
  }, '加载位点/检查点')
}

function onQueryMetrics() {
  return guard(async () => {
    const rows = await contract.listStreamMetrics(window)
    metricRows.value = rows.map((row) => ({
      key: row.jobId,
      name: row.metric,
      value: JSON.stringify(row.value),
      at: row.capturedAt,
    }))
  }, '加载流指标序列')
}

function onQueryObservation() {
  return guard(async () => {
    const obs = await contract.queryStreamObservation(window)
    // §8.4 结构展开为观测项行（速率/积压/偏移/窗口/计数/样本计数概览）
    observationRows.value = [
      { item: '生产速率', value: JSON.stringify(obs.produceRate) },
      { item: '消费速率', value: JSON.stringify(obs.consumeRate) },
      { item: '处理速率', value: JSON.stringify(obs.processRate) },
      { item: '输入数', value: JSON.stringify(obs.inputCount) },
      { item: '输出数', value: JSON.stringify(obs.outputCount) },
      { item: '成功数', value: JSON.stringify(obs.counters.success) },
      { item: '失败数', value: JSON.stringify(obs.counters.failure) },
      { item: '跳过数', value: JSON.stringify(obs.counters.skipped) },
      { item: '重复数', value: JSON.stringify(obs.duplicateCount) },
      { item: '积压量', value: JSON.stringify(obs.lag) },
      { item: '偏移量', value: JSON.stringify(obs.offset.current) },
      { item: '窗口结果', value: `${obs.windowResults.length} 项` },
      { item: '错误样本', value: JSON.stringify(obs.errorSamples) },
    ]
  }, '加载观摩查询')
}

function onQueryRecovery() {
  return guard(async () => {
    recoveryRows.value = await contract.listStreamRecoveryEvents(window)
  }, '加载故障恢复事件')
}
</script>

<style scoped>
.i8-page {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.i8-panel {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 8px;
}

.i8-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
}
</style>
