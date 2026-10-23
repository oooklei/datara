<template>
  <main class="ds-page" aria-label="数据源管理">
    <header class="ds-head">
      <div>
        <h1>数据源管理</h1>
        <p>按项目注册数据库连接并测试连通性；凭据仅写入请求体，服务端响应不回显密码。</p>
      </div>
      <div class="ds-actions">
        <label class="ds-project">项目
          <select v-model="selected" data-project-select @change="reload">
            <option value="">请选择项目</option>
            <option v-for="p in projects" :key="p.id" :value="String(p.id)">{{ p.name }}</option>
          </select>
        </label>
        <button type="button" data-create :disabled="projectId === null" @click="openCreate">注册数据源</button>
      </div>
    </header>

    <!-- 错误横幅独立于内容态：加载失败时无数据可渲染，操作失败时列表须保留 -->
    <p v-if="error" role="alert" data-error>{{ error }}</p>
    <p v-if="testMessage" role="status" data-test-result>{{ testMessage }}</p>
    <p v-if="busy" role="status">正在加载…</p>
    <p v-else-if="projectId === null" data-no-project>请先选择项目</p>
    <p v-else-if="rows.length === 0 && !error" data-empty>暂无数据源</p>

    <div v-else-if="rows.length > 0" class="ds-split">
      <table data-ds-list>
        <thead>
          <tr><th>数据源</th><th>主机</th><th>用户名</th><th>状态</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id" :data-ds-id="row.id"
              :class="{ active: row.id === selectedId }" @click="selectDatasource(row.id)">
            <td>
              <b>{{ row.name }}</b>
              <small>#{{ row.id }} · {{ kindLabel(row.kind) }}</small>
            </td>
            <td>
              <span class="mono">{{ row.host }}:{{ row.port }}</span>
              <small>{{ row.database }}</small>
            </td>
            <td>{{ row.username }}</td>
            <td>
              <span :class="['pill', testClass(row.id)]">{{ testText(row.id) }}</span>
            </td>
            <td class="ds-row-actions" @click.stop>
              <button type="button" data-test :disabled="testingId === row.id" @click="runTest(row)">
                {{ testingId === row.id ? '测试中…' : '测试' }}
              </button>
              <button type="button" data-edit @click="openEdit(row)">编辑</button>
              <button type="button" data-delete @click="removeRow(row)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>

      <aside v-if="selectedId !== null" data-detail>
        <h2>{{ selectedRow?.name ?? '数据源' }} 元数据</h2>
        <p class="ds-meta">库（schema）/ 对象（表·视图）/ 字段三级浏览；字段仅作结构参照。</p>

        <section>
          <h3>库</h3>
          <p v-if="schemas.length === 0" class="ds-muted">无库或加载失败</p>
          <ul class="ds-tree" data-schema-list>
            <li v-for="schema in schemas" :key="schema">
              <button type="button" :class="{ active: schema === activeSchema }" @click="selectSchema(schema)">
                {{ schema }}
              </button>
            </li>
          </ul>
        </section>

        <section v-if="activeSchema">
          <h3>对象 · {{ activeSchema }}</h3>
          <p v-if="objects.length === 0" class="ds-muted">无对象或加载失败</p>
          <ul class="ds-tree" data-object-list>
            <li v-for="obj in objects" :key="`${obj.schema}.${obj.name}`">
              <button type="button" :class="{ active: obj.name === activeObject }" @click="selectObject(obj)">
                {{ obj.name }}<small>{{ obj.type === 'view' ? '视图' : '表' }}</small>
              </button>
            </li>
          </ul>
        </section>

        <section v-if="activeObject">
          <h3>字段 · {{ activeSchema }}.{{ activeObject }}</h3>
          <p v-if="columns.length === 0" class="ds-muted">无字段或加载失败</p>
          <table v-else data-column-list>
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
      <form role="dialog" aria-modal="true" aria-label="注册数据源" @submit.prevent="save">
        <h2>{{ form.id === null ? '注册数据源' : '编辑数据源' }}</h2>
        <label>名称<input v-model.trim="form.name" required maxlength="128" data-name></label>
        <label>类型
          <select v-model="form.kind" data-kind>
            <option value="mysql">MySQL</option>
            <option value="postgresql">PostgreSQL</option>
          </select>
        </label>
        <label>主机<input v-model.trim="form.host" required maxlength="256" data-host></label>
        <label>端口<input v-model.number="form.port" type="number" min="1" max="65535" required data-port></label>
        <label>数据库<input v-model.trim="form.database" required maxlength="128" data-database></label>
        <label>用户名<input v-model.trim="form.username" required maxlength="128" data-username></label>
        <label>密码<input v-model="form.password" type="password" maxlength="256" data-password
                   :placeholder="form.id === null ? '' : '留空则不修改'"></label>
        <footer>
          <button type="button" data-cancel @click="closeEditor">取消</button>
          <button type="submit" data-save>保存</button>
        </footer>
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
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  createDatasourceContract,
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
const activeSchema = ref('')
const objects = ref<{ schema: string; name: string; type: 'table' | 'view' }[]>([])
const activeObject = ref('')
const columns = ref<
  { name: string; dataType: string; databaseType: string; nullable: boolean; primaryKey: boolean }[]
>([])

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
    schemas.value = page.items
  } catch (e) {
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
.ds-page{max-width:1220px;margin:auto;padding:32px 24px;color:#172033}
.ds-head{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.ds-head h1{margin:0}
.ds-head p{margin:4px 0 0;color:#64748b;flex-basis:100%}
.ds-actions{display:flex;align-items:center;gap:12px;margin-left:auto}
.ds-project{display:flex;align-items:center;gap:8px}
.ds-project select{padding:7px 10px;min-width:180px}
button{cursor:pointer;padding:7px 12px}
button:disabled{cursor:not-allowed;opacity:.5}
.ds-split{display:grid;grid-template-columns:minmax(520px,1fr) minmax(320px,.9fr);gap:20px;margin-top:8px;align-items:start}
table{width:100%;border-collapse:collapse;background:#fff}
th,td{text-align:left;padding:11px;border-bottom:1px solid #e2e8f0;vertical-align:top}
tbody tr{cursor:pointer}
tbody tr:hover{background:#f8fafc}
tbody tr.active{background:#eff6ff}
.ds-row-actions{display:flex;gap:6px;white-space:nowrap}
.mono{font-family:ui-monospace,monospace;font-size:12px}
small{display:block;color:#64748b;font-size:11px;font-weight:400}
.pill{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;background:#f1f5f9;color:#64748b}
.pill.ok{background:#dcfce7;color:#15803d}
.pill.warn{background:#fef3c7;color:#b45309}
aside{border:1px solid #e2e8f0;border-radius:8px;padding:16px;background:#fff}
aside h2{margin:0 0 8px}
aside h3{margin:16px 0 8px;font-size:14px;color:#334155}
.ds-meta,.ds-muted{color:#64748b;font-size:12px}
.ds-tree{list-style:none;padding:0;margin:0;display:grid;gap:4px;align-content:start}
.ds-tree button{width:100%;text-align:left;border:1px solid #e2e8f0;background:#fff;border-radius:6px;padding:7px 9px;cursor:pointer;display:flex;justify-content:space-between;gap:8px}
.ds-tree button.active{border-color:#2563eb;background:#eff6ff}
.mask{position:fixed;inset:0;background:#0f172a66;display:grid;place-items:center}
.mask form{width:min(520px,calc(100vw - 40px));display:grid;gap:12px;background:#fff;padding:24px;border-radius:10px}
.mask label{display:grid;gap:5px}
.mask input,.mask select{padding:8px}
.mask footer{display:flex;justify-content:flex-end;gap:8px}
@media(max-width:900px){.ds-split{grid-template-columns:1fr}}
</style>
