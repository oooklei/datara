<script setup lang="ts">
/**
 * Task 6（方案§2.1/§2.6）扩展页签：8 要素之 dropPolicy + extensions + initTemplate + specVersion。
 * - dropPolicy 编辑 emit patchDropPolicy——与右侧 FieldsInspector 拖入策略同走宿主
 *   onPatchDropPolicy（同一 FieldsState.dropPolicy 状态源，两处编辑自然同步，无双源漂移）；
 *   prefillFromUpstream 候选 = 字段 key 全集（FieldsInspector 同口径）。
 * - extensions：hiddenInputs（4 合法枚举多选，白名单与 componentSpec normExtensions 一致）/
 *   capabilities.testable / capabilities.previewLimit（>0 有限数，floor 钳制 ≤100）。
 * - initTemplate：JSON 文本编辑——本地缓冲 + 解析校验，非法 JSON 红标且不上抛（保存兜底
 *   validateSpecPureData 422 二道闸）；清空 = 未声明（缺位键不落 JSON）。
 * 数据流单向：编辑经 patch/patchDropPolicy 上抛宿主，本组件无本地镜像（initTemplate 文本缓冲除外）。
 * 打字即校验：violations 由宿主 validateSpecPureData 下发（dropPolicy/extensions/initTemplate 前缀红标）。
 */
import { computed, ref, watch } from 'vue'
import type { SpecViolation } from '../../services/componentSpec'
import { HIDDEN_INPUT_KEY_VALUES } from '../../services/componentSpec'
import type { FieldRow, DeclExtensions } from '../../views/meta/pageDesigner/fields/fieldsModel'

const props = defineProps<{
  /** 字段行全集（prefillFromUpstream 候选） */
  rows: FieldRow[]
  dropPolicy: Record<string, unknown>
  extensions?: DeclExtensions
  initTemplate?: Record<string, unknown>
  specVersion?: string
  violations: SpecViolation[]
}>()
const emit = defineEmits<{
  (e: 'patchDropPolicy', patch: Record<string, unknown>): void
  (e: 'patch', p: Partial<{ extensions?: DeclExtensions; initTemplate?: Record<string, unknown>; specVersion?: string }>): void
}>()

/* hiddenInputs 值域单一源：白名单数组来自 componentSpec 导出集（与 normalizeSpec.normExtensions 同源），label 仅展示层 */
const HIDDEN_INPUT_LABEL: Record<string, string> = {
  tenantId: 'tenantId 租户', runId: 'runId 运行', nodeId: 'nodeId 节点', workflowId: 'workflowId 工作流',
}
const HIDDEN_INPUTS = HIDDEN_INPUT_KEY_VALUES.map((value) => ({ value, label: HIDDEN_INPUT_LABEL[value] ?? value }))

interface DpShape {
  snapToGrid?: boolean
  autoName?: string
  prefillFromUpstream?: string[]
  autoConnect?: { upstream?: string; downstream?: string }
  maxInstances?: number
}
const dp = computed<DpShape>(() => props.dropPolicy as DpShape)
const ext = computed<DeclExtensions>(() => props.extensions ?? {})

const keyOptions = computed(() =>
  props.rows.map((r, i) => ({ label: `${r.key || `字段${i + 1}`}${r.label ? `（${r.label}）` : ''}`, value: r.key }))
    .filter((x) => x.value !== ''))

function bad(prefix: string): boolean {
  return props.violations.some((v) => v.path === prefix || v.path.startsWith(`${prefix}.`) || v.path.startsWith(`${prefix}[`))
}
function patchDP(p: Record<string, unknown>): void {
  emit('patchDropPolicy', p)
}
function patchAC(side: 'upstream' | 'downstream', v: unknown): void {
  patchDP({ autoConnect: { ...(dp.value.autoConnect ?? {}), [side]: v } })
}

/** extensions 编辑：三项皆空 = 未声明（缺位键不落 JSON）；
 * capabilities 语义级判定——testable===true 或 previewLimit 为有效正数才落键，
 * 避免 { testable:false, previewLimit:undefined } 这类「有键无义」的 {"capabilities":{}} 落 JSON */
function emitExt(p: Partial<DeclExtensions>): void {
  const next: DeclExtensions = { ...ext.value, ...p }
  const cleaned: DeclExtensions = {}
  if (next.hiddenInputs?.length) cleaned.hiddenInputs = next.hiddenInputs
  if (next.capabilities) {
    const c = next.capabilities
    const caps: NonNullable<DeclExtensions['capabilities']> = {}
    if (c.testable === true) caps.testable = true
    const limit = Number(c.previewLimit)
    if (Number.isFinite(limit) && limit > 0) caps.previewLimit = Math.min(Math.floor(limit), 100)
    if (Object.keys(caps).length > 0) cleaned.capabilities = caps
  }
  emit('patch', { extensions: Object.keys(cleaned).length ? cleaned : undefined })
}
function patchCaps(p: Partial<NonNullable<DeclExtensions['capabilities']>>): void {
  emitExt({ capabilities: { ...(ext.value.capabilities ?? {}), ...p } })
}

/* initTemplate JSON 文本编辑：切换编辑对象时回填格式化文本；解析成功才上抛。
 * 回声抑制（审查修复）：自身 emit 的声明经宿主回流（decl 引用变更触发 watch）时，
 * 若当前文本解析结果与新值深度相等则跳过回填——避免 JSON.stringify(v,null,2) 重排
 * 文本/光标跳末尾破坏续输；采用「值相等跳过」而非自写标记，undo/redo/切换组件等
 * 外部值真实变化的场景仍能正确回填，不依赖事件时序。 */
const tplText = ref('')
const tplBad = ref(false)
watch(() => props.initTemplate, (v) => {
  if (v === undefined) {
    /* 仅当文本本就为空时跳过（避免误清用户正在编辑的非法 JSON 草稿）；undefined = 已清空声明 */
    if (tplText.value.trim() === '') { tplBad.value = false; return }
    tplText.value = ''
    tplBad.value = false
    return
  }
  const s = tplText.value.trim()
  if (s !== '') {
    try {
      if (JSON.stringify(JSON.parse(s)) === JSON.stringify(v)) return
    } catch { /* 当前文本非法 JSON（红标态）：外部值真实变化，继续回填 */ }
  }
  tplText.value = JSON.stringify(v, null, 2)
  tplBad.value = false
}, { immediate: true })
function onTplInput(v: string): void {
  tplText.value = v
  const s = v.trim()
  if (s === '') {
    tplBad.value = false
    emit('patch', { initTemplate: undefined })
    return
  }
  try {
    const parsed = JSON.parse(s) as unknown
    if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
      tplBad.value = true
      return
    }
    tplBad.value = false
    emit('patch', { initTemplate: parsed as Record<string, unknown> })
  } catch {
    tplBad.value = true // 非法 JSON 红标，不上抛（保留上次合法声明）
  }
}
function onSpecVersion(v: string): void {
  emit('patch', { specVersion: v || undefined })
}
</script>

<template>
  <div class="sf" data-testid="sf-extension">
    <div class="sf-sec">拖入策略 dropPolicy</div>
    <div class="sf-note">与右侧属性面板「拖入策略」同源编辑（FieldsState 单一状态源）</div>
    <label class="sf-field">
      <span>吸附网格</span>
      <el-switch
        :model-value="dp.snapToGrid === true"
        @update:model-value="patchDP({ snapToGrid: $event === true })"
      />
    </label>
    <label class="sf-field">
      <span>自动命名</span>
      <el-input
        :model-value="String(dp.autoName ?? '')" placeholder="如 {type}_{n}（仅 {type}/{n} 占位符，越界红标）"
        :class="{ 'sf-bad': bad('dropPolicy.autoName') }" data-testid="sf-ex-autoname"
        @update:model-value="patchDP({ autoName: $event })"
      />
    </label>
    <label class="sf-field">
      <span>实例上限</span>
      <el-input-number
        :model-value="Number(dp.maxInstances ?? 0)" :min="0" :step="1"
        @update:model-value="patchDP({ maxInstances: Number($event) > 0 ? Math.floor(Number($event)) : 0 })"
      />
    </label>
    <label class="sf-field">
      <span>预填上游</span>
      <el-select
        multiple :model-value="dp.prefillFromUpstream ?? []" placeholder="drop 时一次性预填的字段"
        @update:model-value="patchDP({ prefillFromUpstream: $event })"
      >
        <el-option v-for="k in keyOptions" :key="k.value" :label="k.label" :value="k.value" />
      </el-select>
    </label>
    <div class="sf-row3">
      <label class="sf-field">
        <span>连上游</span>
        <el-select :model-value="dp.autoConnect?.upstream ?? 'nearest'" @update:model-value="patchAC('upstream', $event)">
          <el-option label="就近连接" value="nearest" />
          <el-option label="不连接" value="none" />
        </el-select>
      </label>
      <label class="sf-field">
        <span>连下游</span>
        <el-select :model-value="dp.autoConnect?.downstream ?? 'nearest'" @update:model-value="patchAC('downstream', $event)">
          <el-option label="就近连接" value="nearest" />
          <el-option label="不连接" value="none" />
        </el-select>
      </label>
    </div>

    <div class="sf-sec">扩展能力 extensions</div>
    <div class="sf-note">运行时消费，不进表单；三项皆空 = 未声明</div>
    <label class="sf-field">
      <span>隐藏输入</span>
      <el-select
        multiple :model-value="ext.hiddenInputs ?? []" placeholder="注入节点的隐藏输入键"
        @update:model-value="emitExt({ hiddenInputs: $event })"
      >
        <el-option v-for="h in HIDDEN_INPUTS" :key="h.value" :label="h.label" :value="h.value" />
      </el-select>
    </label>
    <label class="sf-field">
      <span>可测试</span>
      <el-switch
        :model-value="ext.capabilities?.testable === true"
        @update:model-value="patchCaps({ testable: $event === true })"
      />
    </label>
    <label class="sf-field">
      <span>预览上限</span>
      <el-input-number
        :model-value="ext.capabilities?.previewLimit" :min="1" :max="100" :step="10" placeholder="≤100"
        @update:model-value="patchCaps({ previewLimit: Number($event) > 0 ? Math.min(Math.floor(Number($event)), 100) : undefined })"
      />
    </label>

    <div class="sf-sec">初始化模板 initTemplate</div>
    <div class="sf-note">drop 时合并进字段初值（JSON 对象）；清空 = 未声明</div>
    <el-input
      :model-value="tplText" type="textarea" :rows="5" data-testid="sf-ex-tpl"
      :class="{ 'sf-bad': tplBad || bad('initTemplate') }"
      placeholder='如 {"srcDs": 1}'
      @update:model-value="onTplInput"
    />

    <label class="sf-field">
      <span>schema 版本</span>
      <el-input
        :model-value="specVersion ?? ''" placeholder="如 2.0（缺省视为 1.0 旧格式）"
        @update:model-value="onSpecVersion"
      />
    </label>
  </div>
</template>

<style scoped>
/* specFormShared 口径：与 SpecFormIdentity 等页签组件共用同一套字段/红标样式 */
.sf { display: flex; flex-direction: column; gap: 8px; }
.sf-sec { font-size: 14px; font-weight: 600; color: var(--text); margin-top: 8px; }
.sf-note { font-size: 11px; color: var(--text-3); margin-top: -4px; }
.sf-field { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--text-2); }
.sf-field > span { flex: none; width: 64px; }
.sf-field .el-input, .sf-field .el-select, .sf-field .el-input-number, .sf-field .el-textarea { flex: 1; min-width: 0; }
.sf-row3 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.sf-bad :deep(.el-input__wrapper), .sf-bad :deep(.el-textarea__inner) { box-shadow: 0 0 0 1px var(--danger, #f56c6c) inset; }
</style>
