<template>
  <main class="pg" aria-label="数据源管理">
    <header class="pg-head">
      <h1 class="sec-head">数据源管理</h1>
      <p class="pg-desc">按项目注册数据库连接并测试连通性；凭据仅写入请求体，服务端响应不回显密码。</p>
    </header>

    <div class="toolbar">
      <button type="button" class="tb-new" data-create :disabled="projectId === null" @click="openCreate">
        注册数据源
      </button>
      <span class="spacer"></span>
      <span v-if="testMessage" class="result-line" role="status" data-test-result>{{ testMessage }}</span>
    </div>
    <div class="toolbar ds-filters" aria-label="数据源筛选">
      <input v-model.trim="filterKeyword" data-filter-keyword placeholder="搜索名称、主机或数据库">
      <select v-model="filterKind" data-filter-kind aria-label="数据源类型">
        <option value="">全部类型</option>
        <option value="mysql">MySQL</option>
        <option value="postgresql">PostgreSQL</option>
      </select>
      <select v-model="filterStatus" data-filter-status aria-label="连通状态">
        <option value="">全部状态</option>
        <option value="online">在线</option>
        <option value="offline">离线</option>
        <option value="untested">未测试</option>
      </select>
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
          <span class="pill info">{{ filteredRows.length }} / {{ rows.length }}</span>
          <span class="spacer"></span>
          <span class="hint">点击行查看元数据三级结构</span>
        </div>
        <table class="tbl" data-ds-list>
          <thead>
            <tr><th>数据源</th><th>主机</th><th>用户名</th><th>状态</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="row in filteredRows" :key="row.id" :data-ds-id="row.id"
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
                <button type="button" class="op-btn" data-detail-action @click="selectDatasource(row.id)">详情</button>
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

    <!-- §7.4 三步向导：①选择类型 → ②连接信息 → ③保存并测试；编辑直进连接步 -->
    <div v-if="wizardVisible" class="mask" @click.self="wizardVisible = false">
      <div ref="wizardDlgRef" class="dlg" role="dialog" aria-modal="true" :aria-label="wizardTitle" data-wizard :style="wizardDragStyle">
        <div ref="wizardHdRef" class="dlg-hd" @pointerdown="onWizardDragStart">
          {{ wizardTitle }}
          <button type="button" class="x" aria-label="关闭" @click="wizardVisible = false">×</button>
        </div>
        <div class="dlg-bd">
          <p v-if="wizardError" class="err-box" role="alert" data-wiz-error>{{ wizardError }}</p>
          <ol class="wiz-steps" data-wiz-steps>
            <li v-for="(label, i) in WIZARD_STEPS" :key="label" :class="{ on: wizardStep === i, done: wizardStep > i }">{{ label }}</li>
          </ol>

          <!-- ① 选择类型 -->
          <div v-if="wizardStep === 0" data-wiz-step-type>
            <template v-for="group in TYPE_GROUPS" :key="group.group">
              <div class="wiz-group">{{ group.group }}</div>
              <div class="wiz-grid">
                <button
                  v-for="card in group.cards"
                  :key="card.kind"
                  type="button"
                  class="wiz-card"
                  :class="{ picked: wizardKind === card.kind }"
                  :data-wiz-type="card.kind"
                  @click="pickType(card)"
                >
                  <span class="type-icon" :class="card.kind">{{ card.kind === 'mysql' ? 'My' : 'Pg' }}</span>
                  <span class="wiz-card-txt"><b>{{ card.name }}</b><i>{{ card.tip }}</i></span>
                </button>
              </div>
            </template>
            <p class="hint">Kafka/Redis/MQTT/HTTP 流源与文件源暂无 rebuild 注册契约，按 G09 隐藏。</p>
            <label class="f-item full wiz-name">
              <span>数据源名称</span>
              <input v-model.trim="wizardName" data-wiz-name maxlength="128" placeholder="如：订单库-生产">
            </label>
          </div>

          <!-- ② 连接信息 -->
          <div v-else-if="wizardStep === 1" class="form-grid" data-wiz-step-conn>
            <label class="f-item">
              <span>主机</span>
              <input v-model.trim="wizardHost" maxlength="256" data-host>
            </label>
            <label class="f-item">
              <span>端口</span>
              <input v-model.number="wizardPort" type="number" min="1" max="65535" data-port>
            </label>
            <label class="f-item">
              <span>数据库</span>
              <input v-model.trim="wizardDatabase" maxlength="128" data-database>
            </label>
            <label class="f-item">
              <span>用户名</span>
              <input v-model.trim="wizardUsername" maxlength="128" data-username>
            </label>
            <label class="f-item full">
              <span>密码</span>
              <span class="pwd-wrap">
                <input v-model="wizardPassword" :type="showPwd ? 'text' : 'password'" maxlength="256"
                       data-password autocomplete="new-password" :placeholder="editingRow ? '留空则保持原密码' : ''">
                <button type="button" class="pwd-eye" data-pwd-eye :title="showPwd ? '隐藏密码' : '显示密码'"
                        @click="showPwd = !showPwd">{{ showPwd ? '隐藏' : '显示' }}</button>
              </span>
            </label>
          </div>

          <!-- ③ 保存并测试 -->
          <div v-else class="wiz-final" data-wiz-step-test>
            <div class="sub-summary">
              <div class="sum-row"><span>类型</span><b>{{ kindLabel(wizardKind || 'mysql') }}</b></div>
              <div class="sum-row"><span>名称</span><b>{{ wizardName || '—' }}</b></div>
              <div class="sum-row"><span>目标</span><b class="mono">{{ wizardHost }}:{{ wizardPort }} / {{ wizardDatabase || '—' }}</b></div>
            </div>
            <div class="wiz-actions">
              <button type="button" class="op-btn primary" data-save-test :disabled="saving || testing" @click="saveAndTest">
                {{ saving ? '保存中…' : testing ? '测试中…' : (editingRow ? '保存修改并测试' : (savedId !== null ? '保存并重新测试' : '完成注册并测试')) }}
              </button>
              <button v-if="savedId !== null && testOutcome" type="button" class="op-btn" data-retest :disabled="testing" @click="retestOnly">
                重新测试
              </button>
            </div>
            <div v-if="testOutcome" class="wiz-banner" :class="testOutcome.ok ? 'is-ok' : 'is-fail'" data-wiz-banner>
              <b>{{ testOutcome.ok ? '✓' : '✗' }}</b>
              <span>{{ testOutcome.ok ? testOutcome.text : `连通失败：${testOutcome.text}` }}</span>
            </div>
            <p v-if="testOutcome && !testOutcome.ok && savedId !== null" class="hint">
              数据源已注册（#{{ savedId }}），可返回上一步调整参数后点「重新测试」。
            </p>
          </div>
        </div>
        <div class="dlg-ft">
          <button v-if="wizardStep > 0" type="button" class="op-btn" data-wiz-prev @click="wizardStep--">← 上一步</button>
          <button v-if="wizardStep < 2" type="button" class="op-btn primary" data-wiz-next @click="goNext">下一步 →</button>
          <button v-else type="button" class="op-btn" @click="wizardVisible = false">关闭</button>
        </div>
      </div>
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
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useDraggable } from '../../composables/useDraggable'
import {
  createDatasourceContract,
  type DatasourceColumn,
  type DatasourceContract,
  type DatasourceDraft,
  type DatasourceKind,
  type DatasourceRecord,
} from '../../services/rebuild/datasourceApi'

const route = useRoute()

const rows = ref<DatasourceRecord[]>([])
const busy = ref(false)
const error = ref('')

const selectedId = ref<number | null>(null)
const testingId = ref<number | null>(null)
const testMessage = ref('')
const testStates = ref<Record<number, 'online' | 'offline'>>({})
const filterKeyword = ref('')
const filterKind = ref<'' | DatasourceKind>('')
const filterStatus = ref<'' | 'online' | 'offline' | 'untested'>('')

const schemas = ref<string[]>([])
let schemaRequest = 0
let objectRequest = 0
let columnRequest = 0
const activeSchema = ref('')
const objects = ref<{ schema: string; name: string; type: 'table' | 'view' }[]>([])
const activeObject = ref('')
const columns = ref<DatasourceColumn[]>([])

/* ---- §7.4 三步向导（严格复刻旧 DataSourceWizard 形态）----
 * ①选择类型 → ②连接信息 → ③保存并测试；编辑模式跳过类型直进连接步（标题「编辑数据源」）。
 * 类型卡片仅 mysql/postgresql：旧前端的 Kafka/Redis/MQTT/HTTP/文件源注册在新后端 rebuild
 * datasource 契约无对应端点（contracts.py 仅 {mysql,postgresql}），按 G09 隐藏并注明。 */
const WIZARD_STEPS = ['选择类型', '连接信息', '保存并测试'] as const
const TYPE_GROUPS: { group: string; cards: { kind: DatasourceKind; name: string; port: number; tip: string }[] }[] = [
  {
    group: '连接型数据库',
    cards: [
      { kind: 'mysql', name: 'MySQL', port: 3306, tip: '默认端口 3306' },
      { kind: 'postgresql', name: 'PostgreSQL', port: 5432, tip: '默认端口 5432' },
    ],
  },
]

const wizardVisible = ref(false)
const wizardStep = ref(0)

/* G14 §2.2：弹窗默认可拖动 + 视口钳制 + 位置记忆（把手=标题栏） */
const wizardDlgRef = ref<HTMLElement | null>(null)
const wizardHdRef = ref<HTMLElement | null>(null)
const { dragStyle: wizardDragStyle, onHandlePointerdown: onWizardDragStart } = useDraggable(wizardDlgRef, wizardHdRef, { storageKey: 'ds.wizard' })

const editingRow = ref<DatasourceRecord | null>(null)
const wizardKind = ref<'' | DatasourceKind>('')
const wizardName = ref('')
const wizardHost = ref('')
const wizardPort = ref<number>(3306)
const wizardDatabase = ref('')
const wizardUsername = ref('')
const wizardPassword = ref('')
const showPwd = ref(false)
const wizardError = ref('')
const saving = ref(false)
const testing = ref(false)
const savedId = ref<number | null>(null)
const testOutcome = ref<{ ok: boolean; text: string } | null>(null)

const wizardTitle = computed(() => {
  if (editingRow.value) return '编辑数据源'
  const n = wizardName.value.trim()
  return n ? `注册数据源:${n}` : '注册数据源'
})

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
  return routeProjectId.value
})

const selectedRow = computed(() => rows.value.find((row) => row.id === selectedId.value) ?? null)
const filteredRows = computed(() => {
  const keyword = filterKeyword.value.toLowerCase()
  return rows.value.filter((row) => {
    const state = testStates.value[row.id] ?? 'untested'
    return (!keyword || `${row.name} ${row.host} ${row.database} ${row.username}`.toLowerCase().includes(keyword))
      && (!filterKind.value || row.kind === filterKind.value)
      && (!filterStatus.value || state === filterStatus.value)
  })
})

const testClass = (id: number): string =>
  testingId.value === id ? 'warn' : testStates.value[id] === 'online' ? 'ok' : testStates.value[id] === 'offline' ? 'danger' : 'off'
const testText = (id: number): string => testingId.value === id ? '测试中' : testStates.value[id] === 'online' ? '在线' : testStates.value[id] === 'offline' ? '离线' : '未测试'

async function reload(): Promise<void> {
  schemaRequest += 1
  objectRequest += 1
  columnRequest += 1
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
  objectRequest += 1
  columnRequest += 1
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
  const request = ++objectRequest
  columnRequest += 1
  activeSchema.value = schema
  activeObject.value = ''
  columns.value = []
  if (projectId.value === null || selectedId.value === null) return
  try {
    const page = await api.value.listObjects(selectedId.value, schema)
    if (request !== objectRequest || activeSchema.value !== schema) return
    objects.value = page.items
  } catch (e) {
    if (request !== objectRequest || activeSchema.value !== schema) return
    error.value = message(e)
  }
}

async function selectObject(obj: { schema: string; name: string; type: 'table' | 'view' }): Promise<void> {
  const request = ++columnRequest
  activeObject.value = obj.name
  columns.value = []
  if (projectId.value === null || selectedId.value === null) return
  try {
    const page = await api.value.listColumns(selectedId.value, obj.schema, obj.name)
    if (request !== columnRequest || activeSchema.value !== obj.schema || activeObject.value !== obj.name) return
    columns.value = page.items
  } catch (e) {
    if (request !== columnRequest || activeSchema.value !== obj.schema || activeObject.value !== obj.name) return
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
    testStates.value = { ...testStates.value, [row.id]: 'online' }
    testMessage.value = `连通成功：${probe.database} · ${probe.serverVersion}`
  } catch (e) {
    failure = message(e)
    testStates.value = { ...testStates.value, [row.id]: 'offline' }
  } finally {
    testingId.value = null
    if (failure !== '') error.value = failure
  }
}

function resetWizard(): void {
  wizardStep.value = 0
  editingRow.value = null
  wizardKind.value = ''
  wizardName.value = ''
  wizardHost.value = ''
  wizardPort.value = 3306
  wizardDatabase.value = ''
  wizardUsername.value = ''
  wizardPassword.value = ''
  showPwd.value = false
  wizardError.value = ''
  saving.value = false
  testing.value = false
  savedId.value = null
  testOutcome.value = null
}

function openCreate(): void {
  if (projectId.value === null) return
  resetWizard()
  wizardVisible.value = true
}

/** 编辑直进连接步（§7.4：跳过类型选择），密码不回填，留空 = 保持原密码。 */
function openEdit(row: DatasourceRecord): void {
  if (projectId.value === null) return
  resetWizard()
  editingRow.value = row
  wizardStep.value = 1
  wizardKind.value = row.kind
  wizardName.value = row.name
  wizardHost.value = row.host
  wizardPort.value = row.port
  wizardDatabase.value = row.database
  wizardUsername.value = row.username
  wizardVisible.value = true
}

/** 类型卡片：选中即带出该类型默认端口（复刻旧 pickType）。 */
function pickType(card: { kind: DatasourceKind; port: number }): void {
  wizardKind.value = card.kind
  wizardPort.value = card.port
}

function goNext(): void {
  wizardError.value = ''
  if (wizardStep.value === 0) {
    if (!wizardKind.value) { wizardError.value = '请先选择数据源类型'; return }
    if (!wizardName.value.trim()) { wizardError.value = '请填写数据源名称'; return }
    wizardStep.value = 1
  } else if (wizardStep.value === 1) {
    if (!wizardHost.value.trim()) { wizardError.value = '请填写主机地址'; return }
    if (!wizardPort.value) { wizardError.value = '请填写端口'; return }
    if (!wizardDatabase.value.trim()) { wizardError.value = '请填写数据库名'; return }
    if (!wizardUsername.value.trim()) { wizardError.value = '请填写用户名'; return }
    wizardStep.value = 2
  }
}

/** 保存并测试闭环：create/update → test；连通成功关窗刷新，失败呈现 banner 可改参重试。
 *  savedId 固化首建行：失败后重试走 update，不重复 create（避免名称已存在误报）。 */
async function saveAndTest(): Promise<void> {
  if (projectId.value === null || saving.value || testing.value) return
  if (!wizardKind.value) return
  saving.value = true
  wizardError.value = ''
  try {
    const payload: DatasourceDraft = {
      name: wizardName.value.trim(),
      kind: wizardKind.value,
      host: wizardHost.value.trim(),
      port: wizardPort.value,
      database: wizardDatabase.value.trim(),
      username: wizardUsername.value.trim(),
      password: wizardPassword.value || undefined,
    }
    let id: number
    if (editingRow.value) {
      await api.value.updateDatasource(editingRow.value.id, payload)
      id = editingRow.value.id
    } else if (savedId.value !== null) {
      await api.value.updateDatasource(savedId.value, payload)
      id = savedId.value
    } else {
      const record = await api.value.createDatasource(payload)
      id = record.id
      savedId.value = id
    }
    saving.value = false
    testing.value = true
    try {
      const probe = await api.value.testDatasource(id)
      testOutcome.value = { ok: true, text: `连通成功（${probe.serverVersion}）：${probe.database}` }
      wizardVisible.value = false
      testMessage.value = testOutcome.value.text
      await reload()
    } catch (e) {
      testOutcome.value = { ok: false, text: message(e) }
    } finally {
      testing.value = false
    }
  } catch (e) {
    wizardError.value = message(e)
  } finally {
    saving.value = false
  }
}

/** 创建后测试失败场景：仅重测（不再重复创建/更新）。 */
async function retestOnly(): Promise<void> {
  if (projectId.value === null || savedId.value === null || testing.value) return
  testing.value = true
  wizardError.value = ''
  try {
    const probe = await api.value.testDatasource(savedId.value)
    testOutcome.value = { ok: true, text: `连通成功（${probe.serverVersion}）：${probe.database}` }
    wizardVisible.value = false
    testMessage.value = testOutcome.value.text
    await reload()
  } catch (e) {
    testOutcome.value = { ok: false, text: message(e) }
  } finally {
    testing.value = false
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
  await reload()
})
</script>

<style scoped>
/* 仅保留全局类无法表达的布局/语义态；颜色一律走令牌 */
.ds-split{display:grid;grid-template-columns:minmax(520px,1fr) minmax(320px,.9fr);gap:14px;align-items:start}
.ds-row-actions{display:flex;gap:6px;white-space:nowrap}
.ds-filters{justify-content:flex-start}.ds-filters input{min-width:240px}.ds-filters input,.ds-filters select{padding:7px 10px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--card);color:var(--text)}
.tbl tbody tr{cursor:pointer}
.tbl tbody tr.active td{background:var(--primary-light)}
/* ---- §7.4 三步向导 ---- */
.wiz-steps{display:flex;gap:8px;margin:0 0 14px;padding:0;list-style:none}
.wiz-steps li{flex:1;text-align:center;font-size:12px;color:var(--text-3);padding:6px 0;border-bottom:2px solid var(--border)}
.wiz-steps li.on{color:var(--primary);border-color:var(--primary);font-weight:600}
.wiz-steps li.done{color:var(--success);border-color:var(--success)}
.wiz-group{font-size:12px;color:var(--text-3);margin:10px 0 6px;font-weight:600}
.wiz-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}
.wiz-card{display:flex;gap:9px;align-items:center;border:1px solid var(--border-strong);border-radius:var(--radius);padding:10px;cursor:pointer;background:#fff;text-align:left;color:var(--text)}
.wiz-card:hover{border-color:var(--primary)}
.wiz-card.picked{border-color:var(--primary);box-shadow:0 0 0 2px var(--primary-light)}
.wiz-card-txt b{display:block;font-size:13px}
.wiz-card-txt i{font-style:normal;font-size:11px;color:var(--text-3)}
.type-icon{width:36px;height:36px;border-radius:9px;display:flex;align-items:center;justify-content:center;color:#fff;font-size:13px;font-weight:600;flex-shrink:0}
.type-icon.mysql{background:#0ea958}
.type-icon.postgresql{background:#336791}
.wiz-name{margin-top:14px}
.pwd-wrap{position:relative;display:block;width:100%}
.pwd-wrap input{width:100%;padding-right:52px}
.pwd-eye{position:absolute;right:6px;top:50%;transform:translateY(-50%);border:none;background:none;cursor:pointer;color:var(--text-3);font-size:11.5px;padding:2px}
.pwd-eye:hover{color:var(--primary)}
.wiz-actions{margin-top:14px;display:flex;gap:10px;align-items:center}
.wiz-banner{display:flex;gap:8px;align-items:center;border-radius:var(--radius-sm);padding:10px 12px;font-size:12.5px;margin-top:12px}
.wiz-banner.is-ok{background:var(--success-bg);color:var(--success)}
.wiz-banner.is-fail{background:var(--danger-bg);color:var(--danger)}
.sub-summary{background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px 12px}
.sum-row{display:flex;gap:10px;font-size:12.5px;padding:3px 0}
.sum-row span{width:48px;color:var(--text-3);flex-shrink:0}
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
