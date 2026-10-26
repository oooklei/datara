<template>
  <main class="pg" aria-label="API-Key 管理">
    <header class="pg-head">
      <h1 class="sec-head">API-Key 管理</h1>
      <p class="pg-desc">
        hash-only 存储：服务端只保存摘要，原始 Key 仅在签发响应一次性回显（KeyIssuance.plainKey），关闭弹窗后不可再取。
      </p>
    </header>

    <div class="toolbar">
      <span class="pill" :class="isNotWired ? 'off' : 'info'" data-wired-state>
        {{ isNotWired ? '后端未接线' : '已接线' }}
      </span>
      <span class="spacer"></span>
      <span class="hint" data-apikey-count>Key {{ items.length }} 条</span>
      <button type="button" class="op-btn" data-refresh :disabled="loading" @click="load">刷新</button>
      <!-- 互跳入口：旧版 OpenKeyView 页头按钮，目标路由 /open/api 已注册可达。 -->
      <button type="button" class="op-btn" data-goto-api @click="gotoApi">API管理</button>
      <button type="button" class="tb-new" data-create @click="openCreate">+ 新建Key</button>
    </div>

    <div v-if="error" class="err-box" role="alert" data-error>
      <span>{{ error }}</span>
      <button type="button" class="op-btn retry" :disabled="loading" @click="load">重试</button>
    </div>

    <div v-if="loading" class="panel" role="status" aria-live="polite">
      <div class="skeleton sk-row" style="width:30%"></div>
      <div class="skeleton sk-row" style="width:68%"></div>
      <div class="skeleton sk-row" style="width:46%"></div>
    </div>

    <div v-else-if="isNotWired" class="panel empty" data-not-wired>
      <div class="e-title">后端未接线</div>
      <div class="e-hint">{{ notWiredMsg }}</div>
    </div>

    <div v-else-if="items.length === 0" class="panel empty" data-empty>
      <div class="e-title">暂无 API-Key</div>
      <div class="e-hint">后端 15.2-A~D 接线后，可在此签发受控调用凭证。</div>
    </div>

    <div v-else class="panel">
      <div class="tbl-toolbar">
        <span class="sec-head">API-Key 列表</span>
        <span class="pill info">{{ items.length }}</span>
        <span class="spacer"></span>
      </div>
      <table class="tbl" data-apikey-list>
        <thead>
          <tr>
            <th>名称</th><th>状态</th><th>权限范围</th><th>项目范围</th>
            <th>过期</th><th>最近使用</th><th>创建时间</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="k in items" :key="k.id" :data-key-id="k.id">
            <td>
              <strong>{{ k.name }}</strong>
              <span class="mono" data-key-prefix>{{ k.keyPrefix }}</span>
            </td>
            <td>
              <span class="st" :class="statusClass(k.status)">
                <span class="dot"></span>{{ k.status }}
              </span>
            </td>
            <td class="mono">{{ k.scopes.permissions.join(', ') || '—' }}</td>
            <td>
              <span v-if="k.scopes.projectIds.length === 0" class="hint">全局</span>
              <span v-else class="mono">{{ k.scopes.projectIds.join(', ') }}</span>
            </td>
            <td class="mono">{{ k.expiresAt || '—' }}</td>
            <td class="mono">{{ k.lastUsedAt || '—' }}</td>
            <td class="mono">{{ k.createdAt }}</td>
            <td>
              <button
                v-if="k.status === 'active'"
                type="button"
                class="op-btn danger"
                :data-revoke="k.id"
                :disabled="revoking === k.id"
                @click="revoke(k)"
              >吊销</button>
              <span v-else class="hint">已吊销</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 新建 Key 弹窗（旧版 OpenKeyView 同名入口，字段按 15-P0 冻结契约 ApiKeyInput 组织） -->
    <div v-if="showCreate" class="mask" @click.self="closeCreate">
      <form class="dlg" role="dialog" aria-modal="true" aria-label="新建 API-Key" @submit.prevent="saveCreate">
        <div class="dlg-hd">
          新建 API-Key
          <button type="button" class="x" aria-label="关闭" @click="closeCreate">×</button>
        </div>

        <div class="dlg-bd">
          <!-- 安全红线 C4：原始 key 仅本响应出现一次，关闭弹窗即销毁，重查不可再得。 -->
          <div v-if="issued" class="issued" data-issued>
            <div class="issued-tip">原始 Key 仅此一次完整展示，请立即复制保存；刷新或重查均不可再得。</div>
            <div class="issued-k mono" data-plain-key>{{ issued.plainKey }}</div>
            <button type="button" class="op-btn" data-copy-key @click="copyIssued">
              {{ copied ? '已复制' : '复制 Key' }}
            </button>
          </div>

          <div class="form-grid">
            <label class="f-item full">
              <span>名称</span>
              <input v-model.trim="form.name" required :disabled="saving" placeholder="如：运营分析平台">
            </label>

            <label class="f-item">
              <span>过期时间</span>
              <input v-model="form.expiresAt" type="date" :disabled="saving">
            </label>
            <label class="f-item">
              <span>状态</span>
              <input value="active（签发即启用）" disabled>
            </label>

            <label class="f-item full">
              <span>权限范围</span>
              <div class="checks">
                <label v-for="p in permissionOptions" :key="p" class="check">
                  <input v-model="form.permissions" type="checkbox" :value="p" :disabled="saving">
                  <span class="mono">{{ p }}</span>
                </label>
                <span class="hint">留空 = 无任何调用权限。</span>
              </div>
            </label>

            <label class="f-item full">
              <span>项目范围</span>
              <div class="checks">
                <label v-for="p in projects" :key="p.id" class="check">
                  <input v-model="form.projectIds" type="checkbox" :value="p.id" :disabled="saving">
                  <span>{{ p.name }}</span>
                </label>
                <span v-if="projectsLoaded && projects.length === 0" class="hint">
                  项目列表不可用，留空即为全局 Key（仅 admin 可签发）。
                </span>
              </div>
            </label>
          </div>

          <div v-if="createError" class="err-box" role="alert" data-create-error>
            <span>{{ createError }}</span>
          </div>
        </div>

        <div class="dlg-ft">
          <button type="button" class="op-btn" :disabled="saving" @click="closeCreate">取消</button>
          <button type="submit" class="tb-new" :disabled="saving || form.name.length === 0">创建并生成Key</button>
        </div>
      </form>
    </div>
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  createOpenapiAdminContract,
  OPENAPI_ADMIN_NOT_WIRED,
  OPENAPI_ADMIN_PERMISSION_MATRIX,
  type ApiKeyInput,
  type ApiKeyRecord,
  type ApiKeyStatus,
  type KeyIssuance,
} from '../../services/rebuild/openapiAdminApi'
import { listProjects, type ProjectSummary } from '../../services/rebuild/projectApi'

const router = useRouter()
const contract = createOpenapiAdminContract()

const items = ref<ApiKeyRecord[]>([])
const loading = ref(false)
const error = ref('')
const isNotWired = ref(false)
const notWiredMsg = OPENAPI_ADMIN_NOT_WIRED

/* 权限词形取自本域冻结权限矩阵（单一事实源，不另造枚举）。 */
const permissionOptions = Array.from(new Set(Object.values(OPENAPI_ADMIN_PERMISSION_MATRIX)))

/* 项目范围候选来自真实端点；不可用时显式提示，不静默吞错。 */
const projects = ref<ProjectSummary[]>([])
const projectsLoaded = ref(false)

const message = (e: unknown): string => (e instanceof Error ? e.message : String(e))
const isNotWiredError = (e: unknown): boolean => message(e).includes('OPENAPI_ADMIN_NOT_WIRED')

/** 互跳入口：两页路由均已注册，跳转目标真实可达。 */
function gotoApi(): void {
  router.push('/open/api')
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  isNotWired.value = false
  try {
    items.value = await contract.listApiKeys()
  } catch (e) {
    if (isNotWiredError(e)) {
      isNotWired.value = true
    } else {
      error.value = message(e)
    }
  } finally {
    loading.value = false
  }
}

async function loadProjects(): Promise<void> {
  try {
    const page = await listProjects()
    projects.value = page.list
  } catch {
    projects.value = []
  } finally {
    projectsLoaded.value = true
  }
}

/* ---------- 吊销 ---------- */

const revoking = ref(0)

async function revoke(k: ApiKeyRecord): Promise<void> {
  revoking.value = k.id
  error.value = ''
  isNotWired.value = false
  try {
    await contract.revokeApiKey(k.id)
    await load()
  } catch (e) {
    if (isNotWiredError(e)) {
      isNotWired.value = true
    } else {
      error.value = message(e)
    }
  } finally {
    revoking.value = 0
  }
}

/* ---------- 新建 Key ---------- */

interface KeyForm {
  name: string
  permissions: string[]
  projectIds: number[]
  expiresAt: string
}

const blankForm = (): KeyForm => ({ name: '', permissions: [], projectIds: [], expiresAt: '' })

const showCreate = ref(false)
const saving = ref(false)
const createError = ref('')
const form = ref<KeyForm>(blankForm())
const issued = ref<KeyIssuance | null>(null)
const copied = ref(false)

function openCreate(): void {
  form.value = blankForm()
  createError.value = ''
  issued.value = null
  copied.value = false
  showCreate.value = true
  if (!projectsLoaded.value) void loadProjects()
}

/** 关闭即销毁一次性明文（C4：弹窗关闭后不可再取）。 */
function closeCreate(): void {
  showCreate.value = false
  issued.value = null
  copied.value = false
}

async function saveCreate(): Promise<void> {
  if (form.value.name.length === 0) return
  saving.value = true
  createError.value = ''
  try {
    const input: ApiKeyInput = {
      name: form.value.name,
      scopes: { permissions: [...form.value.permissions], projectIds: [...form.value.projectIds] },
      expiresAt: form.value.expiresAt || null,
    }
    issued.value = await contract.issueApiKey(input)
    await load()
  } catch (e) {
    createError.value = isNotWiredError(e) ? notWiredMsg : message(e)
  } finally {
    saving.value = false
  }
}

async function copyIssued(): Promise<void> {
  if (!issued.value) return
  try {
    await navigator.clipboard.writeText(issued.value.plainKey)
    copied.value = true
  } catch {
    copied.value = false
  }
}

const statusClass = (s: ApiKeyStatus): string => (s === 'active' ? 'st-green' : 'st-red')

onMounted(load)
</script>

<style scoped>
/* 仅保留全局类无法表达的布局/语义态；颜色一律走令牌 */
.pg > .toolbar{flex-wrap:wrap}
td > span{display:block}
td > span.mono{font-size:12px;color:var(--text-3);margin-top:2px}
.checks{display:flex;flex-wrap:wrap;gap:4px 16px;align-items:center}
.check{display:inline-flex;align-items:center;gap:6px;font-size:12.5px;color:var(--text-2);cursor:pointer}
.issued{border:1px solid var(--border-strong);border-radius:var(--radius-sm);background:var(--bg);padding:10px 12px;margin-bottom:12px}
.issued-tip{font-size:12px;color:var(--warn);margin-bottom:6px}
.issued-k{font-size:12.5px;word-break:break-all;line-height:1.6;margin-bottom:8px}
</style>
