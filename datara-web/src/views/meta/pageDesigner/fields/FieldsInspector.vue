<script setup lang="ts">
/**
 * fields 声明式组件·右侧属性面板（表单定义编辑）。
 * - 未选中：参数表单字段清单（选中/上移/下移/删除/添加）+ 拖入策略 dropPolicy 编辑
 *   （snapToGrid/autoName/maxInstances/prefillFromUpstream/autoConnect）；
 * - 选中：字段编辑（key/label/uiType 9 基元/required/default + select 静态候选）；
 *   来源差异键按源写回——fields 源写 desc，form.params（八段底稿）源写 placeholder/hint/visible。
 * 全部编辑为受控 patch 上抛宿主（fieldsState 单一状态源），本组件无本地镜像。
 */
import { computed } from 'vue'
import { SPEC_UI_TYPES } from '../../../../services/componentSpec'
import type { FieldRow, FieldsSource } from './fieldsModel'

const props = defineProps<{
  rows: FieldRow[]
  dropPolicy: Record<string, unknown>
  selectedIdx: number
  source: FieldsSource
}>()
const emit = defineEmits<{
  (e: 'select', idx: number): void
  (e: 'patchRow', idx: number, patch: Record<string, unknown>): void
  (e: 'addRow'): void
  (e: 'removeRow', idx: number): void
  (e: 'moveRow', idx: number, dir: -1 | 1): void
  (e: 'patchDropPolicy', patch: Record<string, unknown>): void
}>()

const sel = computed<FieldRow | null>(() =>
  props.selectedIdx >= 0 && props.selectedIdx < props.rows.length ? props.rows[props.selectedIdx] : null)
const isBaseline = computed(() => props.source === 'form.params')

const UI_LABEL: Record<string, string> = {
  text: '文本', number: '数值', bool: '开关', select: '下拉', expr: '表达式',
  hint: '提示', rows: '行编辑表', mapEditor: '映射编辑', resource: '资源选择',
}
function uiLabel(t: string): string {
  return UI_LABEL[t] ?? t
}

interface DpShape {
  snapToGrid?: boolean
  autoName?: string
  prefillFromUpstream?: string[]
  autoConnect?: { upstream?: string; downstream?: string }
  maxInstances?: number
}
const dp = computed<DpShape>(() => props.dropPolicy as DpShape)

/** prefillFromUpstream 候选 = 字段 key 全集 */
const keyOptions = computed(() =>
  props.rows.map((r, i) => ({ label: `${r.key || `字段${i + 1}`}${r.label ? `（${r.label}）` : ''}`, value: r.key }))
    .filter((x) => x.value !== ''))

function patch(p: Record<string, unknown>): void {
  if (props.selectedIdx >= 0) emit('patchRow', props.selectedIdx, p)
}
function patchDP(p: Record<string, unknown>): void {
  emit('patchDropPolicy', p)
}
function patchAutoConnect(side: 'upstream' | 'downstream', v: unknown): void {
  patchDP({ autoConnect: { ...(dp.value.autoConnect ?? {}), [side]: v } })
}

/** select 静态候选编辑（仅 uiType=select 渲染） */
const selOptions = computed<{ label: string; value: string | number }[]>(() => {
  const o = sel.value?.options
  return Array.isArray(o) ? (o as { label: string; value: string | number }[]) : []
})
function addOption(): void {
  patch({ options: [...selOptions.value, { label: '', value: '' }] })
}
function removeOption(i: number): void {
  patch({ options: selOptions.value.filter((_, x) => x !== i) })
}
function optionChange(i: number, key: 'label' | 'value', v: string): void {
  patch({ options: selOptions.value.map((o, x) => (x === i ? { ...o, [key]: v } : o)) })
}
/** default 编辑：bool 用开关、number 用数值（空落 '' 避免脏 null），其余文本 */
function onDefaultBool(v: unknown): void {
  patch({ default: v === true })
}
function onDefaultNumber(v: unknown): void {
  patch({ default: typeof v === 'number' && Number.isFinite(v) ? v : '' })
}
</script>

<template>
  <aside class="pd-fi">
    <!-- 字段段（未选中）：清单 + 拖入策略 -->
    <template v-if="!sel">
      <div class="pd-fi-title">
        参数表单
        <span class="pd-fi-count">{{ rows.length }} 项</span>
        <el-button size="small" type="primary" plain data-testid="fi-add" @click="emit('addRow')">添加字段</el-button>
      </div>
      <div v-if="rows.length === 0" class="pd-fi-empty" data-testid="fi-empty">
        暂无字段——点「添加字段」定义该组件拖入时的参数表单
      </div>
      <div
        v-for="(r, i) in rows" :key="i" class="pd-fi-row" :class="{ 'is-sel': i === selectedIdx }"
        :data-testid="`fi-row-${i}`" @click="emit('select', i)"
      >
        <span class="pd-fi-row-label">{{ r.label || r.key || '(未命名)' }}</span>
        <span class="pd-fi-row-type">{{ uiLabel(String(r.uiType)) }}</span>
        <span class="pd-fi-row-acts" @click.stop>
          <button type="button" class="pd-fi-mini" title="上移" :disabled="i === 0" @click="emit('moveRow', i, -1)">↑</button>
          <button type="button" class="pd-fi-mini" title="下移" :disabled="i === rows.length - 1" @click="emit('moveRow', i, 1)">↓</button>
          <button type="button" class="pd-fi-mini pd-fi-mini-danger" title="删除" @click="emit('removeRow', i)">删</button>
        </span>
      </div>

      <div class="pd-fi-title" style="margin-top: 16px">拖入策略</div>
      <div class="pd-fi-grid">
        <label class="pd-fi-field pd-fi-field-wide"><span>吸附网格</span>
          <el-switch :model-value="dp.snapToGrid === true" @update:model-value="patchDP({ snapToGrid: $event === true })" />
        </label>
        <label class="pd-fi-field pd-fi-field-wide"><span>自动命名</span>
          <el-input
            :model-value="String(dp.autoName ?? '')" placeholder="如 {type}_{n}（仅 {type}/{n} 占位符）"
            data-testid="fi-autoname" @update:model-value="patchDP({ autoName: $event })"
          />
        </label>
        <label class="pd-fi-field"><span>实例上限</span>
          <el-input-number
            :model-value="Number(dp.maxInstances ?? 0)" :min="0" :step="1"
            @update:model-value="patchDP({ maxInstances: Number($event) > 0 ? Math.floor(Number($event)) : 0 })"
          />
        </label>
        <label class="pd-fi-field pd-fi-field-wide"><span>预填上游</span>
          <el-select
            multiple :model-value="dp.prefillFromUpstream ?? []" placeholder="选择 drop 时预填的字段"
            @update:model-value="patchDP({ prefillFromUpstream: $event })"
          >
            <el-option v-for="k in keyOptions" :key="k.value" :label="k.label" :value="k.value" />
          </el-select>
        </label>
        <label class="pd-fi-field"><span>连上游</span>
          <el-select :model-value="dp.autoConnect?.upstream ?? 'nearest'" @update:model-value="patchAutoConnect('upstream', $event)">
            <el-option label="就近连接" value="nearest" />
            <el-option label="不连接" value="none" />
          </el-select>
        </label>
        <label class="pd-fi-field"><span>连下游</span>
          <el-select :model-value="dp.autoConnect?.downstream ?? 'nearest'" @update:model-value="patchAutoConnect('downstream', $event)">
            <el-option label="就近连接" value="nearest" />
            <el-option label="不连接" value="none" />
          </el-select>
        </label>
      </div>
      <div class="pd-fi-note">来源：{{ isBaseline ? '八段底稿 form.params' : '声明 spec.fields' }}（其余声明内容保存时原样保留）</div>
    </template>

    <!-- 字段编辑（选中） -->
    <template v-else>
      <div class="pd-fi-title">
        编辑字段
        <el-button size="small" data-testid="fi-back" @click="emit('select', -1)">返回清单</el-button>
      </div>
      <div class="pd-fi-grid">
        <label class="pd-fi-field pd-fi-field-wide"><span>key</span>
          <el-input :model-value="sel.key" placeholder="参数键名（如 srcDs）" @update:model-value="patch({ key: $event })" />
        </label>
        <label class="pd-fi-field pd-fi-field-wide"><span>名称</span>
          <el-input :model-value="sel.label" placeholder="表单标签" data-testid="fi-label" @update:model-value="patch({ label: $event })" />
        </label>
        <label class="pd-fi-field pd-fi-field-wide"><span>控件</span>
          <el-select :model-value="sel.uiType" placeholder="控件类型" data-testid="fi-uitype" @update:model-value="patch({ uiType: $event })">
            <el-option v-for="t in SPEC_UI_TYPES" :key="t.value" :label="`${t.label}（${t.value}）`" :value="t.value" />
          </el-select>
        </label>
        <label class="pd-fi-field"><span>必填</span>
          <el-switch :model-value="sel.required === true" @update:model-value="patch({ required: $event === true })" />
        </label>
        <label v-if="isBaseline" class="pd-fi-field"><span>可见</span>
          <el-switch :model-value="sel.visible !== false" @update:model-value="patch({ visible: $event !== false })" />
        </label>
        <label v-if="sel.uiType === 'bool'" class="pd-fi-field pd-fi-field-wide"><span>默认值</span>
          <el-switch :model-value="sel.default === true" @update:model-value="onDefaultBool($event)" />
        </label>
        <label v-else-if="sel.uiType === 'number'" class="pd-fi-field pd-fi-field-wide"><span>默认值</span>
          <el-input-number :model-value="typeof sel.default === 'number' ? sel.default : undefined" @update:model-value="onDefaultNumber($event)" />
        </label>
        <label v-else-if="sel.uiType !== 'hint'" class="pd-fi-field pd-fi-field-wide"><span>默认值</span>
          <el-input :model-value="sel.default === undefined || sel.default === null ? '' : String(sel.default)" @update:model-value="patch({ default: $event })" />
        </label>
        <label v-if="isBaseline" class="pd-fi-field pd-fi-field-wide"><span>占位</span>
          <el-input :model-value="String(sel.placeholder ?? '')" placeholder="输入占位提示" @update:model-value="patch({ placeholder: $event })" />
        </label>
        <label v-else class="pd-fi-field pd-fi-field-wide"><span>说明</span>
          <el-input :model-value="String(sel.desc ?? '')" placeholder="字段说明（渲染于控件下方）" @update:model-value="patch({ desc: $event })" />
        </label>
        <label v-if="isBaseline" class="pd-fi-field pd-fi-field-wide"><span>提示</span>
          <el-input :model-value="String(sel.hint ?? '')" placeholder="控件下方提示文案（hint）" @update:model-value="patch({ hint: $event })" />
        </label>
      </div>

      <!-- select 静态候选 -->
      <template v-if="sel.uiType === 'select'">
        <div class="pd-fi-title" style="margin-top: 12px">
          下拉候选
          <el-button size="small" data-testid="fi-opt-add" @click="addOption">加一项</el-button>
        </div>
        <div v-for="(o, i) in selOptions" :key="i" class="pd-fi-opt" :data-testid="`fi-opt-${i}`">
          <el-input :model-value="String(o.label)" placeholder="标签" @update:model-value="optionChange(i, 'label', $event)" />
          <el-input :model-value="String(o.value)" placeholder="值" @update:model-value="optionChange(i, 'value', $event)" />
          <button type="button" class="pd-fi-mini pd-fi-mini-danger" title="删除候选" @click="removeOption(i)">删</button>
        </div>
        <div v-if="selOptions.length === 0" class="pd-fi-empty">暂无候选</div>
      </template>
    </template>
  </aside>
</template>

<style scoped>
.pd-fi {
  width: 100%;
  height: 100%;
  overflow-y: auto;
  padding: 12px;
  background: var(--card);
  border-left: 1px solid var(--border);
  box-sizing: border-box;
}
.pd-fi-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 4px 2px 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
}
.pd-fi-title .el-button {
  margin-left: auto;
}
.pd-fi-count {
  font-size: 11px;
  font-weight: 400;
  color: var(--text-3);
}
.pd-fi-empty {
  padding: 14px 8px;
  font-size: 12px;
  color: var(--text-3);
  text-align: center;
}
.pd-fi-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm, 6px);
  cursor: pointer;
  font-size: 12px;
}
.pd-fi-row:hover {
  background: var(--primary-light, rgba(22, 119, 255, 0.06));
}
.pd-fi-row.is-sel {
  border-color: var(--primary);
  background: var(--primary-light, rgba(22, 119, 255, 0.06));
}
.pd-fi-row-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  color: var(--text);
}
.pd-fi-row-type {
  flex: none;
  font-size: 10px;
  color: var(--text-3);
  background: var(--bg, rgba(0, 0, 0, 0.04));
  border-radius: 4px;
  padding: 0 4px;
}
.pd-fi-row-acts {
  flex: none;
  display: flex;
  gap: 2px;
}
.pd-fi-mini {
  border: none;
  background: transparent;
  color: var(--text-3);
  font-size: 11px;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 4px;
}
.pd-fi-mini:hover {
  background: var(--bg, rgba(0, 0, 0, 0.06));
  color: var(--text);
}
.pd-fi-mini:disabled {
  opacity: 0.35;
  cursor: default;
}
.pd-fi-mini-danger:hover {
  color: var(--danger, #f56c6c);
}
.pd-fi-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.pd-fi-field {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-2);
}
.pd-fi-field > span {
  flex: none;
  width: 48px;
}
.pd-fi-field-wide {
  grid-column: 1 / -1;
}
.pd-fi-field :deep(.el-input-number),
.pd-fi-field :deep(.el-input),
.pd-fi-field :deep(.el-select) {
  flex: 1;
  min-width: 0;
}
.pd-fi-note {
  margin-top: 12px;
  font-size: 11px;
  color: var(--text-3);
}
.pd-fi-opt {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 6px;
}
.pd-fi-opt .el-input {
  flex: 1;
  min-width: 0;
}
</style>
