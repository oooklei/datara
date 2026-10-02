export const SPEC_UI_TYPES = [
  { value: 'text', label: '文本' },
  { value: 'number', label: '数字' },
  { value: 'select', label: '下拉选择' },
  { value: 'textarea', label: '多行文本' },
  { value: 'bool', label: '开关' },
  { value: 'rows', label: '行编辑' },
  { value: 'resource', label: '资源选择' },
  { value: 'mapEditor', label: '映射编辑' },
  { value: 'args-table', label: '参数表' },
  { value: 'kv-table', label: '键值表' },
  { value: 'params-table', label: '运行参数' },
  { value: 'table-picker', label: '表选择' },
  { value: 'field-select', label: '字段选择' },
  { value: 'topic-select', label: 'Topic 选择' },
  { value: 'dir-select', label: '目录选择' },
  { value: 'upstream-ref', label: '上游引用' },
  { value: 'hint', label: '提示' },
  { value: 'expr', label: '表达式' },
] as const

const SPEC_UI_VALUES = SPEC_UI_TYPES.map((x) => x.value)

export type SpecUiType = typeof SPEC_UI_TYPES[number]['value']

export interface SpecOption { label: string; value: string }
export interface SpecField {
  key: string
  label: string
  uiType: SpecUiType
  required?: boolean
  desc?: string
  default?: unknown
  options?: SpecOption[]
  showIf?: unknown
}

export interface ComponentSpec {
  icon: string
  color: string
  summary: string
  paletteVisible: boolean
  ports: { inputs: Array<{ name: string; type: string }>; outputs: Array<{ name: string; type: string }> }
  fields: SpecField[]
  dropPolicy: {
    autoName: string
    snapToGrid: boolean
    prefillFromUpstream: string[]
    maxInstances: number
    autoConnect: { upstream: 'nearest' | 'none'; downstream: 'nearest' | 'none' }
  }
  meta?: Record<string, any>
}

export interface SpecViolation { path: string; msg: string }

const FORBIDDEN_CODE_SNIPPETS = ['=>', 'function', 'eval(', 'new Function', '${', '<script']

function codeSnippetMsg(value: unknown): string {
  if (typeof value !== 'string') return ''
  const hit = FORBIDDEN_CODE_SNIPPETS.find((s) => value.includes(s))
  return hit ? `含代码片段「${hit}」` : ''
}

function asField(x: any): SpecField {
  const uiType = SPEC_UI_VALUES.includes(x?.uiType) ? x.uiType : 'text'
  return {
    key: String(x?.key ?? ''),
    label: String(x?.label ?? x?.key ?? ''),
    uiType,
    required: !!x?.required,
    desc: String(x?.desc ?? ''),
    default: x?.default,
    options: Array.isArray(x?.options) ? x.options.map((o: any) => ({
      label: String(o?.label ?? o?.value ?? ''),
      value: String(o?.value ?? o?.label ?? ''),
    })) : [],
    showIf: x?.showIf,
  }
}

export function normalizeSpec(raw: any): ComponentSpec {
  const r = raw && typeof raw === 'object' ? raw : {}
  return {
    icon: String(r.icon ?? 'box'),
    color: String(r.color ?? '#64748b'),
    summary: String(r.summary ?? ''),
    paletteVisible: r.paletteVisible !== false,
    ports: {
      inputs: Array.isArray(r.ports?.inputs) ? r.ports.inputs : [],
      outputs: Array.isArray(r.ports?.outputs) ? r.ports.outputs : [],
    },
    fields: Array.isArray(r.fields) ? r.fields.map(asField) : [],
    dropPolicy: {
      autoName: String(r.dropPolicy?.autoName ?? '{type}_{n}'),
      snapToGrid: r.dropPolicy?.snapToGrid !== false,
      prefillFromUpstream: Array.isArray(r.dropPolicy?.prefillFromUpstream) ? r.dropPolicy.prefillFromUpstream.map(String) : [],
      maxInstances: Number(r.dropPolicy?.maxInstances ?? 0),
      autoConnect: {
        upstream: r.dropPolicy?.autoConnect?.upstream === 'none' ? 'none' : 'nearest',
        downstream: r.dropPolicy?.autoConnect?.downstream === 'none' ? 'none' : 'nearest',
      },
    },
    meta: r.meta && typeof r.meta === 'object' ? r.meta : {},
  }
}

export function validateSpecPureData(spec: ComponentSpec): SpecViolation[] {
  const out: SpecViolation[] = []
  const seen = new Set<string>()
  spec.fields.forEach((f, i) => {
    if (!f.key.trim()) out.push({ path: `fields[${i}].key`, msg: 'key required' })
    if (!f.label.trim()) out.push({ path: `fields[${i}].label`, msg: 'label required' })
    if (seen.has(f.key)) out.push({ path: `fields[${i}].key`, msg: 'duplicate key' })
    seen.add(f.key)
    if (!SPEC_UI_VALUES.includes(f.uiType)) out.push({ path: `fields[${i}].uiType`, msg: 'unsupported uiType' })
    for (const [k, v] of Object.entries(f)) {
      if (k === 'options' && Array.isArray(v)) {
        v.forEach((o, oi) => Object.entries(o ?? {}).forEach(([ok, ov]) => {
          const msg = codeSnippetMsg(ov)
          if (msg) out.push({ path: `fields[${i}].options[${oi}].${ok}`, msg })
        }))
        continue
      }
      const msg = codeSnippetMsg(v)
      if (msg) out.push({ path: `fields[${i}].${k}`, msg })
    }
  })
  for (const [k, v] of Object.entries(spec.dropPolicy ?? {})) {
    const msg = codeSnippetMsg(v)
    if (msg) out.push({ path: `dropPolicy.${k}`, msg })
  }
  return out
}
