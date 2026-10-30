<template>
  <main class="pg" aria-label="影响分析">
    <header class="pg-head">
      <h1 class="sec-head">影响分析</h1>
      <p class="pg-desc">按日查看 dbx 成功执行的 SQL 所读取和写入的对象。</p>
    </header>
    <div class="toolbar">
      <label>项目
        <select v-model="selectedProject" data-impact-project @change="load">
          <option value="">请选择项目</option>
          <option v-for="project in projects" :key="project.id" :value="String(project.id)">{{ project.name }}</option>
        </select>
      </label>
      <label>日期 <input v-model="day" data-impact-day type="date" @change="load"></label>
      <button type="button" class="op-btn" :disabled="busy || !projectId" @click="load">查询</button>
      <button v-if="authAccount?.role === 'admin'" type="button" class="op-btn" :disabled="busy || !projectId" @click="refresh">重新采集</button>
    </div>
    <p v-if="error" role="alert" class="err-box">{{ error }}</p>
    <p v-if="!projectId" class="panel empty">请先选择项目</p>
    <p v-else-if="busy" class="panel" role="status">正在读取影响分析…</p>
    <template v-else-if="result">
      <p v-if="!result.collected" class="panel empty">该日尚未完成采集。</p>
      <p v-else-if="!result.items.length" class="panel empty">该日没有可见连接的执行记录。</p>
      <div v-else class="panel">
        <table class="tbl" data-impact-results>
          <thead><tr><th>执行时间</th><th>连接</th><th>数据库</th><th>状态</th><th>读取对象</th><th>写入对象</th></tr></thead>
          <tbody>
            <tr v-for="item in result.items" :key="item.history_id">
              <td>{{ item.executed_at }}</td><td>{{ item.connection_id }}</td><td>{{ item.database }}</td>
              <td>{{ statusLabel(item.status) }}</td>
              <td>{{ item.reads.join('、') || '—' }}</td><td>{{ item.writes.join('、') || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { listProjects, type ProjectSummary } from '../../services/rebuild/projectApi'
import { createImpactContract, type DailyImpactResult } from '../../services/rebuild/impactApi'
import { authAccount } from '../../services/rebuild/authApi'

const route = useRoute()
const projects = ref<ProjectSummary[]>([])
const selectedProject = ref('')
const projectId = computed(() => Number(selectedProject.value) || null)
const yesterday = new Date(Date.now() - 86400000)
const day = ref(`${yesterday.getFullYear()}-${String(yesterday.getMonth() + 1).padStart(2, '0')}-${String(yesterday.getDate()).padStart(2, '0')}`)
const result = ref<DailyImpactResult | null>(null)
const error = ref('')
const busy = ref(false)

function statusLabel(status: string) {
  return ({ ok: '已解析', failed_execution: '执行失败', unparsed: '无法解析', no_sql: '无 SQL' } as Record<string, string>)[status] ?? status
}

async function load() {
  result.value = null
  error.value = ''
  if (!projectId.value) return
  busy.value = true
  try { result.value = await createImpactContract(projectId.value).listDaily(day.value) }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '读取失败' }
  finally { busy.value = false }
}

async function refresh() {
  if (!projectId.value || busy.value) return
  busy.value = true
  error.value = ''
  try {
    await createImpactContract(projectId.value).refreshDaily(day.value)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '采集失败'
    busy.value = false
    return
  }
  busy.value = false
  await load()
}

onMounted(async () => {
  try {
    projects.value = (await listProjects()).list
    const requested = String(route.query.projectId ?? '')
    selectedProject.value = projects.value.some((project) => String(project.id) === requested)
      ? requested : String(projects.value[0]?.id ?? '')
    await load()
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '项目列表读取失败' }
})
</script>
