<script setup lang="ts">
/**
 * M16 开放接口 · 调用日志（/open/log）
 * 网关调用流水 + 「模拟网关调用」：选择 Key 与 API 模拟一次真实调用，
 * 鉴权链路：Key 停用 → 403 denied；API 未绑定 → 403 denied；其余 → 200 success。
 * 调用成功同步累计 api.calls 与 key.calls/lastCalled。
 * 数据：openLogs（读写）/ openApis / apiKeys（读写统计）。
 */
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { dataStore } from '../../services/mock/dataStore'
import ListFilterPanel from '../../components/ListFilterPanel.vue'
import type { Facet } from '../../components/ListFilterPanel.vue'
import type { OpenLog, OpenApiKey, OpenApi } from '../../services/types'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const logs = ref<OpenLog[]>([])
const apis = ref<OpenApi[]>([])
const keys = ref<OpenApiKey[]>([])
const keyword = ref('')
const filters = ref<Record<string, string>>({ result: '', api: '' })

onMounted(async () => {
  await reload()
  const [a, k] = await Promise.all([
    dataStore.list<OpenApi>('openApis'),
    dataStore.list<OpenApiKey>('apiKeys'),
  ])
  apis.value = [...(a ?? [])]
  keys.value = [...(k ?? [])]
})

async function reload() {
  logs.value = [...((await dataStore.list<OpenLog>('openLogs')) ?? [])]
}

const facets = computed<Facet[]>(() => [
  { key: 'result', label: '调用结果', options: [{ v: 'success', t: '成功' }, { v: 'denied', t: '鉴权拒绝' }, { v: 'error', t: '服务错误' }] },
  { key: 'api', label: 'API', options: [...new Set(logs.value.map((l) => l.apiPath))].map((p) => ({ v: p, t: p })) },
])

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return logs.value.filter((l) => {
    if (filters.value.result && l.result !== filters.value.result) return false
    if (filters.value.api && l.apiPath !== filters.value.api) return false
    if (!kw) return true
    return [l.id, l.keyName, l.apiPath, l.msg].some((s) => s.toLowerCase().includes(kw))
  })
})

/* ---- 模拟网关调用 ---- */
const simVisible = ref(false)
const simForm = ref({ keyId: '', apiId: '', params: '' })

function openSim() {
  const ek = keys.value.find((k) => k.status === 'enabled')
  const ea = apis.value.find((a) => a.status === 'enabled')
  simForm.value = { keyId: ek?.id ?? '', apiId: ea?.id ?? '', params: '' }
  simVisible.value = true
}

/** 本地时间戳（含秒），与种子格式一致；禁止 toISOString（UTC 偏移） */
function nowTs(): string {
  const d = new Date()
  const p = (x: number) => String(x).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

function nextLogId(): string {
  const max = logs.value.reduce((m, l) => Math.max(m, Number(l.id.replace(/\D/g, '')) || 0), 0)
  return 'OL' + String(max + 1).padStart(4, '0')
}

async function doSim() {
  const key = keys.value.find((k) => k.id === simForm.value.keyId)
  const api = apis.value.find((a) => a.id === simForm.value.apiId)
  if (!key || !api) {
    ElMessage.warning('请选择 API-Key 与 API')
    return
  }
  /* 鉴权链路：Key 停用 → 拒绝；未绑定 → 拒绝；否则放行 */
  let httpStatus = 200
  let result: OpenLog['result'] = 'success'
  let msg = `模拟返回 ${1 + Math.floor(Math.random() * 12)} 条`
  if (key.status !== 'enabled') {
    httpStatus = 403
    result = 'denied'
    msg = 'Key 已停用，鉴权拒绝'
  } else if (!key.apis.includes(api.id)) {
    httpStatus = 403
    result = 'denied'
    msg = `Key 未绑定该 API（${api.id} 不在授权范围）`
  }
  const costMs = result === 'success' ? 20 + Math.floor(Math.random() * 140) : 3
  const log: OpenLog = {
    id: nextLogId(),
    ts: nowTs(),
    keyId: key.id,
    keyName: key.name,
    apiId: api.id,
    apiPath: api.path,
    params: simForm.value.params.trim() || '-',
    httpStatus,
    costMs,
    result,
    msg,
  }
  await dataStore.save('openLogs', log)
  /* 成功调用累计统计 */
  if (result === 'success') {
    await dataStore.save('openApis', { ...api, calls: api.calls + 1 })
    await dataStore.save('apiKeys', { ...key, calls: key.calls + 1, lastCalled: log.ts.slice(0, 16) })
  }
  await Promise.all([reload(), refreshRefs()])
  simVisible.value = false
  ElMessage[result === 'success' ? 'success' : 'warning'](
    `${result === 'success' ? '调用成功' : '调用被拒绝'}：HTTP ${httpStatus}（${costMs}ms）— ${msg}`,
  )
}

async function refreshRefs() {
  const [a, k] = await Promise.all([
    dataStore.list<OpenApi>('openApis'),
    dataStore.list<OpenApiKey>('apiKeys'),
  ])
  apis.value = [...(a ?? [])]
  keys.value = [...(k ?? [])]
}

/* ---- 徽标 ---- */
function resultCls(r: string): string {
  return r === 'success' ? 'ok' : r === 'denied' ? 'deny' : 'err'
}
function resultLabel(r: string): string {
  return r === 'success' ? '成功' : r === 'denied' ? '鉴权拒绝' : '服务错误'
}
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ListFilterPanel
      v-model:keyword="keyword"
      v-model:filters="filters"
      :facets="facets"
      placeholder="搜索Key/API路径/消息"
      :result-count="filtered.length"
      :total-count="logs.length"
    />
    <div style="flex:1;min-width:0">
      <!-- 页头 -->
      <div class="card page-head">
        <div>
          <div class="ph-title">调用日志</div>
          <div class="ph-desc">网关调用流水：X-API-Key 鉴权 → 绑定范围校验 → 转发；「模拟网关调用」可复演成功与 403 鉴权拒绝链路</div>
        </div>
        <div class="ph-acts">
          <button v-if="auth.canEdit" class="tb-new" @click="openSim">▶ 模拟网关调用</button>
          <button class="op-btn" @click="$router.push('/open/api')">API管理</button>
          <button class="op-btn" @click="$router.push('/open/key')">API-Key管理</button>
        </div>
      </div>

      <!-- 日志列表 -->
      <div class="card panel">
        <div class="tbl-toolbar">
          <span class="sec-head">调用流水</span>
          <span class="pill info">{{ filtered.length }} / {{ logs.length }}</span>
          <span class="spacer" />
        </div>
        <table class="tbl">
          <thead>
            <tr><th>时间</th><th>API-Key</th><th>API</th><th>请求参数</th><th>HTTP</th><th>耗时</th><th>结果</th><th>消息</th></tr>
          </thead>
          <tbody>
            <tr v-for="l in filtered" :key="l.id">
              <td class="mono" style="font-size:11px;white-space:nowrap">{{ l.ts }}</td>
              <td>
                <b>{{ l.keyName }}</b>
                <div class="mono" style="font-size:11px;color:var(--text-3)">{{ l.keyId }}</div>
              </td>
              <td>
                <span class="mono" style="font-size:11.5px">{{ l.apiPath }}</span>
                <div style="font-size:11px;color:var(--text-3)">{{ l.apiId }}</div>
              </td>
              <td class="mono" style="font-size:11px;color:var(--text-2)">{{ l.params }}</td>
              <td><span class="pill" :class="l.httpStatus === 200 ? 'ok' : 'deny'">{{ l.httpStatus }}</span></td>
              <td>{{ l.costMs }}ms</td>
              <td><span class="pill" :class="resultCls(l.result)">{{ resultLabel(l.result) }}</span></td>
              <td style="font-size:11.5px;color:var(--text-2)">{{ l.msg }}</td>
            </tr>
          </tbody>
        </table>
        <div v-if="filtered.length === 0" class="empty">暂无调用记录</div>
      </div>
    </div>

    <!-- 模拟网关调用弹窗 -->
    <el-dialog v-model="simVisible" title="模拟网关调用" width="480px">
      <div class="sim-tip">模拟第三方系统携带 X-API-Key 调用开放 API：Key 停用或 API 未绑定该 Key 时返回 403 鉴权拒绝。</div>
      <div class="form-row">
        <label class="f-label">API-Key<i>*</i></label>
        <select v-model="simForm.keyId" class="f-input">
          <option v-for="k in keys" :key="k.id" :value="k.id">{{ k.name }}（{{ k.id }}{{ k.status === 'enabled' ? '' : ' · 已停用' }}）</option>
        </select>
      </div>
      <div class="form-row">
        <label class="f-label">API<i>*</i></label>
        <select v-model="simForm.apiId" class="f-input">
          <option v-for="a in apis" :key="a.id" :value="a.id">{{ a.name }}（{{ a.id }}{{ a.status === 'enabled' ? '' : ' · 已停用' }}）</option>
        </select>
      </div>
      <div class="form-row">
        <label class="f-label">请求参数</label>
        <input v-model="simForm.params" class="f-input" placeholder="如 status=running（可选，仅记录）" />
      </div>
      <template #footer>
        <button class="op-btn" @click="simVisible = false">取消</button>
        <button class="tb-new" @click="doSim">发起调用</button>
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
.pill.ok{background:var(--success-bg);color:var(--success)}
.pill.deny{background:rgba(229,72,77,.1);color:var(--danger)}
.pill.err{background:var(--warn-bg);color:var(--warn)}
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;font-weight:600;color:var(--text-3);font-size:11.5px;padding:6px 8px;border-bottom:1px solid var(--border);white-space:nowrap}
.tbl td{padding:7px 8px;border-bottom:1px solid var(--border);vertical-align:middle}
.tbl tbody tr:hover{background:var(--bg)}
.empty{padding:24px;text-align:center;color:var(--text-3);font-size:12.5px}
.mono{font-family:ui-monospace,Consolas,monospace}
.form-row{display:flex;gap:10px;margin-bottom:14px;align-items:center}
.f-label{width:70px;flex-shrink:0;font-size:12.5px;color:var(--text-2);text-align:right}
.f-label i{color:var(--danger);font-style:normal;margin-left:2px}
.f-input{flex:1;border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:7px 10px;font-size:12.5px;outline:none;background:#fff}
.f-input:focus{border-color:var(--primary)}
.sim-tip{background:var(--info-bg);color:var(--info);border-radius:var(--radius-sm);padding:8px 10px;font-size:11.5px;margin-bottom:14px}
</style>
