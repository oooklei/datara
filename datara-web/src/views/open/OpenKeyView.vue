<script setup lang="ts">
/**
 * M16 开放接口 · API-Key管理（/open/key）
 * Key 生命周期：创建（生成随机 Key，仅创建时完整展示一次）→ 绑定 API（多选，一套 Key 通用三类 API）
 * → 启用/停用/删除；调用统计随「调用日志」模拟网关累计。
 * 管理操作 canEdit 门控（analyst/viewer 只读）。
 * 数据：apiKeys / openApis（绑定名录）。
 */
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { dataStore, ST } from '../../services/mock/dataStore'
import { localTime } from '../../services/mock/timeUtil'
import ListFilterPanel from '../../components/ListFilterPanel.vue'
import type { Facet } from '../../components/ListFilterPanel.vue'
import type { OpenApiKey, OpenApi } from '../../services/types'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const keys = ref<OpenApiKey[]>([])
const apis = ref<OpenApi[]>([])
const keyword = ref('')
const filters = ref<Record<string, string>>({ status: '' })

onMounted(async () => {
  await reload()
  apis.value = [...((await dataStore.list<OpenApi>('openApis')) ?? [])]
})

async function reload() {
  keys.value = [...((await dataStore.list<OpenApiKey>('apiKeys')) ?? [])]
}

const facets = computed<Facet[]>(() => [
  { key: 'status', label: '状态', options: [{ v: 'enabled', t: '已启用' }, { v: 'disabled', t: '已停用' }] },
])

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return keys.value.filter((k) => {
    if (filters.value.status && k.status !== filters.value.status) return false
    if (!kw) return true
    return [k.id, k.name, k.key, k.owner].some((s) => s.toLowerCase().includes(kw))
  })
})

function apiName(id: string): string {
  return apis.value.find((a) => a.id === id)?.name ?? id
}

/* ---- 新建 Key（随机 Key 仅展示一次） ---- */
const createVisible = ref(false)
const createForm = ref({ name: '', owner: '', apis: [] as string[] })

function openCreate() {
  createForm.value = { name: '', owner: auth.current.name, apis: [] }
  createVisible.value = true
}

/** 生成随机 Key：dk_live_ + 20 位十六进制（crypto.getRandomValues） */
function genKey(): string {
  const bytes = new Uint8Array(10)
  crypto.getRandomValues(bytes)
  return 'dk_live_' + Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
}

/** ID 用现有最大序号 +1（不使用数组长度） */
function nextId(): string {
  const max = keys.value.reduce((m, k) => Math.max(m, Number(k.id.replace(/\D/g, '')) || 0), 0)
  return 'AK' + String(max + 1).padStart(3, '0')
}

async function saveCreate() {
  const name = createForm.value.name.trim()
  if (!name) {
    ElMessage.warning('请填写 Key 名称')
    return
  }
  const key: OpenApiKey = {
    id: nextId(),
    name,
    key: genKey(),
    apis: [...createForm.value.apis],
    status: 'enabled',
    owner: createForm.value.owner.trim() || auth.current.name,
    createdAt: localTime(),
    lastCalled: '-',
    calls: 0,
  }
  await dataStore.save('apiKeys', key)
  await reload()
  createVisible.value = false
  ElMessage.success(`API-Key 已创建：${key.id}`)
  try {
    await ElMessageBox.alert(
      `<div style="font-size:12.5px">请立即复制保存，该 Key 仅此一次完整展示：</div>
       <div class="mono" style="margin-top:8px;padding:9px 12px;background:#0f172a;color:#d6e2f0;border-radius:var(--radius-sm);word-break:break-all">${key.key}</div>`,
      `新 Key — ${key.name}`,
      { dangerouslyUseHTMLString: true, confirmButtonText: '已复制保存' },
    )
  } catch { /* 关闭即视为已知悉 */ }
}

/* ---- 启用/停用 / 删除 ---- */
async function toggle(k: OpenApiKey) {
  if (!auth.canEdit) return
  const next = k.status === 'enabled' ? 'disabled' : 'enabled'
  await dataStore.save('apiKeys', { ...k, status: next })
  await reload()
  ElMessage.success(`${k.name} 已${next === 'enabled' ? '启用' : '停用'}`)
}

async function remove(k: OpenApiKey) {
  if (!auth.canEdit) return
  try {
    await ElMessageBox.confirm(
      `删除后使用该 Key 的第三方系统将立即失去调用权限（403）。确认删除「${k.name}」？`,
      '删除 API-Key',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  await dataStore.remove('apiKeys', k.id)
  await reload()
  ElMessage.success(`API-Key 已删除：${k.name}`)
}

/* ---- 复制 Key ---- */
async function copyKey(k: OpenApiKey) {
  try {
    await navigator.clipboard.writeText(k.key)
    ElMessage.success('Key 已复制到剪贴板')
  } catch {
    ElMessage.warning('复制失败，请手动选择复制')
  }
}

/* ---- 徽标 ---- */
function stCls(s: string): string {
  return ST[s]?.cls ?? 'st-gray'
}
function stLabel(s: string): string {
  return ST[s]?.label ?? s
}
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ListFilterPanel
      v-model:keyword="keyword"
      v-model:filters="filters"
      :facets="facets"
      placeholder="搜索Key名称/负责人"
      :result-count="filtered.length"
      :total-count="keys.length"
    />
    <div style="flex:1;min-width:0">
      <!-- 页头 -->
      <div class="card page-head">
        <div>
          <div class="ph-title">API-Key管理</div>
          <div class="ph-desc">线下分发第三方调用凭证：一套 Key 通用流数据/数据质量/元数据三类 API，按绑定范围鉴权；Key 创建时生成、仅完整展示一次</div>
        </div>
        <div class="ph-acts">
          <button v-if="auth.canEdit" class="tb-new" @click="openCreate">+ 新建Key</button>
          <button class="op-btn" @click="$router.push('/open/api')">API管理</button>
          <button class="op-btn" @click="$router.push('/open/log')">调用日志</button>
        </div>
      </div>

      <!-- Key 列表 -->
      <div class="card panel">
        <div class="tbl-toolbar">
          <span class="sec-head">API-Key 列表</span>
          <span class="pill info">{{ filtered.length }} / {{ keys.length }}</span>
          <span class="spacer" />
        </div>
        <table class="tbl">
          <thead>
            <tr><th>Key</th><th>Key值</th><th>绑定API</th><th>负责人</th><th>创建时间</th><th>最近调用</th><th>调用次数</th><th>状态</th><th style="width:170px">操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="k in filtered" :key="k.id">
              <td>
                <b>{{ k.name }}</b>
                <div class="mono" style="font-size:11px;color:var(--text-3)">{{ k.id }}</div>
              </td>
              <td>
                <span class="mono" style="font-size:11px">{{ k.key.slice(0, 12) }}…</span>
                <button class="op-btn" style="margin-left:5px" @click="copyKey(k)">复制</button>
              </td>
              <td>
                <div style="display:flex;flex-wrap:wrap;gap:3px;max-width:220px">
                  <span v-for="id in k.apis" :key="id" class="pill info" :title="apiName(id)">{{ id }}</span>
                  <span v-if="k.apis.length === 0" style="color:var(--text-3);font-size:11.5px">未绑定（无法调用）</span>
                </div>
              </td>
              <td style="color:var(--text-2)">{{ k.owner }}</td>
              <td class="mono" style="font-size:11px">{{ k.createdAt }}</td>
              <td class="mono" style="font-size:11px">{{ k.lastCalled }}</td>
              <td>{{ k.calls }}</td>
              <td><span class="st" :class="stCls(k.status)"><span class="dot" />{{ stLabel(k.status) }}</span></td>
              <td>
                <template v-if="auth.canEdit">
                  <button class="op-btn" @click="toggle(k)">{{ k.status === 'enabled' ? '停用' : '启用' }}</button>
                  <button class="op-btn danger" @click="remove(k)">删除</button>
                </template>
                <span v-else style="color:var(--text-3);font-size:11.5px">只读</span>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="filtered.length === 0" class="empty">未找到匹配的 API-Key</div>
      </div>
    </div>

    <!-- 新建 Key 弹窗 -->
    <el-dialog v-model="createVisible" title="新建 API-Key" width="520px">
      <div class="form-row">
        <label class="f-label">Key名称<i>*</i></label>
        <input v-model="createForm.name" class="f-input" placeholder="如：运营分析平台" />
      </div>
      <div class="form-row">
        <label class="f-label">负责人</label>
        <input v-model="createForm.owner" class="f-input" placeholder="默认当前用户" />
      </div>
      <div class="form-row">
        <label class="f-label" style="padding-top:4px">绑定API</label>
        <div class="api-checks">
          <label v-for="a in apis.filter((x) => x.status === 'enabled')" :key="a.id" class="api-check">
            <input v-model="createForm.apis" type="checkbox" :value="a.id" />
            <span class="mono" style="font-size:11px">{{ a.id }}</span>
            <span>{{ a.name }}</span>
            <span class="pill info" style="margin-left:auto">{{ a.category }}</span>
          </label>
          <div v-if="apis.filter((x) => x.status === 'enabled').length === 0" class="empty" style="padding:10px">暂无启用中的 API</div>
        </div>
        <div class="f-tip">不绑定 = 无法调用任何 API；后续可在列表中调整启停（绑定范围如需变更请联系管理员）。</div>
      </div>
      <template #footer>
        <button class="op-btn" @click="createVisible = false">取消</button>
        <button class="tb-new" @click="saveCreate">创建并生成Key</button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page-head{padding:14px 16px;display:flex;align-items:flex-start;gap:10px}
.ph-title{font-weight:700;font-size:15px}
.ph-desc{font-size:12px;color:var(--text-2);margin-top:3px}
.ph-acts{margin-left:auto;display:flex;gap:8px;flex-shrink:0}
.panel{padding:14px 16px;margin-top:12px}
.tbl-toolbar{display:flex;align-items:center;gap:10px;margin-bottom:12px;flex-wrap:wrap}
.tbl-toolbar .spacer{flex:1}
.pill{display:inline-flex;align-items:center;padding:1px 9px;border-radius:var(--radius-lg);font-size:11px;font-weight:500}
.pill.info{background:var(--info-bg);color:var(--info)}
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;font-weight:600;color:var(--text-3);font-size:11.5px;padding:6px 8px;border-bottom:1px solid var(--border);white-space:nowrap}
.tbl td{padding:7px 8px;border-bottom:1px solid var(--border);vertical-align:middle}
.tbl tbody tr:hover{background:var(--bg)}
.empty{padding:24px;text-align:center;color:var(--text-3);font-size:12.5px}
.mono{font-family:ui-monospace,Consolas,monospace}
.op-btn.danger{color:var(--danger);border-color:rgba(229,72,77,.4)}
.op-btn.danger:hover{border-color:var(--danger);color:var(--danger)}
.form-row{display:flex;gap:10px;margin-bottom:14px;align-items:flex-start}
.f-label{width:70px;flex-shrink:0;font-size:12.5px;color:var(--text-2);text-align:right;padding-top:7px}
.f-label i{color:var(--danger);font-style:normal;margin-left:2px}
.f-input{flex:1;border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:7px 10px;font-size:12.5px;outline:none}
.f-input:focus{border-color:var(--primary)}
.f-tip{font-size:11px;color:var(--text-3);margin-top:6px;flex:1}
.api-checks{flex:1;display:flex;flex-direction:column;gap:5px;border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px;max-height:180px;overflow:auto}
.api-check{display:flex;align-items:center;gap:8px;font-size:12px;cursor:pointer;padding:3px 4px;border-radius:var(--radius-sm)}
.api-check:hover{background:var(--bg)}
</style>
