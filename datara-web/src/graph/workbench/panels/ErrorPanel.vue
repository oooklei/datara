<script setup lang="ts">
/**
 * ErrorPanel 错误聚合面板（工作台优化 Task 10，方案 §3.3）。
 * 底部可收起抽屉（direction=btt，30%），三页签 节点/边/闸门；
 * node 条目「定位」→ fitView 该节点，edge 条目 → fitView 其 source/target；
 * gate 无锚点不显示定位按钮。定位后目标节点挂 error-focus 类 2s（由宿主 GraphWorkbench 实现）。
 * 纯展示组件：错误列表由宿主实时聚合传入（computed），open 走 v-model 协议回抛宿主。
 */
import { computed } from 'vue'
import type { DocError } from '../../model/docErrors'

const props = defineProps<{ errors: DocError[]; open: boolean }>()
const emit = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'locate', err: DocError): void
}>()

/** 按 kind 一次分组，避免模板里三页签各自 filter 重复遍历 */
const grouped = computed<Record<'node' | 'edge' | 'gate', DocError[]>>(() => {
  const g: Record<'node' | 'edge' | 'gate', DocError[]> = { node: [], edge: [], gate: [] }
  for (const e of props.errors) g[e.kind].push(e)
  return g
})

const tabs = [
  { k: 'node' as const, label: '节点' },
  { k: 'edge' as const, label: '边' },
  { k: 'gate' as const, label: '闸门' },
]

function canLocate(e: DocError): boolean {
  return (e.kind === 'node' && !!e.nodeId) || (e.kind === 'edge' && !!e.edgeId)
}
</script>

<template>
  <el-drawer
    :model-value="open"
    direction="btt"
    size="30%"
    title="校验错误（点「定位」居中到问题位置，红色闪烁节点 2 秒）"
    append-to-body
    @update:model-value="emit('update:open', $event)"
  >
    <el-tabs class="ep-tabs">
      <el-tab-pane v-for="t in tabs" :key="t.k">
        <template #label>{{ t.label }}（{{ grouped[t.k].length }}）</template>
        <div v-if="!grouped[t.k].length" class="ep-empty">✓ 无{{ t.label }}错误</div>
        <div v-for="(e, i) in grouped[t.k]" :key="`${t.k}-${e.code}-${e.nodeId ?? e.edgeId ?? ''}-${i}`" class="ep-item" :class="e.level">
          <span class="ep-code">{{ e.code }}</span>
          <span class="ep-msg" :title="e.message">{{ e.message }}</span>
          <button v-if="canLocate(e)" class="ep-loc" title="居中定位到问题位置" @click="emit('locate', e)">定位</button>
        </div>
      </el-tab-pane>
    </el-tabs>
  </el-drawer>
</template>

<style scoped>
.ep-tabs :deep(.el-tabs__header){margin-bottom:8px}
.ep-empty{padding:18px 0;text-align:center;color:var(--success,#16a34a);font-size:12.5px}
.ep-item{display:flex;align-items:center;gap:8px;padding:5px 8px;border-radius:var(--radius-sm,6px);font-size:12px;border-left:3px solid transparent}
/* level 配色区分（收口修复）：error 红 #dc2626 系（默认）/ warn 琥珀 #d97706 系（色条+徽章同源） */
.ep-item.error{border-left-color:#dc2626}
.ep-item.warn{border-left-color:#d97706}
.ep-item.warn .ep-code{color:#d97706;background:rgba(217,119,6,.08);border-color:rgba(217,119,6,.35)}
.ep-item:hover{background:var(--bg,#f5f7fa)}
.ep-item+.ep-item{margin-top:2px}
.ep-code{flex:none;font-size:10px;font-weight:700;color:#dc2626;background:rgba(220,38,38,.08);border:1px solid rgba(220,38,38,.3);border-radius:4px;padding:1px 5px;font-family:var(--mono,monospace)}
.ep-msg{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text-1,#1e293b)}
.ep-loc{flex:none;border:1px solid var(--border-strong,#cbd5e1);background:#fff;border-radius:var(--radius-sm,6px);padding:2px 10px;font-size:11.5px;cursor:pointer;color:var(--primary,#2563eb)}
.ep-loc:hover{border-color:var(--primary,#2563eb);background:var(--primary-light,#eff6ff)}
</style>
