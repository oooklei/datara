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
      <el-descriptions-item label="契约方法">{{ contractMethodCount }} 项已连接</el-descriptions-item>
    </el-descriptions>

    <splitpanes class="r5a-body">
      <pane size="24" min-size="16">
        <div class="r5a-panel">
          <div class="r5a-panel-head">
            <span>元数据（9 类对象）</span>
                <el-input v-model="keyword" size="small" placeholder="检索对象" clearable @change="onSearch" />
          </div>
          <div class="r5a-panel-body">
            <MetaTree ref="metaTree" :datasource-id="datasourceId" :keyword="keyword" @contract-error="onContractError" @select="onMetaSelect" @search-results="searchResults = $event" />
            <el-button v-for="match in searchResults" :key="`${match.kind}:${match.parent}:${match.name}`" link size="small" @click="locateMatch(match)">{{ match.kind }} · {{ match.name }}</el-button>
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
                  <el-button size="small" text @click="openScripts">脚本</el-button>
                  <el-button size="small" text :disabled="!selectedMeta" @click="showDefinition">DDL只读预览</el-button>
                </span>
              </div>
              <div class="r5a-panel-body">
                <SqlEditor v-model="sqlText" :diagnostics="diagnostics" />
              </div>
            </div>
          </pane>
          <pane min-size="20">
            <div class="r5a-panel">
              <div class="r5a-panel-head">
                <span>结果（多语句多结果集）</span>
                <span class="r5a-actions">
                  <el-button v-for="format in exportFormats" :key="format" size="small" :disabled="!historyId || !activeResult.resultSetId" @click="onExport(format)">导出 {{ format.toUpperCase() }}</el-button>
                  <span class="r5a-status">{{ statusText }}</span>
                </span>
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

    <HistoryDrawer v-model:visible="historyVisible" :entries="history" @select="onHistorySelect" @delete="onHistoryDelete" />
    <el-dialog v-model="definitionVisible" title="DDL 只读预览" width="65%">
      <el-alert v-if="definitionMeta" :title="`${definitionMeta.capability} · ${definitionMeta.constraints.join('；')}`" type="info" :closable="false" />
      <pre class="r5a-ddl">{{ definitionText }}</pre>
    </el-dialog>
    <el-drawer v-model="scriptsVisible" title="SQL 脚本" size="42%">
      <el-form inline><el-input v-model="scriptName" placeholder="脚本名称" /><el-button type="primary" @click="saveCurrentScript">保存当前 SQL</el-button></el-form>
      <el-table :data="scripts" size="small" border>
        <el-table-column prop="name" label="名称" />
        <el-table-column prop="revision" label="revision" width="90" />
        <el-table-column label="操作" width="150"><template #default="{ row }"><el-button link @click="sqlText = row.sqlText; activeScript = row">载入</el-button><el-button link type="danger" @click="deleteScript(row)">删除</el-button></template></el-table-column>
      </el-table>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Splitpanes, Pane } from 'splitpanes'
import 'splitpanes/dist/splitpanes.css'
import {
  R5A_CONTRACT_METHODS,
  createSqlIdeContract,
  type DatabaseMeta,
  type HistoryEntry,
  type DefinitionObjectKind,
  type ObjectKind,
  type ScriptEntry,
  type SqlDiagnostic,
  type SqlDoneEvent,
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
const exportFormats = ['csv', 'json', 'xlsx'] as const
const metaTree = ref<{ search: (keyword: string) => Promise<void>; locate: (match: { kind: ObjectKind; name: string; parent: string | null }) => void } | null>(null)

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
const diagnostics = ref<SqlDiagnostic[]>([])
const searchResults = ref<Array<{ kind: ObjectKind; name: string; parent: string | null }>>([])
const selectedMeta = ref<{ kind: ObjectKind | 'source'; label: string; ref: Record<string, unknown>; capability?: string; constraints?: string[] } | null>(null)
const definitionVisible = ref(false)
const definitionText = ref('')
const definitionMeta = ref<{ capability: string; constraints: string[] } | null>(null)
const scriptsVisible = ref(false)
const scripts = ref<ScriptEntry[]>([])
const scriptName = ref('')
const activeScript = ref<ScriptEntry | null>(null)
const eventStream = ref<EventSource | null>(null)
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
    const databaseEnvelope = await contract.listDatabases(datasourceId.value)
    databases.value = databaseEnvelope.items
    crossSchema.value = databaseEnvelope.capability === 'supported'
    if (!databaseName.value && databases.value.length) databaseName.value = databases.value[0].name
    statusText.value = `${databases.value.length} 个数据库已加载`
  } catch (err) {
    statusText.value = err instanceof Error ? err.message : '数据库加载失败'
  } finally {
    loadingDatabases.value = false
  }
}

onMounted(() => { void loadDatabases() })
onBeforeUnmount(() => eventStream.value?.close())

/* 多结果集（汇合点「分页/取消、多结果」：按 stmtIndex 页签 + 服务端分页取页） */
const results = ref<SqlResultEvent[]>([])
const activeStmt = ref(0)
/** 最近一次执行的历史 ID，用于读取对应结果页。 */
const historyId = ref(0)
const activeResult = computed<SqlResultEvent>(() => results.value.find((r) => r.stmtIndex === activeStmt.value) ?? { stmtIndex: 0, resultSetId: '', columns: [], rows: [], rowsTotal: 0, elapsedMs: 0 })

/* 历史抽屉打开时拉取清单。 */
watch(historyVisible, (visible) => {
  if (visible) {
    guard(() => contract.listHistory(datasourceId.value).then((entries) => (history.value = entries)), '加载历史').catch(() => undefined)
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
      eventStream.value?.close()
      results.value = []
      diagnostics.value = []
      const r = await contract.executeSql({ datasourceId: datasourceId.value, db: databaseName.value || null, sql: sqlText.value, mode: 'auto', sessionId, clientRequestId: crypto.randomUUID() })
      taskId.value = r.taskId
      running.value = true
      statusText.value = `执行中 · ${r.taskId}`
      const stream = contract.openEventStream(r.taskId)
      eventStream.value = stream
      const read = <T,>(event: Event): T | null => { try { return JSON.parse((event as MessageEvent<string>).data) as T } catch { return null } }
      stream.addEventListener('log', (event) => { const log = read<{ message?: string; sql?: string; error?: string }>(event); if (log) statusText.value = log.error || log.message || log.sql || '执行日志已更新' })
      stream.addEventListener('result', (event) => {
        const result = read<SqlResultEvent & { historyId?: number }>(event)
        if (!result?.resultSetId) return
        const resultHistoryId = result.historyId ?? historyId.value
        if (!resultHistoryId) { statusText.value = '结果事件缺少 historyId，无法读取快照'; return }
        historyId.value = resultHistoryId
        const prior = results.value.find((item) => item.resultSetId === result.resultSetId)
        activeStmt.value = result.stmtIndex
        void contract.fetchResultPage(resultHistoryId, result.resultSetId, 0, pageSize.value)
          .then((pageResult) => {
            const loaded = { ...result, ...pageResult, elapsedMs: result.elapsedMs ?? 0 }
            if (prior) Object.assign(prior, loaded); else results.value.push(loaded)
          })
          .catch((error: unknown) => { statusText.value = error instanceof Error ? error.message : '结果快照读取失败' })
      })
      stream.addEventListener('reset-required', () => { statusText.value = '事件已重置，等待服务端重放；任务不会重新执行' })
      stream.addEventListener('done', (event) => {
        const done = read<SqlDoneEvent>(event)
        if (done) void finishExecution(done, stream)
        else { running.value = false; statusText.value = '完成事件格式无效'; stream.close() }
      })
      stream.addEventListener('error', () => { if (running.value) statusText.value = '事件断线，自动重连中；任务不会重新执行' })
    },
    '执行',
  ).catch(() => undefined)

async function finishExecution(done: SqlDoneEvent, stream: EventSource) {
  running.value = false
  historyId.value = done.historyId ?? 0
  statusText.value = `执行 ${done.status} · ${done.elapsedMs}ms`
  stream.close()
  if (historyId.value && done.resultSets?.length) {
    const pages = await Promise.all(done.resultSets.map((set) => contract.fetchResultPage(historyId.value, set.resultSetId, 0, pageSize.value)))
    results.value = pages.map((result) => ({ ...result, elapsedMs: done.resultSets?.find((set) => set.resultSetId === result.resultSetId)?.elapsedMs ?? 0 }))
    activeStmt.value = results.value[0]?.stmtIndex ?? 0
  }
  if (historyVisible.value) history.value = await contract.listHistory(datasourceId.value)
}
const onCancel = () =>
  guard(
    async () => {
      const r = await contract.cancelExecution(taskId.value)
      if (r.canceled) running.value = false
    },
    '取消',
  ).catch(() => undefined)
const onLint = () => guard(() => contract.lintSql(datasourceId.value, sqlText.value).then((items) => { diagnostics.value = items }), '预检').catch(() => undefined)
const onSearch = () => { void metaTree.value?.search(keyword.value) }

/** 服务端分页取页并回填对应 stmt 的结果数据。 */
const onPageChange = (p: number, s: number) => {
  page.value = p
  pageSize.value = s
  guard(
    async () => {
      const target = activeResult.value
      if (!target.resultSetId) throw new Error('结果集缺少 resultSetId，无法分页读取')
      const pg = await contract.fetchResultPage(historyId.value, target.resultSetId, (p - 1) * s, s)
      if (target) target.rows = pg.rows
    },
    '取结果页',
  ).catch(() => undefined)
}

function locateMatch(match: { kind: ObjectKind; name: string; parent: string | null }) {
  metaTree.value?.locate(match)
  selectedMeta.value = { kind: match.kind, label: match.name, ref: { datasourceId: datasourceId.value, database: databaseName.value, schema: match.parent, name: match.name, objectKind: match.kind } }
  statusText.value = `定位对象：${match.parent ? `${match.parent}.` : ''}${match.name}`
}

function onMetaSelect(node: { kind: ObjectKind | 'source'; label: string; ref: Record<string, unknown>; capability?: string; constraints?: string[] }) {
  selectedMeta.value = node
  if (node.kind === 'database') databaseName.value = String(node.ref.name ?? '')
  else if (node.ref.database) databaseName.value = String(node.ref.database)
}

async function showDefinition() {
  const selected = selectedMeta.value
  if (!selected || !databaseName.value || selected.kind === 'source') return
  await guard(async () => {
    if (!['table', 'view', 'function', 'procedure', 'trigger'].includes(selected.kind)) throw new Error('该对象类型不支持 DDL 预览')
    const value = await contract.getDefinition({ datasourceId: datasourceId.value, database: databaseName.value, objectKind: selected.kind as DefinitionObjectKind, objectRef: selected.ref })
    definitionText.value = value.definition
    definitionMeta.value = { capability: value.capability, constraints: value.constraints }
    definitionVisible.value = true
  }, '读取 DDL').catch(() => undefined)
}

async function onHistorySelect(entry: HistoryEntry) {
  if (!entry.resultSets?.length) { statusText.value = `历史 ${entry.historyId} 无可回看结果集`; return }
  await guard(async () => {
    historyId.value = entry.historyId
    const pages = await Promise.all(entry.resultSets!.map((set) => contract.fetchResultPage(entry.historyId, set.resultSetId, 0, pageSize.value)))
    results.value = pages.map((result) => ({ ...result, elapsedMs: 0 }))
    activeStmt.value = results.value[0]?.stmtIndex ?? 0
    historyVisible.value = false
  }, '回看快照').catch(() => undefined)
}

async function onHistoryDelete(id: number) {
  await guard(async () => { await contract.deleteHistory(id); history.value = history.value.filter((entry) => entry.historyId !== id) }, '删除历史').catch(() => undefined)
}

async function openScripts() {
  scriptsVisible.value = true
  await guard(async () => { scripts.value = await contract.listScripts() }, '加载脚本').catch(() => undefined)
}

async function saveCurrentScript() {
  if (!scriptName.value.trim()) { statusText.value = '请填写脚本名称'; return }
  await guard(async () => {
    const saved = await contract.saveScript({ id: activeScript.value?.id, name: scriptName.value.trim(), sqlText: sqlText.value, revision: activeScript.value?.revision })
    activeScript.value = saved
    scripts.value = [...scripts.value.filter((item) => item.id !== saved.id), saved]
  }, '保存脚本').catch((err: unknown) => {
    if (err && typeof err === 'object' && 'code' in err && (err as { code: number }).code === 409) statusText.value = '脚本版本冲突（409），本地 SQL 已保留，请重新载入并合并'
  })
}

async function deleteScript(script: ScriptEntry) {
  await guard(async () => {
    await contract.deleteScript(script.id, script.revision)
    scripts.value = scripts.value.filter((item) => item.id !== script.id)
  }, '删除脚本').catch((err: unknown) => {
    if (err && typeof err === 'object' && 'code' in err && (err as { code: number }).code === 409) statusText.value = '脚本版本冲突（409），脚本列表已保留，请重新载入后重试'
  })
}

async function onExport(format: typeof exportFormats[number]) {
  await guard(async () => {
    const result = await contract.exportResult({ historyId: historyId.value, resultSetId: activeResult.value.resultSetId, format })
    if (result.status !== 'ready' && result.status !== 'completed') throw new Error(`导出暂不可用（${result.status}），TTL 截止 ${result.expiresAt}`)
    window.location.assign(contract.getExportDownloadUrl(result.exportId))
  }, `导出 ${format.toUpperCase()}`).catch(() => undefined)
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
