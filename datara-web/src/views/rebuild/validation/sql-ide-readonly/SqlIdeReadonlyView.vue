<!--
  SQL IDE readonly validation view connected through the A5 contract service.
  权威范围：plan I5（docs/superpowers/plans/2026-10-14-datara-platform-rebuild.md）
  + docs/increments/R5-IDE-开始前影响分析.md §3/§6。
  边界：独立验证页，不改造正式 /ide SPA；请求经 services/rebuild/sqlIdeApi。
-->
<template>
  <div class="r5a-page">
    <div class="r5a-connection">
      <el-input-number v-model="datasourceId" :min="1" controls-position="right" aria-label="数据源 ID" />
      <el-select v-model="databaseName" placeholder="选择数据库" :loading="loadingDatabases">
        <el-option v-for="database in databases" :key="database.name" :label="database.name" :value="database.name" />
      </el-select>
      <el-button size="small" :loading="loadingDatabases" @click="loadDatabases">加载数据库</el-button>
    </div>
    <el-descriptions :column="4" size="small" border class="r5a-context">
      <el-descriptions-item label="数据源">{{ datasourceName }}</el-descriptions-item>
      <el-descriptions-item label="数据库">{{ databaseName || '—' }}</el-descriptions-item>
      <el-descriptions-item label="跨 Schema">{{ crossSchema ? '支持' : '不支持' }}</el-descriptions-item>
      <el-descriptions-item label="契约方法">{{ contractMethodCount }} 项（全部未接线）</el-descriptions-item>
    </el-descriptions>

    <splitpanes class="r5a-body">
      <pane size="24" min-size="16">
        <div class="r5a-panel">
          <div class="r5a-panel-head">
            <span>元数据（9 类对象）</span>
            <el-input v-model="keyword" size="small" placeholder="检索对象" clearable @change="onSearch" />
          </div>
          <div class="r5a-panel-body">
            <MetaTree @contract-error="onContractError" />
          </div>
        </div>
      </pane>
      <pane size="76">
        <splitpanes horizontal>
          <pane size="42" min-size="20">
            <div class="r5a-panel">
              <div class="r5a-panel-head">
                <span>SQL（只读执行）</span>
                <span class="r5a-actions">
                  <el-button size="small" @click="onLint">预检</el-button>
                  <el-button size="small" type="primary" :disabled="running" @click="onExecute">执行</el-button>
                  <el-button size="small" :disabled="!running" @click="onCancel">取消</el-button>
                  <el-button size="small" text @click="historyVisible = true">历史</el-button>
                </span>
              </div>
              <div class="r5a-panel-body">
                <SqlEditor v-model="sqlText" />
              </div>
            </div>
          </pane>
          <pane min-size="20">
            <div class="r5a-panel">
              <div class="r5a-panel-head">
                <span>结果（多语句多结果集）</span>
                <span class="r5a-status">{{ statusText }}</span>
              </div>
              <div class="r5a-panel-body">
                <el-tabs v-if="results.length > 0" v-model="activeStmt" type="card" class="r5a-result-tabs">
                  <el-tab-pane v-for="r in results" :key="r.stmtIndex" :label="`#${r.stmtIndex}（${r.rowsTotal} 行）`" :name="r.stmtIndex" />
                </el-tabs>
                <ResultGrid
                  :columns="activeResult.columns"
                  :rows="activeResult.rows"
                  :rows-total="activeResult.rowsTotal"
                  :page="page"
                  :page-size="pageSize"
                  truncated
                  data-testid="r5a-result-grid"
                  @page-change="onPageChange"
                />
              </div>
            </div>
          </pane>
        </splitpanes>
      </pane>
    </splitpanes>

    <HistoryDrawer v-model:visible="historyVisible" :entries="history" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Splitpanes, Pane } from 'splitpanes'
import 'splitpanes/dist/splitpanes.css'
import {
  R5A_CONTRACT_METHODS,
  createSqlIdeContract,
  getSqlIdeExecutionStatus,
  type DatabaseMeta,
  type HistoryEntry,
  type SqlResultEvent,
} from '../../../../services/rebuild/sqlIdeApi'
import MetaTree from './components/MetaTree.vue'
import SqlEditor from './components/SqlEditor.vue'
import ResultGrid from './components/ResultGrid.vue'
import HistoryDrawer from './components/HistoryDrawer.vue'

defineOptions({ name: 'SqlIdeReadonlyView' })

const projectId = 1
const contract = createSqlIdeContract(projectId)
const contractMethodCount = R5A_CONTRACT_METHODS.length
const sessionId = crypto.randomUUID()

/* 页面上下文使用占位值；数据源选择接 rebuild governance catalog。 */
const datasourceName = ref('SQL IDE')
const datasourceId = ref(1)
const databases = ref<DatabaseMeta[]>([])
const loadingDatabases = ref(false)
const databaseName = ref('')
const crossSchema = ref(false)
const keyword = ref('')

/* 编辑与执行状态 */
const sqlText = ref('SELECT 1;')
const running = ref(false)
const taskId = ref('')
const statusText = ref('待执行')
const historyVisible = ref(false)
const history = ref<HistoryEntry[]>([])
const page = ref(1)
const pageSize = ref(50)

/** MetaTree 子组件契约错误冒泡：统一落状态栏，不中断交互 */
const onContractError = (message: string) => {
  statusText.value = message
}

async function loadDatabases() {
  if (loadingDatabases.value) return
  loadingDatabases.value = true
  try {
    databases.value = await contract.listDatabases(datasourceId.value)
    if (!databaseName.value && databases.value.length) databaseName.value = databases.value[0].name
    statusText.value = `${databases.value.length} 个数据库已加载`
  } catch (err) {
    statusText.value = err instanceof Error ? err.message : '数据库加载失败'
  } finally {
    loadingDatabases.value = false
  }
}

onMounted(() => { void loadDatabases() })

/* 多结果集（汇合点「分页/取消、多结果」：按 stmtIndex 页签 + 服务端分页取页） */
const results = ref<SqlResultEvent[]>([])
const activeStmt = ref(0)
/** 最近一次执行的历史 ID，用于读取对应结果页。 */
const historyId = ref(0)
const activeResult = computed<SqlResultEvent>(() => results.value.find((r) => r.stmtIndex === activeStmt.value) ?? { stmtIndex: 0, columns: [], rows: [], rowsTotal: 0, elapsedMs: 0 })

/* 历史抽屉打开时拉取清单。 */
watch(historyVisible, (visible) => {
  if (visible) {
    guard(() => contract.listHistory(0).then((entries) => (history.value = entries)), '加载历史').catch(() => undefined)
  }
})

/** 将服务错误显示在状态栏并保留页面交互。 */
function guard<T>(fn: () => Promise<T>, label: string): Promise<void> {
  statusText.value = `${label}…`
  return fn()
    .then(() => {
      statusText.value = `${label} 完成`
    })
    .catch((err: unknown) => {
      statusText.value = err instanceof Error ? err.message : `${label} 失败`
      throw err
    })
}

const onExecute = () =>
  guard(
    async () => {
      /* 为断线重试保持 session 与请求标识，后端可据此恢复同一执行。 */
      const r = await contract.executeSql({ datasourceId: datasourceId.value, db: databaseName.value || null, sql: sqlText.value, mode: 'auto', sessionId, clientRequestId: crypto.randomUUID() })
      taskId.value = r.taskId
      running.value = true
      let execution: { status: string; historyId?: number | null } = { status: 'pending' }
      for (let attempt = 0; attempt < 60; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 500))
        execution = await getSqlIdeExecutionStatus(projectId, r.taskId)
        if (execution.status === 'succeeded' || execution.status === 'failed' || execution.status === 'canceled') break
      }
      running.value = false
      historyId.value = execution.historyId ?? 0
      if (!historyId.value) throw new Error(`SQL 执行状态：${execution.status}，未返回结果 ID`)
      const result = await contract.fetchResultPage(historyId.value, 0, 0, pageSize.value)
      results.value = [{ stmtIndex: result.stmtIndex, columns: result.columns, rows: result.rows, rowsTotal: result.rowsTotal, elapsedMs: 0 }]
      activeStmt.value = result.stmtIndex
    },
    '执行',
  ).catch(() => undefined)
const onCancel = () =>
  guard(
    async () => {
      const r = await contract.cancelExecution(taskId.value)
      if (r.canceled) running.value = false
    },
    '取消',
  ).catch(() => undefined)
const onLint = () => guard(() => contract.lintSql(0, sqlText.value), '预检').catch(() => undefined)
const onSearch = () => guard(() => contract.searchObjects(0, keyword.value), '检索').catch(() => undefined)

/** 服务端分页取页并回填对应 stmt 的结果数据。 */
const onPageChange = (p: number, s: number) => {
  page.value = p
  pageSize.value = s
  guard(
    async () => {
      const pg = await contract.fetchResultPage(historyId.value, activeStmt.value, (p - 1) * s, s)
      const target = results.value.find((r) => r.stmtIndex === pg.stmtIndex)
      if (target) target.rows = pg.rows
    },
    '取结果页',
  ).catch(() => undefined)
}
</script>

<style scoped>
.r5a-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
  box-sizing: border-box;
}
.r5a-context {
  flex: none;
}
.r5a-connection {
  display: flex;
  align-items: center;
  gap: 8px;
}
.r5a-body {
  flex: 1;
  min-height: 0;
}
.r5a-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--el-border-color-light);
  border-radius: 4px;
  overflow: hidden;
}
.r5a-panel-head {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 8px;
  background: var(--el-fill-color-light);
  font-size: 13px;
}
.r5a-actions {
  display: inline-flex;
  gap: 4px;
}
.r5a-status {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.r5a-panel-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 4px;
}
.splitpanes__pane {
  transition: none;
}
.r5a-result-tabs {
  margin-bottom: 4px;
}
.r5a-result-tabs :deep(.el-tabs__header) {
  margin-bottom: 4px;
}
</style>
