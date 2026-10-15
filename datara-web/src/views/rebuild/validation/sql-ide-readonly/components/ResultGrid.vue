<!--
  R5-A 页式结果网格（原型态）。
  分页 + 截断提示（影响分析风险点 5：不渲染全量大结果）；虚拟滚动/图表/存数据集（design §7.3）留 R7/R9 消费面。
  数据由父组件注入（RED 阶段为空态），组件自身不发请求。
-->
<template>
  <div class="r5a-result" data-testid="r5a-result-grid">
    <el-empty v-if="!columns.length" description="（无结果集 — 执行契约 A5 未接入）" :image-size="64" />
    <template v-else>
      <el-table :data="rows" size="small" border height="100%" class="r5a-result-table">
        <el-table-column
          v-for="(col, i) in columns"
          :key="`${col}-${i}`"
          :prop="`c${i}`"
          :label="col"
          min-width="120"
          show-overflow-tooltip
        />
      </el-table>
      <div class="r5a-result-bar">
        <el-pagination
          layout="prev, pager, next, sizes, total"
          :total="rowsTotal"
          :page-size="pageSize"
          :current-page="page"
          :page-sizes="[50, 200, 1000]"
          small
          @current-change="onPage"
          @size-change="onSize"
        />
        <span v-if="truncated" class="r5a-truncated">结果已截断显示</span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  columns: string[]
  rows: unknown[][]
  rowsTotal: number
  page: number
  pageSize: number
  truncated?: boolean
}>()

const emit = defineEmits<{ (e: 'page-change', page: number, pageSize: number): void }>()

/** 行数组转 el-table 对象行（c0..cn 稳定列键） */
const rows = computed(() =>
  props.rows.map((r) => Object.fromEntries(r.map((v, i) => [`c${i}`, v])) as Record<string, unknown>),
)

const onPage = (p: number) => emit('page-change', p, props.pageSize)
const onSize = (s: number) => emit('page-change', 1, s)
</script>

<style scoped>
.r5a-result {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.r5a-result-table {
  flex: 1;
  min-height: 0;
}
.r5a-result-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.r5a-truncated {
  color: var(--el-color-warning);
  font-size: 12px;
}
</style>
