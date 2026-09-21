/**
 * ideStore（I10 §5.1）：IDE 全局状态 Pinia 集中管理。
 * - 实例/实例属性卡/当前库/执行模式/环境组
 * - 脚本 Tab 集合（命名=后端 t_ide_script；未命名=sessionStorage，刷新丢失为需求明确行为，上限 5）
 * - 结果 Tab 集合（每次运行按语句各一 Tab；筛选/分页/日志状态 Tab 内隔离）
 * - 执行任务（POST /ide/execute 异步 + EventSource SSE 消费 + cancel）
 * - 全局参数缓存（env 三分组）+ 内置时间参数 14 项（dayjs 前端预览，镜像 common/vars_render.py）
 * - 补全缓存（树已加载 db→table→column 注入 Monaco 补全）
 * 资源释放：EventSource close / 防抖 cancel 在组件层负责（store 只持引用句柄）。
 */
import { computed, reactive, ref, shallowRef } from 'vue'
import { defineStore } from 'pinia'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import { executeIde, cancelIdeTask, buildStreamUrl, getDsMeta, listGlobalParams } from '../services/ideApi'
import { listDataSources, type DsRow } from '../services/datasourceApi'
import type {
  IdeLogEvent, IdeResultEvent, IdeDoneEvent, DsMeta, GlobalParamRow,
} from '../services/ideApi'

export type IdeTheme = 'datara-dark' | 'datara-light'
export type ExecMode = 'auto' | 'manual'
export type EnvKey = 'dev' | 'staging' | 'prod'
export const ENV_LIST: EnvKey[] = ['dev', 'staging', 'prod']
export const UNNAMED_LIMIT = 5

/* ---------- 内置时间参数 14 项（common/vars_render.py builtin_vars 同口径） ---------- */
export interface BuiltinVar { name: string; value: string; desc: string }

export function builtinVars(now?: dayjs.Dayjs): BuiltinVar[] {
  const n = now ?? dayjs()
  const t1 = n.subtract(1, 'day')
  const monthStart = n.startOf('month')
  const lastMonthEnd = monthStart.subtract(1, 'day')
  const lastMonthStart = lastMonthEnd.startOf('month')
  return [
    { name: 'biz_date', value: t1.format('YYYY-MM-DD'), desc: '业务日期（T-1）' },
    { name: 'biz_date_nodash', value: t1.format('YYYYMMDD'), desc: '业务日期无分隔（T-1）' },
    { name: 'today', value: n.format('YYYY-MM-DD'), desc: '今日日期' },
    { name: 'today_nodash', value: n.format('YYYYMMDD'), desc: '今日日期无分隔' },
    { name: 'year', value: n.format('YYYY'), desc: '当前年份' },
    { name: 'lyear', value: n.subtract(1, 'year').format('YYYY'), desc: '上一年' },
    { name: 'month_start', value: monthStart.format('YYYY-MM-DD'), desc: '当月第一天' },
    { name: 'month_end', value: n.endOf('month').format('YYYY-MM-DD'), desc: '当月最后一天' },
    { name: 'last_month_start', value: lastMonthStart.format('YYYY-MM-DD'), desc: '上月第一天' },
    { name: 'last_month_end', value: lastMonthEnd.format('YYYY-MM-DD'), desc: '上月最后一天' },
    { name: 'hour', value: n.format('HH'), desc: '当前小时' },
    { name: 'timestamp', value: String(n.unix()), desc: '时间戳（秒）' },
    { name: 'datetime', value: n.format('YYYY-MM-DD HH:mm:ss'), desc: '当前日期时间' },
    { name: 'ts_nodash', value: n.format('YYYYMMDDHHmmss'), desc: '年月日时分秒无分隔' },
  ]
}

/* ---------- 脚本 Tab ---------- */
export interface ScriptTab {
  id: string
  name: string
  /** 命名=后端持久化；未命名=sessionStorage */
  named: boolean
  /** 后端脚本 id（命名脚本） */
  scriptId: number | null
  content: string
  datasourceId: number | null
  dbName: string | null
}

/* ---------- 结果 Tab（G17~G20） ---------- */
export type FilterOp = 'include' | 'eq' | 'ne' | 'empty' | 'notEmpty' | 'gt' | 'lt'

export const FILTER_OPS: { value: FilterOp; label: string }[] = [
  { value: 'include', label: '包含' },
  { value: 'eq', label: '等于' },
  { value: 'ne', label: '不等于' },
  { value: 'empty', label: '为空' },
  { value: 'notEmpty', label: '非空' },
  { value: 'gt', label: '大于' },
  { value: 'lt', label: '小于' },
]

export interface ResultFilter { col: number; op: FilterOp; value: string }

export interface ResultTab {
  id: string
  /** Tab 序号（结果 #N） */
  seq: number
  stmtIndex: number
  kind: 'query' | 'exec' | 'error'
  /** 原始语句 SQL（渲染前，回显编辑器用） */
  sql: string
  rendered: string | null
  columns: string[]
  rows: string[][]
  rowsTotal: number
  affected: number
  elapsedMs: number
  historyId: number | null
  error: string | null
  warnings: string[]
  /** 列筛选（仅作用当前内存数据，Tab 隔离） */
  filters: ResultFilter[]
  page: number
  pageSize: number
}

/* ---------- 执行日志 ---------- */
export interface IdeLogLine {
  seq: number
  time: string
  kind: 'start' | 'end' | 'error' | 'vars' | 'txn' | 'info'
  text: string
}

let uidCounter = 0
function uid(): string {
  uidCounter += 1
  return `t${Date.now().toString(36)}${uidCounter}`
}

const SS_KEY = 'datara.ide.unnamedScripts'
const THEME_KEY = 'datara.ide.theme'

function loadUnnamed(): ScriptTab[] {
  try {
    const raw = sessionStorage.getItem(SS_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as ScriptTab[]
    return Array.isArray(parsed) ? parsed.slice(0, UNNAMED_LIMIT) : []
  } catch {
    return []
  }
}

function saveUnnamed(tabs: ScriptTab[]): void {
  try {
    sessionStorage.setItem(SS_KEY, JSON.stringify(tabs.filter((t) => !t.named)))
  } catch { /* 隐私模式忽略 */ }
}

export const useIdeStore = defineStore('ide', () => {
  /* ================= 实例 / 上下文 ================= */
  const dsList = ref<DsRow[]>([])
  const activeDsId = ref<number | null>(null)
  const dsMeta = shallowRef<DsMeta | null>(null)
  const currentDb = ref('')
  const env = ref<EnvKey>('dev')
  const mode = ref<ExecMode>('auto')
  const theme = ref<IdeTheme>(
    ((): IdeTheme => {
      try {
        const t = localStorage.getItem(THEME_KEY)
        if (t === 'datara-dark' || t === 'datara-light') return t
      } catch { /* 忽略 */ }
      return 'datara-dark'
    })(),
  )

  function toggleTheme(): void {
    theme.value = theme.value === 'datara-dark' ? 'datara-light' : 'datara-dark'
    try { localStorage.setItem(THEME_KEY, theme.value) } catch { /* 忽略 */ }
  }

  const activeDs = computed(() => dsList.value.find((d) => d.id === activeDsId.value) ?? null)

  async function loadDsList(): Promise<void> {
    const rows = await listDataSources()
    dsList.value = rows.filter((r) => r.status === 'online' && (r.type === 'mysql' || r.type === 'greatdb'))
    if (dsList.value.length > 0 && activeDsId.value === null) {
      await selectDs(dsList.value[0].id)
    }
  }

  async function selectDs(id: number): Promise<void> {
    activeDsId.value = id
    currentDb.value = ''
    dsMeta.value = null
    results.value = []
    logs.value = []
    try {
      dsMeta.value = await getDsMeta(id)
      if (dsMeta.value.defaultSchema) currentDb.value = dsMeta.value.defaultSchema
    } catch { /* 属性卡显示连接失败态，不阻断 IDE */ }
  }

  function setCurrentDb(db: string): void {
    currentDb.value = db
  }

  /* ================= 脚本 Tab（G16） ================= */
  const scripts = ref<ScriptTab[]>(loadUnnamed())
  const activeScriptId = ref<string>(scripts.value[0]?.id ?? '')

  function persistUnnamed(): void {
    saveUnnamed(scripts.value)
  }

  function nextUnnamedSeq(): number {
    let max = 0
    for (const t of scripts.value) {
      const m = /^未命名SQL #(\d+)$/.exec(t.name)
      if (m) max = Math.max(max, Number(m[1]))
    }
    return max + 1
  }

  function newUnnamedScript(content = ''): ScriptTab {
    const unnamed = scripts.value.filter((t) => !t.named)
    if (unnamed.length >= UNNAMED_LIMIT) {
      ElMessage.warning(`未命名脚本最多驻留 ${UNNAMED_LIMIT} 个，请先保存命名脚本`)
      throw new Error('UNNAMED_LIMIT')
    }
    const tab: ScriptTab = {
      id: uid(),
      name: `未命名SQL #${nextUnnamedSeq()}`,
      named: false,
      scriptId: null,
      content,
      datasourceId: activeDsId.value,
      dbName: currentDb.value || null,
    }
    scripts.value.push(tab)
    activeScriptId.value = tab.id
    persistUnnamed()
    return tab
  }

  function ensureActiveTab(): ScriptTab {
    const found = scripts.value.find((t) => t.id === activeScriptId.value)
    if (found) return found
    const tab = newUnnamedScript('')
    return tab
  }

  function setActiveScript(id: string): void {
    activeScriptId.value = id
  }

  function updateScriptContent(id: string, content: string): void {
    const t = scripts.value.find((x) => x.id === id)
    if (t) {
      t.content = content
      if (!t.named) persistUnnamed()
    }
  }

  function renameTab(id: string, name: string, scriptId: number | null): void {
    const t = scripts.value.find((x) => x.id === id)
    if (t) {
      t.name = name
      t.named = true
      t.scriptId = scriptId
      persistUnnamed()
    }
  }

  function closeScript(id: string): void {
    const idx = scripts.value.findIndex((t) => t.id === id)
    if (idx < 0) return
    scripts.value.splice(idx, 1)
    if (activeScriptId.value === id) {
      activeScriptId.value = scripts.value[Math.min(idx, scripts.value.length - 1)]?.id ?? ''
    }
    persistUnnamed()
  }

  /** 打开脚本库的命名脚本为 Tab（已存在同 scriptId Tab 则切换） */
  function openNamedScript(row: { id: number; name: string; content: string; datasourceId: number | null; dbName: string | null }): void {
    const existed = scripts.value.find((t) => t.named && t.scriptId === row.id)
    if (existed) {
      existed.content = row.content
      activeScriptId.value = existed.id
      return
    }
    const tab: ScriptTab = {
      id: uid(), name: row.name, named: true, scriptId: row.id,
      content: row.content, datasourceId: row.datasourceId, dbName: row.dbName,
    }
    scripts.value.push(tab)
    activeScriptId.value = tab.id
  }

  /* ================= 执行（G21/G22） ================= */
  const running = ref(false)
  const taskId = ref('')
  const logs = ref<IdeLogLine[]>([])
  let logSeq = 0
  let es: EventSource | null = null

  const results = ref<ResultTab[]>([])
  const activeResultId = ref('')
  let resultSeq = 0

  function pushLog(kind: IdeLogLine['kind'], text: string): void {
    logSeq += 1
    logs.value.push({ seq: logSeq, time: dayjs().format('HH:mm:ss'), kind, text })
    // 日志内存护栏：超 2000 行丢弃最早部分，防长任务撑爆
    if (logs.value.length > 2000) logs.value.splice(0, logs.value.length - 2000)
  }

  function newResultTab(partial: Partial<ResultTab> & { stmtIndex: number; sql: string }): ResultTab {
    resultSeq += 1
    const tab: ResultTab = {
      id: uid(),
      seq: resultSeq,
      stmtIndex: partial.stmtIndex,
      kind: partial.kind ?? 'error',
      sql: partial.sql,
      rendered: partial.rendered ?? null,
      columns: partial.columns ?? [],
      rows: partial.rows ?? [],
      rowsTotal: partial.rowsTotal ?? 0,
      affected: partial.affected ?? 0,
      elapsedMs: partial.elapsedMs ?? 0,
      historyId: null,
      error: partial.error ?? null,
      warnings: partial.warnings ?? [],
      filters: [],
      page: 1,
      pageSize: 200,
    }
    results.value.push(tab)
    activeResultId.value = tab.id
    return tab
  }

  function closeResultTab(id: string): void {
    const idx = results.value.findIndex((t) => t.id === id)
    if (idx < 0) return
    results.value.splice(idx, 1)
    if (activeResultId.value === id) {
      activeResultId.value = results.value[Math.min(idx, results.value.length - 1)]?.id ?? ''
    }
  }

  function clearResults(): void {
    results.value = []
    activeResultId.value = ''
  }

  /** 点击结果 Tab 回显原始 SQL（切换编辑器脚本内容） */
  const fillRequest = reactive<{ n: number; sql: string }>({ n: 0, sql: '' })

  function requestFill(sql: string): void {
    fillRequest.n += 1
    fillRequest.sql = sql
  }

  function setActiveResult(id: string): void {
    activeResultId.value = id
    const tab = results.value.find((t) => t.id === id)
    if (tab) requestFill(tab.sql)
  }

  function applyResultEvent(evt: IdeResultEvent, stmtSql: string): void {
    const tab = newResultTab({
      stmtIndex: evt.stmtIndex,
      sql: stmtSql,
      kind: 'query',
      columns: evt.columns,
      rows: evt.rows.map((r) => r.map((v) => (v === null || v === undefined ? '' : String(v)))),
      rowsTotal: evt.rowsTotal,
      elapsedMs: evt.elapsedMs,
    })
    tab.historyId = null // done 事件到达后回填
  }

  function handleLogEvent(data: IdeLogEvent): void {
    if (data.type === 'start') {
      pushLog('start', `── 语句 ${data.stmtIndex !== undefined ? data.stmtIndex + 1 : '-'} 开始 ──`)
      if (data.rendered) pushLog('info', `渲染后: ${data.rendered}`)
      if (data.varSnapshot && data.varSnapshot.length > 0) {
        pushLog('vars', `变量快照: ${data.varSnapshot.map((v) => `${v.name}=${v.value}(${v.source})`).join('；')}`)
      }
    } else if (data.type === 'end') {
      if (data.kind === 'exec') {
        newResultTab({
          stmtIndex: data.stmtIndex ?? 0, sql: logsSql[data.stmtIndex ?? 0] ?? '',
          kind: 'exec', affected: data.affected ?? 0, elapsedMs: data.elapsedMs ?? 0,
        })
        pushLog('end', `语句 ${data.stmtIndex !== undefined ? data.stmtIndex + 1 : '-'} 完成：受影响 ${data.affected ?? 0} 行（${data.elapsedMs ?? 0}ms）`)
      } else {
        pushLog('end', `语句 ${data.stmtIndex !== undefined ? data.stmtIndex + 1 : '-'} 完成：${data.rowsTotal ?? 0} 行（${data.elapsedMs ?? 0}ms）`)
      }
      if (data.warnings && data.warnings.length > 0) {
        for (const w of data.warnings) pushLog('vars', `WARNINGS: ${w}`)
      }
    } else if (data.type === 'error') {
      newResultTab({
        stmtIndex: data.stmtIndex ?? -1, sql: logsSql[data.stmtIndex ?? -1] ?? '',
        kind: 'error', error: data.error ?? '执行失败', elapsedMs: data.elapsedMs ?? 0,
      })
      pushLog('error', `语句 ${data.stmtIndex !== undefined ? data.stmtIndex + 1 : '-'} 失败: ${data.error ?? ''}`)
    } else if (data.type === 'txn') {
      pushLog('txn', `事务 ${data.action}${data.reason ? `（${data.reason}）` : ''}`)
    }
  }

  /** 语句原文缓存（end/error 事件不带 SQL，从 execute 入参按序取） */
  let logsSql: string[] = []

  function handleDone(data: IdeDoneEvent): void {
    // 回填 historyId 供分页重放/导出
    for (const t of results.value) {
      if (t.historyId === null) t.historyId = data.historyId
    }
    if (data.status === 'success') {
      ElMessage.success(`执行成功：${data.stmtCount} 条语句，${data.elapsedMs}ms`)
    } else if (data.status === 'canceled') {
      ElMessage.warning(`执行已停止（${data.elapsedMs}ms）`)
    } else {
      ElMessage.error(`执行失败：详见结果 Tab 日志（${data.elapsedMs}ms）`)
    }
    historyDirtyN.value += 1 // done 后通知历史抽屉刷新
  }

  /** 运行结束/再执行后 +1，HistoryDrawer watch 增量刷新 */
  const historyDirtyN = ref(0)

  /** 工具栏「导出」请求 +1 → ResultPanel 打开导出弹窗（活动结果 Tab） */
  const exportDialogN = ref(0)

  function requestExportDialog(): void {
    if (!activeResultId.value) {
      ElMessage.info('暂无执行结果可导出，请先运行 SQL')
      return
    }
    exportDialogN.value += 1
  }

  async function runSql(sqlText: string): Promise<void> {
    if (running.value) {
      ElMessage.warning('已有任务在执行中，请先停止或等待完成')
      return
    }
    if (activeDsId.value === null) {
      ElMessage.warning('请先选择数据源实例')
      return
    }
    const sql = (sqlText ?? '').trim()
    if (!sql) {
      ElMessage.warning('当前查询为空，请先编写 SQL')
      return
    }
    const tab = ensureActiveTab()
    logs.value = []
    logSeq = 0
    resultSeq = 0
    logsSql = sql.split(';').map((s) => s.trim()).filter((s) => s)
    pushLog('info', `提交执行：${logsSql.length} 条语句 · 模式=${mode.value === 'manual' ? '事务(manual)' : '自动(auto)'} · env=${env.value}`)
    running.value = true
    try {
      const resp = await executeIde({
        datasourceId: activeDsId.value,
        db: currentDb.value || null,
        sql,
        mode: mode.value,
        env: env.value,
      })
      taskId.value = resp.taskId
      tab.datasourceId = activeDsId.value
      tab.dbName = currentDb.value || null
      openStream(resp.taskId)
    } catch (err) {
      running.value = false
      throw err instanceof Error ? err : new Error('执行提交失败')
    }
  }

  function openStream(tid: string): void {
    closeStream()
    es = new EventSource(buildStreamUrl(tid))
    es.addEventListener('log', (e: MessageEvent<string>) => {
      try { handleLogEvent(JSON.parse(e.data) as IdeLogEvent) } catch { /* 忽略坏帧 */ }
    })
    es.addEventListener('result', (e: MessageEvent<string>) => {
      try {
        const evt = JSON.parse(e.data) as IdeResultEvent
        applyResultEvent(evt, logsSql[evt.stmtIndex] ?? '')
        pushLog('info', `语句 ${evt.stmtIndex + 1} 结果首屏 ${evt.rows.length}/${evt.rowsTotal} 行已就绪`)
      } catch { /* 忽略坏帧 */ }
    })
    es.addEventListener('done', (e: MessageEvent<string>) => {
      try {
        handleDone(JSON.parse(e.data) as IdeDoneEvent)
        pushLog('info', '── 执行结束 ──')
      } finally {
        closeStream()
        running.value = false
        taskId.value = ''
      }
    })
    es.onerror = () => {
      // EventSource 内建断线重连；仅任务被后端清理（404）时主动关闭
      if (!running.value) closeStream()
    }
  }

  function closeStream(): void {
    if (es) {
      es.close()
      es = null
    }
  }

  async function stopRun(): Promise<void> {
    if (!taskId.value) return
    try {
      const resp = await cancelIdeTask(taskId.value)
      if (resp.canceled) pushLog('info', '已发送停止指令（KILL QUERY）…')
      else ElMessage.info('任务已不在运行中')
    } catch (err) {
      ElMessage.error(err instanceof Error ? err.message : '停止失败')
    }
  }

  /** 组件卸载兜底：关流 + 复位执行态（防泄漏） */
  function disposeRuntime(): void {
    closeStream()
    running.value = false
    taskId.value = ''
  }

  /* ================= 补全缓存（树加载注入，G12） ================= */
  /** db → table → 列名[]（仅当前实例；切实例清空） */
  const schemaCache = reactive<Record<string, Record<string, string[]>>>({})

  function cacheColumns(db: string, table: string, columns: string[]): void {
    if (!schemaCache[db]) schemaCache[db] = {}
    schemaCache[db][table] = columns
  }

  function clearSchemaCache(): void {
    for (const k of Object.keys(schemaCache)) delete schemaCache[k]
  }

  /* ================= 全局参数缓存（G3） ================= */
  const globalParams = reactive<Record<EnvKey, GlobalParamRow[]>>({ dev: [], staging: [], prod: [] })
  const globalParamLoaded = reactive<Record<EnvKey, boolean>>({ dev: false, staging: false, prod: false })

  function setGlobalParams(envKey: EnvKey, rows: GlobalParamRow[]): void {
    globalParams[envKey] = rows
    globalParamLoaded[envKey] = true
  }

  /** 全量拉取全局参数（三分组）——缺陷3 根因修复：IDE 挂载预加载 + 抽屉打开复用同一数据源 */
  async function loadGlobalParams(): Promise<void> {
    try {
      const rows = await listGlobalParams()
      const byEnv: Record<EnvKey, GlobalParamRow[]> = { dev: [], staging: [], prod: [] }
      for (const r of rows) {
        const k = (r.env || 'dev') as EnvKey
        if (byEnv[k]) byEnv[k].push(r)
      }
      for (const e of ENV_LIST) setGlobalParams(e, byEnv[e])
    } catch { /* 预加载失败不阻断 IDE（补全/提示降级为仅内置参数） */ }
  }

  const builtinPreview = computed<BuiltinVar[]>(() => builtinVars())

  return {
    // 实例/上下文
    dsList, activeDsId, activeDs, dsMeta, currentDb, env, mode, theme, toggleTheme,
    loadDsList, selectDs, setCurrentDb,
    // 脚本
    scripts, activeScriptId, newUnnamedScript, ensureActiveTab, setActiveScript,
    updateScriptContent, renameTab, closeScript, openNamedScript,
    // 执行
    running, taskId, logs, results, activeResultId, historyDirtyN, fillRequest, exportDialogN,
    runSql, stopRun, newResultTab, closeResultTab, clearResults, setActiveResult,
    requestFill, requestExportDialog, disposeRuntime, pushLog,
    // 补全
    schemaCache, cacheColumns, clearSchemaCache,
    // 全局参数
    globalParams, globalParamLoaded, setGlobalParams, loadGlobalParams, builtinPreview,
  }
}, {
  // sessionStorage/localStorage 已在动作内持久化，无需 pinia 插件
})
