<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { orchestrationApi, type WorkflowScheduleRow } from '../services/rebuild/orchestrationApi'

const props = defineProps<{ projectId: number | undefined }>()
const emit = defineEmits<{ edit: [code: number, name: string] }>()
const rows = ref<WorkflowScheduleRow[]>([])
const loading = ref(false)
const error = ref('')
const page = ref(1)
const total = ref(0)
const pageSize = 10
let generation = 0

async function load() {
  const current = ++generation
  if (props.projectId === undefined) {
    rows.value = []
    total.value = 0
    error.value = ''
    return
  }
  loading.value = true
  try {
    const result = await orchestrationApi.listWorkflowSchedules(props.projectId, page.value, pageSize)
    if (current !== generation) return
    rows.value = result.list
    total.value = result.total
    error.value = ''
  } catch (reason) {
    if (current !== generation) return
    rows.value = []
    total.value = 0
    error.value = reason instanceof Error ? reason.message : '工作流定时加载失败'
  } finally {
    if (current === generation) loading.value = false
  }
}

async function setOnline(row: WorkflowScheduleRow) {
  if (props.projectId === undefined) return
  const online = row.releaseState !== 'ONLINE'
  try {
    await orchestrationApi.setWorkflowScheduleOnline(props.projectId, row.id, online)
    ElMessage.success(online ? '定时已上线' : '定时已下线')
    await load()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '定时状态更新失败')
  }
}

function changePage(delta: number) {
  const next = page.value + delta
  if (next < 1 || (next - 1) * pageSize >= total.value) return
  page.value = next
  void load()
}

watch(() => props.projectId, () => { page.value = 1; void load() })
onMounted(() => void load())
</script>

<template>
  <section class="tc-schedules" data-tc-schedules>
    <header><h3>工作流定时</h3><button :disabled="loading || projectId === undefined" data-schedule-refresh @click="load">刷新</button></header>
    <p v-if="projectId === undefined">请先选择项目以查看工作流定时</p>
    <p v-else-if="loading">加载中…</p>
    <p v-else-if="error" role="alert">{{ error }}</p>
    <p v-else-if="!rows.length">暂无定时任务。可在工作流行尾的定时操作中创建。</p>
    <template v-else>
      <table data-schedule-table>
        <thead><tr><th>工作流</th><th>Cron</th><th>时区</th><th>有效期</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id" :data-schedule-row="row.id">
            <td>{{ row.workflowDefinitionName ?? `#${row.workflowDefinitionCode}` }}</td>
            <td>{{ row.crontab ?? '—' }}</td>
            <td>{{ row.timezoneId ?? '—' }}</td>
            <td>{{ row.startTime ?? '—' }} 至 {{ row.endTime ?? '—' }}</td>
            <td>{{ row.releaseState === 'ONLINE' ? '已上线' : '未上线' }}</td>
            <td>
              <button data-schedule-edit @click="emit('edit', row.workflowDefinitionCode, row.workflowDefinitionName ?? String(row.workflowDefinitionCode))">打开工作流</button>
              <button data-schedule-toggle @click="setOnline(row)">{{ row.releaseState === 'ONLINE' ? '下线' : '上线' }}</button>
            </td>
          </tr>
        </tbody>
      </table>
      <nav v-if="total > pageSize" aria-label="工作流定时分页">
        <button :disabled="page === 1" @click="changePage(-1)">上一页</button>
        <span>{{ page }} / {{ Math.ceil(total / pageSize) }}</span>
        <button :disabled="page * pageSize >= total" @click="changePage(1)">下一页</button>
      </nav>
    </template>
  </section>
</template>

<style scoped>
.tc-schedules { padding: 18px; overflow: auto; }
header, nav { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
h3 { margin: 0 0 12px; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 9px; border-bottom: 1px solid #dce3eb; text-align: left; }
td:last-child { white-space: nowrap; }
button { margin-right: 8px; cursor: pointer; }
</style>
