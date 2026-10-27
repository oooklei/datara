<template>
  <main class="pg" aria-label="数据源管理">
    <header class="pg-head">
      <h1 class="sec-head">数据源管理</h1>
      <p class="pg-desc">按项目注册数据库连接并测试连通性；凭据仅写入请求体，服务端响应不回显密码。</p>
    </header>

    <div class="toolbar">
      <label class="field"><span>项目</span>
        <select v-model="selected" class="kw" data-project-select @change="reload">
          <option value="">请选择项目</option>
          <option v-for="p in projects" :key="p.id" :value="String(p.id)">{{ p.name }}</option>
        </select>
      </label>
      <button type="button" class="tb-new" data-create :disabled="projectId === null" @click="openCreate">
        注册数据源
      </button>
      <span class="spacer"></span>
      <span v-if="testMessage" class="result-line" role="status" data-test-result>{{ testMessage }}</span>
    </div>

    <!-- 错误横幅独立于内容态：加载失败时无数据可渲染，操作失败时列表须保留 -->
    <div v-if="error" class="err-box" role="alert" data-error>
      <span>{{ error }}</span>
      <button type="button" class="op-btn retry" :disabled="busy" @click="reload">重试</button>
    </div>

    <!-- 加载态：骨架屏替代「正在加载…」文本，避免布局跳动 -->
    <div v-if="busy" class="panel" role="status" aria-live="polite">
      <div class="skeleton sk-row" style="width: 28%"></div>
      <div class="skeleton sk-row" style="width: 66%"></div>
      <div class="skeleton sk-row" style="width: 48%"></div>
    </div>
    <div v-else-if="projectId === null" class="panel empty" data-no-project>
      <div class="e-title">请先选择项目</div>
      <div class="e-hint">数据源按项目隔离；在上方选择项目后加载该项目的数据源列表。</div>
    </div>
    <div v-else-if="rows.length === 0 && !error" class="panel empty" data-empty>
      <div class="e-title">暂无数据源</div>
      <div class="e-hint">点击「注册数据源」录入连接信息，随后可执行连通性测试。</div>
    </div>
    <div v-else-if="rows.length > 0" class="ds-split">
      <div class="panel">
        <div class="tbl-toolbar">
          <span class="sec-head">数据源</span>
          <span class="pill info">{{ rows.length }}</span>
          <span class="spacer"></span>
          <span class="hint">点击行查看元数据三级结构</span>
        </div>
        <table class="tbl" data-ds-list>
          <thead>
            <tr><th>数据源</th><th>主机</th><th>用户名</th><th>状态</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.id" :data-ds-id="row.id"
                :class="{ active: row.id === selectedId }" @click="selectDatasource(row.id)">
              <td>
                <strong>{{ row.name }}</strong>
                <span>#{{ row.id }} · {{ kindLabel(row.kind) }}</span>
              </td>
              <td>
                <span class="mono">{{ row.host }}:{{ row.port }}</span>
                <span>{{ row.database }}</span>
              </td>
              <td>{{ row.username }}</td>
              <td>
                <span class="pill" :class="testClass(row.id)">{{ testText(row.id) }}</span>
              </td>
              <td class="ds-row-actions" @click.stop>
                <button type="button" class="op-btn" data-test :disabled="testingId === row.id" @click="runTest(row)">
                  {{ testingId === row.id ? '测试中…' : '测试' }}
                </button>
                <button type="button" class="op-btn" data-edit @click="openEdit(row)">编辑</button>
                <button type="button" class="op-btn danger" data-delete @click="removeRow(row)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <aside v-if="selectedId !== null" class="panel" data-detail>
        <span class="sub-hd">{{ selectedRow?.name ?? '数据源' }} 元数据</span>
        <p class="hint">库（schema）/ 对象（表·视图）/ 字段三级浏览；字段仅作结构参照。</p>

        <section>
          <span class="sub-hd">库</span>
          <p v-if="schemas.length === 0" class="hint">无库或加载失败</p>
          <ul v-else class="node-list" data-schema-list>
            <li v-for="schema in schemas" :key="schema">
              <button type="button" :class="{ on: schema === activeSchema }" @click="selectSchema(schema)">
                {{ schema }}
              </button>
            </li>
          </ul>
        </section>

        <section v-if="activeSchema">
          <span class="sub-hd">对象 · {{ activeSchema }}</span>
          <p v-if="objects.length === 0" class="hint">无对象或加载失败</p>
          <ul v-else class="node-list" data-object-list>
            <li v-for="obj in objects" :key="`${obj.schema}.${obj.name}`">
              <button type="button" :class="{ on: obj.name === activeObject }" @click="selectObject(obj)">
                <strong>{{ obj.name }}</strong>
                <span>{{ obj.type === 'view' ? '视图' : '表' }}</span>
              </button>
            </li>
          </ul>
        </section>

        <section v-if="activeObject">
          <span class="sub-hd">字段 · {{ activeSchema }}.{{ activeObject }}</span>
          <p v-if="columns.length === 0" class="hint">无字段或加载失败</p>
          <table v-else class="tbl" data-column-list>
            <thead><tr><th>字段</th><th>类型</th><th>可空</th><th>主键</th></tr></thead>
            <tbody>
              <tr v-for="col in columns" :key="col.name">
                <td>{{ col.name }}</td>
                <td>{{ col.databaseType || col.dataType }}</td>
                <td>{{ col.nullable ? '是' : '否' }}</td>
                <td>{{ col.primaryKey ? '是' : '' }}</td>
              </tr>
            </tbody>
          </table>
        </section>
      </aside>
    </div>

    <div v-if="editing" class="mask" @click.self="closeEditor">
      <form class="dlg" role="dialog" aria-modal="true" aria-label="注册数据源" @submit.prevent="save">
        <div class="dlg-hd">
          {{ form.id === null ? '注册数据源' : '编辑数据源' }}
          <button type="button" class="x" aria-label="关闭" @click="closeEditor">×</button>
        </div>
        <div class="dlg-bd">
          <div class="form-grid">
            <label class="f-item full">
              <span>名称</span>
              <input v-model.trim="form.name" required maxlength="128" data-name>
            </label>
            <label class="f-item">
              <span>类型</span>
              <select v-model="form.kind" data-kind>
                <option value="mysql">MySQL</option>
                <option value="postgresql">PostgreSQL</option>
              </select>
            </label>
            <label class="f-item">
              <span>主机</span>
              <input v-model.trim="form.host" required maxlength="256" data-host>
            </label>
            <label class="f-item">
              <span>端口</span>
              <input v-model.number="form.port" type="number" min="1" max="65535" required data-port>
            </label>
            <label class="f-item">
              <span>数据库</span>
              <input v-model.trim="form.database" required maxlength="128" data-database>
            </label>
            <label class="f-item">
              <span>用户名</span>
              <input v-model.trim="form.username" required maxlength="128" data-username>
            </label>
            <label class="f-item full">
              <span>密码</span>
              <input v-model="form.password" type="password" maxlength="256" data-password
                     :placeholder="form.id === null ? '' : '留空则不修改'">
            </label>
          </div>
        </div>
        <div class="dlg-ft">
          <button type="button" class="op-btn" data-cancel @click="closeEditor">取消</button>
          <button type="submit" class="op-btn primary" data-save>保存</button>
        </div>
      </form>
    </div>
  </main>
</template>

<script setup lang="ts">
/**
 * 增量 10 / 10A：数据源管理页（`/ds/list`）。
 *
 * 契约面：`datasourceApi`（createDatasourceContract）——
 *   列表 / 注册 / 编辑 / 删除 / 连通测试 + 元数据三级浏览（库·对象·字段）。
 * 唯一后端事实源为 rebuild-api(8001)；项目数据由 URL 中的 projectId 隔离，
 *   本契约不调用旧 `/datasources` API，password 仅出现在写请求体。
 * 项目上下文：`/ds/list` 为全局模式路由（AppShell 项目模式仅覆盖 `/p/` 前缀），
 *   故项目段从 `route.params.projectId` 或 `route.query.projectId` 承接；
 *   两者皆空时呈现选择器，不渲染空壳。
 *
 * 样式对标旧前端：页面壳 `.pg/.pg-head/.pg-desc/.toolbar/.panel/.tbl-toolbar/.tbl/.mask/.dlg`
 *   全部取自 theme.css 全局令牌层，无 scoped 裸色值。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  createDatasourceContract,
  type DatasourceColumn,
  type DatasourceContract,
  type DatasourceDraft,
  type DatasourceKind,
  type DatasourceRecord,
} from '../../services/rebuild/datasourceApi'
import { listProjects, type ProjectSummary } from '../../services/rebuild/projectApi'

const route = useRoute()

const projects = ref<ProjectSummary[]>([])
const selected = ref('')
const rows = ref<DatasourceRecord[]>([])
const busy = ref(false)
const error = ref('')
const editing = ref(false)

const selectedId = ref<number | null>(null)
const testingId = ref<number | null>(null)
const testMessage = ref('')

const schemas = ref<string[]>([])
let schemaRequest = 0
const activeSchema = ref('')
const objects = ref<{ schema: string; name: string; type: 'table' | 'view' }[]>([])
const activeObject = ref('')
const columns = ref<DatasourceColumn[]>([])

type DatasourceForm = DatasourceDraft & { id: number | null }
const blankForm = (): DatasourceForm => ({
  id: null,
  name: '',
  kind: 'mysql',
  host: '',
  port: 3306,
  database: '',
  username: '',
  password: '',
})
const form = reactive<DatasourceForm>(blankForm())

const KIND_LABEL: Record<DatasourceKind, string> = { mysql: 'MySQL', postgresql: 'PostgreSQL' }
const kindLabel = (k: DatasourceKind): string => KIND_LABEL[k] ?? k
const message = (e: unknown): string => (e instanceof Error ? e.message : String(e))

const api = computed<DatasourceContract>(() =>
  projectId.value === null ? ({} as DatasourceContract) : createDatasourceContract(projectId.value),
)

/** 项目上下文：route 参数优先，其次 query，最后选择器。 */
const routeProjectId = computed<number | null>(() => {
  const raw = route.params.projectId ?? route.query.projectId
  const value = Array.isArray(raw) ? raw[0] : raw
  const n = Number(value)
  return value !== undefined && value !== '' && Number.isInteger(n) && n > 0 ? n : null
})
const projectId = computed<number | null>(() => {
  const fromRoute = routeProjectId.value
  if (fromRoute !== null) return fromRoute
  const n = Number(selected.value)
  return selected.value !== '' && Number.isInteger(n) && n > 0 ? n : null
})

const selectedRow = computed(() => rows.value.find((row) => row.id === selectedId.value) ?? null)

const testClass = (id: number): string =>
  testingId.value === id ? 'warn' : testMessage.value && selectedId.value === id ? 'ok' : 'off'
const testText = (id: number): string => (testingId.value === id ? '测试中' : '未测试')

async function loadProjects(): Promise<void> {
  try {
    projects.value = (await listProjects()).list
  } catch (e) {
    error.value = message(e)
  }
}

async function reload(): Promise<void> {
  schemaRequest += 1
  selectedId.value = null
  schemas.value = []
  activeSchema.value = ''
  objects.value = []
  activeObject.value = ''
  columns.value = []
  testMessage.value = ''
  if (projectId.value === null) {
    rows.value = []
    return
  }
  busy.value = true
  error.value = ''
  try {
    const page = await api.value.listDatasources()
    rows.value = page.items
  } catch (e) {
    error.value = message(e)
  } finally {
    busy.value = false
  }
}

/** 选中数据源：清空元数据态，加载库列表（测试信息不回写行）。 */
async function selectDatasource(id: number): Promise<void> {
  const request = ++schemaRequest
  selectedId.value = id
  schemas.value = []
  activeSchema.value = ''
  objects.value = []
  activeObject.value = ''
  columns.value = []
  testMessage.value = ''
  if (projectId.value === null) return
  try {
    const page = await api.value.listSchemas(id)
    if (request !== schemaRequest || selectedId.value !== id) return
    schemas.value = page.items
  } catch (e) {
    if (request !== schemaRequest || selectedId.value !== id) return
    error.value = message(e)
  }
}

async function selectSchema(schema: string): Promise<void> {
  activeSchema.value = schema
  activeObject.value = ''
  columns.value = []
  if (projectId.value === null || selectedId.value === null) return
  try {
    const page = await api.value.listObjects(selectedId.value, schema)
    objects.value = page.items
  } catch (e) {
    error.value = message(e)
  }
}

async function selectObject(obj: { schema: string; name: string; type: 'table' | 'view' }): Promise<void> {
  activeObject.value = obj.name
  columns.value = []
  if (projectId.value === null || selectedId.value === null) return
  try {
    const page = await api.value.listColumns(selectedId.value, obj.schema, obj.name)
    columns.value = page.items
  } catch (e) {
    error.value = message(e)
  }
}

async function runTest(row: DatasourceRecord): Promise<void> {
  if (projectId.value === null || testingId.value !== null) return
  testingId.value = row.id
  error.value = ''
  testMessage.value = ''
  let failure = ''
  try {
    const probe = await api.value.testDatasource(row.id)
    testMessage.value = `连通成功：${probe.database} · ${probe.serverVersion}`
  } catch (e) {
    failure = message(e)
  } finally {
    testingId.value = null
    if (failure !== '') error.value = failure
  }
}

function openCreate(): void {
  Object.assign(form, blankForm())
  editing.value = true
}

function openEdit(row: DatasourceRecord): void {
  Object.assign(form, {
    id: row.id,
    name: row.name,
    kind: row.kind,
    host: row.host,
    port: row.port,
    database: row.database,
    username: row.username,
    password: '',
  })
  editing.value = true
}

function closeEditor(): void {
  editing.value = false
}

async function save(): Promise<void> {
  if (projectId.value === null) return
  error.value = ''
  try {
    const payload: DatasourceDraft = {
      name: form.name,
      kind: form.kind,
      host: form.host,
      port: form.port,
      database: form.database,
      username: form.username,
      password: form.password || undefined,
    }
    if (form.id === null) await api.value.createDatasource(payload)
    else await api.value.updateDatasource(form.id, payload)
    editing.value = false
    await reload()
  } catch (e) {
    error.value = message(e)
  }
}

async function removeRow(row: DatasourceRecord): Promise<void> {
  if (projectId.value === null) return
  if (!globalThis.confirm(`删除数据源「${row.name}」？该操作不可恢复。`)) return
  error.value = ''
  try {
    await api.value.deleteDatasource(row.id)
    await reload()
  } catch (e) {
    error.value = message(e)
  }
}

onMounted(async () => {
  if (routeProjectId.value !== null) selected.value = String(routeProjectId.value)
  await loadProjects()
  await reload()
})
</script>

<style scoped>
/* 仅保留全局类无法表达的布局/语义态；颜色一律走令牌 */
.ds-split{display:grid;grid-template-columns:minmax(520px,1fr) minmax(320px,.9fr);gap:14px;align-items:start}
.ds-row-actions{display:flex;gap:6px;white-space:nowrap}
.tbl tbody tr{cursor:pointer}
.tbl tbody tr.active td{background:var(--primary-light)}
td > span{display:block}
td > span.mono{font-size:12px}
td > span:not(.mono){font-size:11px;color:var(--text-3);margin-top:2px}
.node-list button{width:100%;border:none;background:transparent;padding:5px 8px;border-radius:var(--radius-sm);cursor:pointer;font:inherit;font-size:12.5px;color:var(--text-2);display:flex;align-items:center;gap:8px;text-align:left}
.node-list button:hover{background:var(--bg)}
.node-list button.on{background:var(--primary-light);color:var(--primary);font-weight:600}
.node-list button strong{font-weight:600}
.node-list button span{font-size:11px;color:var(--text-3)}
.node-list button.on span{color:var(--primary)}
@media(max-width:900px){.ds-split{grid-template-columns:1fr}}
</style>
