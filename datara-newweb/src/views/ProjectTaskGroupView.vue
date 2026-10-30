<template>
  <main class="pg" aria-label="任务组管理">
    <header class="pg-head">
      <h1 class="sec-head">任务组管理</h1>
      <p class="pg-desc">
        海豚任务组：同一任务组内的节点按「组内优先级」串行执行，不同任务组之间并行。任务组按项目隔离，
        节点表单「任务组名称 / 组内优先级」即取自本页。
      </p>
    </header>

    <div class="toolbar">
      <span class="spacer"></span>
      <button v-if="canCreate" type="button" class="op-btn primary" data-create @click="openCreate">新建任务组</button>
      <button type="button" class="op-btn" data-refresh :disabled="listBusy" @click="reload">刷新</button>
    </div>

    <div v-if="error" class="err-box" role="alert" data-error>
      <span>{{ error }}</span>
      <button type="button" class="op-btn retry" :disabled="listBusy" @click="reload">重试</button>
    </div>

    <div v-if="listBusy" class="panel" role="status" aria-live="polite">
      <div class="skeleton sk-row" style="width:28%"></div>
      <div class="skeleton sk-row" style="width:66%"></div>
      <div class="skeleton sk-row" style="width:48%"></div>
    </div>

    <div v-else-if="rows.length === 0 && !error" class="panel empty" data-empty>
      <div class="e-title">暂无任务组</div>
      <div class="e-hint">还没有创建任何任务组；需要串行执行的节点请先在任务组中归类。</div>
    </div>

    <div v-else-if="rows.length > 0" class="panel">
      <div class="tbl-toolbar">
        <span class="sec-head">任务组清单</span>
        <span class="pill info">{{ visibleRows.length }}</span>
        <input v-model.trim="filterKeyword" data-filter-keyword placeholder="搜索名称或说明" />
        <span class="spacer"></span>
      </div>
      <table class="tbl" data-task-group-list>
        <thead>
          <tr>
            <th>任务组名称</th>
            <th>组大小</th>
            <th>状态</th>
            <th>说明</th>
            <th>归属</th>
            <th>写权限</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in visibleRows"
            :key="row.resourceKey"
            :data-resource-key="row.resourceKey"
            :data-can-manage="String(row.canManage)"
          >
            <td data-col="name">{{ text(row.name) }}</td>
            <td data-col="groupSize">{{ row.groupSize === null ? '—' : row.groupSize }}</td>
            <td data-col="status">{{ statusText(row.status) }}</td>
            <td data-col="description">{{ text(row.description) }}</td>
            <td data-owner>{{ row.ownerId === null ? '公共' : `#${row.ownerId}` }}</td>
            <td data-writable>{{ row.canManage ? '可写' : '只读' }}</td>
            <td class="actions">
              <button type="button" data-share :disabled="!row.canManage" @click="openShare(row)">共享</button>
              <button type="button" data-edit :disabled="!row.canManage" @click="openEdit(row)">编辑</button>
              <button type="button" data-delete :disabled="!row.canManage" @click="remove(row)">关闭</button>
            </td>
          </tr>
          <tr v-if="visibleRows.length === 0">
            <td colspan="7">无匹配记录</td>
          </tr>
        </tbody>
      </table>
    </div>

    <p class="lock-tip" role="note" data-scope-note>
      口径：任务组为项目级资源，按项目隔离；项目 admin 全见，其他成员默认仅见自己创建的，项目管理员可显式共享。
      删除映射为海豚「关闭任务组」（海豚无物理删除）。手动刷新，不做轮询。
    </p>

    <div v-if="editing" class="mask" @click.self="closeEditor">
      <form
        ref="editorRef"
        role="dialog"
        aria-modal="true"
        :aria-label="dialogTitle"
        :style="editorStyle"
        @submit.prevent="save"
      >
        <h2 class="drag-handle" @pointerdown="onEditorPointerdown">{{ dialogTitle }}</h2>
        <label>任务组名称<input v-model.trim="draft.name" required data-name /></label>
        <label>组大小<input v-model.number="draft.groupSize" type="number" min="1" data-group-size /></label>
        <label>说明<textarea v-model.trim="draft.description" rows="3" data-description /></label>
        <p v-if="saveError" class="form-err" role="alert" data-save-error>{{ saveError }}</p>
        <footer>
          <button type="button" @click="closeEditor">取消</button>
          <button type="submit" data-save :disabled="saveBusy">保存</button>
        </footer>
      </form>
    </div>

    <div v-if="sharing" class="mask" @click.self="closeShare">
      <form ref="shareRef" role="dialog" aria-modal="true" aria-label="共享任务组" :style="shareStyle" @submit.prevent="submitShare">
        <h2 class="drag-handle" @pointerdown="onSharePointerdown">共享「{{ shareTarget?.name }}」</h2>
        <label>用户名<input v-model.trim="shareUsername" required data-share-username /></label>
        <p v-if="shareError" class="form-err" role="alert" data-share-error>{{ shareError }}</p>
        <footer>
          <button type="button" data-unshare :disabled="shareBusy || !shareUsername" @click="submitUnshare">取消共享</button>
          <button type="button" @click="closeShare">关闭</button>
          <button type="submit" data-share-save :disabled="shareBusy">共享</button>
        </footer>
      </form>
    </div>
  </main>
</template>

<script setup lang="ts">
/**
 * §10.10 R8 任务组管理（datara 项目级资源）。
 *
 * 真源：docs/designs/2026-10-29-dbx-unified-target-design.md §10.10 R8。
 * 契约面：orchestrationApi（/rebuild/orchestration/task-groups，经编排网关代理海豚
 * TaskGroupController）。列表强制按 projectId 解析的海豚 projectCode 过滤；写门禁
 * EDIT_DEFINITION，owner 隔离（项目 admin 全见 / 成员默认仅自己 / 可显式共享）。
 * 删除映射为海豚 close-task-group（海豚 3.4.3 无物理删除端点）。
 */
import { computed, reactive, ref, watch } from 'vue'
import { useDraggable } from '../composables/useDraggable'
import { authAccount } from '../services/rebuild/authApi'
import { roleHasPermission } from '../services/rebuild/rolePermissions'
import {
  orchestrationApi,
  type TaskGroupDraft,
  type TaskGroupRow,
  type TaskGroupUpdateDraft,
} from '../services/rebuild/orchestrationApi'

const props = defineProps<{ projectId: number }>()

const rows = ref<TaskGroupRow[]>([])
const filterKeyword = ref('')
const listBusy = ref(false)
const error = ref('')

const canCreate = computed(() => {
  const role = authAccount.value?.role
  return !!role && roleHasPermission(role, 'edit_definition')
})

const visibleRows = computed(() => {
  const keyword = filterKeyword.value.toLowerCase()
  if (keyword === '') return rows.value
  return rows.value.filter((row) => {
    const haystack = `${row.name ?? ''} ${row.description ?? ''}`.toLowerCase()
    return haystack.includes(keyword) || row.resourceKey.toLowerCase().includes(keyword)
  })
})

function text(value: string | null | undefined): string {
  return value === null || value === undefined || value === '' ? '—' : value
}

/** 海豚任务组状态：1 = 运行中，0 = 已关闭（close-task-group 置 0）。 */
function statusText(status: string | null): string {
  if (status === '1') return '运行中'
  if (status === '0') return '已关闭'
  return status === null || status === '' ? '—' : status
}

const message = (e: unknown): string => (e instanceof Error ? e.message : String(e))

const errorText = (e: unknown): string => {
  const code = (e as { code?: number | string } | null)?.code
  return code !== undefined && code !== 0 && code !== '0' ? `操作失败（code ${code}）：${message(e)}` : message(e)
}

async function reload(): Promise<void> {
  const projectId = props.projectId
  listBusy.value = true
  error.value = ''
  try {
    rows.value = await orchestrationApi.listTaskGroups(projectId)
  } catch (e) {
    rows.value = []
    error.value = errorText(e)
  } finally {
    listBusy.value = false
  }
}

/* ---------- 新建 / 编辑弹窗 ---------- */

const editing = ref(false)
/** 编辑目标的业务键；空表示新建。 */
const editingKey = ref('')
const editingId = ref<number | null>(null)
const saveBusy = ref(false)
const saveError = ref('')

const draft = reactive({
  name: '',
  description: '',
  groupSize: 100,
})

const editorRef = ref<HTMLElement | null>(null)
const { dragStyle: editorStyle, onHandlePointerdown: onEditorPointerdown } = useDraggable(editorRef, editorRef, {
  storageKey: 'orchestration.task-group.edit',
})

const dialogTitle = computed(() => (editingKey.value === '' ? '新建任务组' : '编辑任务组'))

function resetDraft(row?: TaskGroupRow): void {
  draft.name = ''
  draft.description = ''
  draft.groupSize = 100
  if (!row) return
  draft.name = row.name ?? ''
  draft.description = row.description ?? ''
  draft.groupSize = row.groupSize ?? 100
}

function openCreate(): void {
  editingKey.value = ''
  editingId.value = null
  saveError.value = ''
  resetDraft()
  editing.value = true
}

function openEdit(row: TaskGroupRow): void {
  editingKey.value = row.resourceKey
  editingId.value = row.id
  saveError.value = ''
  resetDraft(row)
  editing.value = true
}

function closeEditor(): void {
  editing.value = false
  saveError.value = ''
}

async function save(): Promise<void> {
  saveError.value = ''
  saveBusy.value = true
  const key = editingKey.value
  try {
    if (key === '') {
      const payload: TaskGroupDraft = {
        projectId: props.projectId,
        name: draft.name,
        description: draft.description,
        groupSize: draft.groupSize,
      }
      await orchestrationApi.createTaskGroup(payload)
    } else {
      const payload: TaskGroupUpdateDraft = {
        name: draft.name,
        description: draft.description,
        groupSize: draft.groupSize,
      }
      await orchestrationApi.updateTaskGroup(editingId.value ?? key, payload)
    }
  } catch (e) {
    saveError.value = errorText(e)
    saveBusy.value = false
    return
  }
  saveBusy.value = false
  closeEditor()
  await reload()
}

async function remove(row: TaskGroupRow): Promise<void> {
  if (!globalThis.confirm(`关闭任务组「${row.name}」？关闭后将不可再被节点引用。`)) return
  error.value = ''
  try {
    await orchestrationApi.deleteTaskGroup(row.id ?? row.resourceKey)
    await reload()
  } catch (e) {
    error.value = errorText(e)
  }
}

/* ---------- 显式共享弹窗 ---------- */

const sharing = ref(false)
const shareTarget = ref<TaskGroupRow | null>(null)
const shareUsername = ref('')
const shareBusy = ref(false)
const shareError = ref('')

const shareRef = ref<HTMLElement | null>(null)
const { dragStyle: shareStyle, onHandlePointerdown: onSharePointerdown } = useDraggable(shareRef, shareRef, {
  storageKey: 'orchestration.task-group.share',
})

function openShare(row: TaskGroupRow): void {
  shareTarget.value = row
  shareUsername.value = ''
  shareError.value = ''
  sharing.value = true
}

function closeShare(): void {
  sharing.value = false
  shareError.value = ''
}

async function submitShare(): Promise<void> {
  const target = shareTarget.value
  if (!target) return
  shareError.value = ''
  shareBusy.value = true
  try {
    await orchestrationApi.share('task_group', target.resourceKey, shareUsername.value)
    closeShare()
    await reload()
  } catch (e) {
    shareError.value = errorText(e)
  } finally {
    shareBusy.value = false
  }
}

async function submitUnshare(): Promise<void> {
  const target = shareTarget.value
  if (!target) return
  shareError.value = ''
  shareBusy.value = true
  try {
    await orchestrationApi.unshare('task_group', target.resourceKey, shareUsername.value)
    closeShare()
    await reload()
  } catch (e) {
    shareError.value = errorText(e)
  } finally {
    shareBusy.value = false
  }
}

/**
 * projectId 变化须重新取数（清空过滤与弹窗）。置于弹窗状态声明之后，
 * 避免 immediate 回调触碰尚未初始化的 ref（TDZ）。
 */
watch(
  () => props.projectId,
  () => {
    filterKeyword.value = ''
    rows.value = []
    closeEditor()
    closeShare()
    void reload()
  },
  { immediate: true },
)
</script>

<style scoped>
.actions { display: flex; gap: 6px; }
.mask form {
  width: min(520px, calc(100vw - 40px));
  display: grid;
  gap: 12px;
  background: var(--card);
  padding: 24px;
  border-radius: var(--radius-lg);
}
.mask label { display: grid; gap: 5px; }
.mask input,
.mask textarea { padding: 8px; font: inherit; }
.mask footer { display: flex; justify-content: flex-end; gap: 8px; }
.form-err { color: var(--danger, #d92d20); margin: 0; font-size: 12.5px; }
.drag-handle { cursor: grab; user-select: none; margin: 0; }
.drag-handle:active { cursor: grabbing; }
</style>
