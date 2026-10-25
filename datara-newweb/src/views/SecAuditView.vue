<template>
  <main class="audit-page" aria-label="访问审计">
    <header>
      <div>
        <h1>访问审计</h1>
        <p>管理员专属 · 记录所有用户对数据资产的访问尝试及结果</p>
      </div>
      <button type="button" data-reload @click="reload">刷新</button>
    </header>

    <section class="filters" role="search" aria-label="筛选审计日志">
      <label>
        用户
        <input v-model.trim="draft.userName" data-filter-user placeholder="用户名">
      </label>
      <label>
        动作
        <input v-model.trim="draft.action" data-filter-action placeholder="read / write / delete…">
      </label>
      <label>
        结果
        <select v-model="draft.result" data-filter-result>
          <option value="">全部</option>
          <option value="allow">放行</option>
          <option value="deny">拒绝</option>
        </select>
      </label>
      <button type="button" data-apply @click="applyFilter">应用筛选</button>
      <button type="button" data-reset @click="resetFilter">重置</button>
    </section>

    <p v-if="busy" role="status">正在加载审计日志…</p>
    <p v-else-if="error" role="alert" class="error">{{ error }}</p>
    <p v-else-if="!rows.length" data-empty>暂无审计日志</p>

    <table v-else data-audit-list>
      <thead>
        <tr>
          <th>时间</th>
          <th>用户</th>
          <th>动作</th>
          <th>目标</th>
          <th>行数</th>
          <th>结果</th>
          <th>原因</th>
          <th>请求 ID</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.id" :data-log-id="row.id">
          <td>{{ row.accessedAt ?? '—' }}</td>
          <td>{{ row.userName }}</td>
          <td><code>{{ row.action }}</code></td>
          <td>{{ row.target }}</td>
          <td>{{ row.rowsSeen }}</td>
          <td>
            <span
              :class="['result', row.result]"
              :data-result="row.result"
              :aria-label="row.result === 'allow' ? '放行' : '拒绝'"
            >{{ row.result === 'allow' ? '放行' : '拒绝' }}</span>
          </td>
          <td>{{ row.reason || '—' }}</td>
          <td><code>{{ row.requestId || '—' }}</code></td>
        </tr>
      </tbody>
    </table>

    <footer v-if="!busy && !error && total > 0" class="pagination">
      <span>共 {{ total }} 条</span>
      <button type="button" :disabled="offset === 0" @click="prevPage">上一页</button>
      <span>第 {{ currentPage }} 页</span>
      <button type="button" :disabled="offset + limit >= total" @click="nextPage">下一页</button>
    </footer>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { createSecAuditContract, type AccessLogRecord, type AccessLogQuery, type AccessLogResult } from '../services/rebuild/secAuditApi'

const contract = createSecAuditContract()
const rows = ref<AccessLogRecord[]>([])
const total = ref(0)
const busy = ref(false)
const error = ref('')

const limit = ref(20)
const offset = ref(0)

const draft = reactive<{ userName: string; action: string; result: AccessLogResult | '' }>({
  userName: '',
  action: '',
  result: '',
})
const active = reactive<{ userName: string | null; action: string | null; result: AccessLogResult | null }>({
  userName: null,
  action: null,
  result: null,
})

const currentPage = computed(() => Math.floor(offset.value / limit.value) + 1)

function buildQuery(): AccessLogQuery {
  return {
    userName: active.userName || undefined,
    action: active.action || undefined,
    result: active.result || undefined,
    limit: limit.value,
    offset: offset.value,
  }
}

const message = (e: unknown) => (e instanceof Error ? e.message : String(e))

async function reload() {
  busy.value = true
  error.value = ''
  try {
    const page = await contract.listAccessLogs(buildQuery())
    rows.value = page.list
    total.value = page.total
  } catch (e) {
    error.value = message(e)
    rows.value = []
    total.value = 0
  } finally {
    busy.value = false
  }
}

function applyFilter() {
  active.userName = draft.userName.trim() || null
  active.action = draft.action.trim() || null
  active.result = (draft.result as AccessLogResult | '') || null
  offset.value = 0
  reload()
}

function resetFilter() {
  draft.userName = ''
  draft.action = ''
  draft.result = ''
  applyFilter()
}

function prevPage() {
  offset.value = Math.max(0, offset.value - limit.value)
  reload()
}

function nextPage() {
  offset.value += limit.value
  reload()
}

watch(() => limit.value, () => { offset.value = 0; reload() })
onMounted(reload)
</script>

<style scoped>
.audit-page {
  max-width: 1280px;
  margin: auto;
  padding: 32px 24px;
  color: #172033;
}
.audit-page > header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
}
.audit-page h1 { margin: 0; font-size: 22px; }
.audit-page header p { color: #64748b; margin: 4px 0 0; font-size: 13px; }
button { cursor: pointer; padding: 7px 14px; border: 1px solid #cbd5e1; background: #fff; border-radius: 6px; font-size: 13px; }
button:hover:not(:disabled) { background: #f1f5f9; }
button:disabled { cursor: not-allowed; opacity: .5; }

.filters {
  display: flex;
  gap: 12px;
  align-items: flex-end;
  padding: 14px;
  background: #f8fafc;
  border-radius: 8px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.filters label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: #64748b;
}
.filters input, .filters select {
  padding: 6px 10px;
  border: 1px solid #cbd5e1;
  border-radius: 5px;
  font-size: 13px;
  min-width: 140px;
}

table {
  width: 100%;
  border-collapse: collapse;
  background: #fff;
  font-size: 13px;
}
th, td {
  text-align: left;
  padding: 10px 12px;
  border-bottom: 1px solid #e2e8f0;
}
th {
  background: #f8fafc;
  font-weight: 600;
  color: #475569;
}
td code, th code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  background: #f1f5f9;
  padding: 1px 5px;
  border-radius: 3px;
}

.result {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}
.result.allow { background: #dcfce7; color: #15803d; }
.result.deny  { background: #fee2e2; color: #dc2626; }

.pagination {
  margin-top: 16px;
  display: flex;
  gap: 10px;
  align-items: center;
  font-size: 13px;
  color: #64748b;
}

.error { color: #dc2626; }
</style>
