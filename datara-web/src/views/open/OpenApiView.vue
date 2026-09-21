<script setup lang="ts">
/**
 * M16 开放接口 · API管理（/open/api）
 * 系统自身产出/运行数据的对外查询 API 目录（流数据/数据质量/元数据 三类，产出型只读）：
 * 列表 + 分类筛选 + 详情（参数说明/响应示例）+ 启用停用（canEdit 门控）。
 * 鉴权模拟在「调用日志」页：Key 未绑定/停用 → 403 denied。
 * 数据：openApis。
 */
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { dataStore, ST } from '../../services/mock/dataStore'
import ListFilterPanel from '../../components/ListFilterPanel.vue'
import type { Facet } from '../../components/ListFilterPanel.vue'
import type { OpenApi } from '../../services/types'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const apis = ref<OpenApi[]>([])
const keyword = ref('')
const filters = ref<Record<string, string>>({ category: '', status: '' })

onMounted(async () => {
  await reload()
})

async function reload() {
  // 必须展开为新数组：dataStore.save 原地修改数组，直接赋值不会触发响应式更新。
  apis.value = [...((await dataStore.list<OpenApi>('openApis')) ?? [])]
}

const facets = computed<Facet[]>(() => [
  { key: 'category', label: 'API分类', options: [{ v: '流数据', t: '流数据' }, { v: '数据质量', t: '数据质量' }, { v: '元数据', t: '元数据' }] },
  { key: 'status', label: '状态', options: [{ v: 'enabled', t: '已启用' }, { v: 'disabled', t: '已停用' }] },
])

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return apis.value.filter((a) => {
    if (filters.value.category && a.category !== filters.value.category) return false
    if (filters.value.status && a.status !== filters.value.status) return false
    if (!kw) return true
    return [a.id, a.name, a.path, a.desc].some((s) => s.toLowerCase().includes(kw))
  })
})

/* ---- 详情弹窗 ---- */
const viewVisible = ref(false)
const viewTarget = ref<OpenApi | null>(null)
function openView(a: OpenApi) {
  viewTarget.value = a
  viewVisible.value = true
}

/* ---- 启用/停用 ---- */
async function toggle(a: OpenApi) {
  if (!auth.canEdit) return
  const next = a.status === 'enabled' ? 'disabled' : 'enabled'
  await dataStore.save('openApis', { ...a, status: next })
  await reload()
  ElMessage.success(`${a.name} 已${next === 'enabled' ? '启用' : '停用'}`)
}

/* ---- 徽标 ---- */
function stCls(s: string): string {
  return ST[s]?.cls ?? 'st-gray'
}
function stLabel(s: string): string {
  return ST[s]?.label ?? s
}
function methodCls(m: string): string {
  return m === 'GET' ? 'info' : 'purple'
}
function catCls(c: string): string {
  return c === '流数据' ? 'info' : c === '数据质量' ? 'warn' : 'ok'
}
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ListFilterPanel
      v-model:keyword="keyword"
      v-model:filters="filters"
      :facets="facets"
      placeholder="搜索API名称/路径"
      :result-count="filtered.length"
      :total-count="apis.length"
    />
    <div style="flex:1;min-width:0">
      <!-- 页头 -->
      <div class="card page-head">
        <div>
          <div class="ph-title">API管理</div>
          <div class="ph-desc">系统自身产出/运行数据的对外查询 API（流数据 / 数据质量 / 元数据 三类产出型只读接口）；第三方凭 API-Key 调用，见「调用日志」页模拟网关</div>
        </div>
        <div class="ph-acts">
          <button class="op-btn" @click="$router.push('/open/key')">API-Key管理</button>
          <button class="op-btn" @click="$router.push('/open/log')">调用日志</button>
        </div>
      </div>

      <!-- API 列表 -->
      <div class="card panel">
        <div class="tbl-toolbar">
          <span class="sec-head">API 列表</span>
          <span class="pill info">{{ filtered.length }} / {{ apis.length }}</span>
          <span class="spacer" />
        </div>
        <table class="tbl">
          <thead>
            <tr><th>API</th><th>方法</th><th>分类</th><th>调用次数</th><th>状态</th><th style="width:130px">操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="a in filtered" :key="a.id">
              <td>
                <a @click="openView(a)"><b>{{ a.name }}</b></a>
                <div class="mono" style="font-size:11px;color:var(--text-3)">{{ a.id }} · {{ a.path }}</div>
              </td>
              <td><span class="pill" :class="methodCls(a.method)">{{ a.method }}</span></td>
              <td><span class="pill" :class="catCls(a.category)">{{ a.category }}</span></td>
              <td>{{ a.calls }}</td>
              <td><span class="st" :class="stCls(a.status)"><span class="dot" />{{ stLabel(a.status) }}</span></td>
              <td>
                <button class="op-btn primary" @click="openView(a)">详情</button>
                <button v-if="auth.canEdit" class="op-btn" @click="toggle(a)">{{ a.status === 'enabled' ? '停用' : '启用' }}</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="filtered.length === 0" class="empty">未找到匹配的 API</div>
      </div>
    </div>

    <!-- 详情弹窗 -->
    <el-dialog v-model="viewVisible" :title="viewTarget ? `API 详情 — ${viewTarget.name}` : ''" width="640px">
      <template v-if="viewTarget">
        <div class="desc-grid">
          <div class="d-row"><span class="d-k">API编号</span><span class="mono">{{ viewTarget.id }}</span></div>
          <div class="d-row"><span class="d-k">请求路径</span><span class="mono">{{ viewTarget.method }} {{ viewTarget.path }}</span></div>
          <div class="d-row"><span class="d-k">分类</span><span><span class="pill" :class="catCls(viewTarget.category)">{{ viewTarget.category }}</span></span></div>
          <div class="d-row"><span class="d-k">说明</span><span>{{ viewTarget.desc }}</span></div>
          <div class="d-row"><span class="d-k">鉴权方式</span><span>请求头 <span class="mono">X-API-Key</span>（在「API-Key管理」创建并绑定本 API）</span></div>
        </div>
        <div class="sec-title">请求参数</div>
        <table class="tbl">
          <thead><tr><th>参数</th><th>必填</th><th>说明</th></tr></thead>
          <tbody>
            <tr v-for="p in viewTarget.params" :key="p.name">
              <td class="mono">{{ p.name }}</td>
              <td><span class="pill" :class="p.required ? 'warn' : 'info'">{{ p.required ? '必填' : '可选' }}</span></td>
              <td style="color:var(--text-2)">{{ p.desc }}</td>
            </tr>
          </tbody>
        </table>
        <div class="sec-title">响应示例</div>
        <pre class="resp">{{ viewTarget.respExample }}</pre>
      </template>
      <template #footer>
        <button class="op-btn" @click="viewVisible = false">关闭</button>
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
.pill.purple{background:#f1eaff;color:var(--purple)}
.pill.warn{background:var(--warn-bg);color:var(--warn)}
.pill.ok{background:var(--success-bg);color:var(--success)}
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;font-weight:600;color:var(--text-3);font-size:11.5px;padding:6px 8px;border-bottom:1px solid var(--border);white-space:nowrap}
.tbl td{padding:7px 8px;border-bottom:1px solid var(--border);vertical-align:middle}
.tbl tbody tr:hover{background:var(--bg)}
.empty{padding:24px;text-align:center;color:var(--text-3);font-size:12.5px}
.mono{font-family:ui-monospace,Consolas,monospace}
a{cursor:pointer;color:var(--primary)}
.desc-grid{display:flex;flex-direction:column;margin-bottom:10px}
.d-row{display:flex;gap:12px;padding:6px 0;border-bottom:1px dashed var(--border);font-size:12.5px}
.d-k{width:88px;color:var(--text-3);flex-shrink:0}
.sec-title{font-weight:700;font-size:13px;margin:14px 0 8px;color:var(--text)}
.resp{background:#0f172a;color:#d6e2f0;border-radius:var(--radius);padding:12px;font-size:11.5px;line-height:1.6;overflow:auto;max-height:220px;font-family:ui-monospace,Consolas,monospace;white-space:pre-wrap}
</style>
