<template>
  <div v-if="open" class="ide-dialog-mask" data-table-dialog @click.self="close">
    <section ref="tdPanelRef" class="ide-dialog ide-dialog-wide" role="dialog" aria-label="编辑数据" :style="tdDragStyle">
      <header ref="tdHeadRef" class="ide-dialog-head" @pointerdown="onTdDragStart">
        <h3>编辑数据 · {{ schema }}.{{ table }}</h3>
        <button type="button" data-dialog-close @click="close">×</button>
      </header>

      <p class="ide-muted" data-dialog-pk-hint>
        <template v-if="primaryKeys.length">主键：{{ primaryKeys.join('，') }}（主键列不可编辑）</template>
        <template v-else>⚠ 该表无主键：仅支持追加行，翻页可能漂移</template>
      </p>
      <p v-if="error" class="ide-err" data-dialog-error role="alert">{{ error }}</p>
      <p v-if="notice" class="ide-diag" data-dialog-notice role="status">{{ notice }}</p>
      <p v-if="dirtyCount > 0" class="ide-warn" data-dialog-dirty>未应用变更 {{ dirtyCount }} 条（应用前翻页将丢弃）</p>

      <div class="ide-dialog-body">
        <table class="ide-data-table" data-data-table>
          <thead>
            <tr>
              <th class="ide-col-ops">操作</th>
              <th v-for="c in columns" :key="c">{{ c }}<small v-if="primaryKeys.includes(c)"> 🔑</small></th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="rows.length === 0 && !loading">
              <td :colspan="columns.length + 1" class="ide-muted">暂无数据</td>
            </tr>
            <tr v-for="(row, idx) in rows" :key="idx" :class="{ deleted: row.state === 'deleted' }">
              <td class="ide-col-ops">
                <button v-if="row.state !== 'inserted'" type="button"
                        :data-row-delete="idx"
                        @click="toggleDeleteRow(row)">{{ row.state === 'deleted' ? '恢复' : '删行' }}</button>
                <button v-else type="button" :data-row-drop="idx" @click="dropInsertedRow(idx)">移除</button>
              </td>
              <td v-for="c in columns" :key="c">
                <input v-model="row.data[c]"
                       :data-cell="`${row.state}:${c}`"
                       :class="{ edited: cellEdited(row, c) }"
                       :disabled="primaryKeys.includes(c) && row.state !== 'inserted'"
                       @input="markEdited(row)" />
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="loading" class="ide-muted">加载中…</p>
      </div>

      <footer class="ide-dialog-foot">
        <span class="ide-muted">共 {{ total }} 行 · 第 {{ page }}/{{ pageCount }} 页</span>
        <button type="button" data-page-prev :disabled="page <= 1 || loading" @click="changePage(page - 1)">上一页</button>
        <button type="button" data-page-next :disabled="page >= pageCount || loading" @click="changePage(page + 1)">下一页</button>
        <button type="button" data-row-append :disabled="!primaryKeys.length && !columns.length" @click="appendRow">＋ 追加行</button>
        <button type="button" data-apply-changes :disabled="applying || dirtyCount === 0" @click="applyChanges">
          {{ applying ? '应用中…' : `应用变更（${dirtyCount}）` }}
        </button>
      </footer>
    </section>
  </div>
</template>

<script setup lang="ts">
/**
 * 编辑数据弹窗（对标审计-03 §6.4 / G23）。
 *
 * 数据面走 B4-d 新契约：listTableRows 分页读取（200 行/页）+ applyTableRows
 * 单事务整批提交（后端 1000 行硬上限，失败整体回滚）。变更在行内编辑：
 * edited 行黄框高亮、deleted 行可恢复、inserted 行可移除；主键列只读。
 * 组件不自动执行任何 SQL——全部变更经后端事务接口落库。
 */
import { computed, ref, watch } from 'vue'
import { useDraggable } from '../../composables/useDraggable'
import type { SqlIdeContract } from '../../services/rebuild/sqlIdeApi'

const ROWS_PER_PAGE = 200
const MAX_BATCH_CHANGES = 1000

type RowState = 'clean' | 'edited' | 'deleted' | 'inserted'

interface EditableRow {
  state: RowState
  data: Record<string, unknown>
  original: Record<string, unknown> | null
}

const props = defineProps<{
  open: boolean
  api: SqlIdeContract
  datasourceId: number | null
  schema: string
  table: string
}>()

const emit = defineEmits<{ (e: 'update:open', value: boolean): void; (e: 'applied', summary: string): void }>()

/* G14 §2.2：弹窗默认可拖动 + 视口钳制 + 位置记忆（把手=标题栏） */
const tdPanelRef = ref<HTMLElement | null>(null)
const tdHeadRef = ref<HTMLElement | null>(null)
const { dragStyle: tdDragStyle, onHandlePointerdown: onTdDragStart } = useDraggable(tdPanelRef, tdHeadRef, { storageKey: 'ide.table-data' })

const rows = ref<EditableRow[]>([])
const columns = ref<string[]>([])
const primaryKeys = ref<string[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const applying = ref(false)
const error = ref('')
const notice = ref('')

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / ROWS_PER_PAGE)))
const dirtyCount = computed(() =>
  rows.value.filter((r) => r.state === 'edited' || r.state === 'deleted' || r.state === 'inserted').length,
)

watch(() => props.open, (open) => {
  if (open) void reload(1)
})

async function reload(targetPage: number): Promise<void> {
  // 未选数据源时给出可见提示，而不是静默失败（旧前端行为复刻）
  if (props.datasourceId === null) {
    error.value = '未选择数据源实例，无法加载表数据'
    columns.value = []
    rows.value = []
    total.value = 0
    return
  }
  loading.value = true
  error.value = ''
  notice.value = ''
  try {
    const result = await props.api.listTableRows({
      datasourceId: props.datasourceId,
      schema: props.schema,
      table: props.table,
      limit: ROWS_PER_PAGE,
      offset: (targetPage - 1) * ROWS_PER_PAGE,
    })
    columns.value = result.columns
    primaryKeys.value = result.primaryKeys
    total.value = result.total
    page.value = targetPage
    // rows 是与 columns 对齐的数组（对象键会被 HTTP 适配层 snake→camel 改写）
    rows.value = result.rows.map((arr) => {
      const data: Record<string, unknown> = {}
      columns.value.forEach((c, i) => { data[c] = arr[i] })
      return { state: 'clean', data, original: { ...data } }
    })
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

function cellEdited(row: EditableRow, column: string): boolean {
  if (row.state === 'inserted') return true
  if (row.state !== 'edited' || row.original === null) return false
  return row.data[column] !== row.original[column]
}

function markEdited(row: EditableRow): void {
  if (row.state === 'clean') row.state = 'edited'
}

function toggleDeleteRow(row: EditableRow): void {
  if (row.state === 'deleted') {
    row.state = 'edited'
    row.data = { ...(row.original ?? {}) }
    // 恢复后若无实际差异退回 clean
    row.state = columns.value.every((c) => row.data[c] === row.original?.[c]) ? 'clean' : 'edited'
  } else if (row.state !== 'inserted') {
    row.state = 'deleted'
  }
}

function dropInsertedRow(index: number): void {
  rows.value.splice(index, 1)
}

function appendRow(): void {
  const blank: Record<string, unknown> = {}
  for (const c of columns.value) blank[c] = ''
  rows.value.push({ state: 'inserted', data: blank, original: null })
}

async function changePage(target: number): Promise<void> {
  if (target < 1 || target > pageCount.value) return
  if (dirtyCount.value > 0) notice.value = '未应用变更已丢弃'
  await reload(target)
}

function isEmptyValue(value: unknown): boolean {
  return value === '' || value === null || value === undefined
}

async function applyChanges(): Promise<void> {
  if (props.datasourceId === null) {
    error.value = '未选择数据源实例，无法应用表数据'
    return
  }
  error.value = ''
  const inserts = rows.value
    .filter((r) => r.state === 'inserted')
    .map((r) => r.data)
    .filter((data) => columns.value.some((c) => !isEmptyValue(data[c])))
  const updates = rows.value
    .filter((r) => r.state === 'edited')
    .map((r) => ({
      keys: Object.fromEntries(primaryKeys.value.map((pk) => [pk, r.data[pk]])),
      set: Object.fromEntries(
        columns.value
          .filter((c) => !primaryKeys.value.includes(c) && r.data[c] !== r.original?.[c])
          .map((c) => [c, r.data[c]]),
      ),
    }))
    .filter((u) => Object.keys(u.set).length > 0)
  const deletes = rows.value
    .filter((r) => r.state === 'deleted')
    .map((r) => Object.fromEntries(primaryKeys.value.map((pk) => [pk, r.data[pk]])))
  const batchTotal = inserts.length + updates.length + deletes.length
  if (batchTotal === 0) {
    notice.value = '无有效变更'
    return
  }
  if (batchTotal > MAX_BATCH_CHANGES) {
    error.value = `单次应用上限 ${MAX_BATCH_CHANGES} 行（当前 ${batchTotal} 行），请分批应用`
    return
  }
  applying.value = true
  try {
    const result = await props.api.applyTableRows({
      datasourceId: props.datasourceId,
      schema: props.schema,
      table: props.table,
      primaryKeys: primaryKeys.value,
      inserts,
      updates,
      deletes,
    })
    emit('applied', `应用成功：增 ${result.inserted} / 改 ${result.updated} / 删 ${result.deleted} 条`)
    await reload(page.value)
  } catch (e) {
    error.value = `应用失败，已整体回滚：${e instanceof Error ? e.message : String(e)}`
  } finally {
    applying.value = false
  }
}

function close(): void {
  emit('update:open', false)
}
</script>

<style scoped>
.ide-dialog-mask{position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:60;display:flex;align-items:flex-start;justify-content:center}
.ide-dialog{background:var(--card);color:var(--text);border:1px solid var(--border);border-radius:var(--radius);margin-top:5vh;width:86%;max-width:1400px;display:flex;flex-direction:column;max-height:88vh}
.ide-dialog-head{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;border-bottom:1px solid var(--border);cursor:grab;user-select:none}
.ide-dialog-head:active{cursor:grabbing}
.ide-dialog-head h3{margin:0;font-size:15px}
.ide-dialog-head button{border:none;background:transparent;color:var(--text-2);font-size:18px;cursor:pointer}
.ide-dialog-body{padding:12px 16px;overflow:auto;flex:1;min-height:120px}
.ide-dialog-foot{display:flex;align-items:center;gap:10px;padding:12px 16px;border-top:1px solid var(--border);flex-wrap:wrap}
.ide-dialog-foot button:last-child{margin-left:auto}
.ide-data-table{border-collapse:collapse;width:100%;font-size:12px}
.ide-data-table th,.ide-data-table td{border:1px solid var(--border);padding:4px 6px;text-align:left;white-space:nowrap}
.ide-data-table th{background:var(--card-2,var(--card));position:sticky;top:0}
.ide-data-table input{width:100%;min-width:90px;border:1px solid transparent;background:transparent;color:inherit;font:inherit;padding:2px 4px;box-sizing:border-box}
.ide-data-table input:focus{outline:none;border-color:var(--primary)}
.ide-data-table input.edited{border-color:var(--warn);background:var(--warn-bg)}
.ide-data-table tr.deleted{opacity:.45;text-decoration:line-through}
.ide-col-ops{width:70px}
.ide-warn{color:var(--warn);font-size:12px;margin:6px 16px 0}
.ide-err{color:var(--danger);font-size:12px;margin:6px 16px 0}
.ide-diag{color:var(--text-2);font-size:12px;margin:6px 16px 0}
.ide-muted{color:var(--text-2);font-size:12px}
</style>
