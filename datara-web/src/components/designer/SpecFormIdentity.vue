<script setup lang="ts">
/**
 * Task 6（方案§2.1/§2.6）身份页签：8 要素之 displayName/aliases/summary/description/category/docUrl。
 * type 只读展示——type 在草稿创建时生成（后端主表字段，不随 spec 编辑）。
 * 数据流单向：props 传分片，编辑经 patch 上抛宿主（PageDesignerView 持 FieldsState.decl）。
 * 打字即校验：violations 来自宿主 validateSpecPureData（path 前缀匹配行内红标）。
 */
import { computed } from 'vue'
import type { SpecViolation } from '../../services/componentSpec'

export interface IdentityShape {
  summary: string
  displayName?: string
  aliases?: string[]
  description?: string
  category?: string
  docUrl?: string
}

const props = defineProps<{
  /** 组件 type（草稿创建时生成，只读） */
  type: string
  summary: string
  displayName?: string
  aliases?: string[]
  description?: string
  category?: string
  docUrl?: string
  violations: SpecViolation[]
}>()
const emit = defineEmits<{ (e: 'patch', p: Partial<IdentityShape>): void }>()

/** 行内红标：violations.path 与字段前缀精确/层级匹配（fields[x] 归 fields 前缀同法） */
function bad(prefix: string): boolean {
  return props.violations.some((v) => v.path === prefix || v.path.startsWith(`${prefix}.`) || v.path.startsWith(`${prefix}[`))
}
const aliases = computed<string[]>(() => props.aliases ?? [])
function setAlias(i: number, v: string): void {
  emit('patch', { aliases: aliases.value.map((x, xi) => (xi === i ? v : x)) })
}
function addAlias(): void {
  emit('patch', { aliases: [...aliases.value, ''] })
}
function removeAlias(i: number): void {
  const next = aliases.value.filter((_, xi) => xi !== i)
  emit('patch', { aliases: next.length ? next : undefined }) // 删光 = 未声明（缺位键不落 JSON）
}
</script>

<template>
  <div class="sf" data-testid="sf-identity">
    <label class="sf-field">
      <span>type</span>
      <el-input :model-value="type" disabled data-testid="sf-id-type" />
    </label>
    <div class="sf-note">type 由草稿创建时生成，不可修改；缺 type/summary 不满足拖入落库门槛</div>
    <label class="sf-field">
      <span>展示名</span>
      <el-input
        :model-value="displayName ?? ''" placeholder="工作台/调色板标题（优先于组件名）"
        :class="{ 'sf-bad': bad('displayName') }" data-testid="sf-id-displayname"
        @update:model-value="emit('patch', { displayName: $event || undefined })"
      />
    </label>
    <div class="sf-field sf-aliases">
      <span>别名</span>
      <div class="sf-rows">
        <div v-for="(a, i) in aliases" :key="i" class="sf-row" :class="{ 'sf-bad': bad(`aliases[${i}]`) }">
          <el-input :model-value="a" placeholder="搜索别名" @update:model-value="setAlias(i, $event)" />
          <button type="button" class="sf-mini" title="删除别名" @click="removeAlias(i)">删</button>
        </div>
        <el-button size="small" plain data-testid="sf-id-alias-add" @click="addAlias">加别名</el-button>
      </div>
    </div>
    <label class="sf-field">
      <span>简介</span>
      <el-input
        :model-value="summary" placeholder="一句话简介（palette/目录展示）"
        :class="{ 'sf-bad': bad('summary') }" data-testid="sf-id-summary"
        @update:model-value="emit('patch', { summary: $event })"
      />
    </label>
    <label class="sf-field">
      <span>长描述</span>
      <el-input
        :model-value="description ?? ''" type="textarea" :rows="3" placeholder="Markdown 长描述（summary 的展开位）"
        :class="{ 'sf-bad': bad('description') }" @update:model-value="emit('patch', { description: $event || undefined })"
      />
    </label>
    <label class="sf-field">
      <span>分组</span>
      <el-input
        :model-value="category ?? ''" placeholder="调色板分组路径，如「批处理与同步/数据源」"
        :class="{ 'sf-bad': bad('category') }" @update:model-value="emit('patch', { category: $event || undefined })"
      />
    </label>
    <label class="sf-field">
      <span>文档</span>
      <el-input
        :model-value="docUrl ?? ''" placeholder="外部文档链接"
        :class="{ 'sf-bad': bad('docUrl') }" @update:model-value="emit('patch', { docUrl: $event || undefined })"
      />
    </label>
  </div>
</template>

<style scoped>
/* 4 个 SpecForm 页签子组件共用同一套字段网格/红标样式（specFormShared 口径，各文件内联声明） */
.sf { display: flex; flex-direction: column; gap: 10px; }
.sf-field { display: flex; align-items: flex-start; gap: 8px; font-size: 12px; color: var(--text-2); }
.sf-field > span { flex: none; width: 52px; padding-top: 6px; }
.sf-field .el-input, .sf-field .el-select, .sf-field .el-textarea { flex: 1; min-width: 0; }
.sf-row { display: flex; align-items: center; gap: 4px; width: 100%; margin-bottom: 4px; }
.sf-row .el-input { flex: 1; min-width: 0; }
.sf-rows { flex: 1; min-width: 0; }
.sf-mini { border: none; background: transparent; color: var(--text-3); font-size: 11px; cursor: pointer; padding: 2px 6px; border-radius: 4px; flex: none; }
.sf-mini:hover { background: var(--bg, rgba(0, 0, 0, 0.06)); color: var(--text); }
.sf-note { font-size: 11px; color: var(--text-3); margin: -4px 0 0 60px; }
/* 打字即校验红标：validateSpecPureData 命中该字段 path 时行内标红 */
.sf-bad :deep(.el-input__wrapper),
.sf-bad :deep(.el-textarea__inner) { box-shadow: 0 0 0 1px var(--danger, #f56c6c) inset; }
.sf-row.sf-bad :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px var(--danger, #f56c6c) inset; }
</style>
