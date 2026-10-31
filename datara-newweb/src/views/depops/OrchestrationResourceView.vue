<template>
  <main class="pg" :aria-label="meta.title">
    <header class="pg-head">
      <h1 class="sec-head">{{ meta.title }}</h1>
      <p class="pg-desc">{{ meta.description }}</p>
    </header>

    <div class="toolbar">
      <DepOpsSubNav />
      <span class="spacer"></span>
      <button v-if="canCreate" type="button" class="op-btn primary" data-create @click="openCreate">
        {{ meta.createLabel }}
      </button>
      <button type="button" class="op-btn" data-refresh :disabled="listBusy" @click="reload">刷新</button>
    </div>

    <!-- 错误横幅独立于内容态：加载失败时无数据可渲染，刷新失败时列表须保留 -->
    <div v-if="error" class="err-box" role="alert" data-error>
      <span>{{ error }}</span>
      <button type="button" class="op-btn retry" :disabled="listBusy" @click="reload">重试</button>
    </div>

    <div v-if="listBusy" class="panel" role="status" aria-live="polite">
      <div class="skeleton sk-row" style="width:28%"></div>
      <div class="skeleton sk-row" style="width:66%"></div>
      <div class="skeleton sk-row" style="width:48%"></div>
    </div>

    <!-- 空态须让位于错误态：加载失败时不得呈现「暂无数据」空壳 -->
    <div v-else-if="rows.length === 0 && !error" class="panel empty" data-empty>
      <div class="e-title">{{ meta.emptyTitle }}</div>
      <div class="e-hint">{{ meta.emptyHint }}</div>
    </div>

    <div v-else-if="rows.length > 0" class="panel">
      <div class="tbl-toolbar">
        <span class="sec-head">{{ meta.listTitle }}</span>
        <span class="pill info">{{ visibleRows.length }}</span>
        <input v-model.trim="filterKeyword" data-filter-keyword placeholder="搜索名称或标识" />
        <span class="spacer"></span>
      </div>
      <table class="tbl" data-resource-list>
        <thead>
          <tr>
            <th v-for="col in columns" :key="col.key">{{ col.label }}</th>
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
            <td v-for="col in columns" :key="col.key" :data-col="col.key">{{ col.value(row) }}</td>
            <td data-owner>{{ row.ownerId === null ? '公共' : `#${row.ownerId}` }}</td>
            <td data-writable>{{ row.canManage ? '可写' : '只读' }}</td>
            <td class="actions">
              <button type="button" class="mini-btn" data-share :disabled="!row.canManage" @click="openShare(row)">共享</button>
              <button type="button" class="mini-btn" data-edit :disabled="!row.canManage || isReadonly(row)" @click="openEdit(row)">编辑</button>
              <button type="button" class="mini-btn danger" data-delete :disabled="!row.canManage || isReadonly(row)" @click="remove(row)">删除</button>
            </td>
          </tr>
          <tr v-if="visibleRows.length === 0">
            <td :colspan="columns.length + 3">无匹配记录</td>
          </tr>
        </tbody>
      </table>
    </div>

    <p class="lock-tip" role="note" data-scope-note>{{ meta.note }}</p>

    <!-- 新建 / 编辑弹窗（字段按 kind 分支，一个弹窗覆盖四类资源） -->
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

        <template v-if="kind === 'worker_group'">
          <label>分组名称<input v-model.trim="draft.name" required data-name /></label>
          <label>地址列表<input v-model.trim="draft.addrList" placeholder="host:port，逗号分隔" data-addr-list /></label>
          <label>说明<input v-model.trim="draft.description" data-description /></label>
        </template>

        <template v-else-if="kind === 'environment'">
          <label>环境名称<input v-model.trim="draft.name" required data-name /></label>
          <label>环境变量配置<textarea v-model="draft.config" rows="4" placeholder="KEY=VALUE，每行一条" data-config /></label>
          <label>说明<input v-model.trim="draft.description" data-description /></label>
          <fieldset class="checks" data-worker-groups>
            <legend>关联 Worker 分组</legend>
            <label v-for="name in workerGroupOptions" :key="name" class="check">
              <input v-model="draft.workerGroups" type="checkbox" :value="name" data-worker-group-option />{{ name }}
            </label>
            <p v-if="workerGroupOptions.length === 0" class="hint">暂无可选 worker 分组</p>
          </fieldset>
        </template>

        <template v-else-if="kind === 'queue'">
          <label>队列标识<input v-model.trim="draft.queue" required data-queue /></label>
          <label>队列名称<input v-model.trim="draft.queueName" required data-queue-name /></label>
        </template>

        <template v-else>
          <label>集群名称<input v-model.trim="draft.name" required data-name /></label>
          <label>集群配置<textarea v-model="draft.config" rows="4" data-config /></label>
          <label>说明<input v-model.trim="draft.description" data-description /></label>
        </template>

        <p v-if="saveError" class="form-err" role="alert" data-save-error>{{ saveError }}</p>
        <footer>
          <button type="button" class="mini-btn" @click="closeEditor">取消</button>
          <button type="submit" class="mini-btn primary" data-save :disabled="saveBusy">保存</button>
        </footer>
      </form>
    </div>

    <!-- 显式共享弹窗（§10.10：资源按 admin 或显式共享可见） -->
    <div v-if="sharing" class="mask" @click.self="closeShare">
      <form ref="shareRef" role="dialog" aria-modal="true" aria-label="共享资源" :style="shareStyle" @submit.prevent="submitShare">
        <h2 class="drag-handle" @pointerdown="onSharePointerdown">共享「{{ shareTarget?.resourceKey }}」</h2>
        <label>用户名<input v-model.trim="shareUsername" required data-share-username /></label>
        <p v-if="shareError" class="form-err" role="alert" data-share-error>{{ shareError }}</p>
        <footer>
          <button type="button" class="mini-btn" data-unshare :disabled="shareBusy || !shareUsername" @click="submitUnshare">取消共享</button>
          <button type="button" class="mini-btn" @click="closeShare">关闭</button>
          <button type="submit" class="mini-btn primary" data-share-save :disabled="shareBusy">共享</button>
        </footer>
      </form>
    </div>
  </main>
</template>

<script setup lang="ts">
/**
 * §10.10 部署运维资源页（R1 Worker 分组 / R2 环境管理 / R3 Yarn 队列 / R4 集群管理）。
 *
 * 真源：docs/designs/2026-10-29-dbx-unified-target-design.md §10.10。
 * 契约面：`orchestrationApi`（/rebuild/orchestration，经编排网关代理海豚，前端不直连
 * 海豚 API）。写入门禁与后端一致：worker 分组/环境 = EDIT_DEFINITION，
 * 队列/集群 = MANAGE_USER（admin-only，普通用户只在节点表单选用）。
 *
 * 一个组件按 `kind` prop 驱动四页，避免四份近似重复实现；路由各自具名注册。
 * 数据红线：手动刷新不轮询；空态与错误态互斥；不可写行（含海豚 CONFIG 来源的
 * 系统默认分组）禁用编辑/删除。
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import DepOpsSubNav from '../../components/DepOpsSubNav.vue'
import { useDraggable } from '../../composables/useDraggable'
import { authAccount } from '../../services/rebuild/authApi'
import { roleHasPermission, type Permission } from '../../services/rebuild/rolePermissions'
import {
  ORCHESTRATION_RESOURCE_PERMISSION_MATRIX,
  orchestrationApi,
  type ClusterRow,
  type ClusterDraft,
  type EnvironmentRow,
  type EnvironmentDraft,
  type OrchestrationResourceKind,
  type OrchestrationResourcePermission,
  type QueueRow,
  type QueueDraft,
  type WorkerGroupDraft,
  type WorkerGroupRow,
} from '../../services/rebuild/orchestrationApi'

const props = defineProps<{ kind: DeployOpsResourceKind }>()

/**
 * 本组件承载部署运维的全局/项目环境类资源；任务组属项目级资源
 * （§10.10 R8），由 ProjectTaskGroupView 承载 —— 二者均不进入本组件。
 */
type DeployOpsResourceKind = Exclude<OrchestrationResourceKind, 'task_group' | 'resource_file'>

type ResourceRow = WorkerGroupRow | EnvironmentRow | QueueRow | ClusterRow

interface ColumnDef {
  key: string
  label: string
  value: (row: ResourceRow) => string
}

interface PageMeta {
  title: string
  description: string
  listTitle: string
  emptyTitle: string
  emptyHint: string
  createLabel: string
  note: string
}

const META: Record<DeployOpsResourceKind, PageMeta> = {
  worker_group: {
    title: 'Worker 分组',
    description:
      '海豚 Worker 分组：任务按分组路由到运行位置。数据源不在本页维护（唯一真源为 dbx）；运行位置类节点（SHELL / PYTHON / REMOTESHELL）统一挂 worker 分组。',
    listTitle: '分组清单',
    emptyTitle: '暂无 Worker 分组',
    emptyHint: '还没有创建任何 worker 分组；海豚 CONFIG 来源的系统默认分组也不可见。',
    createLabel: '新建分组',
    note: '口径：写操作经编排网关代理海豚，按 owner 隔离；海豚 CONFIG 来源的系统默认分组为只读。手动刷新，不做轮询。',
  },
  environment: {
    title: '环境管理',
    description:
      '海豚环境：一组环境变量配置，按 worker 分组绑定，节点表单按环境引用。环境变量值经编排网关存储，不在前端持久化。',
    listTitle: '环境清单',
    emptyTitle: '暂无环境',
    emptyHint: '还没有创建任何环境配置。',
    createLabel: '新建环境',
    note: '口径：写操作经编排网关代理海豚，按 owner 隔离。手动刷新，不做轮询。',
  },
  queue: {
    title: 'Yarn 队列',
    description:
      '海豚 Yarn 队列：全局资源配置，仅管理员可新建/修改；普通用户在节点表单中选用，不在本页新建。',
    listTitle: '队列清单',
    emptyTitle: '暂无 Yarn 队列',
    emptyHint: '还没有创建任何 Yarn 队列。',
    createLabel: '新建队列',
    note: '口径：队列为全局资源配置，仅 admin（MANAGE_USER）可写；普通用户只读并在节点表单选用。手动刷新，不做轮询。',
  },
  cluster: {
    title: '集群管理',
    description:
      '海豚集群配置：全局资源配置，仅管理员可新建/修改；普通用户在节点表单中选用。K8s 命名空间不单独立项，跟随集群管理。',
    listTitle: '集群清单',
    emptyTitle: '暂无集群',
    emptyHint: '还没有创建任何集群配置。',
    createLabel: '新建集群',
    note: '口径：集群为全局资源配置，仅 admin（MANAGE_USER）可写；K8s 命名空间跟随集群管理，不单列菜单。手动刷新，不做轮询。',
  },
}

const COLUMNS: Record<DeployOpsResourceKind, ColumnDef[]> = {
  worker_group: [
    { key: 'name', label: '分组名称', value: (r) => text((r as WorkerGroupRow).name) },
    { key: 'addrList', label: '地址列表', value: (r) => text((r as WorkerGroupRow).addrList) },
    { key: 'description', label: '说明', value: (r) => text((r as WorkerGroupRow).description) },
    { key: 'source', label: '来源', value: (r) => text((r as WorkerGroupRow).source) },
  ],
  environment: [
    { key: 'name', label: '环境名称', value: (r) => text((r as EnvironmentRow).name) },
    {
      key: 'workerGroups',
      label: '关联分组',
      value: (r) => {
        const groups = (r as EnvironmentRow).workerGroups
        return groups && groups.length > 0 ? groups.join(', ') : '—'
      },
    },
    { key: 'config', label: '变量配置', value: (r) => text((r as EnvironmentRow).config) },
    { key: 'description', label: '说明', value: (r) => text((r as EnvironmentRow).description) },
  ],
  queue: [
    { key: 'queueName', label: '队列名称', value: (r) => text((r as QueueRow).queueName) },
    { key: 'queue', label: '队列标识', value: (r) => text((r as QueueRow).queue) },
  ],
  cluster: [
    { key: 'name', label: '集群名称', value: (r) => text((r as ClusterRow).name) },
    { key: 'config', label: '集群配置', value: (r) => text((r as ClusterRow).config) },
    { key: 'description', label: '说明', value: (r) => text((r as ClusterRow).description) },
  ],
}

/** 后端权限词（大写）→ 前端冻结矩阵词（小写）。 */
const PERMISSION_WIRE: Record<OrchestrationResourcePermission, Permission> = {
  VIEW_ALL: 'view_all',
  EDIT_DEFINITION: 'edit_definition',
  MANAGE_USER: 'manage_user',
}

const meta = computed(() => META[props.kind])
const columns = computed(() => COLUMNS[props.kind])

/** 新建门：矩阵声明所需权限点，当前角色持有才显示新建按钮（后端仍是最终裁决）。 */
const canCreate = computed(() => {
  const role = authAccount.value?.role
  if (!role) return false
  return roleHasPermission(role, PERMISSION_WIRE[ORCHESTRATION_RESOURCE_PERMISSION_MATRIX[props.kind].create])
})

const rows = ref<ResourceRow[]>([])
const filterKeyword = ref('')
const listBusy = ref(false)
const error = ref('')

const visibleRows = computed(() => {
  const keyword = filterKeyword.value.toLowerCase()
  if (keyword === '') return rows.value
  return rows.value.filter((row) => {
    if (row.resourceKey.toLowerCase().includes(keyword)) return true
    return columns.value.some((col) => col.value(row).toLowerCase().includes(keyword))
  })
})

function text(value: string | null | undefined): string {
  return value === null || value === undefined || value === '' ? '—' : value
}

const message = (e: unknown): string => (e instanceof Error ? e.message : String(e))

/** 非 0 包络码须随错误信息透出（编排网关错误码为字符串，经 preserveEnvelopeCode 保码）。 */
const errorText = (e: unknown): string => {
  const code = (e as { code?: number | string } | null)?.code
  return code !== undefined && code !== 0 && code !== '0' ? `操作失败（code ${code}）：${message(e)}` : message(e)
}

/** 海豚 CONFIG 来源的系统默认分组不可写。 */
function isReadonly(row: ResourceRow): boolean {
  return props.kind === 'worker_group' && (row as WorkerGroupRow).systemDefault === true
}

async function loadRows(kind: DeployOpsResourceKind): Promise<ResourceRow[]> {
  switch (kind) {
    case 'worker_group':
      return orchestrationApi.listWorkerGroups()
    case 'environment':
      return orchestrationApi.listEnvironments()
    case 'queue':
      return orchestrationApi.listQueues()
    case 'cluster':
      return orchestrationApi.listClusters()
  }
}

async function reload(): Promise<void> {
  listBusy.value = true
  error.value = ''
  try {
    rows.value = await loadRows(props.kind)
  } catch (e) {
    error.value = errorText(e)
  } finally {
    listBusy.value = false
  }
}

/* ---------- 新建 / 编辑弹窗 ---------- */

const editing = ref(false)
/** 编辑目标的业务键；空表示新建。 */
const editingKey = ref('')
const saveBusy = ref(false)
const saveError = ref('')
const workerGroupOptions = ref<string[]>([])

const draft = reactive({
  name: '',
  addrList: '',
  description: '',
  config: '',
  workerGroups: [] as string[],
  queue: '',
  queueName: '',
})

const editorRef = ref<HTMLElement | null>(null)
const { dragStyle: editorStyle, onHandlePointerdown: onEditorPointerdown } = useDraggable(editorRef, editorRef, {
  storageKey: 'orchestration.resource.edit',
})

const dialogTitle = computed(() => (editingKey.value === '' ? meta.value.createLabel : `编辑${meta.value.title}`))

function resetDraft(row?: ResourceRow): void {
  draft.name = ''
  draft.addrList = ''
  draft.description = ''
  draft.config = ''
  draft.workerGroups = []
  draft.queue = ''
  draft.queueName = ''
  if (!row) return
  if (props.kind === 'worker_group') {
    const g = row as WorkerGroupRow
    draft.name = g.name ?? ''
    draft.addrList = g.addrList ?? ''
    draft.description = g.description ?? ''
  } else if (props.kind === 'environment') {
    const env = row as EnvironmentRow
    draft.name = env.name ?? ''
    draft.config = env.config ?? ''
    draft.description = env.description ?? ''
    draft.workerGroups = [...(env.workerGroups ?? [])]
  } else if (props.kind === 'queue') {
    const q = row as QueueRow
    draft.queue = q.queue ?? ''
    draft.queueName = q.queueName ?? ''
  } else {
    const c = row as ClusterRow
    draft.name = c.name ?? ''
    draft.config = c.config ?? ''
    draft.description = c.description ?? ''
  }
}

async function loadWorkerGroupOptions(): Promise<void> {
  try {
    const list = await orchestrationApi.listWorkerGroups()
    workerGroupOptions.value = list.map((g) => g.name).filter((n) => n !== '')
  } catch {
    // 关联分组是辅助选项：取不到时留空并如实提示「暂无可选 worker 分组」，不阻塞环境编辑。
    workerGroupOptions.value = []
  }
}

function openCreate(): void {
  editingKey.value = ''
  saveError.value = ''
  resetDraft()
  editing.value = true
  if (props.kind === 'environment') void loadWorkerGroupOptions()
}

function openEdit(row: ResourceRow): void {
  editingKey.value = row.resourceKey
  saveError.value = ''
  resetDraft(row)
  editing.value = true
  if (props.kind === 'environment') void loadWorkerGroupOptions()
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
    switch (props.kind) {
      case 'worker_group': {
        const payload: WorkerGroupDraft = { name: draft.name, addrList: draft.addrList, description: draft.description }
        if (key === '') await orchestrationApi.createWorkerGroup(payload)
        else await orchestrationApi.updateWorkerGroup(key, payload)
        break
      }
      case 'environment': {
        const payload: EnvironmentDraft = {
          name: draft.name,
          config: draft.config,
          description: draft.description,
          workerGroups: [...draft.workerGroups],
        }
        if (key === '') await orchestrationApi.createEnvironment(payload)
        else await orchestrationApi.updateEnvironment(key, payload)
        break
      }
      case 'queue': {
        const payload: QueueDraft = { queue: draft.queue, queueName: draft.queueName }
        if (key === '') await orchestrationApi.createQueue(payload)
        else await orchestrationApi.updateQueue(key, payload)
        break
      }
      case 'cluster': {
        const payload: ClusterDraft = { name: draft.name, config: draft.config, description: draft.description }
        if (key === '') await orchestrationApi.createCluster(payload)
        else await orchestrationApi.updateCluster(key, payload)
        break
      }
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

async function remove(row: ResourceRow): Promise<void> {
  if (!globalThis.confirm(`删除「${row.resourceKey}」？`)) return
  error.value = ''
  try {
    switch (props.kind) {
      case 'worker_group':
        await orchestrationApi.deleteWorkerGroup(row.resourceKey)
        break
      case 'environment':
        await orchestrationApi.deleteEnvironment(row.resourceKey)
        break
      case 'queue':
        await orchestrationApi.deleteQueue(row.resourceKey)
        break
      case 'cluster':
        await orchestrationApi.deleteCluster(row.resourceKey)
        break
    }
    await reload()
  } catch (e) {
    error.value = errorText(e)
  }
}

/* ---------- 显式共享弹窗 ---------- */

const sharing = ref(false)
const shareTarget = ref<ResourceRow | null>(null)
const shareUsername = ref('')
const shareBusy = ref(false)
const shareError = ref('')

const shareRef = ref<HTMLElement | null>(null)
const { dragStyle: shareStyle, onHandlePointerdown: onSharePointerdown } = useDraggable(shareRef, shareRef, {
  storageKey: 'orchestration.resource.share',
})

function openShare(row: ResourceRow): void {
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
    await orchestrationApi.share(props.kind, target.resourceKey, shareUsername.value)
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
    await orchestrationApi.unshare(props.kind, target.resourceKey, shareUsername.value)
    closeShare()
    await reload()
  } catch (e) {
    shareError.value = errorText(e)
  } finally {
    shareBusy.value = false
  }
}

/* ---------- 生命周期 ---------- */

onMounted(reload)

// 四条路由共用本组件实例：kind 变化时重置过滤并重新取数（History 前进/后退同样覆盖）。
watch(
  () => props.kind,
  () => {
    filterKeyword.value = ''
    rows.value = []
    closeEditor()
    closeShare()
    void reload()
  },
)
</script>

<style scoped>
/* 版式/令牌一律走全局设计系统（.pg/.panel/.tbl/.err-box/.mask）；此处仅补表单与操作列细节 */
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
.mask .checks { border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 8px 12px; }
.mask .check { display: flex; align-items: center; gap: 6px; }
.mask footer { display: flex; justify-content: flex-end; gap: 8px; }
.form-err { color: var(--danger); margin: 0; font-size: 12.5px; }
.hint { color: var(--text-3); font-size: 12px; margin: 0; }
.drag-handle { cursor: grab; user-select: none; margin: 0; }
.drag-handle:active { cursor: grabbing; }
</style>
