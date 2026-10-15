<!--
  R5-A 元数据懒加载树（原型态）。
  对象范围对齐 design §7 九类：数据库 / Schema / 表 / 视图 / 字段 / 索引 / 函数 / 存储过程 / 触发器。
  数据全部由父组件通过 loadXxx 注入（RED 阶段返回 NOT_WIRED 错误 → 节点显示占位），组件自身不发请求。
-->
<template>
  <el-tree
    :data="nodes"
    :props="{ label: 'label', children: 'children', isLeaf: 'leaf' }"
    node-key="key"
    lazy
    :load="loadNode"
    :expand-on-click-node="false"
    data-testid="r5a-meta-tree"
  >
    <template #default="{ data }">
      <span class="r5a-node">
        <el-icon :size="14"><component :is="iconOf(data.kind)" /></el-icon>
        <span :class="{ 'r5a-node-muted': data.placeholder }">{{ data.label }}</span>
        <el-tag v-if="data.placeholder" size="small" type="info">未接入</el-tag>
      </span>
    </template>
  </el-tree>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Coin, Folder, Grid, Key, Link, Menu, Operation, Tickets, Collection } from '@element-plus/icons-vue'
import type { Component } from 'vue'
import { createSqlIdeContract, type ObjectKind } from '../../../../../services/rebuild/sqlIdeApi'

interface MetaNode {
  key: string
  label: string
  kind: ObjectKind
  leaf?: boolean
  placeholder?: boolean
  children?: MetaNode[]
}

const emit = defineEmits<{ (e: 'contract-error', message: string): void }>()

const contract = createSqlIdeContract()
const nodes = ref<MetaNode[]>([
  { key: 'root-placeholder', label: '（数据源未接入 — A5 后端就绪后自动填充）', kind: 'database', leaf: true, placeholder: true },
])

const iconMap: Record<ObjectKind, Component> = {
  database: Coin,
  schema: Folder,
  table: Grid,
  view: Menu,
  column: Key,
  index: Link,
  function: Operation,
  procedure: Collection,
  trigger: Tickets,
}

const iconOf = (kind: ObjectKind): Component => iconMap[kind] ?? Folder

/** 懒加载：NOT_WIRED 异常统一转占位节点并上抛事件（原型态可渲染、可观测） */
async function loadNode(node: unknown, resolve: (children: MetaNode[]) => void): Promise<void> {
  void node
  try {
    // 契约调用点（RED）：真实层级装配在 A5 就绪后实现
    void contract.listDatabases(0)
    resolve([])
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    emit('contract-error', message)
    resolve([{ key: `ph-${Math.random().toString(36).slice(2)}`, label: 'A5 契约未接入', kind: 'database', leaf: true, placeholder: true }])
  }
}
</script>

<style scoped>
.r5a-node {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.r5a-node-muted {
  color: var(--el-text-color-secondary);
}
</style>
