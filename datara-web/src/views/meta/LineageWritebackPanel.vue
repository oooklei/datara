<script setup lang="ts">
/**
 * LineageWriteback 消费面 UI 骨架（FE-12 / B6-b 批次，可先行骨架）。
 * 承接 services/rebuild/metricsApi.listLineageWritebacks（GREEN 真实通道，P1 冻结词形）：
 * 回写数据（执行器写入 lineage_writeback 表）在本面板渲染，供血缘分析页 /meta/lineage 消费。
 * 边界：回写链路「统计由实际执行器写入」1.9 实测未完成（门 6 解阻事件，大盘 #9）——
 * 本面板为展示层消费骨架，真实数据可见性待 1.9 实测；不伪造回写记录、不造本地假数据。
 * 嵌入方式：独立组件，可在 LineageView（/meta/lineage）中按页签/面板嵌入。
 */
import { reactive, ref } from 'vue'
import {
  createMetricsContract,
  type LineageWritebackEntry,
  type TimeWindowQuery,
} from '../../services/rebuild/metricsApi'

defineOptions({ name: 'LineageWritebackPanel' })

const contract = createMetricsContract()

/* ---------- 时间窗 + kind 筛选（TimeWindowQuery 四字段 + runKind 四态） ---------- */
const queryWindow = reactive<TimeWindowQuery>({
  from: '1970-01-01T00:00:00Z',
  to: '2030-01-01T00:00:00Z',
  offset: 0,
  limit: 50,
})
const KIND_OPTIONS = [
  { value: 'all', label: '全部' },
  { value: 'sql', label: 'SQL 运行' },
  { value: 'sync', label: '同步任务' },
  { value: 'workflow', label: '工作流运行' },
] as const
const kind = ref<'all' | 'sql' | 'sync' | 'workflow'>('all')

const rows = ref<LineageWritebackEntry[]>([])
const statusText = ref('待操作')

/** GREEN 契约请求；失败/未接线统一落状态栏（不中断交互） */
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
    rows.value = await contract.listLineageWritebacks(1, queryWindow, kind.value)
  }, '加载血缘回写')
}
</script>

<template>
  <div class="lw-panel-root" data-testid="lineage-writeback-panel">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      data-testid="lw-banner"
      title="LineageWriteback 消费面（R7 GREEN 契约）— 执行器写入的回写血缘在本面板渲染；真实数据可见性待回写链路 1.9 实测（大盘 #9）"
    />

    <div class="lw-filter">
      <el-form inline size="small">
        <el-form-item label="From"><el-input v-model="queryWindow.from" data-testid="lw-from" style="width: 180px" /></el-form-item>
        <el-form-item label="To"><el-input v-model="queryWindow.to" data-testid="lw-to" style="width: 180px" /></el-form-item>
        <el-form-item label="Offset"><el-input v-model.number="queryWindow.offset" data-testid="lw-offset" style="width: 80px" /></el-form-item>
        <el-form-item label="Limit"><el-input v-model.number="queryWindow.limit" data-testid="lw-limit" style="width: 80px" /></el-form-item>
        <el-form-item label="RunKind">
          <el-select v-model="kind" data-testid="lw-kind" style="width: 130px">
            <el-option v-for="k in KIND_OPTIONS" :key="k.value" :label="k.label" :value="k.value" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button size="small" type="primary" data-testid="lw-load" @click="onLoad">加载</el-button>
        </el-form-item>
      </el-form>
    </div>

    <el-table :data="rows" size="small" empty-text="（暂无回写记录 — 待执行器写入 / 1.9 实测）" data-testid="lw-table">
      <el-table-column prop="runId" label="Run ID" width="100" />
      <el-table-column prop="runKind" label="RunKind" width="100" />
      <el-table-column prop="sourceEntity" label="源实体" show-overflow-tooltip />
      <el-table-column prop="targetEntity" label="目标实体" show-overflow-tooltip />
      <el-table-column prop="writebackAt" label="回写时间" width="170" />
    </el-table>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      data-testid="lw-status-bar"
      :title="statusText"
    />
  </div>
</template>

<style scoped>
.lw-panel-root {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.lw-filter {
  margin: 0;
}
</style>
