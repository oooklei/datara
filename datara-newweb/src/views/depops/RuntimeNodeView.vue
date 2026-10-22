<template>
  <main class="runtime-page" aria-label="运行时节点">
    <header class="runtime-head">
      <div>
        <h1>运行时节点</h1>
        <p>运行时节点注册清单（只读，不含凭据）。点击节点浏览其运行时目录；目录浏览经 SFTP 实时读取。</p>
      </div>
      <button type="button" data-refresh @click="reload">刷新</button>
    </header>

    <!-- 错误横幅独立于内容态：加载失败时无数据可渲染，刷新失败时表格须保留 -->
    <p v-if="error" role="alert" data-error>{{ error }}</p>
    <p v-if="listBusy" role="status">正在加载节点清单…</p>
    <p v-else-if="nodes.length === 0 && !error" data-empty>暂无运行时节点</p>

    <table v-if="nodes.length > 0" data-node-list>
      <thead>
        <tr>
          <th>名称</th><th>类型</th><th>主机</th><th>端口</th><th>用户</th>
          <th>运行时目录</th><th>状态</th><th>最近心跳</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in nodes"
          :key="row.id"
          :data-node="String(row.id)"
          :data-selected="String(selectedId === row.id)"
          @click="select(row.id)"
        >
          <td data-node-name>{{ row.name }}</td>
          <td data-node-kind>{{ row.kind || '—' }}</td>
          <td data-node-host>{{ row.host || '—' }}</td>
          <td data-node-port>{{ row.port ?? '—' }}</td>
          <td data-node-user>{{ row.user || '—' }}</td>
          <td data-node-dir>{{ row.runtimeDir || '—' }}</td>
          <td :data-node-status="row.status">{{ row.status || '—' }}</td>
          <td data-node-heartbeat>{{ row.lastHeartbeat || '—' }}</td>
        </tr>
      </tbody>
    </table>

    <section v-if="selectedId !== null" class="runtime-ls" data-ls-panel>
      <header class="runtime-ls-head">
        <span>目录浏览：<strong data-ls-path>{{ lsPathLabel }}</strong></span>
        <button type="button" data-parent :disabled="!canGoParent" @click="goParent">上级</button>
        <button type="button" data-ls-refresh @click="loadListing">刷新目录</button>
      </header>
      <p v-if="lsError" role="alert" data-ls-error>{{ lsError }}</p>
      <p v-if="lsBusy" role="status">正在读取目录…</p>
      <p v-else-if="listing && listing.entries.length === 0" data-ls-empty>该目录为空</p>
      <table v-if="listing && listing.entries.length > 0" data-entry-list>
        <thead>
          <tr><th>名称</th><th>类型</th><th>大小</th><th>修改时间</th></tr>
        </thead>
        <tbody>
          <tr
            v-for="entry in listing.entries"
            :key="entry.name"
            :data-entry="entry.name"
            :data-entry-dir="String(entry.dir)"
            @click="openEntry(entry)"
          >
            <td data-entry-name>{{ entry.name }}</td>
            <td data-entry-type>{{ entry.dir ? '目录' : '文件' }}</td>
            <td data-entry-size>{{ formatSize(entry) }}</td>
            <td data-entry-mtime>{{ formatMtime(entry.mtime) }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <p class="runtime-note" role="note" data-ls-note>
      口径：清单为只读注册面，不含凭据；目录浏览经 SFTP 实时读取，单次上限 500 条；空目录如实显示「该目录为空」；
      上级仅在根目录内不可用。手动刷新，不做轮询。
    </p>
  </main>
</template>

<script setup lang="ts">
/**
 * 17.4 运行时节点页组件段（IMPL-v4-17，不含路由/菜单壳）。
 *
 * 契约面：`createRuntimeNodeContract()`（B6 runtimeNodeApi，REGISTRY #19 GREEN）。
 * 数据红线：
 *  - 仅经契约工厂取数，禁直连 fetch/axios；
 *  - 清单为空如实显示，不含凭据字段；
 *  - 目录浏览失败不虚构内容，空目录如实呈现；
 *  - 手动刷新，不做高频轮询。
 */
import { computed, onMounted, ref } from 'vue'
import {
  createRuntimeNodeContract,
  type RuntimeNode,
  type RuntimeNodeDirEntry,
  type RuntimeNodeDirListing,
} from '../../services/rebuild/runtimeNodeApi'

const runtime = createRuntimeNodeContract()

const nodes = ref<RuntimeNode[]>([])
const selectedId = ref<number | null>(null)
const requestedPath = ref('')
const listing = ref<RuntimeNodeDirListing | null>(null)
const listBusy = ref(false)
const lsBusy = ref(false)
const error = ref('')
const lsError = ref('')

const canGoParent = computed(() => {
  const path = listing.value?.path
  return !!path && path !== '/'
})

const lsPathLabel = computed(() =>
  listing.value?.path ?? (requestedPath.value === '' ? '（家目录）' : requestedPath.value || '—'),
)

const message = (e: unknown): string => (e instanceof Error ? e.message : String(e))

/** 非 0 包络码须随错误信息透出（runtimeNodeApi 经 preserveEnvelopeCode 保码）。 */
const errorText = (e: unknown): string => {
  const code = (e as { code?: number | string } | null)?.code
  return code !== undefined && code !== 0 ? `加载失败（code ${code}）：${message(e)}` : message(e)
}

const formatSize = (entry: RuntimeNodeDirEntry): string => (entry.dir ? '—' : String(entry.size))

const formatMtime = (ts: number): string => {
  if (!ts) return '—'
  const d = new Date(ts * 1000)
  const pad = (n: number): string => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

const joinPath = (base: string, name: string): string => {
  const root = base.replace(/\/+$/, '')
  return `${root}/${name}` || '/'
}

const parentPath = (path: string): string => {
  if (!path || path === '/') return '/'
  const trimmed = path.replace(/\/+$/, '')
  const idx = trimmed.lastIndexOf('/')
  return idx <= 0 ? '/' : trimmed.slice(0, idx)
}

async function loadListing(): Promise<void> {
  if (selectedId.value === null) return
  lsBusy.value = true
  lsError.value = ''
  try {
    listing.value = await runtime.lsRuntimeNodeDir(selectedId.value, requestedPath.value)
  } catch (e) {
    lsError.value = errorText(e)
  } finally {
    lsBusy.value = false
  }
}

function select(id: number): void {
  if (selectedId.value === id) return
  selectedId.value = id
  requestedPath.value = ''
  listing.value = null
  void loadListing()
}

function openEntry(entry: RuntimeNodeDirEntry): void {
  if (!entry.dir) return
  requestedPath.value = joinPath(listing.value?.path ?? '', entry.name)
  void loadListing()
}

function goParent(): void {
  requestedPath.value = parentPath(listing.value?.path ?? '')
  void loadListing()
}

async function reload(): Promise<void> {
  listBusy.value = true
  error.value = ''
  try {
    nodes.value = await runtime.listRuntimeNodes()
    if (selectedId.value !== null && !nodes.value.some((n) => n.id === selectedId.value)) {
      selectedId.value = null
      listing.value = null
    } else if (selectedId.value !== null) {
      await loadListing()
    }
  } catch (e) {
    error.value = errorText(e)
  } finally {
    listBusy.value = false
  }
}

onMounted(reload)
</script>

<style scoped>
.runtime-page{max-width:1180px;margin:auto;padding:32px 24px;color:#172033}
.runtime-head{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.runtime-head h1{margin:0}
.runtime-head p{margin:4px 0 0;color:#64748b;flex-basis:100%}
button{cursor:pointer;padding:7px 12px}
table{width:100%;border-collapse:collapse;background:#fff;margin-top:8px}
th,td{text-align:left;padding:11px;border-bottom:1px solid #e2e8f0;vertical-align:top}
tbody tr{cursor:pointer}
tbody tr[data-selected='true']{background:#eff6ff}
.runtime-ls{margin-top:20px}
.runtime-ls-head{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.runtime-ls-head strong{font-weight:600}
button:disabled{cursor:not-allowed;opacity:.5}
.runtime-note{margin-top:16px;color:#475569;font-size:13px}
</style>
