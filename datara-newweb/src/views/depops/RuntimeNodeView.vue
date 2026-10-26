<template>
  <main class="pg" aria-label="运行时节点">
    <header class="pg-head">
      <h1 class="sec-head">运行时节点</h1>
      <p class="pg-desc">运行时节点注册清单（只读，不含凭据）。点击节点浏览其运行时目录；目录浏览经 SFTP 实时读取。</p>
    </header>

    <div class="toolbar">
      <span class="spacer"></span>
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
    <div v-else-if="nodes.length === 0 && !error" class="panel empty" data-empty>
      <div class="e-title">暂无运行时节点</div>
      <div class="e-hint">还没有注册任何运行时节点。</div>
    </div>

    <div v-else-if="nodes.length > 0" class="panel">
      <div class="tbl-toolbar">
        <span class="sec-head">节点清单</span>
        <span class="pill info">{{ nodes.length }}</span>
        <span class="spacer"></span>
      </div>
      <table class="tbl" data-node-list>
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
    </div>

    <section v-if="selectedId !== null" class="panel" data-ls-panel>
      <header class="tbl-toolbar">
        <span class="sec-head">目录浏览</span>
        <span class="code-chip" data-ls-path>{{ lsPathLabel }}</span>
        <span class="spacer"></span>
        <button type="button" class="op-btn" data-parent :disabled="!canGoParent" @click="goParent">上级</button>
        <button type="button" class="op-btn" data-ls-refresh :disabled="lsBusy" @click="loadListing">刷新目录</button>
      </header>

      <div v-if="lsError" class="err-box" role="alert" data-ls-error>
        <span>{{ lsError }}</span>
        <button type="button" class="op-btn retry" :disabled="lsBusy" @click="loadListing">重试</button>
      </div>

      <div v-if="lsBusy" class="skeleton sk-row" style="width:52%"></div>

      <div v-else-if="listing && listing.entries.length === 0 && !lsError" class="empty" data-ls-empty>
        <div class="e-title">该目录为空</div>
        <div class="e-hint">该目录下没有可浏览的条目。</div>
      </div>

      <table v-else-if="listing && listing.entries.length > 0" class="tbl" data-entry-list>
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

    <p class="lock-tip" role="note" data-ls-note>
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
 *
 * 样式范式：复用全局设计系统（`.pg`/`.panel`/`.tbl`/`.tbl-toolbar`/`.code-chip`/`.err-box`
 *   + `var(--*)` 令牌），与旧前端 datara-web 节点页的 `.card.panel` + `table.tbl` 范式对齐。
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
/* 仅保留交互态着色；版式/令牌一律走全局设计系统（.pg/.panel/.tbl/.code-chip） */
.tbl tbody tr { cursor: pointer; }
.tbl tbody tr[data-selected='true'] { background: var(--primary-light); }
</style>
