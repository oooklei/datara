<script setup lang="ts">
/**
 * ER 实体节点：表实体卡片（表名 + 分层徽标 + 字段列表 PK/FK 徽标）。
 * 通过 profile.nodeComp 注入内核，替换通用 DataNode。
 */
import type { GNode } from '../model'
import type { NodeSchema } from '../profiles/types'

const props = defineProps<{
  id: string
  gnode: GNode
  schema: NodeSchema
  selected: boolean
}>()

const LAYER_C: Record<string, string> = {
  ODS: '#0891b2', DIM: '#d97706', DWD: '#1668dc', DWS: '#7c3aed', ADS: '#16a34a',
}

const fields = props.gnode.data.fields as
  { name: string; type: string; key?: 'PK' | 'FK' }[] | undefined
const layer = String(props.gnode.data.layer ?? 'ODS')
const color = LAYER_C[layer] ?? props.schema.color
</script>

<template>
  <div class="er-node" :class="{ sel: selected }" :style="{ borderColor: selected ? color : undefined }">
    <div class="er-head" :style="{ background: `${color}14`, borderBottom: `2px solid ${color}` }">
      <span class="er-icon" :style="{ color }">▤</span>
      <span class="er-name" :title="gnode.data.name">{{ gnode.data.name }}</span>
      <span class="er-layer" :style="{ background: `${color}1c`, color }">{{ layer }}</span>
    </div>
    <div v-if="fields?.length" class="er-fields">
      <div v-for="f in fields" :key="f.name" class="er-field">
        <span v-if="f.key" class="er-key" :class="{ pk: f.key === 'PK' }">{{ f.key }}</span>
        <span v-else class="er-key-dot" />
        <span class="er-fname" :title="f.name">{{ f.name }}</span>
        <span class="er-ftype">{{ f.type }}</span>
      </div>
    </div>
    <div v-else class="er-empty">双击右侧面板添加字段</div>
  </div>
</template>

<style scoped>
.er-node{width:230px;background:#fff;border:1.5px solid var(--border);border-radius:9px;overflow:hidden;box-shadow:0 1px 4px rgba(15,23,42,.08);font-size:11px}
.er-node.sel{box-shadow:0 0 0 2px rgba(22,104,220,.25),0 2px 8px rgba(15,23,42,.12)}
.er-head{display:flex;align-items:center;gap:6px;padding:7px 10px}
.er-icon{font-size:13px}
.er-name{flex:1;font-weight:600;font-size:11.5px;color:var(--text-1);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-family:var(--mono,monospace)}
.er-layer{font-size:9.5px;font-weight:600;padding:1px 6px;border-radius:9px}
.er-fields{max-height:190px;overflow:auto;padding:4px 0}
.er-field{display:flex;align-items:center;gap:6px;padding:2.5px 10px}
.er-field:hover{background:var(--bg)}
.er-key{font-size:8.5px;font-weight:700;padding:0 4px;border-radius:4px;background:#fff7e6;color:#d97706;border:1px solid #f5d9a8;flex-shrink:0}
.er-key.pk{background:#e8f4ff;color:#1668dc;border-color:#b8d8fb}
.er-key-dot{width:14px;flex-shrink:0}
.er-fname{flex:1;color:var(--text-2);font-family:var(--mono,monospace);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.er-ftype{color:var(--text-3);font-size:9.5px;flex-shrink:0}
.er-empty{padding:10px;color:var(--text-3);text-align:center}
</style>
