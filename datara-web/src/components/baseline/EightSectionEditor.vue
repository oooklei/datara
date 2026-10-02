<script setup lang="ts">
/**
 * M-B0 八段低代码表单编辑器（inputs/outputs/params/conditions/constraints/
 * exclusions/refs/exports）。
 *
 * 职责与边界：
 * - 纯受控组件：不调用任何 API，全部数据经 v-model:spec 双向绑定（defineModel）；
 *   readonly 时所有编辑控件禁用（目录页/评审态复用预留）。
 * - 打字即校验：内部以 validateBaselineSpec 为判定真源（computed 即时重算），
 *   违规行红标 + 顶部违规条——交互对齐 ComponentDesignView 的行内红标。
 * - select 的 options / resource 的 cap 以折叠 JSON 文本域编辑：失焦 JSON.parse
 *   校验，非法红标不写回（对齐设计器 showIfText 的编辑模式）。
 * - 底部「配置抽屉预览」只读面板：按 uiType 9 基元渲染 params+inputs 中
 *   visible=true 且未被 conditions.show 引用的字段（预览为无值静态态——被条件
 *   show 引用的字段默认视为隐藏，与运行时「条件满足才显示」语义一致）。
 * - 下拉/多选用原生 select/checkbox（先例：设计器的 .native 下拉与 req-c 开关）；
 *   输入类用 Element Plus el-input，按钮 el-button，开关 el-switch。
 */
import { computed, watch, ref } from 'vue'
import {
  SPEC_OPS, REF_SCOPES, CONSTRAINT_TYPES, EXPORT_FROMS,
  validateBaselineSpec,
  type BaselineSpec, type FormFieldDecl, type FormSectionKey, type FieldSectionKey,
} from '../../services/baselineSpec'
import { SPEC_UI_TYPES } from '../../services/componentSpec'
import type { SpecViolation } from '../../services/componentSpec'

const spec = defineModel<BaselineSpec>('spec', { required: true })
const props = defineProps<{ readonly?: boolean }>()

/** 八段页签（中文名；顺序即工作流惯例：先三段字段后五类横切） */
const SECTIONS: { key: FormSectionKey; t: string }[] = [
  { key: 'inputs', t: '输入' },
  { key: 'outputs', t: '输出' },
  { key: 'params', t: '参数' },
  { key: 'conditions', t: '条件' },
  { key: 'constraints', t: '约束' },
  { key: 'exclusions', t: '排除' },
  { key: 'refs', t: '引用变量' },
  { key: 'exports', t: '输出变量' },
]
const activeTab = ref<FormSectionKey>('inputs')
const isFieldSection = computed(() =>
  activeTab.value === 'inputs' || activeTab.value === 'outputs' || activeTab.value === 'params')

/** 八段行数（页签计数徽标） */
function countOf(k: FormSectionKey): number {
  return (spec.value.form[k] as unknown[]).length
}

/* ---------------- 打字即校验（validateBaselineSpec 为真源） ---------------- */

const violations = computed<SpecViolation[]>(() => validateBaselineSpec(spec.value))

/** 行级违规（path 形如 form.inputs[0] / form.inputs[0].key / form.conditions[2]…） */
function rowMsgs(sec: FormSectionKey, i: number): string[] {
  const tag = `form.${sec}[${i}]`
  return violations.value
    .filter((v) => v.path === tag || v.path.startsWith(`${tag}.`))
    .map((v) => v.msg)
}

/** 字段行红标：结构违规或行内 JSON 解析失败 */
function fieldBad(sec: FieldSectionKey, i: number): boolean {
  return rowMsgs(sec, i).length > 0 || !!jsonErrOf(sec, i)
}

/* ---------------- 三段字段行编辑 ---------------- */

const fieldRows = computed<FormFieldDecl[]>(() => {
  const k = activeTab.value
  return k === 'inputs' || k === 'outputs' || k === 'params'
    ? (spec.value.form[k] as FormFieldDecl[])
    : []
})

/** 三段字段键全集（conditions/constraints/exclusions/refs 的下拉与多选数据源） */
const fieldKeys = computed<string[]>(() =>
  [...spec.value.form.inputs, ...spec.value.form.outputs, ...spec.value.form.params]
    .map((f) => f.key)
    .filter(Boolean))

function addField(sec: FieldSectionKey): void {
  spec.value.form[sec].push({ key: '', label: '', uiType: 'text', required: false, visible: true })
}

function removeAt(sec: FormSectionKey, i: number): void {
  ;(spec.value.form[sec] as unknown[]).splice(i, 1)
}

/** default 编辑：与设计器 setFieldDefault 同规则——编辑后落字符串，存量非字符串原样保留 */
function defaultText(f: FormFieldDecl): string {
  return f.default === undefined ? '' : typeof f.default === 'string' ? f.default : JSON.stringify(f.default)
}
function setDefault(f: FormFieldDecl, v: string | number | null | undefined): void {
  const s = String(v ?? '')
  if (s === '') delete f.default
  else f.default = s
}

/* ---------------- options / cap 折叠 JSON 文本域（失焦 JSON.parse 校验） ---------------- */

const jsonKindOf = (f: FormFieldDecl): 'options' | 'cap' => (f.uiType === 'select' ? 'options' : 'cap')
const jkey = (sec: string, i: number, kind: string): string => `${sec}.${i}.${kind}`

/** JSON 文本缓存（key=段.行.类）与解析错误；外部 spec 引用替换时全量重灌 */
const jsonText = ref<Record<string, string>>({})
const jsonErr = ref<Record<string, string>>({})

function jsonErrOf(sec: FieldSectionKey, i: number): string {
  const f = fieldRows.value[i]
  return f ? jsonErr.value[jkey(sec, i, jsonKindOf(f))] ?? '' : ''
}

watch(
  () => spec.value,
  () => {
    const t: Record<string, string> = {}
    for (const sec of ['inputs', 'outputs', 'params'] as FieldSectionKey[]) {
      (spec.value.form[sec] as FormFieldDecl[]).forEach((f, i) => {
        if (f.uiType === 'select') {
          t[jkey(sec, i, 'options')] = f.options?.length ? JSON.stringify(f.options, null, 2) : ''
        }
        if (f.uiType === 'resource') {
          t[jkey(sec, i, 'cap')] = f.cap ? JSON.stringify(f.cap, null, 2) : ''
        }
      })
    }
    jsonText.value = t
    jsonErr.value = {}
  },
  { immediate: true },
)

/** 输入过程只缓存文本（不写回，避免半截 JSON 干扰声明） */
function onJsonInput(sec: FieldSectionKey, i: number, kind: 'options' | 'cap', v: string): void {
  jsonText.value[jkey(sec, i, kind)] = v
}

/** 失焦 JSON.parse 校验：合法才写回（非法红标、保留文本供修正） */
function onJsonBlur(sec: FieldSectionKey, i: number, kind: 'options' | 'cap'): void {
  const f = (spec.value.form[sec] as FormFieldDecl[])[i]
  if (!f) return
  const k = jkey(sec, i, kind)
  const txt = (jsonText.value[k] ?? '').trim()
  if (!txt) {
    if (kind === 'options') delete f.options
    else delete f.cap
    delete jsonErr.value[k]
    return
  }
  let parsed: unknown
  try {
    parsed = JSON.parse(txt)
  } catch (e) {
    jsonErr.value[k] = `JSON 语法错误：${e instanceof Error ? e.message : String(e)}`
    return
  }
  if (kind === 'options') {
    if (!Array.isArray(parsed)) {
      jsonErr.value[k] = 'options 须为 JSON 数组，如 [{"label":"并行","value":"parallel"}]'
      return
    }
    f.options = parsed.map((x) => {
      const o = (x !== null && typeof x === 'object' && !Array.isArray(x) ? x : {}) as Record<string, unknown>
      const val = o.value
      return {
        label: String(o.label ?? ''),
        value: typeof val === 'string' || typeof val === 'number' ? val : String(val ?? ''),
      }
    })
  } else {
    if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
      jsonErr.value[k] = 'cap 须为 JSON 对象（resource 选择器差异参数，纯数据）'
      return
    }
    f.cap = parsed as Record<string, unknown>
  }
  delete jsonErr.value[k]
}

/* ---------------- value 通用输入（conditions/constraints/exclusions 复用） ---------------- */

/** 展示：非字符串存量值以 JSON 字面展示，字符串/空原样 */
function valueText(v: unknown): string {
  if (v === undefined) return ''
  return typeof v === 'string' ? v : JSON.stringify(v)
}

/** 写回：空串删键；可 JSON.parse 存解析值（数值/数组/对象）；否则按字符串存 */
function setJsonLike(target: { value?: unknown }, v: string | number | null | undefined): void {
  const s = String(v ?? '')
  if (!s.trim()) {
    delete target.value
    return
  }
  try {
    target.value = JSON.parse(s)
  } catch {
    target.value = s
  }
}

/** exclude.values 编辑（逗号分隔文本 ↔ 字符串数组；空段剔除） */
function valuesText(v: unknown): string {
  return Array.isArray(v) ? v.map(String).join(', ') : valueText(v)
}
function setValuesText(target: { values?: unknown }, v: string): void {
  const arr = v.split(',').map((x) => x.trim()).filter(Boolean)
  if (!arr.length) delete target.values
  else target.values = arr
}

/* ---------------- 配置抽屉预览（只读、简化模拟） ---------------- */

/** 条件隐藏集合：被任一 condition.show 引用的字段，预览（无值态）默认视为隐藏 */
const condHidden = computed<Set<string>>(() => {
  const s = new Set<string>()
  for (const c of spec.value.form.conditions) for (const k of c.show) s.add(k)
  return s
})

/** 预览字段：params+inputs 中 visible=true 且未被条件 show 引用（params 在前，任务口径） */
const previewFields = computed<FormFieldDecl[]>(() =>
  [...spec.value.form.params, ...spec.value.form.inputs].filter(
    (f) => f.visible && f.key && !condHidden.value.has(f.key),
  ))

/** 依赖运行时上下文的基元 → 占位说明 */
function phText(uiType: string): string {
  switch (uiType) {
    case 'expr': return '表达式输入（运行时渲染）'
    case 'rows': return '行编辑表（运行时渲染）'
    case 'mapEditor': return '映射编辑器（运行时渲染）'
    case 'resource': return '资源选择器（运行时渲染）'
    case 'hint': return '提示块（运行时渲染）'
    default: return `占位：${uiType}`
  }
}
</script>

<template>
  <div class="ese" :class="{ ro: props.readonly }">
    <!-- 八段页签 -->
    <div class="tabbar">
      <button
        v-for="s in SECTIONS" :key="s.key" type="button"
        class="sect-tab" :class="{ on: activeTab === s.key }"
        :disabled="props.readonly" @click="activeTab = s.key"
      >
        {{ s.t }}<span class="cnt">{{ countOf(s.key) }}</span>
      </button>
    </div>

    <!-- 顶部违规条（打字即校验结果汇总） -->
    <div v-if="violations.length" class="viol-bar">
      <span class="vt">违规 {{ violations.length }} 项</span>
      <span v-for="(v, i) in violations.slice(0, 4)" :key="i" class="vm">{{ v.msg }}</span>
      <span v-if="violations.length > 4" class="vm dim">…等 {{ violations.length }} 项</span>
    </div>

    <!-- 字段三段（inputs/outputs/params）共用行编辑 -->
    <div v-if="isFieldSection" class="rows">
      <div
        v-for="(f, i) in fieldRows" :key="i"
        class="frow" :class="{ bad: fieldBad(activeTab as FieldSectionKey, i) }"
      >
        <div class="row-grid">
          <el-input v-model="f.key" placeholder="key" size="small" class="w-key" :disabled="props.readonly" />
          <el-input v-model="f.label" placeholder="标签" size="small" class="w-label" :disabled="props.readonly" />
          <select v-model="f.uiType" class="native w-ui" title="控件类型（9 基元）" :disabled="props.readonly">
            <option v-for="t in SPEC_UI_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
          </select>
          <label class="ck" title="必填">
            <input v-model="f.required" type="checkbox" :disabled="props.readonly" />必填
          </label>
          <label class="ck" title="设计态抽屉可见">
            <input v-model="f.visible" type="checkbox" :disabled="props.readonly" />可见
          </label>
          <el-input
            :model-value="defaultText(f)" placeholder="默认值" size="small" class="w-def"
            :disabled="props.readonly"
            @update:model-value="setDefault(f, $event)"
          />
          <el-input v-model="f.hint" placeholder="提示" size="small" class="w-hint" :disabled="props.readonly" />
          <el-button v-if="!props.readonly" link type="danger" size="small" @click="removeAt(activeTab, i)">删除</el-button>
        </div>
        <!-- select 的 options / resource 的 cap：折叠 JSON 文本域（失焦 JSON.parse 校验，非法红标） -->
        <details v-if="f.uiType === 'select' || f.uiType === 'resource'" class="json-box">
          <summary>{{ jsonKindOf(f) === 'options' ? 'options 静态候选' : 'cap 选择器参数' }}（JSON · 失焦校验）</summary>
          <el-input
            :model-value="jsonText[jkey(activeTab, i, jsonKindOf(f))]"
            type="textarea" :rows="4" size="small" class="json-ta"
            :disabled="props.readonly"
            :class="{ badinput: jsonErr[jkey(activeTab, i, jsonKindOf(f))] }"
            @update:model-value="onJsonInput(activeTab as FieldSectionKey, i, jsonKindOf(f), $event)"
            @blur="onJsonBlur(activeTab as FieldSectionKey, i, jsonKindOf(f))"
          />
          <div v-if="jsonErr[jkey(activeTab, i, jsonKindOf(f))]" class="err-line">
            {{ jsonErr[jkey(activeTab, i, jsonKindOf(f))] }}
          </div>
        </details>
        <div v-for="(m, mi) in rowMsgs(activeTab as FieldSectionKey, i)" :key="mi" class="err-line">{{ m }}</div>
      </div>
      <el-button v-if="!props.readonly" size="small" type="primary" plain class="add-btn" @click="addField(activeTab as FieldSectionKey)">
        ＋ 添加字段
      </el-button>
    </div>

    <!-- conditions：声明式条件可见（替代旧 showIf 函数） -->
    <div v-else-if="activeTab === 'conditions'" class="rows">
      <div v-for="(c, i) in spec.form.conditions" :key="i" class="frow" :class="{ bad: rowMsgs('conditions', i).length }">
        <div class="row-grid cond-grid">
          <el-input v-model="c.id" placeholder="条件 id" size="small" class="w-key" :disabled="props.readonly" />
          <select v-model="c.when.field" class="native" title="条件字段" :disabled="props.readonly">
            <option value="">字段…</option>
            <option v-for="k in fieldKeys" :key="k" :value="k">{{ k }}</option>
          </select>
          <select v-model="c.when.op" class="native" title="操作符" :disabled="props.readonly">
            <option v-for="o in SPEC_OPS" :key="o" :value="o">{{ o }}</option>
          </select>
          <el-input
            :model-value="valueText(c.when.value)" placeholder="比较值" size="small" class="w-def"
            :disabled="props.readonly"
            @update:model-value="setJsonLike(c.when, $event)"
          />
          <span class="rl">满足时显示 →</span>
          <span class="cks">
            <label v-for="k in fieldKeys" :key="k" class="ck">
              <input v-model="c.show" type="checkbox" :value="k" :disabled="props.readonly" />{{ k }}
            </label>
          </span>
          <el-button v-if="!props.readonly" link type="danger" size="small" @click="removeAt('conditions', i)">删除</el-button>
        </div>
        <div v-for="(m, mi) in rowMsgs('conditions', i)" :key="mi" class="err-line">{{ m }}</div>
      </div>
      <el-button
        v-if="!props.readonly" size="small" type="primary" plain class="add-btn"
        @click="spec.form.conditions.push({ id: '', when: { field: '', op: 'eq' }, show: [] })"
      >
        ＋ 添加条件
      </el-button>
    </div>

    <!-- constraints：字段级约束 -->
    <div v-else-if="activeTab === 'constraints'" class="rows">
      <div v-for="(c, i) in spec.form.constraints" :key="i" class="frow" :class="{ bad: rowMsgs('constraints', i).length }">
        <div class="row-grid">
          <select v-model="c.field" class="native" title="约束字段" :disabled="props.readonly">
            <option value="">字段…</option>
            <option v-for="k in fieldKeys" :key="k" :value="k">{{ k }}</option>
          </select>
          <select v-model="c.type" class="native" title="约束类型" :disabled="props.readonly">
            <option v-for="t in CONSTRAINT_TYPES" :key="t" :value="t">{{ t }}</option>
          </select>
          <el-input
            :model-value="valueText(c.value)" placeholder="约束值" size="small" class="w-def"
            :disabled="props.readonly"
            @update:model-value="setJsonLike(c, $event)"
          />
          <el-input v-model="c.msg" placeholder="违规提示 msg" size="small" class="w-label" :disabled="props.readonly" />
          <el-button v-if="!props.readonly" link type="danger" size="small" @click="removeAt('constraints', i)">删除</el-button>
        </div>
        <div v-for="(m, mi) in rowMsgs('constraints', i)" :key="mi" class="err-line">{{ m }}</div>
      </div>
      <el-button
        v-if="!props.readonly" size="small" type="primary" plain class="add-btn"
        @click="spec.form.constraints.push({ field: '', type: 'min' })"
      >
        ＋ 添加约束
      </el-button>
    </div>

    <!-- exclusions：互斥排除 -->
    <div v-else-if="activeTab === 'exclusions'" class="rows">
      <div v-for="(c, i) in spec.form.exclusions" :key="i" class="frow" :class="{ bad: rowMsgs('exclusions', i).length }">
        <div class="row-grid">
          <span class="rl">当</span>
          <select v-model="c.when.field" class="native" title="条件字段" :disabled="props.readonly">
            <option value="">字段…</option>
            <option v-for="k in fieldKeys" :key="k" :value="k">{{ k }}</option>
          </select>
          <el-input
            :model-value="valueText(c.when.value)" placeholder="值" size="small" class="w-def"
            :disabled="props.readonly"
            @update:model-value="setJsonLike(c.when, $event)"
          />
          <span class="rl">时禁选</span>
          <select v-model="c.exclude.field" class="native" title="排除字段" :disabled="props.readonly">
            <option value="">字段…</option>
            <option v-for="k in fieldKeys" :key="k" :value="k">{{ k }}</option>
          </select>
          <el-input
            :model-value="valuesText(c.exclude.values)" placeholder="禁选值（逗号分隔）" size="small" class="w-def"
            :disabled="props.readonly"
            @update:model-value="setValuesText(c.exclude, $event)"
          />
          <el-button v-if="!props.readonly" link type="danger" size="small" @click="removeAt('exclusions', i)">删除</el-button>
        </div>
        <div v-for="(m, mi) in rowMsgs('exclusions', i)" :key="mi" class="err-line">{{ m }}</div>
      </div>
      <el-button
        v-if="!props.readonly" size="small" type="primary" plain class="add-btn"
        @click="spec.form.exclusions.push({ when: { field: '' }, exclude: { field: '', values: [] } })"
      >
        ＋ 添加排除
      </el-button>
    </div>

    <!-- refs：引用变量域白名单（五域多选） -->
    <div v-else-if="activeTab === 'refs'" class="rows">
      <div v-for="(c, i) in spec.form.refs" :key="i" class="frow" :class="{ bad: rowMsgs('refs', i).length }">
        <div class="row-grid">
          <select v-model="c.field" class="native" title="引用字段" :disabled="props.readonly">
            <option value="">字段…</option>
            <option v-for="k in fieldKeys" :key="k" :value="k">{{ k }}</option>
          </select>
          <span class="cks">
            <label v-for="sc in REF_SCOPES" :key="sc" class="ck" :title="`域 ${sc}`">
              <input v-model="c.scopes" type="checkbox" :value="sc" :disabled="props.readonly" />{{ sc }}
            </label>
          </span>
          <el-button v-if="!props.readonly" link type="danger" size="small" @click="removeAt('refs', i)">删除</el-button>
        </div>
        <div v-for="(m, mi) in rowMsgs('refs', i)" :key="mi" class="err-line">{{ m }}</div>
      </div>
      <el-button
        v-if="!props.readonly" size="small" type="primary" plain class="add-btn"
        @click="spec.form.refs.push({ field: '', scopes: [] })"
      >
        ＋ 添加引用
      </el-button>
    </div>

    <!-- exports：输出变量声明 -->
    <div v-else class="rows">
      <div v-for="(c, i) in spec.form.exports" :key="i" class="frow" :class="{ bad: rowMsgs('exports', i).length }">
        <div class="row-grid">
          <el-input v-model="c.key" placeholder="变量 key" size="small" class="w-key" :disabled="props.readonly" />
          <select v-model="c.from" class="native" title="来源" :disabled="props.readonly">
            <option v-for="fr in EXPORT_FROMS" :key="fr" :value="fr">{{ fr }}</option>
          </select>
          <el-input v-model="c.type" placeholder="类型（如 str/int/table）" size="small" class="w-def" :disabled="props.readonly" />
          <el-input v-model="c.logKey" placeholder="logKey（from=log 必填）" size="small" class="w-def" :disabled="props.readonly" />
          <el-input v-model="c.desc" placeholder="说明" size="small" class="w-hint" :disabled="props.readonly" />
          <el-button v-if="!props.readonly" link type="danger" size="small" @click="removeAt('exports', i)">删除</el-button>
        </div>
        <div v-for="(m, mi) in rowMsgs('exports', i)" :key="mi" class="err-line">{{ m }}</div>
      </div>
      <el-button
        v-if="!props.readonly" size="small" type="primary" plain class="add-btn"
        @click="spec.form.exports.push({ key: '', from: 'result', type: '' })"
      >
        ＋ 添加输出变量
      </el-button>
    </div>

    <!-- 底部只读预览面板：配置抽屉所见即所得（简化模拟） -->
    <details class="pv-box" open>
      <summary>配置抽屉预览（只读）</summary>
      <p class="pv-note">
        所见即所得说明：预览为无值静态态——被条件（conditions.show）引用的字段默认隐藏（条件满足才显示）；
        expr/rows/mapEditor/resource/hint 依赖运行时上下文，以占位框呈现。
      </p>
      <div v-if="!previewFields.length" class="pv-empty">
        暂无可见字段（visible=true 且未被条件引用）
      </div>
      <div v-for="f in previewFields" :key="f.key" class="pv-field">
        <label class="pv-label">{{ f.label || f.key }}<i v-if="f.required" class="req">*</i></label>
        <template v-if="f.uiType === 'text'">
          <textarea v-if="f.multiline" :rows="f.rows ?? 4" disabled :placeholder="f.placeholder" />
          <input v-else type="text" disabled :placeholder="f.placeholder" />
        </template>
        <input v-else-if="f.uiType === 'number'" type="number" disabled />
        <label v-else-if="f.uiType === 'bool'" class="pv-switch">
          <input type="checkbox" disabled /><span>开关</span>
        </label>
        <select v-else-if="f.uiType === 'select'" disabled>
          <option v-for="o in f.options ?? []" :key="String(o.value)" :value="String(o.value)">
            {{ o.label || o.value }}
          </option>
        </select>
        <div v-else class="pv-ph">{{ phText(f.uiType) }}</div>
        <div v-if="f.hint" class="pv-hint">{{ f.hint }}</div>
      </div>
    </details>
  </div>
</template>

<style scoped>
.ese { display: flex; flex-direction: column; gap: 8px; min-width: 0; }

/* 八段页签 */
.tabbar { display: flex; gap: 4px; flex-wrap: wrap; }
.sect-tab {
  border: 1px solid var(--line, #e2e8f0); background: #fff; border-radius: 6px;
  padding: 4px 10px; font-size: 12px; cursor: pointer; color: #475569;
}
.sect-tab:hover { border-color: #94a3b8; }
.sect-tab.on { background: #1e293b; border-color: #1e293b; color: #fff; }
.sect-tab:disabled { cursor: not-allowed; opacity: .6; }
.cnt {
  margin-left: 4px; font-size: 10px; padding: 0 5px; border-radius: 8px;
  background: rgba(148, 163, 184, .25);
}
.sect-tab.on .cnt { background: rgba(255, 255, 255, .25); }

/* 顶部违规条 */
.viol-bar {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  background: #fef2f2; border: 1px solid #fecaca; color: #b91c1c;
  border-radius: 6px; padding: 6px 10px; font-size: 12px;
}
.viol-bar .vt { font-weight: 600; }
.viol-bar .vm::before { content: '·'; margin-right: 4px; }
.viol-bar .dim { color: #dc2626; opacity: .7; }

/* 行编辑 */
.rows { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.frow {
  border: 1px solid var(--line, #e2e8f0); border-radius: 6px;
  padding: 6px 8px; display: flex; flex-direction: column; gap: 4px; background: #fff;
}
.frow.bad { border-color: #f87171; background: #fff5f5; }
.row-grid { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; min-width: 0; }
.w-key { width: 140px; }
.w-label { width: 140px; }
.w-ui { width: 110px; }
.w-def { width: 140px; }
.w-hint { width: 160px; }
.ck { display: inline-flex; align-items: center; gap: 2px; font-size: 12px; color: #475569; white-space: nowrap; }
.cks { display: inline-flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.rl { font-size: 12px; color: #64748b; white-space: nowrap; }
.native {
  height: 24px; border: 1px solid var(--line, #cbd5e1); border-radius: 4px;
  font-size: 12px; background: #fff; color: #0f172a; padding: 0 4px;
}
.add-btn { align-self: flex-start; }

/* JSON 折叠域 */
.json-box { font-size: 12px; }
.json-box summary { cursor: pointer; color: #64748b; user-select: none; }
.json-ta { margin-top: 4px; font-family: Consolas, Menlo, monospace; }
.badinput :deep(textarea),
.badinput :deep(.el-textarea__inner) { border-color: #f87171 !important; }

/* 违规行内红标 */
.err-line { font-size: 12px; color: #dc2626; }

/* 配置抽屉预览 */
.pv-box {
  border: 1px dashed var(--line, #cbd5e1); border-radius: 8px; padding: 8px 10px;
  background: #f8fafc;
}
.pv-box summary { cursor: pointer; font-size: 12px; font-weight: 600; color: #475569; user-select: none; }
.pv-note { font-size: 12px; color: #94a3b8; margin: 6px 0; }
.pv-empty { font-size: 12px; color: #94a3b8; padding: 8px 0; }
.pv-field { padding: 6px 0; border-top: 1px solid #eef2f7; }
.pv-field:first-of-type { border-top: 0; }
.pv-label { display: block; font-size: 12px; color: #334155; margin-bottom: 4px; }
.pv-label .req { color: #ef4444; font-style: normal; margin-left: 2px; }
.pv-field input[type='text'],
.pv-field input[type='number'],
.pv-field select,
.pv-field textarea {
  width: 100%; max-width: 360px; border: 1px solid var(--line, #cbd5e1); border-radius: 4px;
  font-size: 12px; padding: 3px 6px; background: #fff; color: #94a3b8;
}
.pv-ph {
  border: 1px dashed var(--line, #cbd5e1); border-radius: 4px; background: #fff;
  font-size: 12px; color: #94a3b8; padding: 4px 8px; max-width: 360px;
}
.pv-switch { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; color: #64748b; }
.pv-hint { font-size: 11px; color: #94a3b8; margin-top: 2px; }
</style>
