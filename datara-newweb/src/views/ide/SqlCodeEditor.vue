<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { basicSetup } from 'codemirror'
import { sql } from '@codemirror/lang-sql'
import { EditorState, RangeSetBuilder, StateEffect, Text } from '@codemirror/state'
import type { CompletionContext, CompletionResult } from '@codemirror/autocomplete'
import { Decoration, EditorView, ViewPlugin, ViewUpdate, hoverTooltip } from '@codemirror/view'
import type { DecorationSet } from '@codemirror/view'
import { linter } from '@codemirror/lint'
import type { Diagnostic } from '@codemirror/lint'
import { oneDark } from '@codemirror/theme-one-dark'
import { undo, redo, selectAll, toggleComment, canUndoSelection, canRedoSelection } from '@codemirror/commands'

/**
 * S1/S7 编辑器能力面（CodeMirror 6 内核，用户裁定冻结）：
 *   - 补全：${scope.name} 变量引用补全（语言数据挂载，与 lang-sql 关键字补全共存）+
 *     对象树已展开关系名（表/视图）word 补全；
 *   - lint：500ms 防抖（linter delay），后端 lintSql 诊断映射为编辑器内下划线；
 *   - 变量分色：合法引用 cm-var-token / 未定义 cm-var-undefined / 语法异常 cm-var-syntax-error；
 *   - hover：变量引用悬浮展示后端现时解析值（previewResolution），未定义给出提示；
 *   - 未定义警告：variables 提供时对不在清单内的引用降级着色。
 * 契约仍由宿主（IdeView）以 provider 注入，编辑器组件不直接持有后端事实源。
 */

export interface EditorLintItem {
  line: number
  col: number
  severity: 'error' | 'warning' | 'info'
  message: string
}

const props = defineProps<{
  modelValue: string
  placeholder?: string
  /** S7：当前项目可用变量（提供后启用变量补全/分色/未定义警告） */
  variables?: Array<{ scope: string; name: string }>
  /** S1：关系名（表/视图）补全清单 */
  relationNames?: string[]
  /** S1：500ms 防抖 lint 提供方（后端 lintSql 包装）；未提供则关闭编辑器内 lint */
  lintProvider?: (sql: string) => Promise<EditorLintItem[]>
  /** S7：变量解析 hover 提供方（previewResolution 包装）；null = 未定义 */
  hoverProvider?: (expression: string) => Promise<string | null>
}>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const host = ref<HTMLElement | null>(null)
let view: EditorView | undefined

/* ---------- 变量 token 识别（与 variableApi.parseVariableReferences 语法对齐） ---------- */

const VAR_REF_RE = /\$\{[a-zA-Z]+\.[a-zA-Z0-9_.]+\}/g
const VAR_ANY_RE = /\$\{[^{}\n]*\}/g
const VAR_INNER_RE = /^[a-zA-Z]+\.[a-zA-Z0-9_.]+$/

const varTokenMark = Decoration.mark({ class: 'cm-var-token' })
const varUndefinedMark = Decoration.mark({ class: 'cm-var-token cm-var-undefined' })
const varSyntaxMark = Decoration.mark({ class: 'cm-var-syntax-error' })

/** variables 更新时触发装饰重建（plugin 只在 doc/viewport 变化时重算）。 */
const rebuildVarDecos = StateEffect.define<null>()

function buildVarDecorations(v: EditorView): DecorationSet {
  const definedSet = props.variables ? new Set(props.variables.map((item) => `${item.scope}.${item.name}`)) : null
  const builder = new RangeSetBuilder<Decoration>()
  for (const { from, to } of v.visibleRanges) {
    const text = v.state.doc.sliceString(from, to)
    for (const match of text.matchAll(VAR_ANY_RE)) {
      const start = from + (match.index ?? 0)
      const inner = match[0].slice(2, -1)
      const mark = !VAR_INNER_RE.test(inner)
        ? varSyntaxMark
        : definedSet && !definedSet.has(inner)
          ? varUndefinedMark
          : varTokenMark
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

/* ---------- 补全：变量引用 + 关系名（与 lang-sql 内建关键字补全共存） ---------- */

function ideCompletionSource(context: CompletionContext): CompletionResult | null {
  const varPrefix = context.matchBefore(/\$\{?[a-zA-Z0-9_.]*/)
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
  const word = context.matchBefore(/[a-zA-Z_][\w$]*/)
  if (!word || !props.relationNames || props.relationNames.length === 0) return null
  const needle = word.text.toLowerCase()
  const options = [...new Set(props.relationNames)]
    .filter((name) => name.toLowerCase().startsWith(needle))
    .map((label) => ({ label, type: 'class' as const }))
  if (options.length === 0) return null
  return { from: word.from, options, validFor: /^[\w$]*$/ }
}

/* ---------- lint：500ms 防抖，后端诊断 → 编辑器诊断 ---------- */

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

const lintExtension = props.lintProvider
  ? linter(
      async (v) => {
        const text = v.state.doc.toString()
        if (text.trim() === '') return []
        try {
          const items = await props.lintProvider!(text)
          return items.map((item) => toCmDiagnostic(v.state.doc, item)).filter((d): d is Diagnostic => d !== null)
        } catch {
          return []
        }
      },
      { delay: 500 },
    )
  : []

/* ---------- hover：变量引用现时解析值（带缓存，variables 变化时失效） ---------- */

const hoverCache = new Map<string, string | null>()

const hoverExtension = props.hoverProvider
  ? hoverTooltip(
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
        if (!hoverCache.has(hit.expr)) {
          try {
            hoverCache.set(hit.expr, (await props.hoverProvider!(hit.expr)) ?? null)
          } catch {
            hoverCache.set(hit.expr, null)
          }
        }
        const resolved = hoverCache.get(hit.expr) ?? null
        const anchor = hit
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
  : []

watch(() => props.variables, () => {
  hoverCache.clear()
  view?.dispatch({ effects: rebuildVarDecos.of(null) })
})

onMounted(() => {
  if (!host.value) return
  const sqlSupport = sql()
  // 变量/关系补全走语言数据挂载（.of() 返回的 facet 扩展须进 extensions 才生效），
  // 与 basicSetup 的 autocompletion + lang-sql 关键字补全叠加
  const ideCompletionExtension = sqlSupport.language.data.of({ autocomplete: ideCompletionSource })
  const extensions = [
    basicSetup,
    sqlSupport,
    ideCompletionExtension,
    varHighlighter,
    EditorView.lineWrapping,
    lintExtension,
    hoverExtension,
    EditorView.updateListener.of((update) => {
      if (update.docChanged) emit('update:modelValue', update.state.doc.toString())
    }),
    EditorView.theme({
      '&': { height: '100%', fontSize: '13px' },
      '.cm-scroller': { fontFamily: 'var(--font-mono, ui-monospace, monospace)', overflow: 'auto' },
    }),
  ]
  if (document.documentElement.dataset.theme === 'dark') extensions.push(oneDark)
  view = new EditorView({
    parent: host.value,
    state: EditorState.create({ doc: props.modelValue, extensions }),
  })
})

watch(() => props.modelValue, (value) => {
  if (!view || value === view.state.doc.toString()) return
  view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: value } })
})

function updateFromBridge(event: Event) {
  emit('update:modelValue', (event.target as HTMLTextAreaElement).value)
}

function insertText(text: string) {
  if (!view) {
    emit('update:modelValue', `${props.modelValue}${text}`)
    return
  }
  const { from, to } = view.state.selection.main
  view.dispatch({ changes: { from, to, insert: text }, selection: { anchor: from + text.length }, scrollIntoView: true })
  view.focus()
}

/** G12 工具栏暴露 API：撤销/重做/全选/注释 toggle/清空（对标旧前端工具栏完整度）。 */
function exposeUndo(): boolean { return view ? undo(view) : false }
function exposeRedo(): boolean { return view ? redo(view) : false }
function exposeSelectAll(): boolean { return view ? selectAll(view) : false }
function exposeToggleComment(): boolean { return view ? toggleComment(view) : false }
function exposeClear(): void { if (view) view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: '' } }) }
function exposeCanUndo(): boolean { return view ? canUndoSelection(view.state) : false }
function exposeCanRedo(): boolean { return view ? canRedoSelection(view.state) : false }

defineExpose({
  insertText,
  focus: () => view?.focus(),
  getView: () => view,
  undo: exposeUndo,
  redo: exposeRedo,
  selectAll: exposeSelectAll,
  toggleComment: exposeToggleComment,
  clear: exposeClear,
  canUndo: exposeCanUndo,
  canRedo: exposeCanRedo,
})
onBeforeUnmount(() => {
  hoverCache.clear()
  view?.destroy()
})
</script>

<template>
  <div class="sql-code-editor" data-codemirror-editor>
    <div ref="host" class="sql-code-host" />
    <textarea
      class="sql-test-bridge"
      data-sql-editor
      :value="modelValue"
      :aria-label="placeholder ?? 'SQL 编辑器'"
      @input="updateFromBridge"
    />
  </div>
</template>

<style scoped>
.sql-code-editor{position:relative;height:100%;min-height:220px;border:1px solid var(--border);border-radius:var(--radius-sm);overflow:hidden;background:var(--card)}
.sql-code-host{height:100%}
.sql-test-bridge{position:absolute!important;width:1px!important;height:1px!important;padding:0!important;margin:-1px!important;overflow:hidden!important;clip:rect(0,0,0,0)!important;white-space:nowrap!important;border:0!important}
.sql-code-editor :deep(.cm-var-token){color:var(--info)}
.sql-code-editor :deep(.cm-var-undefined){color:var(--warning);text-decoration:underline dashed var(--warning);text-underline-offset:3px}
.sql-code-editor :deep(.cm-var-syntax-error){color:var(--danger);text-decoration:underline wavy var(--danger);text-underline-offset:3px}
.sql-code-editor :deep(.cm-var-hover){padding:6px 9px;font-size:12px;max-width:360px}
.sql-code-editor :deep(.cm-var-hover-head){font-family:var(--font-mono, ui-monospace, monospace);color:var(--primary)}
.sql-code-editor :deep(.cm-var-hover-body){margin-top:3px;color:var(--text-2)}
</style>
