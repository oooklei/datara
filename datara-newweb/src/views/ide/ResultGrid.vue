<template>
  <div class="ide-result-grid">
    <VxeGrid v-bind="gridOptions" @cell-click="onCellClick" />
  </div>
</template>

<script setup lang="ts">
/**
 * S4 结果网格（对标审计-03 G18/G19 前端呈现面）：vxe-grid 承载——
 * 虚拟滚动（scroll-y gt:60）、列宽可调、本地排序、seq 序号固定列、单元格点击复制。
 * 纯呈现组件：分页/筛选/重放逻辑留在 IdeView（内存优先 + fetchResultPage 重放），
 * 后端契约不经过本组件。复制优先 clipboard API，降级 execCommand。
 */
import { computed } from 'vue'
import { VxeGrid } from 'vxe-table'
import 'vxe-pc-ui/lib/style.css'
import 'vxe-table/lib/style.css'

const props = defineProps<{ columns: string[]; rows: unknown[][] }>()
const emit = defineEmits<{ copied: [text: string] }>()

/** 列键 c{i}：规避结果集重复列名冲突，标题仍用原始列名。 */
const gridColumns = computed(() => [
  { type: 'seq' as const, width: 56, fixed: 'left' as const, title: '#' },
  ...props.columns.map((c, i) => ({
    field: `c${i}`,
    title: c,
    sortable: true,
    resizable: true,
    showOverflow: 'tooltip' as const,
    minWidth: 96,
  })),
])

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

const gridData = computed(() =>
  props.rows.map((row) => Object.fromEntries(row.map((value, i) => [`c${i}`, formatCell(value)]))),
)

const gridOptions = computed(() => ({
  columns: gridColumns.value,
  data: gridData.value,
  height: '100%',
  size: 'small' as const,
  border: true,
  stripe: true,
  showOverflow: true,
  scrollY: { gt: 60 },
  columnConfig: { resizable: true },
  rowConfig: { isHover: true },
}))

function onCellClick(params: { row?: Record<string, unknown>; column?: { field?: string } }): void {
  const field = params.column?.field
  if (!field || !params.row || !(field in params.row)) return
  const text = String(params.row[field] ?? '')
  void copyText(text)
  emit('copied', text)
}

async function copyText(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.setAttribute('readonly', '')
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    ta.remove()
  }
}
</script>

<style scoped>
.ide-result-grid {
  flex: 1;
  min-height: 240px;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.ide-result-grid :deep(.vxe-grid) {
  flex: 1;
  min-height: 0;
}
</style>
