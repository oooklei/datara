<script setup lang="ts">
/**
 * M03 数据源列表/筛选（I4 §3.3 接真）
 * 数据源：GET /datasources（datasourceApi）；关键字/环境/分组客户端过滤 + 状态过滤。
 * 行操作：详情 / 连通测试（POST /{id}/test，结果回写 status）/ 编辑（向导复用）/ 删除（被引用 409 后端拦截）。
 * 列表列：类型徽标 / 主机 / 环境 / 分组 / 标签 / 状态 / 最近测试时间。
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listDataSources, testDataSource, deleteDataSource,
  type DsRow, type DsTestResult,
} from '../../services/datasourceApi'
import { dsTypeColor, dsTypeShort } from '../../services/mock/dsUtils'
import { useAuthStore } from '../../stores/auth'
import ListFilterPanel from '../../components/ListFilterPanel.vue'
import DataSourceWizard from './DataSourceWizard.vue'

const router = useRouter()
const auth = useAuthStore()

const showWizard = ref(false)
const editRow = ref<DsRow | null>(null)

const rows = ref<DsRow[]>([])
const keyword = ref('')
const filters = ref<Record<string, string>>({ env: '', group: '', status: '' })

const envOptions = ['生产', '测试', '开发']
const groupOptions = ['交易域', '经营域', '财务域', '商品域', '数仓', '消息', '公共']

const facets = [
  { key: 'env', label: '环境', options: envOptions.map((e) => ({ v: e, t: e })) },
  { key: 'group', label: '分组', options: groupOptions.map((g) => ({ v: g, t: g })) },
  { key: 'status', label: '状态', options: [{ v: 'online', t: '在线' }, { v: 'offline', t: '离线' }, { v: 'untested', t: '未测试' }] },
]

function statusText(r: DsRow): string {
  if (r.status === 'online') return '在线'
  if (r.status === 'offline') return '离线'
  return '未测试'
}
function statusClass(r: DsRow): string {
  if (r.status === 'online') return 'ok'
  if (r.status === 'offline') return 'err'
  return 'off'
}

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return rows.value.filter((r) => {
    if (kw) {
      const hay = [r.name, r.type, r.host ?? '', r.db ?? '', String(r.id), r.group ?? ''].join(' ').toLowerCase()
      if (!hay.includes(kw)) return false
    }
    if (filters.value.env && (r.env ?? '') !== filters.value.env) return false
    if (filters.value.group && (r.group ?? '') !== filters.value.group) return false
    if (filters.value.status) {
      const st = r.status || 'untested'
      if (st !== filters.value.status) return false
    }
    return true
  })
})

async function reload() {
  rows.value = await listDataSources()
}

onMounted(reload)

/* ---- 连通测试（行内） ---- */
const testingId = ref<number | null>(null)
const lastTest = ref<DsTestResult | null>(null)

async function runTest(r: DsRow) {
  if (testingId.value !== null) return
  testingId.value = r.id
  try {
    const res = await testDataSource(r.id)
    lastTest.value = res
    if (res.status === 'online') ElMessage.success(`${r.name}：${res.message}（${res.elapsedMs}ms）`)
    else ElMessage.error(`${r.name}：${res.message}`)
    await reload()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '测试失败')
  } finally {
    testingId.value = null
  }
}

/* ---- 编辑（向导复用，全量覆盖） ---- */
function openEdit(r: DsRow) {
  editRow.value = r
  showWizard.value = true
}

/* ---- 删除（二次确认；被工作流引用 → 后端 409 拦截） ---- */
async function removeRow(r: DsRow) {
  try {
    await ElMessageBox.confirm(`确认删除数据源「${r.name}」？该操作不可恢复。`, '删除确认', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
  } catch {
    return
  }
  try {
    await deleteDataSource(r.id)
    ElMessage.success('已删除')
  } catch (err) {
    ElMessage.warning(err instanceof Error ? err.message : '删除失败')
  }
  await reload()
}

function goDetail(r: DsRow) {
  router.push(`/ds/detail/${r.id}`)
}
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ListFilterPanel
      v-model:keyword="keyword"
      v-model:filters="filters"
      :facets="facets"
      :result-count="filtered.length"
      :total-count="rows.length"
      placeholder="搜索名称/类型/主机/库名"
    />
    <div style="flex:1;min-width:0">
    <div class="card" style="padding:16px">
      <div class="tbl-toolbar">
        <span class="sec-head">数据源列表</span>
        <span class="pill info">{{ filtered.length }} / {{ rows.length }}</span>
        <span class="spacer" />
        <button class="tb-new" @click="editRow = null; showWizard = true">＋ 注册</button>
      </div>

      <table class="tbl">
        <thead>
          <tr>
            <th>数据源</th><th>主机</th><th>环境</th><th>分组</th><th>标签</th>
            <th>状态</th><th>最近测试</th><th style="width:190px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in filtered" :key="r.id">
            <td>
              <div style="display:flex;gap:9px;align-items:center">
                <span class="type-icon" :style="{ background: dsTypeColor(r.type) }">{{ dsTypeShort(r.type) }}</span>
                <div>
                  <a @click="goDetail(r)"><b>{{ r.name }}</b></a>
                  <div style="color:var(--text-3);font-size:11px">#{{ r.id }} · {{ r.type }}</div>
                </div>
              </div>
            </td>
            <td>
              <template v-if="r.type === 'file'">
                <span class="mono" style="font-size:11.5px">/datara/files</span>
                <div style="color:var(--text-3);font-size:11px">{{ (r.params?.path as string) || '-' }}</div>
              </template>
              <template v-else>
                <span class="mono" style="font-size:11.5px">{{ r.host }}:{{ r.port }}</span>
                <div style="color:var(--text-3);font-size:11px">{{ r.db || '-' }}</div>
              </template>
            </td>
            <td>
              <span class="pill" :class="r.env === '生产' ? 'err' : r.env === '测试' ? 'warn' : 'info'">{{ r.env || '-' }}</span>
            </td>
            <td>{{ r.group || '-' }}</td>
            <td>
              <span v-for="t in r.tags" :key="t" class="pill info" style="margin-right:4px">{{ t }}</span>
              <span v-if="!r.tags || r.tags.length === 0" style="color:var(--text-3)">-</span>
            </td>
            <td>
              <span class="pill" :class="statusClass(r)">{{ statusText(r) }}</span>
            </td>
            <td style="color:var(--text-3);font-size:11.5px">{{ r.updateTime || '-' }}</td>
            <td>
              <button class="op-btn primary" @click="goDetail(r)">详情</button>
              <button class="op-btn" :disabled="testingId === r.id" @click="runTest(r)">
                {{ testingId === r.id ? '测试中' : '测试' }}
              </button>
              <button class="op-btn" @click="openEdit(r)">编辑</button>
              <button v-if="auth.can('ds:delete')" class="op-btn danger" @click="removeRow(r)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-if="filtered.length === 0" class="empty">
        未找到匹配的数据源，请调整筛选条件
      </div>
    </div>
    </div>

    <!-- 注册/编辑向导（I4 §3.3：三步 + 文件参数动态表单） -->
    <DataSourceWizard v-model:visible="showWizard" :edit-row="editRow" @saved="reload" />
  </div>
</template>

<style scoped>
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;padding:9px 10px;background:var(--bg);color:var(--text-2);font-weight:600;border-bottom:1px solid var(--border)}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--border)}
.tbl tr:hover td{background:var(--primary-light)}
.type-icon{width:30px;height:30px;border-radius:var(--radius-sm);display:flex;align-items:center;justify-content:center;color:#fff;font-size:10px;font-weight:700;flex-shrink:0}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease)}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
.op-btn.primary{color:var(--primary);border-color:rgba(22,104,220,.4);font-weight:600}
.op-btn.danger{color:var(--danger);border-color:rgba(229,72,77,.35)}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.op-btn:disabled{opacity:.55;cursor:not-allowed}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
</style>
