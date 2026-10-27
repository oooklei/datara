<template>
  <main class="ide-page" aria-label="数据开发IDE">
    <header class="ide-head">
      <div>
        <h1>数据开发 IDE</h1>
        <p>R5-A 只读态：对象树（库·Schema·表/视图/例程/索引）→ 写 SQL（含变量引用）→ 执行 → 结果网格 → 历史。DDL 写路径归增量 16/R5-B。</p>
      </div>
      <div class="ide-actions">
        <label class="ide-ds">数据源
          <select v-model="selectedDs" data-ds-select @change="selectDatasource(Number(selectedDs))">
            <option value="">请选择数据源</option>
            <option v-for="d in datasources" :key="d.id" :value="String(d.id)">{{ d.name }}</option>
          </select>
        </label>
        <button type="button" data-variable-manage :disabled="projectId === null" @click="variableManagementOpen = true">变量管理</button>
        <button type="button" data-execute :disabled="!canExecute" @click="runSql">
          {{ executing ? '执行中…' : '执行' }}
        </button>
        <button type="button" data-cancel :disabled="!executing || cancelBusy" @click="cancelRun">{{ cancelBusy ? '取消中…' : '取消' }}</button>
      </div>
    </header>

    <!-- 错误横幅独立于内容态：加载失败不丢上下文，执行失败保留编辑器 -->
    <p v-if="error" role="alert" data-error>{{ error }}</p>
    <p v-if="contractError" role="alert" data-contract-error>{{ contractError }}</p>
    <p v-if="status" role="status" data-status>{{ status }}</p>
    <p v-if="projectId === null" data-no-project>请先选择项目</p>
    <p v-else-if="datasourceId === null" data-no-datasource>请先选择数据源</p>

    <Splitpanes v-else class="ide-split" data-ide-workspace @resized="onIdeResize('workspace', $event)">
      <Pane :size="ideSplit.workspace[0]">
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
      </Pane>

      <Pane :size="ideSplit.workspace[1]">
      <section class="ide-right">
        <Splitpanes horizontal class="ide-editor-split" @resized="onIdeResize('editor', $event)">
        <Pane :size="ideSplit.editor[0]">
        <div class="ide-editor-pane">
        <div class="ide-editor-head">
          <span class="ide-editor-title">SQL</span>
          <button type="button" data-lint :disabled="sqlText.trim() === '' || datasourceId === null" @click="runLint">语法检查</button>
          <button type="button" data-format :disabled="sqlText.trim() === ''" @click="formatCurrentSql">格式化</button>
          <button type="button" data-var-check :disabled="varCheckBusy || projectId === null || sqlText.trim() === ''" @click="checkVariableReferences">
            {{ varCheckBusy ? '变量校验中…' : '变量校验' }}
          </button>
          <button type="button" data-var-complete :disabled="projectId === null" @click="toggleVarSuggestions">插入变量</button>
          <button type="button" data-save-script :disabled="sqlText.trim() === ''" @click="saveScript">存为脚本</button>
          <button type="button" data-export :disabled="lastResultSetId === null || exportBusy" @click="exportCurrent">{{ exportBusy ? '导出中…' : '导出结果' }}</button>
          <button type="button" data-lineage :disabled="projectId === null" @click="openLineage">查看血缘</button>
        </div>
        <SqlCodeEditor ref="sqlEditorEl" v-model="sqlText" placeholder="SELECT … -- 支持变量引用" />

        <p v-if="diagnostics.length" class="ide-diag" data-diagnostics>
          <span v-for="(d, i) in diagnostics" :key="i" :class="['pill', d.severity]">
            L{{ d.line }}:{{ d.col }} {{ d.severity }} {{ d.code }} — {{ d.message }}
          </span>
        </p>
        <p v-if="varCheckError" class="ide-err" data-var-check-error>变量校验失败：{{ varCheckError }}</p>
        <p v-else-if="varCheckResult" class="ide-diag" data-var-check-result>
          <span :class="['pill', varCheckResult.status]">
            {{ varCheckResult.status === 'valid' ? '变量校验通过' : '变量校验未通过' }}
          </span>
          <span v-for="(d, i) in varCheckResult.diagnostics" :key="i" :class="['pill', varCheckResult.status]">
            {{ d.code }} {{ d.label }} — {{ d.message }}
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

        <section v-if="varSuggestionsOpen" class="ide-var-suggestions" data-var-suggestions>
          <h3>插入变量引用</h3>
          <p v-if="varSuggestions.length === 0" class="ide-muted">当前项目暂无可用变量</p>
          <ul v-else>
            <li v-for="s in varSuggestions" :key="`${s.scope}.${s.name}`">
              <button type="button" data-var-suggestion @click="insertVariableRef(s)">
                <code>${{ `${s.scope}.${s.name}` }}</code><small>{{ s.valueType }}</small>
              </button>
            </li>
          </ul>
        </section>
        </div>
        </Pane>

        <Pane :size="ideSplit.editor[1]">
        <div class="ide-results-pane" :data-result-column-count="resultColumns.length">
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
        <div v-else class="ide-result-empty">执行 SQL 后在此查看分页结果</div>
        </div>
        </Pane>
        </Splitpanes>
      </section>
      </Pane>
    </Splitpanes>

    <aside v-if="historyOpen" class="ide-history" data-history data-history-drawer>
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

    <aside v-if="scriptsOpen" class="ide-history" data-scripts>
      <header>
        <h2>SQL 资产</h2>
        <button type="button" data-scripts-toggle @click="scriptsOpen = false">收起</button>
      </header>
      <p v-if="scripts.length === 0" class="ide-muted">暂无已保存脚本</p>
      <ul v-else>
        <li v-for="script in scripts" :key="script.id">
          <button type="button" class="ide-history-item" data-script-open @click="restoreScript(script)">
            <b>{{ script.name }}</b>
            <code>{{ script.sqlText.slice(0, 60) }}</code>
            <small>版本 {{ script.revision }}</small>
          </button>
          <button type="button" class="ide-history-del" data-script-delete @click="removeScript(script)">删除</button>
        </li>
      </ul>
    </aside>
    <button v-else type="button" class="ide-scripts-open" data-scripts-toggle @click="openScripts">SQL 资产</button>
    <GlobalParamDrawer
      v-model="variableManagementOpen"
      :project-id="projectId ?? undefined"
    />
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
 * 范式：CodeMirror 6 编辑器 + splitpanes 持久化工作区，业务操作仍只调用真实后端契约。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Pane, Splitpanes, type SplitpanesResizedPayload } from 'splitpanes'
import { format } from 'sql-formatter'
import GlobalParamDrawer from '../../components/VariableManagementDialog.vue'
import SqlCodeEditor from './SqlCodeEditor.vue'
import 'splitpanes/dist/splitpanes.css'
import {
  createSqlIdeContract,
  type HistoryEntry,
  type RoutineMeta,
  type ScriptEntry,
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
import {
  createVariableContract,
  parseVariableReferences,
  type VariableCompletionItem,
  type VariableContract,
} from '../../services/rebuild/variableApi'
import {
  checkVariableReferenceField,
  defineVariableReferenceField,
  type VariableReferenceCheckViewModel,
} from '../../services/rebuild/variableReferenceField'
import { listProjects, type ProjectSummary } from '../../services/rebuild/projectApi'

const props = defineProps<{ projectId?: number }>()
const route = useRoute()
const router = useRouter()

const IDE_SPLIT_KEY = 'datara.ide.split.v1'
function initialIdeSplit(): { workspace: [number, number]; editor: [number, number] } {
  try {
    const value = JSON.parse(localStorage.getItem(IDE_SPLIT_KEY) ?? '{}') as { workspace?: number[]; editor?: number[] }
    return {
      workspace: value.workspace?.length === 2 ? [value.workspace[0], value.workspace[1]] : [25, 75],
      editor: value.editor?.length === 2 ? [value.editor[0], value.editor[1]] : [58, 42],
    }
  } catch {
    return { workspace: [25, 75], editor: [58, 42] }
  }
}
const ideSplit = ref(initialIdeSplit())

function onIdeResize(area: 'workspace' | 'editor', payload: SplitpanesResizedPayload) {
  if (!Array.isArray(payload.panes) || payload.panes.length !== 2) return
  ideSplit.value = { ...ideSplit.value, [area]: [payload.panes[0].size, payload.panes[1].size] }
  localStorage.setItem(IDE_SPLIT_KEY, JSON.stringify(ideSplit.value))
}

const projects = ref<ProjectSummary[]>([])
const variableManagementOpen = ref(false)
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
const currentEventStream = ref<EventSource | null>(null)
const cancelBusy = ref(false)
const exportBusy = ref(false)
const diagnostics = ref<SqlDiagnostic[]>([])
const contractError = ref('')
const error = ref('')
const status = ref('')

const resultColumns = ref<string[]>([])
const resultRows = ref<unknown[][]>([])
const resultRowsTotal = ref(0)
const resultSetIds = ref<string[]>([])
const currentResultSetIndex = ref(0)
const lastHistoryId = ref<string | number | null>(null)
const lastResultSetId = ref<string | null>(null)
const resultPage = ref(1)
const resultPageSize = 50
const resultHasMore = ref(false)

const varRefs = ref<Array<{ scope: string; name: string }>>([])
const varErrors = ref<string[]>([])
const varTimes = ref<string[]>([])
const varValues = ref<Record<string, string | null>>({})

/** §5B 变量三要求（校验按钮/现时值/补全）：本编辑器作为输入位显式登记（L5-04 契约的首个 UI 消费方）。 */
const sqlReferenceField = defineVariableReferenceField({
  surfaceId: 'ide.sql-editor',
  fieldPath: 'sql',
  label: 'SQL 编辑器',
  inputKind: 'sql',
  allowScopedReference: true,
  allowTimeExpression: true,
})
const sqlEditorEl = ref<{ insertText: (text: string) => void; focus: () => void } | null>(null)
const varCheckBusy = ref(false)
const varCheckResult = ref<VariableReferenceCheckViewModel | null>(null)
const varCheckError = ref('')
const varSuggestionsOpen = ref(false)
const varSuggestions = ref<VariableCompletionItem[]>([])

const history = ref<HistoryEntry[]>([])
const historyOpen = ref(false)
const scripts = ref<ScriptEntry[]>([])
const scriptsOpen = ref(false)
let datasourceGeneration = 0

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
  datasourceGeneration += 1
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
  const generation = datasourceGeneration
  if (projectId.value === null) return
  try {
    const page = await api.value.listDatabases(id)
    if (generation !== datasourceGeneration || datasourceId.value !== id) return
    databases.value = page.items.map((d) => d.name)
    treeCapability.value = page.capability
    treeConstraints.value = page.constraints
  } catch (e) {
    if (generation !== datasourceGeneration || datasourceId.value !== id) return
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

/** G01 终态兜底：SSE 无心跳事件，断线期间用 status 端点轮询收敛，避免 executing 永久悬挂。 */
const TERMINAL_EXECUTION_STATUSES = new Set(['succeeded', 'failed', 'partial_failure', 'canceled', 'timed_out'])
const EXECUTION_POLL_MS = 2000
const EXECUTION_POLL_MAX_FAILURES = 5
const EXECUTION_LONG_WAIT_MS = 60000
let statusPollTimer: ReturnType<typeof setInterval> | null = null
let statusPollFailures = 0
let longWaitTimer: ReturnType<typeof setTimeout> | null = null

function stopStatusPolling(): void {
  if (statusPollTimer !== null) {
    clearInterval(statusPollTimer)
    statusPollTimer = null
  }
  statusPollFailures = 0
}

function clearLongWaitTimer(): void {
  if (longWaitTimer !== null) {
    clearTimeout(longWaitTimer)
    longWaitTimer = null
  }
}

function settleExecution(terminalStatus: string | null): void {
  stopStatusPolling()
  clearLongWaitTimer()
  currentEventStream.value?.close()
  currentEventStream.value = null
  executing.value = false
  if (terminalStatus === 'succeeded') {
    status.value = '执行完成（状态查询确认）；结果集请见执行历史'
  } else if (terminalStatus === 'canceled') {
    status.value = '执行已取消'
  } else if (terminalStatus !== null) {
    contractError.value = '执行失败'
  } else {
    contractError.value = '执行状态查询连续失败，已停止等待；结果可在执行历史中确认'
  }
  if (datasourceId.value !== null) void loadHistory()
}

function startStatusPolling(taskId: string): void {
  if (statusPollTimer !== null) return
  statusPollFailures = 0
  statusPollTimer = setInterval(() => {
    void (async () => {
      try {
        const result = await api.value.getExecutionStatus(taskId)
        if (!executing.value || currentTaskId.value !== taskId) {
          stopStatusPolling()
          return
        }
        statusPollFailures = 0
        if (TERMINAL_EXECUTION_STATUSES.has(result.status)) settleExecution(result.status)
      } catch {
        statusPollFailures += 1
        if (statusPollFailures >= EXECUTION_POLL_MAX_FAILURES) settleExecution(null)
      }
    })()
  }, EXECUTION_POLL_MS)
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
    const execution = await api.value.executeSql({
      datasourceId: datasourceId.value as number,
      db: activeDatabase.value || null,
      sql: sqlText.value,
      mode: 'auto',
      sessionId: currentTaskId.value,
      clientRequestId: `req-${Date.now()}`,
    })
    const { taskId } = execution
    currentTaskId.value = taskId
    if (execution.historyId !== undefined && execution.resultSetId) {
      const result = await api.value.fetchResultPage(execution.historyId, execution.resultSetId, 0, resultPageSize)
      resultColumns.value = result.columns
      resultRows.value = result.rows
      resultRowsTotal.value = result.rowsTotal
      lastHistoryId.value = execution.historyId
      lastResultSetId.value = result.resultSetId
      resultSetIds.value = [result.resultSetId]
      resultPage.value = 1
      resultHasMore.value = result.rows.length < result.rowsTotal
    } else if (execution.columns?.length) {
      resultColumns.value = execution.columns
      resultRows.value = execution.rows ?? []
      resultRowsTotal.value = execution.totalRows ?? execution.rowCount ?? resultRows.value.length
      lastHistoryId.value = execution.historyId ?? null
      lastResultSetId.value = execution.resultSetId ?? null
      resultSetIds.value = execution.resultSetId ? [execution.resultSetId] : []
      resultPage.value = 1
      resultHasMore.value = resultRows.value.length < resultRowsTotal.value
    }
    openStream(taskId)
  } catch (e) {
    contractError.value = message(e)
    executing.value = false
  }
}

function openStream(taskId: string): void {
  currentEventStream.value?.close()
  stopStatusPolling()
  clearLongWaitTimer()
  const es = api.value.openEventStream(taskId)
  currentEventStream.value = es
  es.addEventListener('open', () => {
    if (status.value.startsWith('事件流连接中断')) status.value = ''
    stopStatusPolling()
  })
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
    resultHasMore.value = data.rows.length < data.rowsTotal
  })
  es.addEventListener('done', async (ev: MessageEvent) => {
    es.close()
    stopStatusPolling()
    clearLongWaitTimer()
    if (currentEventStream.value === es) currentEventStream.value = null
    executing.value = false
    const wire = JSON.parse(ev.data) as SqlDoneEvent & {
      history_id?: string | number | null
      result_set_id?: string
      elapsed_ms?: number
      stmt_count?: number
    }
    const data: SqlDoneEvent = {
      ...wire,
      historyId: wire.historyId ?? wire.history_id ?? null,
      elapsedMs: wire.elapsedMs ?? wire.elapsed_ms ?? 0,
      stmtCount: wire.stmtCount ?? wire.stmt_count ?? wire.resultSets?.length ?? resultSetIds.value.length,
    }
    lastHistoryId.value = data.historyId
    const fallbackResultSetId = wire.result_set_id ?? data.resultSets?.[0]?.resultSetId ?? null
    if (resultColumns.value.length === 0 && data.historyId !== null && fallbackResultSetId) {
      try {
        const result = await api.value.fetchResultPage(data.historyId, fallbackResultSetId, 0, resultPageSize)
        resultColumns.value = result.columns
        resultRows.value = result.rows
        resultRowsTotal.value = result.rowsTotal
        lastResultSetId.value = result.resultSetId
        resultSetIds.value = resultSetIds.value.includes(result.resultSetId)
          ? resultSetIds.value
          : [...resultSetIds.value, result.resultSetId]
        resultPage.value = 1
        resultHasMore.value = result.rows.length < result.rowsTotal
      } catch (e) {
        error.value = message(e)
      }
    }
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
    // The authenticated SSE adapter owns Last-Event-ID replay and retries.
    // Keep this run cancellable until a terminal `done` event arrives; while
    // the stream is down, poll the status endpoint as a heartbeat fallback.
    status.value = '事件流连接中断，正在恢复…'
    startStatusPolling(taskId)
  })
  longWaitTimer = setTimeout(() => {
    if (executing.value) status.value = '执行时间较长，可点击取消；执行完成后结果将保留在执行历史'
  }, EXECUTION_LONG_WAIT_MS)
}

async function cancelRun(): Promise<void> {
  const taskId = currentTaskId.value
  if (!taskId || cancelBusy.value) return
  cancelBusy.value = true
  error.value = ''
  try {
    const result = await api.value.cancelExecution(taskId)
    if (!result.canceled) {
      status.value = '取消请求未被接受，任务仍在运行'
      return
    }
    currentEventStream.value?.close()
    currentEventStream.value = null
    stopStatusPolling()
    clearLongWaitTimer()
    executing.value = false
    currentTaskId.value = ''
    status.value = '执行已取消'
  } catch (e) {
    error.value = message(e)
  } finally {
    cancelBusy.value = false
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
  scriptsOpen.value = false
  historyOpen.value = true
  await loadHistory()
}

function restoreHistory(h: HistoryEntry): void {
  sqlText.value = h.sqlText
}

async function removeHistory(historyId: string | number): Promise<void> {
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
    if (scriptsOpen.value) await loadScripts()
  } catch (e) {
    error.value = message(e)
  }
}

async function loadScripts(): Promise<void> {
  try {
    scripts.value = await api.value.listScripts()
  } catch (e) {
    error.value = message(e)
  }
}

async function openScripts(): Promise<void> {
  historyOpen.value = false
  scriptsOpen.value = true
  await loadScripts()
}

function restoreScript(script: ScriptEntry): void {
  sqlText.value = script.sqlText
}

async function removeScript(script: ScriptEntry): Promise<void> {
  try {
    await api.value.deleteScript(script.id, script.revision)
    await loadScripts()
  } catch (e) {
    error.value = message(e)
  }
}

async function exportCurrent(): Promise<void> {
  if (lastHistoryId.value === null || lastResultSetId.value === null || exportBusy.value) return
  exportBusy.value = true
  error.value = ''
  try {
    const result = await api.value.exportResult({ historyId: lastHistoryId.value, resultSetId: lastResultSetId.value, format: 'csv' })
    if (result.status === 'failed') throw new Error(`导出失败：${result.exportId}`)
    if (result.status === 'ready' || result.status === 'completed') {
      const downloadUrl = result.downloadUrl || api.value.getExportDownloadUrl(result.exportId)
      globalThis.open(downloadUrl, '_blank', 'noopener,noreferrer')
      status.value = `导出下载已打开：${result.exportId}`
    } else {
      status.value = `导出任务已创建：${result.exportId}，正在生成`
    }
  } catch (e) {
    error.value = message(e)
  } finally {
    exportBusy.value = false
  }
}

function formatCurrentSql(): void {
  try {
    sqlText.value = format(sqlText.value, { language: 'sql', keywordCase: 'upper' })
    status.value = 'SQL 格式化完成'
  } catch (e) {
    error.value = `SQL 格式化失败：${message(e)}`
  }
}

function openLineage(): void {
  if (projectId.value === null) return
  void router.push({ path: `/p/${projectId.value}/meta/lineage`, query: activeRelation.value ? { object: activeRelation.value } : {} })
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

/** §5B 三要求·校验：显式按钮触发服务端 checkReference，诊断码+消息原样透出（§5B 显式触发语义）。 */
async function checkVariableReferences(): Promise<void> {
  if (projectId.value === null || sqlText.value.trim() === '') return
  varCheckBusy.value = true
  varCheckError.value = ''
  try {
    varCheckResult.value = await checkVariableReferenceField(
      sqlReferenceField,
      sqlText.value,
      { projectId: projectId.value },
      varApi.value,
    )
  } catch (e) {
    varCheckResult.value = null
    varCheckError.value = message(e)
  } finally {
    varCheckBusy.value = false
  }
}

/** §5B 三要求·补全：拉取当前项目可用变量清单，点选后按光标位置插入引用 token。 */
async function toggleVarSuggestions(): Promise<void> {
  varSuggestionsOpen.value = !varSuggestionsOpen.value
  if (!varSuggestionsOpen.value || projectId.value === null) return
  try {
    varSuggestions.value = await varApi.value.completeVariables('', { projectId: projectId.value })
  } catch (e) {
    error.value = message(e)
  }
}

function insertVariableRef(item: VariableCompletionItem): void {
  const token = `\${${item.scope}.${item.name}}`
  if (sqlEditorEl.value) sqlEditorEl.value.insertText(token)
  else sqlText.value = `${sqlText.value}${token}`
}

onMounted(async () => {
  if (projectId.value !== null) selected.value = String(projectId.value)
  await loadProjects()
  await reload()
  refreshVarPreview()
  if (datasourceId.value !== null) await loadHistory()
})
onUnmounted(() => {
  currentEventStream.value?.close()
  stopStatusPolling()
  clearLongWaitTimer()
})
</script>

<style scoped>
/* FE-MERGE-B5: visual values come from the shared r6 token foundation. */
.ide-page{max-width:1400px;margin:auto;padding:32px 24px;color:var(--text)}
.ide-head{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.ide-head h1{margin:0}
.ide-head p{margin:4px 0 0;color:var(--text-2);flex-basis:100%;font-size:13px}
.ide-actions{display:flex;align-items:center;gap:10px;margin-left:auto;flex-wrap:wrap}
.ide-project,.ide-ds{display:flex;align-items:center;gap:6px}
.ide-project select,.ide-ds select{padding:7px 10px;min-width:150px}
button{cursor:pointer;padding:7px 12px}
button:disabled{cursor:not-allowed;opacity:.5}
.ide-split{height:calc(100vh - 190px);min-height:520px;margin-top:16px;border:1px solid var(--border);border-radius:var(--radius);background:var(--card);overflow:hidden}
.ide-split :deep(.splitpanes__splitter){position:relative;background:var(--border);min-width:5px;min-height:5px}.ide-split :deep(.splitpanes__splitter:hover){background:var(--primary)}
.ide-left,.ide-right{height:100%;min-width:0;box-sizing:border-box;background:var(--card)}
.ide-left{padding:16px;overflow:auto}.ide-right{overflow:hidden}.ide-editor-split{height:100%}.ide-editor-pane,.ide-results-pane{height:100%;box-sizing:border-box;padding:12px;overflow:auto}.ide-editor-pane{display:flex;flex-direction:column}.ide-editor-pane .sql-code-editor{flex:1;min-height:220px}
.ide-left h2{margin:0 0 8px;font-size:15px}
.ide-left h3{margin:16px 0 8px;font-size:13px;color:var(--text)}
.ide-search{display:flex;flex-direction:column;gap:4px;font-size:12px;color:var(--text-2)}
.ide-search input{padding:6px 8px}
.ide-cap{font-size:12px;color:var(--primary);margin:8px 0 0}
.ide-muted{color:var(--text-2);font-size:12px;margin:6px 0 0}
.ide-tree{list-style:none;padding:0;margin:0;display:grid;gap:4px;align-content:start}
.ide-tree button{width:100%;text-align:left;border:1px solid var(--border);background:var(--card);border-radius:var(--radius-sm);padding:6px 9px;cursor:pointer;display:flex;justify-content:space-between;gap:8px}
.ide-tree button.active{border-color:var(--primary);background:var(--primary-light)}
.ide-search-result{display:flex;flex-wrap:wrap;gap:6px}
.ide-search-result span{border:1px solid var(--border);border-radius:var(--radius-sm);padding:4px 8px;display:flex;flex-direction:column}
.ide-search-result small{color:var(--text-2)}
.ide-editor-head{display:flex;align-items:center;gap:10px;margin-bottom:8px}
.ide-editor-title{font-weight:600}
.ide-diag{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 0}
.pill{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;background:var(--bg-deep);color:var(--text-2)}
.pill.error,.pill.invalid{background:var(--danger-bg);color:var(--danger)}
.pill.warning{background:var(--warn-bg);color:var(--warn)}
.pill.info,.pill.valid{background:var(--info-bg);color:var(--info)}
.ide-vars{margin-top:12px;border-top:1px solid var(--border);padding-top:8px}
.ide-vars h3{margin:0 0 6px;font-size:13px}
.ide-var{display:flex;gap:8px;margin:4px 0;font-size:12px}
.ide-err{color:var(--danger);font-size:12px;margin:4px 0}
.ide-var-suggestions{margin-top:12px;border-top:1px solid var(--border);padding-top:8px}
.ide-var-suggestions h3{margin:0 0 6px;font-size:13px}
.ide-var-suggestions ul{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:6px}
.ide-var-suggestions li button{display:flex;align-items:center;gap:6px;border:1px solid var(--border);background:var(--card);border-radius:var(--radius-sm);padding:5px 9px}
.ide-var-suggestions small{color:var(--text-2)}
.ide-result{min-height:100%}
.ide-result-empty{display:grid;place-items:center;height:100%;color:var(--text-3);font-size:13px}
.ide-result-head{display:flex;align-items:center;gap:14px;margin-bottom:8px;flex-wrap:wrap}
.ide-result-nav{display:flex;align-items:center;gap:8px;margin-left:auto}
table{width:100%;border-collapse:collapse;background:var(--card)}
th,td{text-align:left;padding:9px;border-bottom:1px solid var(--border);font-size:12px;vertical-align:top}
.ide-history{border:1px solid var(--border);border-radius:var(--radius);padding:16px;background:var(--card);margin-top:16px}
[data-history-drawer]{position:fixed;z-index:80;top:58px;right:0;bottom:0;width:min(420px,92vw);margin:0;border-radius:var(--radius) 0 0 var(--radius);box-shadow:var(--shadow-lg);overflow:auto}
.ide-history header{display:flex;align-items:center;justify-content:space-between}
.ide-history h2{margin:0;font-size:15px}
.ide-history ul{list-style:none;padding:0;margin:8px 0 0;display:grid;gap:6px}
.ide-history li{display:flex;align-items:center;gap:8px}
.ide-history-item{flex:1;display:flex;flex-direction:column;gap:2px;text-align:left;border:1px solid var(--border);background:var(--card);border-radius:var(--radius-sm);padding:6px 9px;cursor:pointer}
.ide-history-del{flex:none}
.ide-history-open,.ide-scripts-open{margin-top:16px}
.mono,code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}
@media(max-width:900px){.ide-split{height:auto;min-height:0;overflow:visible}.ide-split:deep(>.splitpanes__pane){width:100%!important}.ide-split{display:block}.ide-left{max-height:320px}.ide-right{height:720px}}
</style>
