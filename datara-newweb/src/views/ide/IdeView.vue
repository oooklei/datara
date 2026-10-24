<template>
  <main class="ide-page" aria-label="数据开发IDE">
    <header class="ide-head">
      <div>
        <h1>数据开发 IDE</h1>
        <p>R5-A 只读态：对象树（库·Schema·表/视图/例程/索引）→ 写 SQL（含变量引用）→ 执行 → 结果网格 → 历史。DDL 写路径归增量 16/R5-B。</p>
      </div>
      <div class="ide-actions">
        <label class="ide-project">项目
          <select v-model="selected" data-project-select @change="reload">
            <option value="">请选择项目</option>
            <option v-for="p in projects" :key="p.id" :value="String(p.id)">{{ p.name }}</option>
          </select>
        </label>
        <label class="ide-ds">数据源
          <select v-model="selectedDs" data-ds-select @change="selectDatasource(Number(selectedDs))">
            <option value="">请选择数据源</option>
            <option v-for="d in datasources" :key="d.id" :value="String(d.id)">{{ d.name }}</option>
          </select>
        </label>
        <button type="button" data-execute :disabled="!canExecute" @click="runSql">
          {{ executing ? '执行中…' : '执行' }}
        </button>
        <button type="button" data-cancel :disabled="!executing" @click="cancelRun">取消</button>
      </div>
    </header>

    <!-- 错误横幅独立于内容态：加载失败不丢上下文，执行失败保留编辑器 -->
    <p v-if="error" role="alert" data-error>{{ error }}</p>
    <p v-if="status" role="status" data-status>{{ status }}</p>
    <p v-else-if="projectId === null" data-no-project>请先选择项目</p>
    <p v-else-if="datasourceId === null" data-no-datasource>请先选择数据源</p>

    <div v-else class="ide-split">
      <aside class="ide-left" data-object-panel>
        <section>
          <h2>对象树</h2>
          <label class="ide-search">搜索对象
            <input v-model.trim="keyword" data-search-input placeholder="表 / 视图 / 例程名"
                   @keyup.enter="runSearch" />
          </label>
          <button type="button" data-search :disabled="keyword === ''" @click="runSearch">搜索</button>
          <p v-if="treeCapability" class="ide-cap" data-capability>能力分级：{{ treeCapability }}</p>
          <p v-if="treeConstraints.length" class="ide-muted">{{ treeConstraints.join('；') }}</p>
        </section>

        <section v-if="databases.length">
          <h3>库</h3>
          <ul class="ide-tree" data-database-list>
            <li v-for="db in databases" :key="db">
              <button type="button" :class="{ active: db === activeDatabase }" @click="openDatabase(db)">{{ db }}</button>
            </li>
          </ul>
        </section>

        <section v-if="schemas.length">
          <h3>Schema · {{ activeDatabase }}</h3>
          <ul class="ide-tree" data-schema-list>
            <li v-for="s in schemas" :key="s">
              <button type="button" :class="{ active: s === activeSchema }" @click="openSchema(s)">{{ s }}</button>
            </li>
          </ul>
        </section>

        <section v-if="relations.length">
          <h3>对象 · {{ activeSchema }}</h3>
          <ul class="ide-tree" data-relation-list>
            <li v-for="r in relations" :key="`${r.kind}.${r.name}`">
              <button type="button" :class="{ active: r.name === activeRelation }" @click="openRelation(r)">
                {{ r.name }}<small>{{ r.kind === 'view' ? '视图' : '表' }}</small>
              </button>
            </li>
          </ul>
        </section>

        <section v-if="routines.length">
          <h3>例程 · {{ activeSchema }}</h3>
          <ul class="ide-tree" data-routine-list>
            <li v-for="r in routines" :key="`${r.kind}.${r.name}`">
              <button type="button" @click="showDefinition(r)">{{ r.name }}<small>{{ routineLabel(r.kind) }}</small></button>
            </li>
          </ul>
        </section>

        <section v-if="columns.length">
          <h3>字段 · {{ activeSchema }}.{{ activeRelation }}</h3>
          <table data-column-list>
            <thead><tr><th>字段</th><th>类型</th><th>可空</th><th>键</th></tr></thead>
            <tbody>
              <tr v-for="c in columns" :key="c.name">
                <td>{{ c.name }}</td>
                <td>{{ c.dataType }}</td>
                <td>{{ c.nullable ? '是' : '否' }}</td>
                <td>{{ c.key ?? '' }}</td>
              </tr>
            </tbody>
          </table>
        </section>

        <section v-if="indexes.length">
          <h3>索引 · {{ activeRelation }}</h3>
          <table data-index-list>
            <thead><tr><th>索引</th><th>列</th><th>唯一</th></tr></thead>
            <tbody>
              <tr v-for="i in indexes" :key="i.name">
                <td>{{ i.name }}</td>
                <td>{{ i.columns.join(', ') }}</td>
                <td>{{ i.unique ? '是' : '否' }}</td>
              </tr>
            </tbody>
          </table>
        </section>

        <p v-if="searched.length" class="ide-search-result" data-search-result>
          <span v-for="s in searched" :key="`${s.kind}.${s.name}`">{{ s.name }}<small>{{ s.kind }}</small></span>
        </p>
      </aside>

      <section class="ide-right">
        <div class="ide-editor-head">
          <span class="ide-editor-title">SQL</span>
          <button type="button" data-lint :disabled="sqlText.trim() === '' || datasourceId === null" @click="runLint">语法检查</button>
          <button type="button" data-save-script :disabled="sqlText.trim() === ''" @click="saveScript">存为脚本</button>
          <button type="button" data-export :disabled="lastResultSetId === null" @click="exportCurrent">导出结果</button>
        </div>
        <textarea v-model="sqlText" data-sql-editor rows="12" spellcheck="false"
                  placeholder="SELECT … -- 支持 ${scope.name} 与 $[时间] 变量引用"></textarea>

        <p v-if="diagnostics.length" class="ide-diag" data-diagnostics>
          <span v-for="(d, i) in diagnostics" :key="i" :class="['pill', d.severity]">
            L{{ d.line }}:{{ d.col }} {{ d.severity }} {{ d.code }} — {{ d.message }}
          </span>
        </p>

        <section v-if="varRefs.length || varErrors.length" class="ide-vars" data-vars>
          <h3>变量引用</h3>
          <p v-for="v in varRefs" :key="`${v.scope}.${v.name}`" class="ide-var">
            <code>${{ `${v.scope}.${v.name}` }}</code>
            <span v-if="varValues[`${v.scope}.${v.name}`] !== undefined">
              → {{ varValues[`${v.scope}.${v.name}`] ?? '（不可解析）' }}
            </span>
          </p>
          <p v-for="e in varErrors" :key="e" class="ide-err" data-var-error>{{ e }}</p>
          <p v-if="varTimes.length" class="ide-muted">时间表达式：{{ varTimes.join('，') }}</p>
        </section>

        <section v-if="resultColumns.length" class="ide-result" data-result-grid>
          <header class="ide-result-head">
            <span>结果集 {{ currentResultSetIndex + 1 }} / {{ resultSetIds.length }}</span>
            <span class="ide-muted" data-result-meta>共 {{ resultRowsTotal }} 行 · 已取 {{ resultRows.length }} 行</span>
            <span class="ide-result-nav">
              <button type="button" :disabled="resultPage <= 1" @click="changePage(resultPage - 1)">上一页</button>
              <span data-result-page>第 {{ resultPage }} 页</span>
              <button type="button" :disabled="!resultHasMore" @click="changePage(resultPage + 1)">下一页</button>
            </span>
          </header>
          <table v-if="resultRows.length">
            <thead>
              <tr><th v-for="c in resultColumns" :key="c">{{ c }}</th></tr>
            </thead>
            <tbody>
              <tr v-for="(row, ri) in resultRows" :key="ri">
                <td v-for="(cell, ci) in row" :key="ci">{{ formatCell(cell) }}</td>
              </tr>
            </tbody>
          </table>
          <p v-else class="ide-muted">无数据行</p>
        </section>
      </section>
    </div>

    <aside v-if="historyOpen" class="ide-history" data-history>
      <header>
        <h2>执行历史</h2>
        <button type="button" data-history-toggle @click="historyOpen = false">收起</button>
      </header>
      <p v-if="history.length === 0" class="ide-muted">暂无历史</p>
      <ul v-else>
        <li v-for="h in history" :key="h.historyId">
          <button type="button" class="ide-history-item" @click="restoreHistory(h)">
            <b>{{ h.status }}</b>
            <code>{{ h.sqlText.slice(0, 60) }}</code>
            <small>{{ h.stmtCount }} 语句 · {{ h.elapsedMs }}ms</small>
          </button>
          <button type="button" class="ide-history-del" @click="removeHistory(h.historyId)">删除</button>
        </li>
      </ul>
    </aside>
    <button v-else type="button" class="ide-history-open" data-history-toggle @click="openHistory">执行历史</button>
  </main>
</template>

<script setup lang="ts">
/**
 * 增量 11：数据开发 IDE 只读态（`/ide`）。
 *
 * 契约面：`sqlIdeApi`（createSqlIdeContract，R5-A 只读 23 方法）——
 *   对象树 listDatabases/Schemas/Relations/Columns/Routines/Indexes/searchObjects、
 *   lintSql、executeSql + openEventStream(SSE) + fetchResultPage 分页、
 *   listHistory/deleteHistory、listScripts/saveScript、exportResult/getExportDownloadUrl。
 * 数据源列表复用 `datasourceApi`（createDatasourceContract.listDatasources）。
 * 唯一后端事实源为 rebuild-api(8001)；项目数据由 URL 中的 projectId 隔离。
 * 项目上下文：`/ide` 为全局模式路由（AppShell 项目模式仅覆盖 `/p/` 前缀），
 *   故项目段从 `route.params.projectId` 或 `route.query.projectId` 承接；
 *   两者皆空时呈现选择器，不渲染空壳。
 * 范式：手写 HTML/CSS（零 element-plus）；编辑器=轻量 textarea
 *   （codemirror 换芯登记候接，不阻塞只读态语义）。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  createSqlIdeContract,
  type HistoryEntry,
  type RoutineMeta,
  type SqlDiagnostic,
  type SqlDoneEvent,
  type SqlResultEvent,
  type SqlIdeContract,
} from '../../services/rebuild/sqlIdeApi'
import {
  createDatasourceContract,
  type DatasourceContract,
  type DatasourceRecord,
} from '../../services/rebuild/datasourceApi'
import { createVariableContract, parseVariableReferences, type VariableContract } from '../../services/rebuild/variableApi'
import { listProjects, type ProjectSummary } from '../../services/rebuild/projectApi'

const props = defineProps<{ projectId?: number }>()
const route = useRoute()

const projects = ref<ProjectSummary[]>([])
const selected = ref('')
const datasources = ref<DatasourceRecord[]>([])
const selectedDs = ref('')

const databases = ref<string[]>([])
const activeDatabase = ref('')
const schemas = ref<string[]>([])
const activeSchema = ref('')
const relations = ref<Array<{ kind: 'table' | 'view'; name: string }>>([])
const activeRelation = ref('')
const columns = ref<Array<{ name: string; dataType: string; nullable: boolean; key?: string | null }>>([])
const indexes = ref<Array<{ name: string; columns: string[]; unique: boolean }>>([])
const routines = ref<RoutineMeta[]>([])
const searched = ref<Array<{ kind: string; name: string; parent: string | null }>>([])
const keyword = ref('')

const treeCapability = ref('')
const treeConstraints = ref<string[]>([])

const sqlText = ref('')
const executing = ref(false)
const currentTaskId = ref('')
const diagnostics = ref<SqlDiagnostic[]>([])
const contractError = ref('')
const error = ref('')
const status = ref('')

const resultColumns = ref<string[]>([])
const resultRows = ref<unknown[][]>([])
const resultRowsTotal = ref(0)
const resultSetIds = ref<string[]>([])
const currentResultSetIndex = ref(0)
const lastHistoryId = ref<number | null>(null)
const lastResultSetId = ref<string | null>(null)
const resultPage = ref(1)
const resultPageSize = 50
const resultHasMore = ref(false)

const varRefs = ref<Array<{ scope: string; name: string }>>([])
const varErrors = ref<string[]>([])
const varTimes = ref<string[]>([])
const varValues = ref<Record<string, string | null>>({})

const history = ref<HistoryEntry[]>([])
const historyOpen = ref(false)

const ROUTINE_LABEL: Record<RoutineMeta['kind'], string> = { function: '函数', procedure: '存储过程', trigger: '触发器' }
const routineLabel = (k: RoutineMeta['kind']): string => ROUTINE_LABEL[k] ?? k
const message = (e: unknown): string => (e instanceof Error ? e.message : String(e))

const dsApi = computed<DatasourceContract>(() =>
  projectId.value === null ? ({} as DatasourceContract) : createDatasourceContract(projectId.value),
)
const api = computed<SqlIdeContract>(() =>
  projectId.value === null ? ({} as SqlIdeContract) : createSqlIdeContract(projectId.value),
)
const varApi = computed<VariableContract>(() => createVariableContract())

/** 项目上下文：项目段注入优先，其次 route 参数/query，最后选择器。
 * ProjectSegmentView 以 prop 挂载本页；若只读取 route，会在 /p/:id/ide
 * 下退化成「请选择项目」并且不会加载数据源。 */
const routeProjectId = computed<number | null>(() => {
  const raw = route.params.projectId ?? route.query.projectId
  const value = Array.isArray(raw) ? raw[0] : raw
  const n = Number(value)
  return value !== undefined && value !== '' && Number.isInteger(n) && n > 0 ? n : null
})
const projectId = computed<number | null>(() => {
  if (Number.isInteger(props.projectId) && props.projectId! > 0) return props.projectId!
  const fromRoute = routeProjectId.value
  if (fromRoute !== null) return fromRoute
  const n = Number(selected.value)
  return selected.value !== '' && Number.isInteger(n) && n > 0 ? n : null
})
const datasourceId = computed<number | null>(() => {
  const n = Number(selectedDs.value)
  return selectedDs.value !== '' && Number.isInteger(n) && n > 0 ? n : null
})
const canExecute = computed(() => datasourceId.value !== null && sqlText.value.trim() !== '' && !executing.value)

const formatCell = (cell: unknown): string => {
  if (cell === null || cell === undefined) return ''
  if (typeof cell === 'object') return JSON.stringify(cell)
  return String(cell)
}

async function loadProjects(): Promise<void> {
  try {
    projects.value = (await listProjects()).list
  } catch (e) {
    error.value = message(e)
  }
}

function clearTree(): void {
  databases.value = []
  activeDatabase.value = ''
  schemas.value = []
  activeSchema.value = ''
  relations.value = []
  activeRelation.value = ''
  columns.value = []
  indexes.value = []
  routines.value = []
  searched.value = []
  treeCapability.value = ''
  treeConstraints.value = []
}

async function reload(): Promise<void> {
  datasources.value = []
  selectedDs.value = ''
  clearTree()
  if (projectId.value === null) return
  try {
    datasources.value = (await dsApi.value.listDatasources()).items
  } catch (e) {
    error.value = message(e)
  }
}

async function selectDatasource(id: number): Promise<void> {
  clearTree()
  if (projectId.value === null) return
  try {
    const page = await api.value.listDatabases(id)
    databases.value = page.items.map((d) => d.name)
    treeCapability.value = page.capability
    treeConstraints.value = page.constraints
  } catch (e) {
    error.value = message(e)
  }
}

async function openDatabase(db: string): Promise<void> {
  activeDatabase.value = db
  schemas.value = []
  activeSchema.value = ''
  relations.value = []
  activeRelation.value = ''
  columns.value = []
  indexes.value = []
  routines.value = []
  if (datasourceId.value === null) return
  try {
    const page = await api.value.listSchemas(datasourceId.value, db)
    schemas.value = page.items.map((s) => s.name)
  } catch (e) {
    error.value = message(e)
  }
}

async function openSchema(schema: string): Promise<void> {
  activeSchema.value = schema
  relations.value = []
  activeRelation.value = ''
  columns.value = []
  indexes.value = []
  routines.value = []
  if (datasourceId.value === null) return
  try {
    const [tables, views, funcs, procs, triggers] = await Promise.all([
      api.value.listRelations(datasourceId.value, activeDatabase.value, schema, 'table'),
      api.value.listRelations(datasourceId.value, activeDatabase.value, schema, 'view'),
      api.value.listRoutines(datasourceId.value, activeDatabase.value, schema, 'function'),
      api.value.listRoutines(datasourceId.value, activeDatabase.value, schema, 'procedure'),
      api.value.listRoutines(datasourceId.value, activeDatabase.value, schema, 'trigger'),
    ])
    relations.value = [...tables.items, ...views.items].map((r) => ({ kind: r.kind, name: r.name }))
    routines.value = [...funcs.items, ...procs.items, ...triggers.items]
  } catch (e) {
    error.value = message(e)
  }
}

async function openRelation(r: { kind: 'table' | 'view'; name: string }): Promise<void> {
  activeRelation.value = r.name
  columns.value = []
  indexes.value = []
  if (datasourceId.value === null) return
  try {
    const [cols, idx] = await Promise.all([
      api.value.listColumns(datasourceId.value, activeDatabase.value, r.name, activeSchema.value),
      api.value.listIndexes(datasourceId.value, activeDatabase.value, r.name, activeSchema.value),
    ])
    columns.value = cols.items.map((c) => ({ name: c.name, dataType: c.dataType, nullable: c.nullable, key: c.key }))
    indexes.value = idx.items.map((i) => ({ name: i.name, columns: i.columns, unique: i.unique }))
  } catch (e) {
    error.value = message(e)
  }
}

async function showDefinition(r: RoutineMeta): Promise<void> {
  if (datasourceId.value === null) return
  try {
    const def = await api.value.getDefinition({
      datasourceId: datasourceId.value,
      database: activeDatabase.value,
      objectKind: r.kind,
      objectRef: { schema: activeSchema.value, name: r.name },
    })
    sqlText.value = def.definition
    status.value = `已载入定义：${r.name}（${def.capability}）`
  } catch (e) {
    error.value = message(e)
  }
}

async function runSearch(): Promise<void> {
  if (datasourceId.value === null || keyword.value === '') return
  try {
    const page = await api.value.searchObjects(datasourceId.value, keyword.value)
    searched.value = page.items.map((o) => ({ kind: o.kind, name: o.name, parent: o.parent }))
  } catch (e) {
    error.value = message(e)
  }
}

async function runLint(): Promise<void> {
  if (datasourceId.value === null) return
  diagnostics.value = []
  try {
    diagnostics.value = await api.value.lintSql(datasourceId.value, sqlText.value)
  } catch (e) {
    error.value = message(e)
  }
}

function clearResult(): void {
  resultColumns.value = []
  resultRows.value = []
  resultRowsTotal.value = 0
  resultSetIds.value = []
  currentResultSetIndex.value = 0
  lastHistoryId.value = null
  lastResultSetId.value = null
  resultPage.value = 1
  resultHasMore.value = false
}

async function runSql(): Promise<void> {
  if (!canExecute.value) return
  executing.value = true
  contractError.value = ''
  error.value = ''
  status.value = ''
  diagnostics.value = []
  clearResult()
  currentTaskId.value = `ide-${Date.now()}`
  try {
    const { taskId } = await api.value.executeSql({
      datasourceId: datasourceId.value as number,
      db: activeDatabase.value || null,
      sql: sqlText.value,
      mode: 'auto',
      sessionId: currentTaskId.value,
      clientRequestId: `req-${Date.now()}`,
    })
    currentTaskId.value = taskId
    openStream(taskId)
  } catch (e) {
    contractError.value = message(e)
    executing.value = false
  }
}

function openStream(taskId: string): void {
  const es = api.value.openEventStream(taskId)
  es.addEventListener('result', (ev: MessageEvent) => {
    const data = JSON.parse(ev.data) as SqlResultEvent
    resultColumns.value = data.columns
    resultRows.value = data.rows
    resultRowsTotal.value = data.rowsTotal
    resultSetIds.value = resultSetIds.value.includes(data.resultSetId)
      ? resultSetIds.value
      : [...resultSetIds.value, data.resultSetId]
    lastResultSetId.value = data.resultSetId
    resultPage.value = 1
  })
  es.addEventListener('done', (ev: MessageEvent) => {
    es.close()
    executing.value = false
    const data = JSON.parse(ev.data) as SqlDoneEvent
    lastHistoryId.value = data.historyId
    if (data.status === 'succeeded') {
      status.value = `执行成功：${data.stmtCount} 语句 · ${data.elapsedMs}ms`
    } else if (data.status === 'canceled') {
      status.value = '执行已取消'
    } else {
      contractError.value = '执行失败'
    }
    if (datasourceId.value !== null) void loadHistory()
  })
  es.addEventListener('error', () => {
    es.close()
    executing.value = false
    contractError.value = 'SSE 事件流异常断开'
  })
}

async function cancelRun(): Promise<void> {
  const taskId = currentTaskId.value
  if (!taskId) return
  try {
    await api.value.cancelExecution(taskId)
    status.value = '已请求取消'
  } catch (e) {
    error.value = message(e)
  }
}

async function changePage(page: number): Promise<void> {
  if (lastHistoryId.value === null || lastResultSetId.value === null) return
  const offset = (page - 1) * resultPageSize
  try {
    const result = await api.value.fetchResultPage(lastHistoryId.value, lastResultSetId.value, offset, resultPageSize)
    resultRows.value = result.rows
    resultColumns.value = result.columns
    resultRowsTotal.value = result.rowsTotal
    resultPage.value = page
    resultHasMore.value = offset + result.rows.length < result.rowsTotal
  } catch (e) {
    error.value = message(e)
  }
}

async function loadHistory(): Promise<void> {
  if (datasourceId.value === null) return
  try {
    history.value = await api.value.listHistory(datasourceId.value)
  } catch (e) {
    error.value = message(e)
  }
}

async function openHistory(): Promise<void> {
  historyOpen.value = true
  await loadHistory()
}

function restoreHistory(h: HistoryEntry): void {
  sqlText.value = h.sqlText
}

async function removeHistory(historyId: number): Promise<void> {
  try {
    await api.value.deleteHistory(historyId)
    await loadHistory()
  } catch (e) {
    error.value = message(e)
  }
}

async function saveScript(): Promise<void> {
  try {
    await api.value.saveScript({ name: `脚本-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}`, sqlText: sqlText.value })
    status.value = '脚本已保存'
  } catch (e) {
    error.value = message(e)
  }
}

async function exportCurrent(): Promise<void> {
  if (lastHistoryId.value === null || lastResultSetId.value === null) return
  try {
    const result = await api.value.exportResult({ historyId: lastHistoryId.value, resultSetId: lastResultSetId.value, format: 'csv' })
    status.value = `导出已创建：${result.exportId}`
  } catch (e) {
    error.value = message(e)
  }
}

/** 变量引用：本地语法归类 + 服务端现时解析预览（best-effort）。 */
function refreshVarPreview(): void {
  const parsed = parseVariableReferences(sqlText.value)
  varRefs.value = parsed.refs
  varErrors.value = parsed.syntaxErrors
  varTimes.value = parsed.timeExpressions
  varValues.value = {}
  if (projectId.value === null) return
  for (const ref of parsed.refs) {
    const expression = `\${${ref.scope}.${ref.name}}`
    varApi.value
      .previewResolution(expression, { projectId: projectId.value })
      .then((preview) => {
        varValues.value = { ...varValues.value, [`${ref.scope}.${ref.name}`]: preview.resolvedValue }
      })
      .catch(() => {
        varValues.value = { ...varValues.value, [`${ref.scope}.${ref.name}`]: null }
      })
  }
}

// Keep the variable reference panel in sync with edits made in the SQL editor.
// Without this watcher the initial empty editor was parsed once on mount and
// newly typed `${scope.name}` references remained invisible until a remount.
watch(sqlText, refreshVarPreview)

onMounted(async () => {
  if (projectId.value !== null) selected.value = String(projectId.value)
  await loadProjects()
  await reload()
  refreshVarPreview()
  if (datasourceId.value !== null) await loadHistory()
})
</script>

<style scoped>
.ide-page{max-width:1400px;margin:auto;padding:32px 24px;color:#172033}
.ide-head{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.ide-head h1{margin:0}
.ide-head p{margin:4px 0 0;color:#64748b;flex-basis:100%;font-size:13px}
.ide-actions{display:flex;align-items:center;gap:10px;margin-left:auto;flex-wrap:wrap}
.ide-project,.ide-ds{display:flex;align-items:center;gap:6px}
.ide-project select,.ide-ds select{padding:7px 10px;min-width:150px}
button{cursor:pointer;padding:7px 12px}
button:disabled{cursor:not-allowed;opacity:.5}
.ide-split{display:grid;grid-template-columns:minmax(300px,.7fr) minmax(520px,1.3fr);gap:20px;margin-top:16px;align-items:start}
.ide-left,.ide-right{border:1px solid #e2e8f0;border-radius:8px;padding:16px;background:#fff}
.ide-left h2{margin:0 0 8px;font-size:15px}
.ide-left h3{margin:16px 0 8px;font-size:13px;color:#334155}
.ide-search{display:flex;flex-direction:column;gap:4px;font-size:12px;color:#475569}
.ide-search input{padding:6px 8px}
.ide-cap{font-size:12px;color:#2563eb;margin:8px 0 0}
.ide-muted{color:#64748b;font-size:12px;margin:6px 0 0}
.ide-tree{list-style:none;padding:0;margin:0;display:grid;gap:4px;align-content:start}
.ide-tree button{width:100%;text-align:left;border:1px solid #e2e8f0;background:#fff;border-radius:6px;padding:6px 9px;cursor:pointer;display:flex;justify-content:space-between;gap:8px}
.ide-tree button.active{border-color:#2563eb;background:#eff6ff}
.ide-search-result{display:flex;flex-wrap:wrap;gap:6px}
.ide-search-result span{border:1px solid #e2e8f0;border-radius:6px;padding:4px 8px;display:flex;flex-direction:column}
.ide-search-result small{color:#64748b}
.ide-editor-head{display:flex;align-items:center;gap:10px;margin-bottom:8px}
.ide-editor-title{font-weight:600}
.ide-right textarea{width:100%;box-sizing:border-box;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px;line-height:1.5;padding:8px;border:1px solid #cbd5e1;border-radius:6px;color:#172033;background:#fff}
.ide-diag{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 0}
.pill{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;background:#f1f5f9;color:#64748b}
.pill.error{background:#fee2e2;color:#b91c1c}
.pill.warning{background:#fef3c7;color:#b45309}
.pill.info{background:#dbeafe;color:#1d4ed8}
.ide-vars{margin-top:12px;border-top:1px solid #e2e8f0;padding-top:8px}
.ide-vars h3{margin:0 0 6px;font-size:13px}
.ide-var{display:flex;gap:8px;margin:4px 0;font-size:12px}
.ide-err{color:#b91c1c;font-size:12px;margin:4px 0}
.ide-result{margin-top:16px}
.ide-result-head{display:flex;align-items:center;gap:14px;margin-bottom:8px;flex-wrap:wrap}
.ide-result-nav{display:flex;align-items:center;gap:8px;margin-left:auto}
table{width:100%;border-collapse:collapse;background:#fff}
th,td{text-align:left;padding:9px;border-bottom:1px solid #e2e8f0;font-size:12px;vertical-align:top}
.ide-history{border:1px solid #e2e8f0;border-radius:8px;padding:16px;background:#fff;margin-top:16px}
.ide-history header{display:flex;align-items:center;justify-content:space-between}
.ide-history h2{margin:0;font-size:15px}
.ide-history ul{list-style:none;padding:0;margin:8px 0 0;display:grid;gap:6px}
.ide-history li{display:flex;align-items:center;gap:8px}
.ide-history-item{flex:1;display:flex;flex-direction:column;gap:2px;text-align:left;border:1px solid #e2e8f0;background:#fff;border-radius:6px;padding:6px 9px;cursor:pointer}
.ide-history-del{flex:none}
.ide-history-open{margin-top:16px}
.mono,code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}
@media(max-width:900px){.ide-split{grid-template-columns:1fr}}
</style>
