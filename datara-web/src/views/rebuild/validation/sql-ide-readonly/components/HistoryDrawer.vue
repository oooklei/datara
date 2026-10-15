<!--
  R5-A 执行历史抽屉（原型态）。
  数据由父组件注入（RED 阶段为空态）；删除/重放分页（legacy /ide/history、/ide/result）在 A5 就绪后接线。
-->
<template>
  <el-drawer
    :model-value="visible"
    title="执行历史（R5-A）"
    size="46%"
    :destroy-on-close="false"
    @update:model-value="emit('update:visible', $event)"
  >
    <el-empty v-if="!entries.length" description="（无历史 — A5 契约未接入）" :image-size="72" />
    <el-table v-else :data="entries" size="small" border>
      <el-table-column prop="historyId" label="#" width="72" />
      <el-table-column prop="status" label="状态" width="96">
        <template #default="{ row }">
          <el-tag size="small" :type="row.status === 'success' ? 'success' : row.status === 'canceled' ? 'info' : 'danger'">
            {{ row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="sqlText" label="SQL" min-width="200" show-overflow-tooltip />
      <el-table-column prop="stmtCount" label="语句" width="72" />
      <el-table-column prop="elapsedMs" label="耗时(ms)" width="96" />
      <el-table-column prop="createdAt" label="时间" width="160" />
    </el-table>
  </el-drawer>
</template>

<script setup lang="ts">
import type { HistoryEntry } from '../../../../../services/rebuild/sqlIdeApi'

defineProps<{ visible: boolean; entries: HistoryEntry[] }>()
const emit = defineEmits<{ (e: 'update:visible', v: boolean): void }>()
</script>
