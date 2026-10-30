<script setup lang="ts">
/**
 * 统一代码编辑器（CodeMirror 6）——资源脚本 SQL / Python / Shell 共用。
 *
 * S1 能力面（用户裁定「移植到 CodeEditor.vue」，内核 CodeMirror 6 冻结）：
 *   - 补全：${scope.name} 变量引用（语言数据挂载，与 lang-sql 关键字补全共存）+
 *     关系名（表/视图）补全 + 表字段补全（`table.` 前缀，支持 columnsProvider 懒加载）；
 *   - lint：500ms 防抖，lintProvider 注入后端静态校验诊断；未注入时保持空源载体，
 *     诊断仍由外部 diagnostics 经 setDiagnostics 推送；
 *   - 变量分色：合法引用 cm-var-token / 未定义 cm-var-undefined / 语法异常 cm-var-syntax-error；
 *   - hover：变量引用悬浮展示现时解析值（hoverProvider），未定义给出提示。
 * 后端事实源一律由宿主以 props/provider 注入，编辑器不直接持有数据。
 *
 * 契约：v-model 双向绑定正文；diagnostics 结构 {line,column,severity,message}；
 * 根元素即 CodeMirror 挂载点，测试可用 EditorView.findFromDOM 取回视图。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { basicSetup } from 'codemirror'
import { sql } from '@codemirror/lang-sql'
import { python } from '@codemirror/lang-python'
import { shell } from '@codemirror/legacy-modes/mode/shell'
import { StreamLanguage } from '@codemirror/language'
import { Compartment, EditorState, RangeSetBuilder, StateEffect } from '@codemirror/state'
import type { Extension, Text } from '@codemirror/state'
import { Decoration, EditorView, ViewPlugin, hoverTooltip } from '@codemirror/view'
import type { DecorationSet, ViewUpdate } from '@codemirror/view'
import type { CompletionContext, CompletionResult } from '@codemirror/autocomplete'
import { lintGutter, linter, setDiagnostics } from '@codemirror/lint'
import type { Diagnostic } from '@codemirror/lint'
import { oneDark } from '@codemirror/theme-one-dark'

type EditorLanguage = 'sql' | 'python' | 'shell'

interface EditorDiagnostic {
  line: number | null
  column: number | null
  severity: string
  message: string
}

/** 变量引用补全/分色所需的最小变量描述（与 variableApi.VariableDefinition 对齐取用） */
export interface EditorVariable {
  scope: string
  name: string
}

/** 表字段补全项 */
export interface EditorTableColumn {
  name: string
  dataType?: string
}

/** lint 提供方返回项（1 基行列），由宿主把后端诊断映射到此结构 */
export interface EditorLintItem {
  line: number
  col: number
  severity: 'error' | 'warning' | 'info'
  message: string
}

const props = withDefaults(
  defineProps<{
    modelValue: string
    language: EditorLanguage
    readonly?: boolean
    diagnostics?: EditorDiagnostic[]
    /** 当前项目可用变量（提供后启用变量补全/分色/未定义警告） */
    variables?: EditorVariable[]
    /** 关系名（表/视图）补全清单 */
    relationNames?: string[]
    /** 表字段补全清单（表名 → 字段），对象树已展开的表才有条目 */
    tableColumns?: Record<string, EditorTableColumn[]>
    /** 表字段懒加载（tableColumns 未覆盖的表按需拉取；未提供则只补全已加载表） */
    columnsProvider?: (table: string) => Promise<EditorTableColumn[]>
    /** 500ms 防抖 lint 提供方（后端静态校验包装）；未提供则关闭编辑器内 lint 源 */
    lintProvider?: (text: string) => Promise<EditorLintItem[]>
    /** 变量解析 hover 提供方（previewResolution 包装）；null = 未定义 */
    hoverProvider?: (expression: string) => Promise<string | null>
    /** 补全上下文标识（如数据源切换）：变化时清空字段/解析缓存 */
    completionContextKey?: string
  }>(),
  { readonly: false, diagnostics: () => [], tableColumns: () => ({}) },
)
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const host = ref<HTMLElement | null>(null)
let view: EditorView | undefined
const languageCompartment = new Compartment()
const readonlyCompartment = new Compartment()
const lintCompartment = new Compartment()
const hoverCompartment = new Compartment()

function languageExtension(kind: EditorLanguage): Extension {
  if (kind === 'sql') return sql()
  if (kind === 'python') return python()
  return StreamLanguage.define(shell)
}

/* ---------- 变量 token 识别（与 variableApi.parseVariableReferences 语法对齐） ---------- */

const VAR_REF_RE = /\$\{[a-zA-Z]+\.[a-zA-Z0-9_.]+\}/g
const VAR_ANY_RE = /\$\{[^{}\n]*\}/g
const VAR_INNER_RE = /^[a-zA-Z]+\.[a-zA-Z0-9_.]+$/

const varTokenMark = Decoration.mark({ class: 'cm-var-token' })
const varUndefinedMark = Decoration.mark({ class: 'cm-var-token cm-var-undefined' })
const varSyntaxMark = Decoration.mark({ class: 'cm-var-syntax-error' })

/** variables / language 更新时触发装饰重建（plugin 只在 doc/viewport 变化时重算）。 */
const rebuildVarDecos = StateEffect.define<null>()

function buildVarDecorations(v: EditorView): DecorationSet {
  const definedSet = props.variables ? new Set(props.variables.map((item) => `${item.scope}.${item.name}`)) : null
  // Shell 中 ${VAR} 是合法语法，仅对 ${scope.name} 形式着色，避免假阳性报错
  const shellMode = props.language === 'shell'
  const builder = new RangeSetBuilder<Decoration>()
  for (const { from, to } of v.visibleRanges) {
    const text = v.state.doc.sliceString(from, to)
    for (const match of text.matchAll(VAR_ANY_RE)) {
      const inner = match[0].slice(2, -1)
      const valid = VAR_INNER_RE.test(inner)
      if (shellMode && !valid) continue
      const mark = !valid
        ? varSyntaxMark
        : definedSet && !definedSet.has(inner)
          ? varUndefinedMark
          : varTokenMark
      const start = from + (match.index ?? 0)
      builder.add(start, start + match[0].length, mark)
    }
  }
  return builder.finish()
}

const varHighlighter = ViewPlugin.fromClass(
  class {
    decorations: DecorationSet
    constructor(v: EditorView) {
      this.decorations = buildVarDecorations(v)
    }
    update(update: ViewUpdate) {
      const rebuild = update.transactions.some((tr) => tr.effects.some((e) => e.is(rebuildVarDecos)))
      if (update.docChanged || update.viewportChanged || rebuild) {
        this.decorations = buildVarDecorations(update.view)
      }
    }
  },
  { decorations: (v) => v.decorations },
)

/* ---------- 补全：变量引用 + 关系名 + 表字段（与 lang-sql 内建关键字补全共存） ---------- */

/** 表名大小写不敏感索引（MySQL 等方言标识符大小写不统一） */
const columnIndex = computed(() => {
  const index = new Map<string, EditorTableColumn[]>()
  for (const [table, columns] of Object.entries(props.tableColumns ?? {})) {
    index.set(table.toLowerCase(), columns)
  }
  return index
})

/** 懒加载表字段缓存：table(小写) → 字段；pending 去重并发请求 */
const lazyColumnCache = new Map<string, EditorTableColumn[]>()
const lazyColumnPending = new Map<string, Promise<EditorTableColumn[]>>()

async function resolveColumns(qualifier: string): Promise<EditorTableColumn[]> {
  const key = qualifier.toLowerCase()
  const eager = columnIndex.value.get(key)
  if (eager && eager.length > 0) return eager
  const cached = lazyColumnCache.get(key)
  if (cached) return cached
  if (!props.columnsProvider) return []
  const existing = lazyColumnPending.get(key)
  if (existing) return existing
  const request = props.columnsProvider(qualifier)
    .then((columns) => {
      lazyColumnCache.set(key, columns)
      return columns
    })
    .catch(() => [] as EditorTableColumn[])
    .finally(() => {
      lazyColumnPending.delete(key)
    })
  lazyColumnPending.set(key, request)
  return request
}

/** `alias.` / `table.` 前缀后的字段补全 → 变量引用补全 → 关系名补全。 */
async function ideCompletionSource(context: CompletionContext): Promise<CompletionResult | null> {
  const qualified = context.matchBefore(/[a-zA-Z_][\w$]*\.[\w$]*/)
  const varPrefix = context.matchBefore(/\$\{?[a-zA-Z0-9_.]*/)
  const word = context.matchBefore(/[a-zA-Z_][\w$]*/)

  if (qualified && (columnIndex.value.size > 0 || props.columnsProvider)) {
    const dot = qualified.text.indexOf('.')
    const columns = await resolveColumns(qualified.text.slice(0, dot))
    const needle = qualified.text.slice(dot + 1).toLowerCase()
    const options = columns
      .filter((column) => column.name.toLowerCase().startsWith(needle))
      .map((column) => ({
        label: column.name,
        type: 'property' as const,
        detail: column.dataType ?? undefined,
        boost: 60,
      }))
    if (options.length > 0) return { from: qualified.from + dot + 1, options, validFor: /^[\w$]*$/ }
  }
  if (varPrefix && props.variables && props.variables.length > 0) {
    const needle = varPrefix.text.replace(/[${]/g, '').toLowerCase()
    const options = props.variables
      .map((item) => `\${${item.scope}.${item.name}}`)
      .filter((label) => label.toLowerCase().includes(needle))
      .map((label) => ({ label, type: 'variable' as const, boost: 80 }))
    if (options.length > 0) {
      return { from: varPrefix.from, options, validFor: /^\$\{?[a-zA-Z0-9_.}]*$/ }
    }
  }
  if (word && props.relationNames && props.relationNames.length > 0) {
    const needle = word.text.toLowerCase()
    const options = [...new Set(props.relationNames)]
      .filter((name) => name.toLowerCase().startsWith(needle))
      .map((label) => ({ label, type: 'class' as const }))
    if (options.length > 0) return { from: word.from, options, validFor: /^[\w$]*$/ }
  }
  return null
}

/* ---------- lint：500ms 防抖；无 provider 时保留空源载体承载 setDiagnostics ---------- */

function toCmDiagnostic(doc: Text, item: EditorLintItem): Diagnostic | null {
  const lineNo = Math.min(Math.max(1, Math.trunc(item.line)), doc.lines)
  const line = doc.line(lineNo)
  if (line.length === 0) return null
  const col = Math.min(Math.max(1, Math.trunc(item.col)), line.length)
  const from = line.from + col - 1
  const to = Math.min(line.to, from + 1)
  if (to <= from) return null
  return {
    from,
    to,
    message: item.message,
    severity: item.severity === 'error' ? 'error' : item.severity === 'warning' ? 'warning' : 'info',
  }
}

function buildLintExtension(): Extension {
  const provider = props.lintProvider
  if (!provider) return linter(() => [], { delay: 500 })
  return linter(
    async (v) => {
      const text = v.state.doc.toString()
      if (text.trim() === '') return []
      try {
        const items = await provider(text)
        return items.map((item) => toCmDiagnostic(v.state.doc, item)).filter((d): d is Diagnostic => d !== null)
      } catch {
        return []
      }
    },
    { delay: 500 },
  )
}

/* ---------- hover：变量引用现时解析值（带缓存，variables/上下文变化时失效） ---------- */

const hoverCache = new Map<string, string | null>()

function buildHoverExtension(): Extension {
  const provider = props.hoverProvider
  if (!provider) return []
  return hoverTooltip(
    async (v, pos) => {
      const docText = v.state.doc.toString()
      let hit: { expr: string; from: number; to: number } | null = null
      for (const match of docText.matchAll(VAR_REF_RE)) {
        const from = match.index ?? 0
        const to = from + match[0].length
        if (pos >= from && pos <= to) {
          hit = { expr: match[0], from, to }
          break
        }
      }
      if (!hit) return null
      const anchor = hit
      if (!hoverCache.has(anchor.expr)) {
        try {
          hoverCache.set(anchor.expr, (await provider(anchor.expr)) ?? null)
        } catch {
          hoverCache.set(anchor.expr, null)
        }
      }
      const resolved = hoverCache.get(anchor.expr) ?? null
      return {
        pos: anchor.from,
        end: anchor.to,
        create: () => {
          const dom = document.createElement('div')
          dom.className = 'cm-var-hover'
          const head = document.createElement('div')
          head.className = 'cm-var-hover-head'
          head.textContent = anchor.expr
          const body = document.createElement('div')
          body.className = 'cm-var-hover-body'
          body.textContent = resolved === null ? '未定义：当前项目无该变量的解析结果' : `解析值：${resolved}`
          dom.append(head, body)
          return { dom }
        },
      }
    },
    { hoverTime: 300 },
  )
}

/* ---------- 外部诊断（服务端校验结果）推送 ---------- */

function toDiagnostic(doc: Text, item: EditorDiagnostic): Diagnostic | null {
  if (item.line === null) return null
  const lineNo = Math.min(Math.max(1, Math.trunc(item.line)), doc.lines)
  const line = doc.line(lineNo)
  if (line.length === 0) return null
  const col = Math.min(Math.max(1, Math.trunc(item.column ?? 1)), line.length)
  const from = line.from + col - 1
  return {
    from,
    to: Math.min(line.to, from + 1),
    message: item.message,
    severity: item.severity === 'error' ? 'error' : item.severity === 'warning' ? 'warning' : 'info',
  }
}

function applyDiagnostics(): void {
  if (!view) return
  const diagnostics = props.diagnostics
    .map((item) => toDiagnostic(view!.state.doc, item))
    .filter((item): item is Diagnostic => item !== null)
  view.dispatch(setDiagnostics(view.state, diagnostics))
}

/* ---------- 视图构建与生命周期 ---------- */

function buildView(): void {
  if (!host.value) return
  // 补全源走语言数据挂载（与 basicSetup 的 autocompletion + lang-sql 关键字补全叠加），
  // 语言无关，切换 SQL/Python/Shell 均可用
  const completionExtension = EditorState.languageData.of(() => [{ autocomplete: ideCompletionSource }])
  const extensions: Extension[] = [
    basicSetup,
    languageCompartment.of(languageExtension(props.language)),
    completionExtension,
    varHighlighter,
    lintCompartment.of(buildLintExtension()),
    lintGutter(),
    hoverCompartment.of(buildHoverExtension()),
    EditorView.lineWrapping,
    readonlyCompartment.of(EditorState.readOnly.of(props.readonly)),
    EditorView.updateListener.of((update) => {
      if (update.docChanged) emit('update:modelValue', update.state.doc.toString())
    }),
    EditorView.theme({
      '&': { height: '100%', fontSize: '13px' },
      '.cm-scroller': { fontFamily: 'var(--font-mono, ui-monospace, monospace)', overflow: 'auto' },
    }),
  ]
  if (document.documentElement.dataset.theme === 'dark') extensions.push(oneDark)
  view = new EditorView({ parent: host.value, state: EditorState.create({ doc: props.modelValue, extensions }) })
  applyDiagnostics()
}

watch(
  () => props.modelValue,
  (value) => {
    if (!view) return
    if (value === view.state.doc.toString()) return
    view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: value } })
  },
)

watch(() => props.diagnostics, applyDiagnostics, { deep: true })

watch(
  () => props.language,
  (kind) => {
    // 语言变化：重配语言解析器 + 变量着色需按新语言规则重建（shell 跳过非 ${scope.name}）
    view?.dispatch({
      effects: [languageCompartment.reconfigure(languageExtension(kind)), rebuildVarDecos.of(null)],
    })
  },
)

watch(
  () => props.readonly,
  (flag) => {
    view?.dispatch({ effects: readonlyCompartment.reconfigure(EditorState.readOnly.of(flag)) })
  },
)

watch(
  () => props.variables,
  () => {
    hoverCache.clear()
    view?.dispatch({ effects: rebuildVarDecos.of(null) })
  },
  { deep: true },
)

watch(
  () => props.tableColumns,
  () => {
    lazyColumnCache.clear()
    lazyColumnPending.clear()
  },
  { deep: true },
)

watch(
  () => props.lintProvider,
  () => {
    view?.dispatch({ effects: lintCompartment.reconfigure(buildLintExtension()) })
  },
)

watch(
  () => props.hoverProvider,
  () => {
    hoverCache.clear()
    view?.dispatch({ effects: hoverCompartment.reconfigure(buildHoverExtension()) })
  },
)

watch(
  () => props.completionContextKey,
  () => {
    lazyColumnCache.clear()
    lazyColumnPending.clear()
    hoverCache.clear()
  },
)

onMounted(buildView)

onBeforeUnmount(() => {
  hoverCache.clear()
  lazyColumnCache.clear()
  lazyColumnPending.clear()
  view?.destroy()
  view = undefined
})

defineExpose({
  focus: () => view?.focus(),
  getView: () => view,
})
</script>

<template>
  <div ref="host" class="code-editor" />
</template>

<style scoped>
.code-editor{height:100%;min-height:0;overflow:hidden}
.code-editor :deep(.cm-var-token){color:var(--info)}
.code-editor :deep(.cm-var-undefined){color:var(--warning);text-decoration:underline dashed var(--warning);text-underline-offset:3px}
.code-editor :deep(.cm-var-syntax-error){color:var(--danger);text-decoration:underline wavy var(--danger);text-underline-offset:3px}
.code-editor :deep(.cm-var-hover){padding:6px 9px;font-size:12px;max-width:360px}
.code-editor :deep(.cm-var-hover-head){font-family:var(--font-mono, ui-monospace, monospace);color:var(--primary)}
.code-editor :deep(.cm-var-hover-body){margin-top:3px;color:var(--text-2)}
</style>
