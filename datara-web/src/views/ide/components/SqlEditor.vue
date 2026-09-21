<script setup lang="ts">
/**
 * SqlEditor（I10 G12/G14/G16 + G4）：
 * - Monaco 封装：官方 ?worker 导入（self.MonacoEnvironment），自定义 monarch 语言 datara-sql（${var} 分色叠加）
 * - 主题 datara-dark（黑底）/ datara-light 联动 ideStore.theme
 * - 补全：SQL 关键字 + 树已加载表/字段（schemaCache 注入）+ `${` 触发变量列表（全局参数 + 内置 14 项）
 * - markers：POST /ide/lint 500ms 防抖映射波浪线
 * - 工具栏 15 按钮（区域顶部）+ 快捷键 Ctrl+Enter/Ctrl+S/Ctrl+Shift+F
 * - 脚本 Tab：命名=后端 scripts；未命名=sessionStorage 上限 5；切换内容隔离
 * 资源释放：editor.dispose / 防抖 cancel / providers 模块级单例不重复注册。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { debounce } from 'lodash-es'
import { format } from 'sql-formatter'
// monaco 0.56：根入口走 exports map（types+runtime 双可用）；深层 editor.api 子路径被 exports map
// 的 `./*.js → ./esm/vs/*.js` 映射排除，故 worker 以包内相对路径 ?worker 引入（vite/client 通配类型兜底）
import * as monaco from 'monaco-editor'
import EditorWorker from '../../../../node_modules/monaco-editor/esm/vs/editor/editor.worker.js?worker'
import { useIdeStore } from '../../../stores/ideStore'
import {
  lintSql, listIdeScripts, createIdeScript, updateIdeScript, deleteIdeScript,
  type IdeScriptRow, type IdeLintItem,
} from '../../../services/ideApi'

const store = useIdeStore()

/* ================= Monaco 模块级初始化（单例） ================= */

const SQL_KEYWORDS = [
  'SELECT', 'FROM', 'WHERE', 'INSERT', 'INTO', 'VALUES', 'UPDATE', 'SET', 'DELETE',
  'CREATE', 'TABLE', 'VIEW', 'INDEX', 'UNIQUE', 'DROP', 'TRUNCATE', 'ALTER', 'ADD',
  'COLUMN', 'PRIMARY', 'KEY', 'FOREIGN', 'REFERENCES', 'JOIN', 'LEFT', 'RIGHT', 'INNER',
  'OUTER', 'ON', 'AS', 'AND', 'OR', 'NOT', 'NULL', 'IN', 'BETWEEN', 'LIKE', 'IS',
  'GROUP', 'BY', 'ORDER', 'HAVING', 'LIMIT', 'OFFSET', 'UNION', 'ALL', 'DISTINCT',
  'CASE', 'WHEN', 'THEN', 'ELSE', 'END', 'IF', 'EXISTS', 'BEGIN', 'COMMIT', 'ROLLBACK',
  'DESC', 'ASC', 'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'WITH', 'SHOW', 'USE', 'DESCRIBE',
  'EXPLAIN', 'CONSTRAINT', 'DEFAULT', 'COMMENT', 'AUTO_INCREMENT', 'REPLACE', 'CALL',
]
const SQL_FUNCTIONS = [
  'COUNT(*)', 'NOW()', 'DATE_FORMAT', 'COALESCE', 'IFNULL', 'NULLIF', 'CONCAT',
  'SUBSTRING', 'TRIM', 'UPPER', 'LOWER', 'ROUND', 'ABS', 'LENGTH', 'DATEDIFF',
  'DATE_ADD', 'DATE_SUB', 'STR_TO_DATE', 'CAST', 'UNIX_TIMESTAMP', 'FROM_UNIXTIME',
]

const DATARA_SQL_LANG: monaco.languages.IMonarchLanguage = {
  defaultToken: '',
  tokenPostfix: '.datara',
  ignoreCase: true,
  keywords: SQL_KEYWORDS,
  functions: SQL_FUNCTIONS,
  brackets: [
    { open: '(', close: ')', token: 'delimiter.parenthesis' },
    { open: '[', close: ']', token: 'delimiter.square' },
  ],
  tokenizer: {
    root: [
      // ${var} 变量单独分色（G4/G12 核心诉求）
      [/\$\{[^}]*\}/, 'variable.datara'],
      { include: '@comments' },
      { include: '@whitespace' },
      [/"/, { token: 'string.quote', bracket: '@open', next: '@dstring' }],
      [/'/, { token: 'string.quote', bracket: '@open', next: '@sstring' }],
      [/`/, { token: 'identifier.quote', bracket: '@open', next: '@btident' }],
      [/0[xX][0-9a-fA-F]+/, 'number.hex'],
      [/\d[\d_]*(\.\d+)?([eE][+-]?\d+)?/, 'number.float'],
      [
        /[@#$]?[a-zA-Z_][\w$]*/,
        {
          cases: {
            '@keywords': 'keyword',
            '@functions': 'keyword.function',
            '@default': 'identifier',
          },
        },
      ],
      [/[;,.()]/, 'delimiter'],
      [/[<>=!%&+\-*/|~^?]/, 'operator'],
    ],
    comments: [
      [/--[^\n]*/, 'comment'],
      [/#(?!\{)[^\n]*/, 'comment'],
      [/\/\*/, 'comment', '@comment'],
    ],
    comment: [
      [/[^/*]+/, 'comment'],
      [/\*\//, 'comment', '@pop'],
      [/[/*]/, 'comment'],
    ],
    whitespace: [[/\s+/, 'white']],
    dstring: [
      [/[^"]*/, 'string'],
      [/""/, 'string'],
      [/"/, { token: 'string.quote', bracket: '@close', next: '@pop' }],
    ],
    sstring: [
      [/[^']*/, 'string'],
      [/''/, 'string'],
      [/'/, { token: 'string.quote', bracket: '@close', next: '@pop' }],
    ],
    btident: [
      [/[^`]*/, 'identifier'],
      [/``/, 'identifier'],
      [/`/, { token: 'identifier.quote', bracket: '@close', next: '@pop' }],
    ],
  },
}

const THEMES: Record<string, monaco.editor.IStandaloneThemeData> = {
  'datara-dark': {
    base: 'vs-dark',
    inherit: true,
    rules: [
      { token: 'variable.datara', foreground: 'e5c07b', fontStyle: 'bold' },
      { token: 'keyword.datara', foreground: '61afef' },
      { token: 'keyword.function.datara', foreground: 'c678dd' },
      { token: 'string.datara', foreground: '98c379' },
      { token: 'comment.datara', foreground: '6a737d', fontStyle: 'italic' },
      { token: 'number.float.datara', foreground: 'd19a66' },
      { token: 'number.hex.datara', foreground: 'd19a66' },
    ],
    colors: {
      'editor.background': '#0e1116',
      'editorLineNumber.foreground': '#495464',
      'editorGutter.background': '#0e1116',
      'editor.lineHighlightBackground': '#161b22',
    },
  },
  'datara-light': {
    base: 'vs',
    inherit: true,
    rules: [
      { token: 'variable.datara', foreground: 'b26a00', fontStyle: 'bold' },
      { token: 'keyword.datara', foreground: '0550ae' },
      { token: 'keyword.function.datara', foreground: '8250df' },
      { token: 'string.datara', foreground: '116329' },
      { token: 'comment.datara', foreground: '6e7781', fontStyle: 'italic' },
      { token: 'number.float.datara', foreground: '953800' },
      { token: 'number.hex.datara', foreground: '953800' },
    ],
    colors: {
      'editor.background': '#fbfcfe',
      'editor.lineHighlightBackground': '#f0f3f8',
    },
  },
}

let monacoSingletonReady = false

function ensureMonacoSetup(): void {
  if (monacoSingletonReady) return
  ;(globalThis as { MonacoEnvironment?: monaco.Environment }).MonacoEnvironment = {
    getWorker(): Worker {
      return new EditorWorker()
    },
  }
  monaco.languages.register({ id: 'datara-sql' })
  monaco.languages.setMonarchTokensProvider('datara-sql', DATARA_SQL_LANG)
  monaco.languages.setLanguageConfiguration('datara-sql', {
    comments: { lineComment: '--', blockComment: ['/*', '*/'] },
    brackets: [['(', ')'], ['[', ']']],
    autoClosingPairs: [
      { open: '(', close: ')' }, { open: "'", close: "'" }, { open: '"', close: '"' },
      { open: '`', close: '`' }, { open: '${', close: '}' },
    ],
  })
  monaco.languages.registerCompletionItemProvider('datara-sql', {
    triggerCharacters: ['$', '{'],
    provideCompletionItems(model, position) {
      const word = model.getWordUntilPosition(position)
      const range: monaco.IRange = {
        startLineNumber: position.lineNumber,
        endLineNumber: position.lineNumber,
        startColumn: word.startColumn,
        endColumn: word.endColumn,
      }
      const linePrefix = model.getValueInRange({
        startLineNumber: position.lineNumber, startColumn: 1,
        endLineNumber: position.lineNumber, endColumn: position.column,
      })
      const suggestions: monaco.languages.CompletionItem[] = []
      // `${` 触发变量补全（全局参数 by env + 内置 14 项 + date(N) 函数式）
      if (/\$\{?[\w)]*$/.test(linePrefix)) {
        const varRange: monaco.IRange = {
          startLineNumber: position.lineNumber, endLineNumber: position.lineNumber,
          startColumn: Math.max(1, position.column - 1), endColumn: position.column,
        }
        for (const p of store.globalParams[store.env]) {
          suggestions.push({
            label: `\${${p.name}}`, kind: monaco.languages.CompletionItemKind.Variable,
            detail: `全局参数（${p.env}）`, insertText: `\${${p.name}}`, range: varRange,
          })
        }
        for (const b of store.builtinPreview) {
          suggestions.push({
            label: `\${${b.name}}`, kind: monaco.languages.CompletionItemKind.Variable,
            detail: `内置时间参数 · ${b.desc}`, insertText: `\${${b.name}}`, range: varRange,
          })
        }
        suggestions.push({
          label: '${date(N)}', kind: monaco.languages.CompletionItemKind.Function,
          detail: '函数式日期（N 可为负，如 date(-1)=T-1）', insertText: '${date(0)}', range: varRange,
        })
        return { suggestions }
      }
      // 表/字段（树已加载缓存注入，仅当前库）
      const db = store.currentDb
      const schema = store.schemaCache[db] ?? {}
      for (const tb of Object.keys(schema)) {
        suggestions.push({
          label: tb, kind: monaco.languages.CompletionItemKind.Class,
          detail: `表 · ${db}`, insertText: tb, range,
        })
        for (const c of schema[tb]) {
          suggestions.push({
            label: c, kind: monaco.languages.CompletionItemKind.Field,
            detail: `字段 · ${db}.${tb}`, insertText: c, range,
          })
        }
      }
      for (const kw of SQL_KEYWORDS) {
        suggestions.push({
          label: kw, kind: monaco.languages.CompletionItemKind.Keyword, insertText: kw, range,
        })
      }
      for (const fn of SQL_FUNCTIONS) {
        suggestions.push({
          label: fn, kind: monaco.languages.CompletionItemKind.Function, insertText: fn, range,
        })
      }
      return { suggestions }
    },
  })
  for (const [name, data] of Object.entries(THEMES)) {
    monaco.editor.defineTheme(name, data)
  }
  /* 缺陷3 hover：悬浮 ${var} 显示参数值/说明（读 store 实时值，单例注册一次） */
  monaco.languages.registerHoverProvider('datara-sql', {
    provideHover(model, position) {
      const lineText = model.getLineContent(position.lineNumber)
      for (const mm of lineText.matchAll(/\$\{([^}]*)\}/g)) {
        const start = (mm.index ?? 0) + 1 // 去掉 $ 前缀后光标落在 ${} 范围内才响应
        const end = (mm.index ?? 0) + mm[0].length
        if (position.column < start || position.column > end) continue
        const inner = (mm[1] ?? '').trim()
        if (!inner) continue
        // 函数式日期 ${date(N)}
        if (/^date\s*\(\s*-?\d*\s*\)$/i.test(inner)) {
          return {
            contents: [
              { value: `**\${${inner}}** — 函数式动态日期` },
              { value: `内置函数，${inner === 'date(0)' ? 'T 当日' : inner.includes('(-') ? 'T 前 N 日' : inner.includes('(+') ? 'T 后 N 日' : 'T 相对偏移日'}，如 date(-1)=T-1。` },
            ],
          }
        }
        const gp = store.globalParams[store.env].find((p) => p.name === inner)
        if (gp) {
          return {
            contents: [
              { value: `**\${${inner}}** — 全局参数（${gp.env}）` },
              { value: gp.value ? `当前值：\`${gp.value}\`` : '当前值：*（空）*' },
              ...(gp.desc ? [{ value: gp.desc }] : []),
            ],
          }
        }
        const b = store.builtinPreview.find((x) => x.name === inner)
        if (b) {
          return {
            contents: [
              { value: `**\${${inner}}** — 内置时间参数` },
              { value: b.desc },
            ],
          }
        }
        return {
          contents: [
            { value: `**\${${inner}}** — ⚠ 未定义变量` },
            { value: `当前环境（${store.env}）全局参数与内置参数中均未定义，执行时将保留原文不被替换。` },
          ],
        }
      }
      return undefined
    },
  })
  monacoSingletonReady = true
}

/* ================= lint markers（500ms 防抖，语句级 line/col → 文档位置映射） ================= */

interface StmtSpan { startLine: number; startCol: number }

/** 与后端 _split_sql 同口径：分号拆分（跟踪每条语句起始行列，供 lint 位置映射） */
function splitStmtSpans(text: string): StmtSpan[] {
  const spans: StmtSpan[] = []
  let startLine = 1
  let startCol = 1
  let curLine = 1
  let curCol = 1
  let pending = true
  let inStmt = false
  for (const ch of text) {
    if (pending && !/\s/.test(ch) && ch !== ';') {
      startLine = curLine
      startCol = curCol
      pending = false
      inStmt = true
    }
    if (ch === ';' && inStmt) {
      spans.push({ startLine, startCol })
      pending = true
      inStmt = false
    }
    if (ch === '\n') { curLine += 1; curCol = 1 } else { curCol += 1 }
  }
  if (inStmt) spans.push({ startLine, startCol })
  return spans
}

/** 提取语句原文（与 spans 对齐，供本地风控判定） */
function splitStmtTexts(text: string): string[] {
  const parts: string[] = []
  let cur = ''
  for (const ch of text) {
    if (ch === ';') { parts.push(cur.trim()); cur = '' } else { cur += ch }
  }
  if (cur.trim()) parts.push(cur.trim())
  return parts
}

/** 编辑器内未被定义的 ${var} 列表（缺陷3 提示条数据源：env 全局参数 + 内置 + date(N) 之外均视为未定义） */
const unknownVars = ref<string[]>([])

/** 本地风控标记（矛盾3 黄色风险）：未定义参数 + SELECT 无 LIMIT 全量扫描，仅在保留原文可运行时给 Warning 而非 Error */
function localRiskMarkers(text: string): monaco.editor.IMarkerData[] {
  const markers: monaco.editor.IMarkerData[] = []
  const known = new Set<string>([
    ...store.globalParams[store.env].map((p) => p.name),
    ...store.builtinPreview.map((b) => b.name),
  ])
  // 未定义参数：全文正则提取（排除数值环绕的越界场景不在此处理）
  const unk = new Set<string>()
  for (const mm of text.matchAll(/\$\{([^{}]*)\}/g)) {
    const inner = (mm[1] ?? '').trim()
    if (!inner) continue
    if (/^date\s*\(\s*-?\d*\s*\)$/i.test(inner)) continue // 函数式日期为内置
    if (known.has(inner)) continue
    unk.add(inner)
  }
  unknownVars.value = [...unk]
  const lines = text.split('\n')
  for (const name of unk) {
    // 定位首次出现位置
    for (let i = 0; i < lines.length; i += 1) {
      const col = lines[i].indexOf(`\${${name}}`)
      if (col >= 0) {
        markers.push({
          severity: monaco.MarkerSeverity.Warning,
          message: `未定义参数 \${${name}}：当前环境（${store.env}）无此全局/内置参数，执行时将保留原文`,
          startLineNumber: i + 1,
          startColumn: col + 1,
          endLineNumber: i + 1,
          endColumn: col + name.length + 4,
        })
        break
      }
    }
  }
  // SELECT 无 LIMIT：整条语句级风险提示（矛盾3，§6 黄色警告约定）
  const stmtTexts = splitStmtTexts(text)
  const spans = splitStmtSpans(text)
  for (let i = 0; i < stmtTexts.length; i += 1) {
    const s = stmtTexts[i]
    if (!/^SELECT\b/i.test(s)) continue
    if (/\bLIMIT\b/i.test(s)) continue
    const span = spans[i] ?? { startLine: 1, startCol: 1 }
    markers.push({
      severity: monaco.MarkerSeverity.Warning,
      message: 'SELECT 未加 LIMIT：可能全量/大结果集返回（驻留层上限 2000 行会自动截断，导出不受此限）',
      startLineNumber: span.startLine,
      startColumn: span.startCol,
      endLineNumber: span.startLine,
      endColumn: span.startCol + Math.min(40, Math.max(8, s.length)),
    })
  }
  return markers
}

async function doLint(text: string): Promise<void> {
  if (!editor || !modelRef) return
  let items: IdeLintItem[] = []
  if (text.trim()) {
    try {
      items = await lintSql(text)
    } catch { /* lint 服务不可用不阻塞编辑 */ }
  }
  if (!editor || !modelRef) return // 卸载后放弃结果
  const spans = splitStmtSpans(text)
  const markers: monaco.editor.IMarkerData[] = []
  for (const item of items) {
    if (item.ok) continue
    const span = spans[item.stmtIndex] ?? { startLine: 1, startCol: 1 }
    const relLine = item.line && item.line > 0 ? item.line - 1 : 0
    const relCol = item.col && item.col > 0 ? item.col - 1 : 0
    markers.push({
      severity: monaco.MarkerSeverity.Error,
      message: item.error ?? '语法错误',
      startLineNumber: span.startLine + relLine,
      startColumn: relLine === 0 ? span.startCol + relCol : relCol + 1,
      endLineNumber: span.startLine + relLine,
      endColumn: relLine === 0 ? span.startCol + relCol + 1 : relCol + 2,
    })
  }
  // 本地风控标记并入（黄色 Warning，与服务端 Error 并存）
  markers.push(...localRiskMarkers(text))
  monaco.editor.setModelMarkers(modelRef, 'datara-lint', markers)
}

const lintDebounced = debounce(doLint, 500)

/* ================= 编辑器实例 ================= */

const hostRef = ref<HTMLElement | null>(null)
let editor: monaco.editor.IStandaloneCodeEditor | null = null
let modelRef: monaco.editor.ITextModel | null = null
let syncingContent = false // set 文本时抑制双向同步
const charCount = ref(0) // 响应式字符计数（工具栏展示）
const DEFAULT_SQL = 'SELECT *\nFROM ...\nLIMIT 100;'

function currentText(): string {
  return modelRef?.getValue() ?? ''
}

function setText(text: string): void {
  if (!modelRef) return
  syncingContent = true
  try {
    modelRef.pushEditOperations(
      [],
      [{ range: modelRef.getFullModelRange(), text }],
      () => null,
    )
  } finally {
    syncingContent = false
  }
  charCount.value = text.length
  lintDebounced(text)
}

function getSelectionOrAll(): string {
  if (!editor || !modelRef) return ''
  const sel = editor.getSelection()
  if (sel && !sel.isEmpty()) {
    const frag = modelRef.getValueInRange(sel).trim()
    if (frag) return frag
  }
  return modelRef.getValue().trim()
}

/* ---- 执行 / 停止 ---- */
async function runSql(): Promise<void> {
  const sql = getSelectionOrAll()
  try {
    await store.runSql(sql)
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '执行失败')
  }
}

function stopRun(): void {
  void store.stopRun()
}

/* ---- 脚本保存 / 载入 / 另存为 ---- */

async function promptScriptName(defaultName: string): Promise<string | null> {
  try {
    const { value } = await ElMessageBox.prompt('脚本名', '保存脚本', {
      inputValue: defaultName, inputPattern: /^\S.{0,127}$/, inputErrorMessage: '脚本名不能为空（≤128 字符）',
    })
    return value.trim()
  } catch {
    return null
  }
}

async function saveScript(saveAs = false): Promise<void> {
  if (store.activeDsId === null) {
    ElMessage.warning('请先选择实例再保存')
    return
  }
  const tab = store.ensureActiveTab()
  const content = currentText()
  store.updateScriptContent(tab.id, content)
  try {
    if (tab.named && tab.scriptId !== null && !saveAs) {
      await updateIdeScript(tab.scriptId, {
        name: tab.name, datasourceId: store.activeDsId, dbName: store.currentDb || null, content,
      })
      ElMessage.success(`脚本已更新：${tab.name}`)
    } else {
      const name = await promptScriptName(tab.named ? `${tab.name}_副本` : tab.name)
      if (!name) return
      const row = await createIdeScript({
        name, datasourceId: store.activeDsId, dbName: store.currentDb || null, content,
      })
      store.renameTab(tab.id, row.name, row.id)
      ElMessage.success(`脚本已保存：${row.name}`)
    }
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '保存失败')
  }
}

const loadDialogVisible = ref(false)
const scriptRows = ref<IdeScriptRow[]>([])
const scriptLoading = ref(false)

async function openLoadDialog(): Promise<void> {
  loadDialogVisible.value = true
  scriptLoading.value = true
  try {
    scriptRows.value = await listIdeScripts()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '脚本列表加载失败')
  } finally {
    scriptLoading.value = false
  }
}

function loadScript(row: IdeScriptRow): void {
  store.openNamedScript(row)
  loadDialogVisible.value = false
}

async function removeScript(row: IdeScriptRow): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认删除脚本「${row.name}」？`, '删除脚本', { type: 'warning' })
    await deleteIdeScript(row.id)
    ElMessage.success('脚本已删除')
    scriptRows.value = scriptRows.value.filter((r) => r.id !== row.id)
  } catch { /* 取消 */ }
}

/* ---- 工具栏其余操作 ---- */

function fmtSql(): void {
  const text = currentText().trim()
  if (!text) {
    ElMessage.warning('当前 SQL 为空')
    return
  }
  try {
    setText(format(text, { language: 'mysql', tabWidth: 2, keywordCase: 'preserve' }))
    ElMessage.success('SQL 已格式化')
  } catch {
    ElMessage.warning('格式化失败：SQL 存在语法问题，已保留原文')
  }
}

function clearEditor(): void {
  setText('')
}

function toggleComment(): void {
  void editor?.getAction('editor.action.commentLine')?.run()
}

function undo(): void {
  void editor?.trigger('toolbar', 'undo', null)
}

function redo(): void {
  void editor?.trigger('toolbar', 'redo', null)
}

async function copySelection(): Promise<void> {
  const sel = editor?.getSelection()
  const text = sel && modelRef && !sel.isEmpty() ? modelRef.getValueInRange(sel) : currentText()
  if (!text.trim()) {
    ElMessage.info('无内容可复制')
    return
  }
  await navigator.clipboard.writeText(text)
  ElMessage.success('已复制到剪贴板')
}

async function pasteClipboard(): Promise<void> {
  try {
    const text = await navigator.clipboard.readText()
    if (!text) return
    const sel = editor?.getSelection()
    if (sel && editor) editor.executeEdits('toolbar', [{ range: sel, text }])
  } catch {
    ElMessage.warning('剪贴板不可读（浏览器权限限制）')
  }
}

function toggleMode(): void {
  store.mode = store.mode === 'auto' ? 'manual' : 'auto'
  ElMessage.info(`事务模式：${store.mode === 'auto' ? '自动提交' : '事务包裹（BEGIN/COMMIT/ROLLBACK）'}`)
}

function newScript(): void {
  try {
    store.newUnnamedScript('')
  } catch { /* 上限拦截已在 store 提示 */ }
}

/* ================= 生命周期 / 同步 ================= */

onMounted(() => {
  ensureMonacoSetup()
  if (!hostRef.value) return
  const tab = store.ensureActiveTab()
  editor = monaco.editor.create(hostRef.value, {
    value: tab.content || DEFAULT_SQL,
    language: 'datara-sql',
    theme: store.theme,
    automaticLayout: true,
    minimap: { enabled: false },
    fontSize: 13,
    lineNumbers: 'on',
    wordWrap: 'on',
    scrollBeyondLastLine: false,
    fixedOverflowWidgets: true,
    tabSize: 2,
  })
  modelRef = editor.getModel()
  if (modelRef) charCount.value = modelRef.getValue().length
  editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, runSql)
  editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => void saveScript(false))
  editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyF, fmtSql)
  editor.onDidChangeModelContent(() => {
    if (syncingContent || !modelRef) return
    const text = modelRef.getValue()
    charCount.value = text.length
    if (store.activeScriptId) store.updateScriptContent(store.activeScriptId, text)
    lintDebounced(text)
  })
  if (!tab.content) store.updateScriptContent(tab.id, DEFAULT_SQL)
  // 挂载即跑一次本地风控（未定义参数提示条 / SELECT 无 LIMIT 风险警告首屏生效）
  lintDebounced(currentText())
})

/** Tab 切换 / 回显 → 编辑器内容隔离切换 */
watch(() => store.activeScriptId, (id) => {
  if (!id || !editor) return
  const tab = store.scripts.find((t) => t.id === id)
  if (tab && modelRef && modelRef.getValue() !== tab.content) setText(tab.content)
})

watch(() => store.fillRequest.n, () => {
  const sql = store.fillRequest.sql
  const tab = store.ensureActiveTab()
  store.updateScriptContent(tab.id, sql)
  setText(sql)
})

watch(() => store.theme, (t) => {
  monaco.editor.setTheme(t)
})

onBeforeUnmount(() => {
  lintDebounced.cancel()
  modelRef = null
  editor?.dispose()
  editor = null
  store.disposeRuntime()
})

const scriptTabs = computed(() => store.scripts)
const running = computed(() => store.running)

function onTabClick(id: string): void {
  store.setActiveScript(id)
}

function onTabClose(id: string): void {
  store.closeScript(id)
}
</script>

<template>
  <div class="sql-ed">
    <!-- 工具栏（区域顶部） -->
    <div class="ed-toolbar">
      <button class="tbtn run" :disabled="running" title="运行（Ctrl+Enter，选中片段则仅执行片段）" @click="runSql">▶ 运行</button>
      <button class="tbtn" :disabled="!running" title="停止当前执行任务" @click="stopRun">⏹ 停止</button>
      <span class="tsep" />
      <button class="tbtn" title="新建脚本" @click="newScript">📄 新建</button>
      <button class="tbtn" title="载入命名脚本" @click="openLoadDialog">📂 载入</button>
      <button class="tbtn" title="保存脚本（Ctrl+S）" @click="saveScript(false)">💾 保存</button>
      <button class="tbtn" title="另存为新脚本" @click="saveScript(true)">💠 另存为</button>
      <span class="tsep" />
      <button class="tbtn" title="格式化（Ctrl+Shift+F）" @click="fmtSql">🪄 格式化</button>
      <button class="tbtn" title="导出当前执行结果" @click="store.requestExportDialog()">⇩ 导出</button>
      <button class="tbtn" title="清空编辑器" @click="clearEditor">🧹 清空</button>
      <button class="tbtn" title="注释/取消注释" @click="toggleComment">💬 注释</button>
      <button class="tbtn" title="撤销" @click="undo">↩</button>
      <button class="tbtn" title="重做" @click="redo">↪</button>
      <button class="tbtn" title="复制选中代码" @click="copySelection">📋</button>
      <button class="tbtn" title="粘贴" @click="pasteClipboard">📄</button>
      <span class="tsep" />
      <button class="tbtn" :class="{ mode: store.mode === 'manual' }" title="切换事务模式（自动提交/事务包裹）" @click="toggleMode">
        🔄 {{ store.mode === 'auto' ? '自动提交' : '事务包裹' }}
      </button>
      <span class="spacer" />
      <span class="mono ed-meta">{{ charCount }} 字符{{ running ? ' · 执行中…' : '' }}</span>
    </div>

    <!-- 脚本 Tab 条（G16） -->
    <div class="script-tabs">
      <div
        v-for="t in scriptTabs"
        :key="t.id"
        class="stab"
        :class="{ on: t.id === store.activeScriptId, named: t.named }"
        @click="onTabClick(t.id)"
      >
        <span class="stab-ico">{{ t.named ? '📁' : '📄' }}</span>
        <span class="stab-name">{{ t.name }}</span>
        <span class="stab-x" title="关闭" @click.stop="onTabClose(t.id)">×</span>
      </div>
      <button class="stab-add" title="新建脚本" @click="newScript">＋</button>
    </div>

    <div class="ed-host">
      <!-- 缺陷3 提示条：编辑器内未定义 ${var} 实时提示（与 lint Warning 同源） -->
      <div v-if="unknownVars.length" class="unk-bar" title="执行时未定义参数将保留原文不被替换">
        ⚠ 未定义参数：<span v-for="n in unknownVars" :key="n" class="unk-name">{{ '\${' + n + '}' }}</span>
        <span class="unk-hint">当前环境（{{ store.env }}）无此全局/内置参数</span>
      </div>
      <div ref="hostRef" class="ed-host-inner" />
    </div>

    <!-- 载入脚本弹窗 -->
    <el-dialog v-model="loadDialogVisible" title="载入命名脚本" width="560px" append-to-body>
      <div v-if="scriptLoading" class="ld-empty">加载中…</div>
      <template v-else-if="scriptRows.length">
        <div v-for="row in scriptRows" :key="row.id" class="ld-row" @click="loadScript(row)">
          <span class="stab-ico">📁</span>
          <span class="ld-name">{{ row.name }}</span>
          <span class="ld-meta">{{ row.updateTime ?? '' }}</span>
          <button class="op-btn danger" @click.stop="removeScript(row)">删除</button>
        </div>
      </template>
      <div v-else class="ld-empty">暂无命名脚本</div>
    </el-dialog>
  </div>
</template>

<style scoped>
.sql-ed{display:flex;flex-direction:column;height:100%;background:var(--ide-card);overflow:hidden}
.ed-toolbar{display:flex;align-items:center;gap:4px;padding:6px 8px;border-bottom:1px solid var(--ide-border);flex-wrap:wrap}
.tbtn{border:1px solid transparent;background:transparent;border-radius:var(--radius-sm);padding:4px 8px;font-size:12px;cursor:pointer;color:var(--ide-text-2);white-space:nowrap}
.tbtn:hover{background:var(--ide-hover);color:var(--primary)}
.tbtn:disabled{opacity:.45;cursor:not-allowed}
.tbtn.run{background:var(--primary);color:#fff;font-weight:600}
.tbtn.run:hover{background:var(--primary-hover);color:#fff}
.tbtn.mode{border-color:var(--warn);color:var(--warn)}
.tsep{width:1px;height:16px;background:var(--ide-border);margin:0 3px}
.spacer{flex:1}
.ed-meta{font-size:11px;color:var(--ide-text-3)}
.script-tabs{display:flex;align-items:center;gap:2px;padding:4px 6px 0;border-bottom:1px solid var(--ide-border);overflow-x:auto;flex-shrink:0}
.stab{display:inline-flex;align-items:center;gap:5px;padding:5px 8px 5px 10px;font-size:12px;cursor:pointer;color:var(--ide-text-2);border:1px solid transparent;border-bottom:none;border-radius:6px 6px 0 0;white-space:nowrap}
.stab:hover{background:var(--ide-hover)}
.stab.on{background:var(--ide-bg);border-color:var(--ide-border);color:var(--primary);font-weight:600}
.stab-ico{font-size:11px}
.stab-name{max-width:150px;overflow:hidden;text-overflow:ellipsis}
.stab-x{border-radius:3px;padding:0 4px;color:var(--ide-text-3);font-size:13px}
.stab-x:hover{background:var(--danger-bg);color:var(--danger)}
.stab-add{border:1px dashed var(--ide-border-strong);background:transparent;border-radius:var(--radius-sm);padding:2px 9px;font-size:13px;cursor:pointer;color:var(--ide-text-3);margin:0 0 4px 6px}
.stab-add:hover{color:var(--primary);border-color:var(--primary)}
.ed-host{flex:1;min-height:120px;display:flex;flex-direction:column;overflow:hidden}
.ed-host-inner{flex:1;min-height:0}
.unk-bar{flex-shrink:0;display:flex;align-items:center;gap:6px;flex-wrap:wrap;padding:5px 10px;font-size:12px;background:var(--ide-warn-bg);color:var(--ide-warn);border-bottom:1px solid var(--ide-border)}
.unk-name{font-family:var(--font-mono, monospace);background:var(--ide-hover);border-radius:3px;padding:0 5px}
.unk-hint{color:var(--ide-text-3)}
.ld-row{display:flex;align-items:center;gap:8px;padding:8px 10px;border:1px solid var(--ide-border);border-radius:var(--radius-sm);margin-bottom:6px;cursor:pointer}
.ld-row:hover{border-color:var(--primary)}
.ld-name{font-weight:600;font-size:12.5px}
.ld-meta{margin-left:auto;font-size:11px;color:var(--ide-text-3)}
.ld-empty{padding:20px;text-align:center;color:var(--ide-text-3);font-size:12.5px}
.op-btn.danger{color:var(--danger)}
</style>
