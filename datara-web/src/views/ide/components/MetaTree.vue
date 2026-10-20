<template>
  <el-tree
    ref="treeRef"
    :data="roots"
    :props="{ label: 'label', children: 'children', isLeaf: 'leaf' }"
    node-key="key"
    lazy
    :load="loadNode"
    :expand-on-click-node="false"
    data-testid="ide-meta-tree"
    @node-click="emit('select', $event)"
  >
    <template #default="{ data }">
      <span class="ide-node">
        <el-icon :size="14"><component :is="iconOf(data.kind)" /></el-icon>
        <span :class="{ 'ide-node-muted': data.capability === 'unsupported' }">{{ data.label }}</span>
        <el-tag v-if="data.capability === 'conditional'" size="small" type="warning">条件支持</el-tag>
        <el-tag v-else-if="data.capability === 'unsupported'" size="small" type="info">不支持</el-tag>
      </span>
    </template>
  </el-tree>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Coin, Folder, Grid, Key, Link, Menu, Operation, Tickets, Collection } from '@element-plus/icons-vue'
import type { Component } from 'vue'
import { createSqlIdeContract, SqlIdeApiError, type MetadataEnvelope, type ObjectKind } from '../../../services/rebuild/sqlIdeApi'

interface MetaNode {
  key: string
  label: string
  kind: ObjectKind | 'source'
  ref: Record<string, unknown>
  capability?: string
  constraints?: string[]
  leaf?: boolean
}
const props = defineProps<{ datasourceId: number; keyword?: string }>()
const emit = defineEmits<{
  (e: 'contract-error', message: string): void
  (e: 'select', node: MetaNode): void
  (e: 'search-results', matches: Array<{ kind: ObjectKind; name: string; parent: string | null }>): void
}>()
const contract = createSqlIdeContract()
const searchMatches = ref<Array<{ kind: ObjectKind; name: string; parent: string | null }>>([])
const treeRef = ref<{ setCurrentKey: (key: string) => void } | null>(null)
const roots = computed<MetaNode[]>(() => [
  { key: `source:${props.datasourceId}`, label: '数据库', kind: 'source', ref: { datasourceId: props.datasourceId } },
  ...searchMatches.value.map((match) => ({ key: `search:${match.kind}:${match.parent}:${match.name}`, label: `${match.parent ? `${match.parent}.` : ''}${match.name}`, kind: match.kind, ref: { datasourceId: props.datasourceId, database: match.parent, schema: match.parent, name: match.name, objectKind: match.kind }, leaf: true })),
])
const iconMap: Record<ObjectKind | 'source', Component> = {
  database: Coin, schema: Folder, table: Grid, view: Menu, column: Key, index: Link,
  function: Operation, procedure: Collection, trigger: Tickets, source: Coin,
}

const iconOf = (kind: ObjectKind | 'source') => iconMap[kind] ?? Folder
async function allPages<T>(fetchPage: (cursor?: string) => Promise<MetadataEnvelope<T>>): Promise<MetadataEnvelope<T>> {
  const items: T[] = []
  const seen = new Set<string>()
  let cursor: string | undefined
  let envelope: MetadataEnvelope<T> | undefined
  do {
    envelope = await fetchPage(cursor)
    items.push(...envelope.items)
    if (!envelope.page.hasMore) break
    const next = envelope.page.nextCursor
    if (!next || seen.has(next)) throw new Error('元数据分页游标缺失或重复，已停止加载')
    seen.add(next)
    cursor = next
  } while (true)
  return { ...envelope!, items, page: { ...envelope!.page, nextCursor: null, hasMore: false } }
}
async function metadata<T extends { name: string }>(fetchPage: (cursor?: string) => Promise<MetadataEnvelope<T>>, kind: ObjectKind): Promise<MetadataEnvelope<T>> {
  void kind
  try { return await allPages(fetchPage) }
  catch (error) {
    if (!(error instanceof SqlIdeApiError) || !error.errorCode?.startsWith('CAPABILITY_')) throw error
    const capability = error.errorCode === 'CAPABILITY_CONDITION_NOT_MET' ? 'conditional' : error.errorCode === 'CAPABILITY_UNKNOWN' ? 'unknown' : 'unsupported'
    const details = error.details && typeof error.details === 'object' ? error.details as { constraints?: string[] } : {}
    return { items: [], capability, constraints: details.constraints ?? [], page: { nextCursor: null, hasMore: false } }
  }
}
const toNodes = <T extends { name: string; kind?: ObjectKind; schema?: string | null; capability?: string; constraints?: string[] }>(
  envelope: MetadataEnvelope<T>, kind: ObjectKind, parent: Record<string, unknown>,
): MetaNode[] => envelope.items.map((item) => ({
  key: `${kind}:${String(item.schema ?? '')}:${item.name}`,
  label: item.name,
  kind: item.kind ?? kind,
  ref: { ...parent, schema: item.schema ?? parent.schema, name: item.name, objectKind: item.kind ?? kind },
  capability: item.capability ?? envelope.capability,
  constraints: item.constraints ?? envelope.constraints,
  leaf: item.capability === 'unsupported' || kind === 'function' || kind === 'procedure' || kind === 'trigger',
})).concat(envelope.items.length || envelope.capability === 'supported' ? [] : [{
  key: `capability:${kind}:${String(parent.database ?? '')}:${String(parent.schema ?? '')}`,
  label: kind,
  kind,
  ref: { ...parent, schema: parent.schema, name: kind, objectKind: kind },
  capability: envelope.capability,
  constraints: envelope.constraints,
  leaf: true,
}])

async function loadNode(node: { data: MetaNode }, resolve: (children: MetaNode[]) => void) {
  const current = node.data
  try {
    if (current.kind === 'source') {
      const result = await metadata((cursor) => contract.listDatabases(props.datasourceId, cursor), 'database')
      resolve(toNodes(result, 'database', current.ref))
      return
    }
    const database = String(current.ref.database ?? (current.kind === 'database' ? current.ref.name : ''))
    const schema = current.kind === 'schema' ? String(current.ref.name) : (current.ref.schema as string | undefined) ?? null
    if (current.kind === 'database') {
      const schemas = await metadata((cursor) => contract.listSchemas(props.datasourceId, database, cursor), 'schema')
      resolve(toNodes(schemas, 'schema', { datasourceId: props.datasourceId, database }))
      return
    }
    if (current.kind === 'schema') {
      const [tables, views, functions, procedures, triggers] = await Promise.all([
        metadata((cursor) => contract.listRelations(props.datasourceId, database, schema, 'table', cursor), 'table'),
        metadata((cursor) => contract.listRelations(props.datasourceId, database, schema, 'view', cursor), 'view'),
        metadata((cursor) => contract.listRoutines(props.datasourceId, database, schema, 'function', cursor), 'function'),
        metadata((cursor) => contract.listRoutines(props.datasourceId, database, schema, 'procedure', cursor), 'procedure'),
        metadata((cursor) => contract.listRoutines(props.datasourceId, database, schema, 'trigger', cursor), 'trigger'),
      ])
      resolve([
        ...toNodes(tables, 'table', { datasourceId: props.datasourceId, database, schema }),
        ...toNodes(views, 'view', { datasourceId: props.datasourceId, database, schema }),
        ...toNodes(functions, 'function', { datasourceId: props.datasourceId, database, schema }),
        ...toNodes(procedures, 'procedure', { datasourceId: props.datasourceId, database, schema }),
        ...toNodes(triggers, 'trigger', { datasourceId: props.datasourceId, database, schema }),
      ])
      return
    }
    if (current.kind === 'table' || current.kind === 'view') {
      const [columns, indexes] = await Promise.all([
        metadata((cursor) => contract.listColumns(props.datasourceId, database, String(current.ref.name), schema, cursor), 'column'),
        metadata((cursor) => contract.listIndexes(props.datasourceId, database, String(current.ref.name), schema, cursor), 'index'),
      ])
      resolve([
        ...columns.items.map((item) => ({ key: `column:${item.name}`, label: item.name, kind: 'column' as const, ref: { ...current.ref, name: item.name }, capability: columns.capability, constraints: columns.constraints, leaf: true })),
        ...indexes.items.map((item) => ({ key: `index:${item.name}`, label: item.name, kind: 'index' as const, ref: { ...current.ref, name: item.name }, capability: indexes.capability, constraints: indexes.constraints, leaf: true })),
      ])
      return
    }
    resolve([])
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    emit('contract-error', message)
    resolve([])
  }
}

async function search(keyword: string) {
  if (!keyword.trim()) { searchMatches.value = []; emit('search-results', []); return }
  try {
    const envelope = await allPages((cursor) => contract.searchObjects(props.datasourceId, keyword.trim(), cursor))
    searchMatches.value = envelope.items
    emit('search-results', searchMatches.value)
  }
  catch (err) { emit('contract-error', err instanceof Error ? err.message : String(err)) }
}
function locate(match: { kind: ObjectKind; name: string; parent: string | null }) {
  treeRef.value?.setCurrentKey(`search:${match.kind}:${match.parent}:${match.name}`)
}
defineExpose({ search, locate })
</script>

<style scoped>
.ide-node { display: inline-flex; align-items: center; gap: 6px; }
.ide-node-muted { color: var(--el-text-color-secondary); }
</style>
