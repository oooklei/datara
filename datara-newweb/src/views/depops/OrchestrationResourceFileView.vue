<template>
  <main class="pg" aria-label="资源文件">
    <header class="pg-head">
      <h1 class="sec-head">资源文件</h1>
      <p class="pg-desc">
        海豚资源文件（全局文件树）：SHELL / PYTHON / SQL 等节点引用的脚本与资源包。节点表单按
        fullName 引用；上传 / 建目录 / 重命名 / 删除经编排网关代理海豚，按 owner 隔离。
      </p>
    </header>

    <div class="toolbar">
      <DepOpsSubNav />
      <span class="spacer"></span>
      <button v-if="canWrite" type="button" class="op-btn primary" data-create-directory @click="openDirectory(ROOT_DIR)">
        新建目录
      </button>
      <button v-if="canWrite" type="button" class="op-btn" data-upload @click="pickFiles(ROOT_DIR)">上传文件</button>
      <button type="button" class="op-btn" data-refresh :disabled="listBusy" @click="reload">刷新</button>
      <input ref="fileInput" type="file" multiple hidden data-upload-input @change="onPickedFiles" />
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
    <div v-else-if="nodes.length === 0 && !error" class="panel empty" data-empty>
      <div class="e-title">暂无资源文件</div>
      <div class="e-hint">还没有上传任何资源文件；可直接把文件拖到本页上传到根目录。</div>
    </div>

    <div
      v-else-if="nodes.length > 0"
      class="panel tree-panel"
      :class="{ dragging }"
      data-resource-file-tree
      @dragover="onDragOver"
      @dragleave="onDragLeave"
      @drop="onDrop($event, ROOT_DIR)"
    >
      <div class="tbl-toolbar">
        <span class="sec-head">文件树</span>
        <span class="pill info" data-file-count>{{ fileCount }}</span>
        <input v-model.trim="filterKeyword" data-filter-keyword placeholder="搜索文件或目录名" />
        <span class="spacer"></span>
      </div>

      <ul class="tree-list">
        <li
          v-for="item in flatNodes"
          :key="item.node.fullName"
          class="tree-row"
          :class="{ dir: item.node.dirctory }"
          :data-full-name="item.node.fullName"
          :data-dir="String(item.node.dirctory)"
          :style="{ paddingLeft: `${8 + item.depth * 18}px` }"
          @dragover.stop="onDragOver"
          @drop="onRowDrop($event, item.node)"
        >
          <button
            v-if="item.node.dirctory"
            type="button"
            class="toggle"
            :data-toggle="item.node.fullName"
            :aria-label="isExpanded(item.node.fullName) ? '折叠' : '展开'"
            @click="toggle(item.node.fullName)"
          >
            {{ isExpanded(item.node.fullName) ? '▾' : '▸' }}
          </button>
          <span v-else class="toggle placeholder"></span>
          <span class="name" :data-node-name="item.node.name">{{ item.node.name }}</span>
          <span class="kind">{{ item.node.dirctory ? '目录' : '文件' }}</span>
          <span class="spacer"></span>

          <template v-if="item.node.dirctory">
            <button v-if="canWrite" type="button" data-upload-to :disabled="!canWrite" @click="pickFiles(item.node.fullName)">
              上传到此
            </button>
            <button
              v-if="canWrite"
              type="button"
              data-create-directory-in
              :disabled="!canWrite"
              @click="openDirectory(item.node.fullName)"
            >
              新建子目录
            </button>
          </template>
          <button v-else type="button" data-download @click="download(item.node)">下载</button>

          <button v-if="canWrite" type="button" data-rename :disabled="!canWrite" @click="openRename(item.node)">重命名</button>
          <button v-if="canWrite" type="button" data-share :disabled="!canWrite" @click="openShare(item.node)">共享</button>
          <button v-if="canWrite" type="button" data-delete :disabled="!canWrite" @click="remove(item.node)">删除</button>
        </li>
        <li v-if="flatNodes.length === 0" class="tree-row empty-row">无匹配记录</li>
      </ul>
    </div>

    <p class="lock-tip" role="note" data-scope-note>
      口径：资源文件为全局文件树，按 owner 隔离（未登记归属的既有资源对所有登录用户可见）；写门禁
      EDIT_DEFINITION。上传/建目录的 currentDir 为根 <code>/</code> 或目标目录 fullName；手动刷新，不做轮询。
    </p>

    <!-- 新建目录 / 重命名 / 共享 三态共用一个弹窗（单输入框） -->
    <div v-if="dialogMode !== ''" class="mask" @click.self="closeDialog">
      <form
        ref="dialogRef"
        role="dialog"
        aria-modal="true"
        :aria-label="dialogTitle"
        :style="dialogStyle"
        @submit.prevent="submitDialog"
      >
        <h2 class="drag-handle" @pointerdown="onDialogPointerdown">{{ dialogTitle }}</h2>
        <label>{{ dialogFieldLabel }}<input v-model.trim="dialogValue" required data-dialog-input /></label>
        <p v-if="dialogError" class="form-err" role="alert" data-dialog-error>{{ dialogError }}</p>
        <footer>
          <button type="button" class="mini-btn" @click="closeDialog">取消</button>
          <button type="submit" class="mini-btn primary" data-dialog-save :disabled="dialogBusy">{{ dialogSubmitLabel }}</button>
        </footer>
      </form>
    </div>
  </main>
</template>

<script setup lang="ts">
/**
 * §10.10 R9 部署运维「资源文件」页（全局文件树）。
 *
 * 真源：docs/designs/2026-10-29-dbx-unified-target-design.md §10.10 R9。
 * 契约面：`orchestrationApi`（/rebuild/orchestration/resources，经编排网关代理海豚，
 * 前端不直连海豚 API）。树形字段沿用海豚线形态（`dirctory` 为 DS 源码拼写）。
 *
 * currentDir 语义（对齐海豚 CreateDirectoryRequestTransformer）：根目录传 `/`，
 * 子目录传该目录的 `fullName`；两者均不得为空，否则海豚抛 ILLEGAL_RESOURCE_PATH。
 * 数据红线：手动刷新不轮询；空态与错误态互斥；不可写节点隐藏全部写操作。
 */
import { computed, onMounted, ref } from 'vue'
import DepOpsSubNav from '../../components/DepOpsSubNav.vue'
import { useDraggable } from '../../composables/useDraggable'
import { authAccount } from '../../services/rebuild/authApi'
import { roleHasPermission, type Permission } from '../../services/rebuild/rolePermissions'
import {
  ORCHESTRATION_RESOURCE_PERMISSION_MATRIX,
  orchestrationApi,
  type ResourceFileNode,
} from '../../services/rebuild/orchestrationApi'

/** 海豚根目录标识（非空；空串会被海豚判为非法路径）。 */
const ROOT_DIR = '/'

const nodes = ref<ResourceFileNode[]>([])
const filterKeyword = ref('')
const listBusy = ref(false)
const error = ref('')
const dragging = ref(false)

/** 写入门：矩阵声明所需权限点，当前角色持有才显示写操作（后端仍是最终裁决）。 */
const canWrite = computed(() => {
  const role = authAccount.value?.role
  if (!role) return false
  const wire = ORCHESTRATION_RESOURCE_PERMISSION_MATRIX.resource_file.create
  return roleHasPermission(role, wireToPermission(wire))
})

function wireToPermission(wire: string): Permission {
  if (wire === 'MANAGE_USER') return 'manage_user'
  if (wire === 'EDIT_DEFINITION') return 'edit_definition'
  return 'view_all'
}

const message = (e: unknown): string => (e instanceof Error ? e.message : String(e))

/** 非 0 包络码须随错误信息透出（编排网关错误码为字符串，经 preserveEnvelopeCode 保码）。 */
const errorText = (e: unknown): string => {
  const code = (e as { code?: number | string } | null)?.code
  return code !== undefined && code !== 0 && code !== '0' ? `操作失败（code ${code}）：${message(e)}` : message(e)
}

/* ---------- 树展开 / 过滤 ---------- */

const collapsed = ref<string[]>([])

/** 过滤态强制全展开，避免命中项被折叠隐藏。 */
function isExpanded(key: string): boolean {
  return filterKeyword.value !== '' || !collapsed.value.includes(key)
}

function toggle(key: string): void {
  collapsed.value = collapsed.value.includes(key)
    ? collapsed.value.filter((item) => item !== key)
    : [...collapsed.value, key]
}

function prune(list: ResourceFileNode[], keyword: string): ResourceFileNode[] {
  const out: ResourceFileNode[] = []
  for (const node of list) {
    const children = prune(node.children ?? [], keyword)
    if (node.name.toLowerCase().includes(keyword) || children.length > 0) {
      out.push({ ...node, children })
    }
  }
  return out
}

const visibleTree = computed<ResourceFileNode[]>(() => {
  const keyword = filterKeyword.value.toLowerCase()
  return keyword === '' ? nodes.value : prune(nodes.value, keyword)
})

interface FlatNode {
  node: ResourceFileNode
  depth: number
}

const flatNodes = computed<FlatNode[]>(() => {
  const out: FlatNode[] = []
  const walk = (list: ResourceFileNode[], depth: number): void => {
    for (const node of list) {
      out.push({ node, depth })
      const children = node.children ?? []
      if (node.dirctory && children.length > 0 && isExpanded(node.fullName)) walk(children, depth + 1)
    }
  }
  walk(visibleTree.value, 0)
  return out
})

const fileCount = computed(() => {
  const count = (list: ResourceFileNode[]): number =>
    list.reduce((sum, node) => sum + (node.dirctory ? count(node.children ?? []) : 1), 0)
  return count(nodes.value)
})

/* ---------- 取数 ---------- */

async function reload(): Promise<void> {
  listBusy.value = true
  error.value = ''
  try {
    nodes.value = await orchestrationApi.listResourceFiles()
  } catch (e) {
    error.value = errorText(e)
  } finally {
    listBusy.value = false
  }
}

/* ---------- 上传（工具栏 / 行内 / 拖拽） ---------- */

const fileInput = ref<HTMLInputElement | null>(null)
/** 待上传目标目录：根为 `/`，行内上传为目标目录 fullName。 */
const pendingDir = ref(ROOT_DIR)

function pickFiles(currentDir: string): void {
  pendingDir.value = currentDir
  fileInput.value?.click()
}

async function onPickedFiles(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const files = input.files
  if (files && files.length > 0) await uploadFiles(files, pendingDir.value)
  input.value = ''
}

async function uploadFiles(files: FileList | File[], currentDir: string): Promise<void> {
  listBusy.value = true
  error.value = ''
  try {
    for (const file of Array.from(files)) {
      const form = new FormData()
      form.append('name', file.name)
      form.append('current_dir', currentDir)
      form.append('file', file, file.name)
      await orchestrationApi.createResourceFile(form)
    }
    await reload()
  } catch (e) {
    error.value = errorText(e)
  } finally {
    listBusy.value = false
  }
}

function onDragOver(): void {
  dragging.value = true
}

function onDragLeave(): void {
  dragging.value = false
}

async function onDrop(event: DragEvent, currentDir: string): Promise<void> {
  event.preventDefault()
  dragging.value = false
  const files = event.dataTransfer?.files
  if (files && files.length > 0) await uploadFiles(files, currentDir)
}

/** 行内拖放：仅目录可接收，落到该目录 fullName；文件行不拦截。 */
function onRowDrop(event: DragEvent, node: ResourceFileNode): void {
  event.preventDefault()
  event.stopPropagation()
  if (!node.dirctory) return
  dragging.value = false
  const files = event.dataTransfer?.files
  if (files && files.length > 0) void uploadFiles(files, node.fullName)
}

/* ---------- 下载 / 删除 ---------- */

async function download(node: ResourceFileNode): Promise<void> {
  error.value = ''
  try {
    const blob = await orchestrationApi.downloadResourceFile(node.fullName)
    if (typeof URL.createObjectURL !== 'function') return
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = node.name
    anchor.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    error.value = errorText(e)
  }
}

async function remove(node: ResourceFileNode): Promise<void> {
  if (!globalThis.confirm(`删除「${node.fullName}」？目录将递归删除。`)) return
  error.value = ''
  try {
    await orchestrationApi.deleteResourceFile(node.fullName)
    await reload()
  } catch (e) {
    error.value = errorText(e)
  }
}

/* ---------- 新建目录 / 重命名 / 共享 弹窗 ---------- */

type DialogMode = '' | 'directory' | 'rename' | 'share'

const dialogMode = ref<DialogMode>('')
const dialogValue = ref('')
const dialogError = ref('')
const dialogBusy = ref(false)
const dialogTarget = ref<ResourceFileNode | null>(null)
/** 新建目录的父目录 currentDir（根为 `/`）。 */
const dialogDir = ref(ROOT_DIR)

const dialogRef = ref<HTMLElement | null>(null)
const { dragStyle: dialogStyle, onHandlePointerdown: onDialogPointerdown } = useDraggable(dialogRef, dialogRef, {
  storageKey: 'orchestration.resource.file.dialog',
})

const dialogTitle = computed(() => {
  switch (dialogMode.value) {
    case 'directory':
      return '新建目录'
    case 'rename':
      return `重命名「${dialogTarget.value?.name ?? ''}」`
    case 'share':
      return `共享「${dialogTarget.value?.fullName ?? ''}」`
    default:
      return ''
  }
})

const dialogFieldLabel = computed(() => (dialogMode.value === 'share' ? '用户名' : '名称'))
const dialogSubmitLabel = computed(() => (dialogMode.value === 'share' ? '共享' : '保存'))

function openDirectory(parent: string): void {
  dialogMode.value = 'directory'
  dialogDir.value = parent
  dialogTarget.value = null
  dialogValue.value = ''
  dialogError.value = ''
}

function openRename(node: ResourceFileNode): void {
  dialogMode.value = 'rename'
  dialogTarget.value = node
  dialogValue.value = node.name
  dialogError.value = ''
}

function openShare(node: ResourceFileNode): void {
  dialogMode.value = 'share'
  dialogTarget.value = node
  dialogValue.value = ''
  dialogError.value = ''
}

function closeDialog(): void {
  dialogMode.value = ''
  dialogError.value = ''
  dialogBusy.value = false
}

async function submitDialog(): Promise<void> {
  const mode = dialogMode.value
  const target = dialogTarget.value
  if (mode === 'rename' || mode === 'share') {
    if (!target) return
  }
  dialogError.value = ''
  dialogBusy.value = true
  try {
    if (mode === 'directory') {
      const form = new FormData()
      form.append('name', dialogValue.value)
      form.append('current_dir', dialogDir.value)
      await orchestrationApi.createResourceFile(form)
    } else if (mode === 'rename') {
      await orchestrationApi.renameResourceFile({ fullName: target!.fullName, name: dialogValue.value })
    } else if (mode === 'share') {
      await orchestrationApi.share('resource_file', target!.fullName, dialogValue.value)
    }
  } catch (e) {
    dialogError.value = errorText(e)
    dialogBusy.value = false
    return
  }
  dialogBusy.value = false
  closeDialog()
  await reload()
}

onMounted(reload)
</script>

<style scoped>
/* 版式/令牌一律走全局设计系统（.pg/.panel/.tbl/.err-box/.mask）；此处仅补树与弹窗细节 */
.tree-panel { padding-bottom: 10px; }
.tree-panel.dragging { outline: 2px dashed var(--primary); outline-offset: -4px; }
.tree-list { list-style: none; margin: 0; padding: 0; }
.tree-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  padding-right: 10px;
  border-top: 1px solid var(--border);
  font-size: 13px;
}
.tree-row:first-child { border-top: none; }
.tree-row.dir .name { font-weight: 600; }
.tree-row.empty-row { color: var(--text-3); justify-content: center; }
.toggle {
  width: 18px;
  min-width: 18px;
  height: 18px;
  line-height: 16px;
  padding: 0;
  border: none;
  background: transparent;
  color: var(--text-2);
  cursor: pointer;
}
.toggle.placeholder { cursor: default; }
.name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kind { color: var(--text-3); font-size: 11.5px; }
.tree-row button {
  font-size: 12px;
  padding: 3px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--card);
  color: var(--text-2);
  cursor: pointer;
}
.tree-row button:disabled { opacity: .5; cursor: not-allowed; }
.lock-tip code { font-size: 11.5px; }
.mask form {
  width: min(460px, calc(100vw - 40px));
  display: grid;
  gap: 12px;
  background: var(--card);
  padding: 24px;
  border-radius: var(--radius-lg);
}
.mask label { display: grid; gap: 5px; }
.mask input { padding: 8px; font: inherit; }
.mask footer { display: flex; justify-content: flex-end; gap: 8px; }
.form-err { color: var(--danger); margin: 0; font-size: 12.5px; }
.drag-handle { cursor: grab; user-select: none; margin: 0; }
.drag-handle:active { cursor: grabbing; }
</style>
