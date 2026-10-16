<!--
  I7：调度运行时验证页（RED/原型态）。
  权威范围：plan I7（docs/superpowers/plans/2026-10-14-datara-platform-rebuild.md）
  + docs/increments/I7-I9-前端消费面分析.md §1/§3。
  边界：独立验证页，不进正式菜单（I11 融合）；契约全部经 services/rebuild/scheduleApi
  （后端接入前抛 R6_SCHEDULER_NOT_WIRED，UI 统一横幅提示）；不触发增量 GREEN。
-->
<template>
  <div class="i7-page">
    <el-alert
      type="warning"
      :closable="false"
      show-icon
      data-testid="i7-red-banner"
      title="I7 RED 骨架（原型态）— rebuild/schedule 后端契约未接入，所有 I/O 返回 R6_SCHEDULER_NOT_WIRED"
    />

    <el-descriptions :column="3" size="small" border class="i7-context">
      <el-descriptions-item label="触发类型面">MANUAL / CRON / DEPENDENCY / EVENT / TRIAL</el-descriptions-item>
      <el-descriptions-item label="观测面">misfire / 并发 / 优先级 / 超时 / 重试 / Master 分派</el-descriptions-item>
      <el-descriptions-item label="契约方法">{{ contractMethodCount }} 项（全部未接线）</el-descriptions-item>
    </el-descriptions>

    <el-row :gutter="12">
      <el-col :span="12">
        <div class="i7-panel">
          <div class="i7-panel-head">
            <span>触发注册</span>
            <el-button size="small" @click="onListTriggers">加载</el-button>
          </div>
          <el-table :data="triggers" size="small" empty-text="（未接线）">
            <el-table-column prop="name" label="名称" />
            <el-table-column prop="kind" label="类型" width="110" />
            <el-table-column prop="nextFireAt" label="Next Fire" width="160" />
            <el-table-column prop="misfirePolicy" label="Misfire" width="110" />
          </el-table>
        </div>
      </el-col>
      <el-col :span="12">
        <div class="i7-panel">
          <div class="i7-panel-head">
            <span>实例队列（并发/优先级/misfire）</span>
            <el-button size="small" @click="onListQueue">加载</el-button>
          </div>
          <el-table :data="queue" size="small" empty-text="（未接线）">
            <el-table-column prop="instanceId" label="实例" width="80" />
            <el-table-column prop="state" label="状态" width="110" />
            <el-table-column prop="priority" label="优先级" width="80" />
            <el-table-column prop="concurrencySlot" label="槽位" width="70" />
          </el-table>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="12">
      <el-col :span="12">
        <div class="i7-panel">
          <div class="i7-panel-head">
            <span>超时/重试事件流（Master 分派 + Logger 事件链）</span>
            <el-button size="small" @click="onListEvents">加载</el-button>
          </div>
          <el-table :data="events" size="small" empty-text="（未接线）">
            <el-table-column prop="seq" label="Seq" width="70" />
            <el-table-column prop="type" label="类型" width="120" />
            <el-table-column prop="attempt" label="Attempt" width="80" />
            <el-table-column prop="occurredAt" label="时间" width="160" />
          </el-table>
        </div>
      </el-col>
      <el-col :span="12">
        <div class="i7-panel">
          <div class="i7-panel-head">
            <span>Alert 记录</span>
            <el-button size="small" @click="onListAlerts">加载</el-button>
          </div>
          <el-table :data="alerts" size="small" empty-text="（未接线）">
            <el-table-column prop="level" label="级别" width="80" />
            <el-table-column prop="channel" label="通道" width="120" />
            <el-table-column prop="createdAt" label="时间" width="160" />
          </el-table>
        </div>
      </el-col>
    </el-row>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      data-testid="i7-status-bar"
      :title="statusText"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import {
  R6_CONTRACT_METHODS,
  R6_SCHEDULER_NOT_WIRED,
  createScheduleContract,
  type ScheduleAlert,
  type ScheduleQueueEntry,
  type ScheduleRuntimeEvent,
  type TriggerRegistration,
} from '../../../../services/rebuild/scheduleApi'

defineOptions({ name: 'ScheduleValidationView' })

const contract = createScheduleContract()
const contractMethodCount = R6_CONTRACT_METHODS.length

/* 观测面数据（后端接入前恒为空，展示空态） */
const triggers = ref<TriggerRegistration[]>([])
const queue = ref<ScheduleQueueEntry[]>([])
const events = ref<ScheduleRuntimeEvent[]>([])
const alerts = ref<ScheduleAlert[]>([])

/** NOT_WIRED 统一落状态栏语义：提示 + 不中断交互 */
function guard<T>(fn: () => Promise<T>, label: string): Promise<void> {
  statusText.value = `${label}…`
  return fn()
    .then(() => {
      statusText.value = `${label} 完成`
    })
    .catch((err: unknown) => {
      statusText.value =
        err instanceof Error && err.message.startsWith(R6_SCHEDULER_NOT_WIRED)
          ? `${label}：后端未接线（${R6_SCHEDULER_NOT_WIRED.split(':')[0]}）`
          : `${label} 失败：${err instanceof Error ? err.message : String(err)}`
    })
}

const statusText = ref('待操作')

function onListTriggers() {
  return guard(async () => {
    triggers.value = await contract.listTriggers()
  }, '加载触发注册')
}

function onListQueue() {
  return guard(async () => {
    queue.value = await contract.listQueue()
  }, '加载实例队列')
}

function onListEvents() {
  return guard(async () => {
    events.value = await contract.listRuntimeEvents(null)
  }, '加载事件流')
}

function onListAlerts() {
  return guard(async () => {
    alerts.value = await contract.listAlerts()
  }, '加载 Alert')
}
</script>

<style scoped>
.i7-page {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.i7-panel {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 8px;
}

.i7-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
}
</style>
