<script setup lang="ts">
import { Handle, Position } from '@vue-flow/core'

defineProps<{ selected?: boolean }>()
</script>

<template>
  <div class="reroute-node" :class="{ selected }" title="转接节点（仅设计态，运行编译时自动消除）">
    <Handle type="target" :position="Position.Left" />
    <span />
    <Handle type="source" :position="Position.Right" />
  </div>
</template>

<style scoped>
.reroute-node{width:18px;height:18px;border-radius:50%;border:2px solid #64748b;background:#fff;box-shadow:0 1px 4px rgba(15,23,42,.18);display:grid;place-items:center}
.reroute-node span{width:5px;height:5px;border-radius:50%;background:#64748b}
.reroute-node.selected{border-color:#2563eb;box-shadow:0 0 0 3px rgba(37,99,235,.16)}
.reroute-node :deep(.vue-flow__handle){width:7px;height:7px;background:#64748b;border:1px solid #fff}
</style>
