<script setup lang="ts">
/**
 * 资源脚本编辑弹窗（资源管理列表「修改」入口）。
 *
 * 能力面：
 *  - 读正文：getResourceVersionContent 读取当前最新版本 UTF-8 文本；
 *  - 校验：checkResourceScript(execute=false) 服务端静态校验（SQL 用 sqlglot 方言解析、
 *    Python 用 ast、Shell 用 bash -n/sh -n，并做 ${resource.<name>} 跨资源引用与表名提示）；
 *  - 试运行：SQL 走 dbx；Python/Shell 走所选 SSH 节点并回传 stdout/stderr/退出码；
 *  - 保存：appendResourceVersion 按 resource_id 追加不可变版本（不会因改名新建资源）。
 * 语法层存在 error 时禁止保存；内容变更后旧的校验结论自动失效，保存前会重跑静态校验。
 *
 * 编辑器统一由 CodeEditor（CodeMirror 6）承载，本组件不再内联编辑器实现；
 * 标题下环境状态栏标明所选执行目标；目标主机的软件版本由实际运行结果决定。
 */
import { computed, onMounted, ref } from 'vue'
import { useDraggable } from '../../composables/useDraggable'
import CodeEditor from '../../components/CodeEditor.vue'
import {
  createResourceContract,
  type ResourceMeta,
  type ResourceVersion,
  type ScriptCheckResult,
  type ScriptDiagnostic,
  type ScriptEnvironment,
} from '../../services/rebuild/resourceApi'
import { createVariableContract } from '../../services/rebuild/variableApi'
import { createDbxContract, type DbxConnection, type DbxObject } from '../../services/rebuild/dbxApi'
import { sshNodeApi, type SshNodeRecord } from '../../services/rebuild/sshNodeApi'

const props = defineProps<{ projectId: number; resource: ResourceMeta }>()
const emit = defineEmits<{ close: []; saved: [version: ResourceVersion] }>()

const api = createResourceContract()
const variableApi = createVariableContract()
const dbxApi = createDbxContract(props.projectId)
const dialogRef = ref<HTMLElement | null>(null)
const handleRef = ref<HTMLElement | null>(null)
const { dragStyle, onHandlePointerdown } = useDraggable(dialogRef, handleRef, { storageKey: 'resource.editor' })

const content = ref('')
const originalContent = ref('')
const checkedContent = ref('')
const checkResult = ref<ScriptCheckResult | null>(null)
const environment = ref<ScriptEnvironment | null>(null)
const envError = ref('')
const loading = ref(false)
const checking = ref(false)
const running = ref(false)
const saving = ref(false)
const error = ref('')
const notice = ref('')

/* ---------- S1 编辑器能力面（补全 / lint / 变量分色 / hover）上下文 ---------- */

/** 表字段补全项（结构对齐 CodeEditor.EditorTableColumn） */
type EditorTableColumn = { name: string; dataType?: string }
/** lint 提供方返回项（结构对齐 CodeEditor.EditorLintItem，1 基行列） */
type EditorLintItem = { line: number; col: number; severity: 'error' | 'warning' | 'info'; message: string }

const variables = ref<Array<{ scope: string; name: string }>>([])
/** 变量清单读取成功后才启用「未定义」判定，读取失败时全部按已定义处理（避免假阳性告警） */
const variablesReady = ref(false)
const datasources = ref<DbxConnection[]>([])
const selectedDatasourceId = ref<string | null>(null)
const databases = ref<string[]>([])
const selectedDatabase = ref<string | null>(null)
const schemas = ref<string[]>([])
const relations = ref<DbxObject[]>([])
const datasourceError = ref('')
const trialNodes = ref<SshNodeRecord[]>([])
const selectedTrialNodeId = ref<number | null>(null)
/** 当前补全所用 schema（listSchemas 首个；不可得时回退数据源配置库名） */
const activeSchema = ref<string | null>(null)
let datasourceSeq = 0
let relationsSeq = 0

const isSql = computed(() => props.resource.kind === 'sql')
const selectedDatasource = computed(() => datasources.value.find((item) => item.id === selectedDatasourceId.value) ?? null)
const editorVariables = computed(() => (variablesReady.value ? variables.value : undefined))
const relationNames = computed(() => relations.value.map((item) => item.name))
/** 数据源切换 → 编辑器清空字段/解析缓存 */
const completionContextKey = computed(() => `${props.projectId}:${selectedDatasourceId.value ?? 'none'}`)

const kindLabel = computed(() => ({ sql: 'SQL', python: 'Python', shell: 'Shell' })[props.resource.kind])
const busy = computed(() => loading.value || checking.value || running.value || saving.value)
const dirty = computed(() => content.value !== originalContent.value)
const nextVersion = computed(() => props.resource.latestVersion + 1)
const allDiagnostics = computed<ScriptDiagnostic[]>(() => {
  const result = checkResult.value
  if (!result) return []
  return [...result.syntax.diagnostics, ...result.references]
})
const syntaxLabel = computed(() => {
  const status = checkResult.value?.syntax.status
  return status === 'ok' ? '通过' : status === 'error' ? '存在错误' : status === 'skipped' ? '已跳过（无校验器）' : ''
})
const statusText = computed(() => {
  if (loading.value) return '正在读取内容…'
  if (checking.value) return '正在校验…'
  if (running.value) return '正在试运行…'
  if (saving.value) return '正在保存…'
  if (notice.value) return notice.value
  return dirty.value ? '有未保存修改' : ''
})

/* ---------- 环境状态栏 ---------- */

/** 运行位置由 SQL 连接或 SSH 试运行节点决定。 */
const locationText = computed(() => {
  if (!isSql.value) {
    const node = trialNodes.value.find((item) => item.id === selectedTrialNodeId.value)
    return node ? `SSH 试运行节点 · ${node.name} (${node.host})` : '请选择可试运行的 SSH 节点'
  }
  return selectedDatasource.value && selectedDatabase.value
    ? `dbx SQL · ${selectedDatasource.value.name} / ${selectedDatabase.value}`
    : '请选择 dbx 连接与数据库'
})

/** 本地静态检查环境不能代表远程试运行主机。 */
const languageText = computed(() => {
  if (props.resource.kind === 'sql') return 'SQL 方言由 dbx 连接决定'
  return '解释器及依赖以所选 SSH 主机为准'
})

const outputText = computed(() => (environment.value ? environment.value.output.label : ''))

/* ---------- 诊断映射 ---------- */

/** 服务端诊断 → CodeEditor 诊断（message 前缀 code，便于对照校验结果表） */
const editorDiagnostics = computed(() =>
  allDiagnostics.value.map((item) => ({
    line: item.line,
    column: item.column,
    severity: item.severity,
    message: `${item.code}：${item.message}`,
  })),
)

/* ---------- 数据流 ---------- */

async function loadEnvironment(): Promise<void> {
  try {
    environment.value = await api.getScriptEnvironment(props.projectId)
  } catch (cause) {
    envError.value = cause instanceof Error ? cause.message : '环境信息读取失败'
  }
}

async function loadContent(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const payload = await api.getResourceVersionContent(props.resource.resourceId, props.resource.latestVersion, props.projectId)
    originalContent.value = payload.content
    checkedContent.value = ''
    checkResult.value = null
    content.value = payload.content
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '内容读取失败'
  } finally {
    loading.value = false
  }
}

/* ---------- S1 能力面数据源 ---------- */

async function loadVariables(): Promise<void> {
  try {
    const list = await variableApi.listVariables(props.projectId)
    variables.value = list.map((item) => ({ scope: item.scope, name: item.name }))
    variablesReady.value = true
  } catch {
    // 变量清单不可得时退化为「全部视为已定义」，不干扰编辑
    variablesReady.value = false
  }
}

async function loadDatasources(): Promise<void> {
  if (!isSql.value) return
  const seq = ++datasourceSeq
  try {
    const connections = await dbxApi.listConnections()
    if (seq !== datasourceSeq) return
    datasources.value = connections
    if (connections.length > 0) {
      selectedDatasourceId.value = connections[0].id
      void onDatasourceChange()
    }
  } catch (cause) {
    if (seq !== datasourceSeq) return
    datasourceError.value = cause instanceof Error ? cause.message : '数据源清单加载失败'
  }
}

async function loadTrialNodes(): Promise<void> {
  if (isSql.value) return
  try {
    trialNodes.value = await sshNodeApi.trialCandidates()
    selectedTrialNodeId.value = trialNodes.value[0]?.id ?? null
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : 'SSH 试运行节点读取失败'
  }
}

/** dbx 对象树按连接、库、schema 逐级加载。 */
async function onDatasourceChange(): Promise<void> {
  relations.value = []
  databases.value = []
  schemas.value = []
  selectedDatabase.value = null
  activeSchema.value = null
  datasourceError.value = ''
  const ds = selectedDatasource.value
  if (!ds) return
  const seq = ++relationsSeq
  try {
    const list = await dbxApi.listDatabases(ds.id)
    if (seq !== relationsSeq) return
    databases.value = list.map((item) => item.name).filter(Boolean)
    selectedDatabase.value = databases.value.includes(ds.database ?? '') ? ds.database! : databases.value[0] ?? null
    await onDatabaseChange()
  } catch (cause) {
    if (seq !== relationsSeq) return
    datasourceError.value = cause instanceof Error ? cause.message : '数据库清单加载失败'
  }
}

async function onDatabaseChange(): Promise<void> {
  relations.value = []
  schemas.value = []
  activeSchema.value = null
  const ds = selectedDatasource.value
  const database = selectedDatabase.value
  if (!ds || !database) return
  const seq = ++relationsSeq
  try {
    const list = await dbxApi.listSchemas(ds.id, database)
    if (seq !== relationsSeq) return
    schemas.value = list
    activeSchema.value = list[0] ?? null
    await onSchemaChange()
  } catch (cause) {
    if (seq !== relationsSeq) return
    datasourceError.value = cause instanceof Error ? cause.message : 'Schema 清单加载失败'
  }
}

async function onSchemaChange(): Promise<void> {
  relations.value = []
  const ds = selectedDatasource.value
  const database = selectedDatabase.value
  const schema = activeSchema.value
  if (!ds || !database || !schema) return
  const seq = ++relationsSeq
  try {
    const list = await dbxApi.listObjects(ds.id, database, schema)
    if (seq === relationsSeq) relations.value = list
  } catch (cause) {
    if (seq === relationsSeq) datasourceError.value = cause instanceof Error ? cause.message : '对象清单加载失败'
  }
}

/** 表字段懒加载（`table.` 触发） */
async function loadTableColumns(table: string): Promise<EditorTableColumn[]> {
  const ds = selectedDatasource.value
  if (!ds || !selectedDatabase.value || !activeSchema.value) return []
  const columns = await dbxApi.listColumns(ds.id, selectedDatabase.value, activeSchema.value, table)
  return columns.map((item) => ({ name: item.name, dataType: item.data_type ?? item.dataType }))
}

/** 500ms 防抖 lint：后端静态校验诊断（lint 不依赖数据源真实连通） */
async function lintSqlContent(text: string): Promise<EditorLintItem[]> {
  try {
    const result = await api.checkResourceScript({ projectId: props.projectId, resourceId: props.resource.resourceId, content: text, execute: false })
    return result.syntax.diagnostics.filter((item) => item.line !== null).map((item) => ({
      line: item.line!,
      col: item.column ?? 1,
      severity: item.severity,
      message: `${item.code}：${item.message}`,
    }))
  } catch {
    return []
  }
}

/** 变量引用 hover：现时解析值，null 表示未定义 */
async function resolveVariableHover(expression: string): Promise<string | null> {
  try {
    const preview = await variableApi.previewResolution(expression, { projectId: props.projectId })
    return preview.resolvedValue
  } catch {
    return null
  }
}

async function requestCheck(execute: boolean): Promise<ScriptCheckResult | null> {
  try {
    if (execute && !isSql.value) {
      if (selectedTrialNodeId.value === null) throw new Error('请先选择可试运行的 SSH 节点')
      const trial = await api.trialScriptOnSsh({
        projectId: props.projectId, resourceId: props.resource.resourceId,
        nodeId: selectedTrialNodeId.value, content: content.value,
      })
      checkResult.value = trial
      checkedContent.value = content.value
      notice.value = trial.run?.executed ? '试运行完成' : '脚本校验未通过'
      return trial
    }
    const result = await api.checkResourceScript({
      projectId: props.projectId,
      resourceId: props.resource.resourceId,
      content: content.value,
      execute: false,
    })
    if (execute && isSql.value && result.syntax.status !== 'error') {
      const connection = selectedDatasource.value
      const database = selectedDatabase.value
      if (!connection || !database) throw new Error('请先选择 dbx 连接与数据库')
      const output = await dbxApi.executeSql({
        connectionId: connection.id,
        database,
        schemaName: activeSchema.value ?? undefined,
        sql: content.value,
        maxRows: 100,
      })
      result.run = { executed: true, exitCode: 0, stdout: JSON.stringify(output, null, 2).slice(0, 32000), stderr: '' }
    }
    checkResult.value = result
    checkedContent.value = content.value
    notice.value = execute ? '试运行完成' : '校验完成'
    return result
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : (execute ? '试运行失败' : '校验失败')
    return null
  }
}

async function runCheck(execute: boolean): Promise<void> {
  if (busy.value) return
  error.value = ''
  notice.value = ''
  if (!content.value.trim()) {
    error.value = '脚本内容不能为空'
    return
  }
  if (execute) running.value = true
  else checking.value = true
  try {
    await requestCheck(execute)
  } finally {
    running.value = false
    checking.value = false
  }
}

async function save(): Promise<void> {
  if (busy.value) return
  error.value = ''
  notice.value = ''
  if (!content.value.trim()) {
    error.value = '脚本内容不能为空'
    return
  }
  if (!dirty.value) {
    error.value = '内容未修改，无需保存新版本'
    return
  }
  saving.value = true
  try {
    if (checkedContent.value !== content.value) {
      const result = await requestCheck(false)
      if (result === null) return
      if (result.syntax.status === 'error') {
        error.value = '存在语法错误，已阻止保存；请修正后重新校验'
        return
      }
    } else if (checkResult.value?.syntax.status === 'error') {
      error.value = '存在语法错误，已阻止保存；请修正后重新校验'
      return
    }
    const version = await api.appendResourceVersion({
      projectId: props.projectId,
      resourceId: props.resource.resourceId,
      filename: props.resource.name,
      content: content.value,
    })
    emit('saved', version)
    emit('close')
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '保存失败'
  } finally {
    saving.value = false
  }
}

function resetContent(): void {
  if (busy.value) return
  error.value = ''
  notice.value = '已还原为当前版本内容'
  content.value = originalContent.value
  checkResult.value = null
  checkedContent.value = ''
}

function position(item: ScriptDiagnostic): string {
  if (item.line === null) return '-'
  return item.column === null ? `第 ${item.line} 行` : `${item.line}:${item.column}`
}

function close(): void {
  if (saving.value) return
  emit('close')
}

onMounted(() => {
  void loadEnvironment()
  void loadContent()
  void loadVariables()
  void loadDatasources()
  void loadTrialNodes()
})
</script>

<template>
  <div class="mask" data-script-editor-mask @click.self="close">
    <section
      ref="dialogRef"
      class="script-dialog"
      role="dialog"
      aria-modal="true"
      :aria-label="`${resource.name} 脚本编辑`"
      :style="dragStyle"
    >
      <header ref="handleRef" @pointerdown="onHandlePointerdown">
        <div>
          <h2>{{ resource.name }}</h2>
          <p>{{ kindLabel }} · 当前 v{{ resource.latestVersion }} · 保存后生成 v{{ nextVersion }}</p>
        </div>
        <button type="button" data-close-editor aria-label="关闭脚本编辑" @click="close">关闭</button>
      </header>

      <div class="env-bar" data-env-bar>
        <span class="env-item" data-env-location title="试运行实际执行位置">
          <em>运行位置</em>{{ locationText }}
        </span>
        <span v-if="languageText" class="env-item" data-env-language title="该脚本语言的实际运行环境">
          <em>{{ kindLabel }} 环境</em>{{ languageText }}
        </span>
        <span v-if="outputText" class="env-item" data-env-output title="试运行结果的展示位置">
          <em>输出位置</em>{{ outputText }}
        </span>
        <span v-if="envError" class="env-item error" data-env-error title="运行环境探测失败，不影响编辑与校验">
          <em>环境探测</em>{{ envError }}
        </span>
      </div>

      <div class="toolbar">
        <button type="button" class="mini-btn" data-check-script :disabled="busy || !content.trim()" @click="runCheck(false)">校验</button>
        <button type="button" class="mini-btn" data-run-script :disabled="busy || !content.trim()" @click="runCheck(true)">试运行</button>
        <button type="button" class="mini-btn primary" data-save-version :disabled="busy || !content.trim()" @click="save">保存新版本</button>
        <button type="button" class="mini-btn" data-reset-content :disabled="busy || !dirty" @click="resetContent">还原</button>
        <label v-if="isSql" class="ds-select" title="选择数据连接，SQL 试运行也使用此连接">
          数据连接
          <select v-model="selectedDatasourceId" data-completion-datasource @change="onDatasourceChange()">
            <option :value="null">不启用</option>
            <option v-for="ds in datasources" :key="ds.id" :value="ds.id">{{ ds.name }}</option>
          </select>
        </label>
        <label v-if="isSql && selectedDatasourceId" class="ds-select">数据库
          <select v-model="selectedDatabase" data-dbx-database @change="onDatabaseChange()">
            <option v-for="database in databases" :key="database" :value="database">{{ database }}</option>
          </select>
        </label>
        <label v-if="isSql && selectedDatabase" class="ds-select">Schema
          <select v-model="activeSchema" data-dbx-schema @change="onSchemaChange()">
            <option v-for="schema in schemas" :key="schema" :value="schema">{{ schema }}</option>
          </select>
        </label>
        <label v-if="!isSql" class="ds-select">SSH 试运行节点
          <select v-model.number="selectedTrialNodeId" data-trial-ssh-node>
            <option :value="null">请选择</option>
            <option v-for="node in trialNodes" :key="node.id" :value="node.id">{{ node.name }} ({{ node.host }})</option>
          </select>
        </label>
        <span v-if="!isSql && trialNodes.length === 0" class="ds-error" data-trial-empty-hint>暂无可试运行节点：请在「部署运维 → SSH 试运行节点」编辑节点并勾选「允许脚本试运行」。</span>
        <span v-if="!isSql" class="ds-select">试运行节点不决定正式运行的 Worker 分组。</span>
        <span v-if="datasourceError" class="ds-error" data-datasource-error>{{ datasourceError }}</span>
        <span v-if="statusText" class="status" role="status" data-editor-status>{{ statusText }}</span>
      </div>

      <p v-if="error" class="error" role="alert" data-editor-error>{{ error }}</p>

      <div class="body">
        <div v-if="loading" class="loading" role="status">正在读取 v{{ resource.latestVersion }} 内容…</div>
        <div v-show="!loading" class="editor-workspace">
          <aside v-if="isSql" class="object-tree" aria-label="数据对象树" data-dbx-object-tree>
            <strong>{{ selectedDatabase ?? '请选择数据库' }}<template v-if="activeSchema"> / {{ activeSchema }}</template></strong>
            <p v-if="!selectedDatasource">选择数据连接后浏览对象</p>
            <p v-else-if="!relations.length">当前 schema 暂无对象</p>
            <ul v-else><li v-for="relation in relations" :key="relation.name" :title="relation.object_type ?? relation.type ?? ''">{{ relation.name }}</li></ul>
          </aside>
          <CodeEditor
            v-model="content"
            class="editor-host"
            :language="resource.kind"
            :diagnostics="editorDiagnostics"
            :variables="editorVariables"
            :relation-names="isSql ? relationNames : undefined"
            :columns-provider="isSql ? loadTableColumns : undefined"
            :lint-provider="isSql ? lintSqlContent : undefined"
            :hover-provider="resolveVariableHover"
            :completion-context-key="completionContextKey"
            data-script-code-host
          />
        </div>

        <section v-if="checkResult" class="result" data-check-result>
          <h3>校验结果 <span :class="['badge', checkResult.syntax.status]">{{ syntaxLabel }}</span></h3>
          <table v-if="allDiagnostics.length">
            <thead><tr><th>级别</th><th>来源</th><th>位置</th><th>代码</th><th>说明</th></tr></thead>
            <tbody>
              <tr v-for="(item, index) in allDiagnostics" :key="index" :class="item.severity">
                <td>{{ item.severity }}</td>
                <td>{{ item.source }}</td>
                <td>{{ position(item) }}</td>
                <td><code>{{ item.code }}</code></td>
                <td>{{ item.message }}</td>
              </tr>
            </tbody>
          </table>
          <p v-else class="ok">未发现语法或引用问题</p>
        </section>

        <section v-if="checkResult?.run" class="run" data-run-log>
          <h3>试运行日志</h3>
          <p v-if="!checkResult.run.executed" class="warn">
            {{ checkResult.run.reason }}<template v-if="checkResult.run.message"> · {{ checkResult.run.message }}</template>
          </p>
          <template v-else>
            <p class="meta">
              exit={{ checkResult.run.exitCode }} · 耗时 {{ checkResult.run.elapsedMs }}ms
              <template v-if="checkResult.run.timedOut"> · 已超时（{{ checkResult.run.timeoutSeconds }}s）</template>
            </p>
            <pre class="stdout" data-run-stdout>{{ checkResult.run.stdout || '(无标准输出)' }}</pre>
            <pre v-if="checkResult.run.stderr" class="stderr" data-run-stderr>{{ checkResult.run.stderr }}</pre>
          </template>
        </section>
      </div>
    </section>
  </div>
</template>

<style scoped>
/* 超宽档：86% 宽 + top 5vh，编辑器弹窗统一档位（对齐前端构建方案 §弹窗宽度档位纪律） */
.mask{position:fixed;inset:0;z-index:30;display:flex;align-items:flex-start;justify-content:center;padding:5vh 24px 24px;background:var(--mask-bg)}
.script-dialog{display:flex;flex-direction:column;width:86%;max-width:1440px;height:90vh;padding:22px;background:var(--card);border-radius:10px;box-shadow:0 20px 45px color-mix(in srgb, var(--text) 20%, transparent)}
.script-dialog>header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:10px;cursor:grab;user-select:none}
.script-dialog>header:active{cursor:grabbing}
.script-dialog h2,.script-dialog p{margin:0}
.script-dialog header p{color:var(--text-2);font-size:12px}
.env-bar{display:flex;flex-wrap:wrap;gap:6px 16px;margin-bottom:10px;padding:8px 10px;border:1px solid var(--border);border-radius:var(--radius-sm);background:color-mix(in srgb, var(--text) 3%, transparent);font-size:12px;color:var(--text-2)}
.env-item{display:inline-flex;gap:6px;align-items:baseline;overflow-wrap:anywhere}
.env-item em{font-style:normal;color:var(--text-3);opacity:.8}
.env-item.error{color:var(--danger)}
.toolbar{display:flex;align-items:center;gap:8px;margin-bottom:10px;flex-wrap:wrap}
.ds-select{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--text-2)}
.ds-select select{padding:2px 6px;font-size:12px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--card);color:var(--text)}
.ds-error{font-size:12px;color:var(--danger)}
.status{font-size:12px;color:var(--text-2)}
.body{display:flex;flex-direction:column;gap:0;flex:1;min-height:0;overflow:auto}
.editor-host{height:340px;flex:none;border:1px solid var(--border);border-radius:var(--radius-sm);overflow:hidden;background:var(--card)}
.editor-workspace{display:grid;grid-template-columns:minmax(180px,220px) minmax(0,1fr);gap:10px;min-height:340px}
.editor-workspace:not(:has(.object-tree)){grid-template-columns:minmax(0,1fr)}
.object-tree{min-height:340px;max-height:440px;overflow:auto;border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px;background:var(--card);font-size:12px}
.object-tree strong{display:block;overflow-wrap:anywhere}.object-tree p{color:var(--text-2)}.object-tree ul{margin:8px 0 0;padding:0;list-style:none}.object-tree li{padding:4px 2px;border-bottom:1px solid var(--border);overflow-wrap:anywhere}
@media(max-width:700px){.editor-workspace{grid-template-columns:1fr}.object-tree{min-height:0;max-height:120px}}
.loading{padding:16px;color:var(--text-2)}
.error{color:var(--danger);font-size:13px;margin-bottom:8px}
.result,.run{margin-top:14px}
.result h3,.run h3{display:flex;align-items:center;gap:8px;margin:0 0 8px;font-size:13px}
.badge{padding:1px 8px;border-radius:999px;font-size:11px;font-weight:400;border:1px solid currentColor}
.badge.ok{color:var(--success)}.badge.error{color:var(--danger)}.badge.skipped{color:var(--warn)}
.result table{width:100%;border-collapse:collapse;font-size:12px}
.result th,.result td{padding:6px 8px;border-bottom:1px solid var(--border);text-align:left;vertical-align:top}
.result tr.error td:first-child{color:var(--danger)}
.result tr.warning td:first-child{color:var(--warn)}
.result code{overflow-wrap:anywhere}
.result .ok{color:var(--success);font-size:12px}
.run .meta{font-size:12px;color:var(--text-2)}
.run .warn{font-size:12px;color:var(--warn)}
.run pre{margin:6px 0 0;padding:10px;max-height:200px;overflow:auto;background:color-mix(in srgb, var(--text) 6%, transparent);border-radius:6px;font-size:12px;white-space:pre-wrap;overflow-wrap:anywhere}
.run .stderr{color:var(--danger)}
</style>
