<script setup lang="ts">
/**
 * M03 数据源详情（I4 §3.3 接真）
 * 概要（基本信息）+ 连接信息（连接型 host:port/账号；文件型 params 表）+ 连通测试（真实接口，结果回写 status）
 * + 测试历史（最近 10 次，localStorage 按源存储）+ 库表树预览（连接型三级树 / 文件型 schema+20 行抽样）。
 */
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  listDataSources, testDataSource, getDataSourceTree,
  type DsRow, type DsTestResult, type DsTree,
} from '../../services/datasourceApi'
import { dsTypeColor, dsTypeShort } from '../../services/mock/dsUtils'

const route = useRoute()
const router = useRouter()

const ds = ref<DsRow | null>(null)
const notFound = ref(false)
const loading = ref(false)

/* ---- 连通测试 ---- */
const testing = ref(false)
const testResult = ref<DsTestResult | null>(null)

interface TestHistoryEntry { ts: string; status: string; elapsedMs: number; message: string }
const testHistory = ref<TestHistoryEntry[]>([])
const HISTORY_KEY = 'datara.db.dsTest'

function fmtNow(): string {
  const d = new Date()
  const p = (x: number) => String(x).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

function loadHistory(id: number | string): TestHistoryEntry[] {
  try {
    const raw = localStorage.getItem(`${HISTORY_KEY}.${id}`)
    return raw ? (JSON.parse(raw) as TestHistoryEntry[]) : []
  } catch {
    return []
  }
}

function persistHistory(id: number | string, h: TestHistoryEntry[]) {
  try {
    localStorage.setItem(`${HISTORY_KEY}.${id}`, JSON.stringify(h.slice(0, 10)))
  } catch { /* 内存态继续 */ }
}

/* ---- 库表树 ---- */
const tree = ref<DsTree | null>(null)
const treeLoading = ref(false)
const treeError = ref('')
const expandedDbs = ref<Set<string>>(new Set())

/* ---- 加载 ---- */
async function reload() {
  const id = String(route.params.id ?? '')
  if (!id) {
    notFound.value = true
    return
  }
  loading.value = true
  try {
    const rows = await listDataSources()
    const found = rows.find((r) => String(r.id) === id) ?? null
    ds.value = found
    notFound.value = !found
    if (found) {
      testHistory.value = loadHistory(found.id)
      testResult.value = null
      tree.value = null
      treeError.value = ''
      expandedDbs.value = new Set()
      void loadTree(found)
    }
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '数据源加载失败')
  } finally {
    loading.value = false
  }
}

async function loadTree(row: DsRow) {
  treeLoading.value = true
  try {
    tree.value = await getDataSourceTree(row.id)
    // 连接型默认展开第一个库
    if (tree.value.kind === 'connection' && tree.value.databases.length > 0) {
      expandedDbs.value = new Set([tree.value.databases[0].name])
    }
  } catch (err) {
    treeError.value = err instanceof Error ? err.message : '库表树加载失败'
    tree.value = null
  } finally {
    treeLoading.value = false
  }
}

onMounted(reload)
// 同一组件实例在 /ds/detail/:id 间切换（hash 导航复用实例）时重新加载
watch(() => route.params.id, reload)

/* ---- 测试 ---- */
async function runTest() {
  if (testing.value || !ds.value) return
  const target = ds.value
  testing.value = true
  try {
    const res = await testDataSource(target.id)
    testResult.value = res
    const entry: TestHistoryEntry = {
      ts: fmtNow(), status: res.status, elapsedMs: res.elapsedMs, message: res.message,
    }
    const h = [entry, ...loadHistory(target.id)]
    persistHistory(target.id, h)
    testHistory.value = h.slice(0, 10)
    if (res.status === 'online') {
      ElMessage.success(`${target.name}：${res.message}（${res.elapsedMs}ms）`)
      target.status = 'online'
    } else {
      ElMessage.error(`${target.name}：${res.message}`)
      target.status = 'offline'
    }
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '测试失败')
  } finally {
    testing.value = false
  }
}

/* ---- 文件参数展示行 ---- */
const fileParamsRows = computed(() => {
  const p = (ds.value?.params ?? {}) as Record<string, unknown>
  const rows: { k: string; v: string }[] = []
  const put = (k: string, v: unknown) => rows.push({ k, v: v == null || v === '' ? '-' : String(v) })
  put('格式 format', p.format)
  put('路径 path', p.path ? `/datara/files/${p.path}` : '')
  put('编码 encoding', p.encoding)
  put('分隔符 delimiter', p.delimiter)
  put('首行表头 header', p.header === false || p.header === 'false' ? '否' : '是')
  put('Sheet', p.sheet)
  return rows
})

function toggleDb(name: string) {
  const next = new Set(expandedDbs.value)
  if (next.has(name)) next.delete(name)
  else next.add(name)
  expandedDbs.value = next
}

function nullRateText(r: number): string {
  return `${(r * 100).toFixed(1)}%`
}

/* ---- 文件抽样表：header=true 首行为表头；否则按 schema 生成 col_N 表头 ---- */
const sampleHead = computed<string[]>(() => {
  if (!tree.value || tree.value.kind !== 'file' || tree.value.sample.length === 0) return []
  if (ds.value) {
    const p = (ds.value.params ?? {}) as Record<string, unknown>
    if (p.header === false || p.header === 'false') {
      const width = tree.value.sample[0].length
      return Array.from({ length: width }, (_, i) => `col_${i + 1}`)
    }
  }
  return tree.value.sample[0]
})
const sampleBody = computed<string[][]>(() => {
  if (!tree.value || tree.value.kind !== 'file') return []
  const skip = sampleHead.value.length > 0 && sampleHead.value === tree.value.sample[0] ? 1 : 0
  return tree.value.sample.slice(skip, skip + 20)
})
</script>

<template>
  <div class="page">
    <!-- 空态 -->
    <div v-if="notFound" class="card detail-empty">
      <div style="text-align:center;color:var(--text-3);padding:48px 0">
        <div style="font-size:36px;margin-bottom:8px">🔍</div>
        <div style="font-size:14px;margin-bottom:4px">数据源不存在</div>
        <div style="font-size:12px">请检查数据源 ID 是否正确，或返回列表重新选择。</div>
        <button class="btn-primary" style="margin-top:16px" @click="router.push('/ds/list')">返回列表</button>
      </div>
    </div>

    <!-- 详情主体 -->
    <div v-if="ds" class="card detail-shell">
      <!-- 顶栏 -->
      <div class="detail-head">
        <button class="op-btn" @click="router.push('/ds/list')">← 返回列表</button>
        <span class="type-icon" :style="{ background: dsTypeColor(ds.type) }">{{ dsTypeShort(ds.type) }}</span>
        <div class="title-text">
          <b style="font-size:15px">{{ ds.name }}</b>
          <div style="color:var(--text-3);font-size:11.5px">#{{ ds.id }} · {{ ds.type }}</div>
        </div>
        <span class="spacer" />
        <span class="pill" :class="ds.status === 'online' ? 'ok' : ds.status === 'offline' ? 'err' : 'off'">
          {{ ds.status === 'online' ? '在线' : ds.status === 'offline' ? '离线' : '未测试' }}
        </span>
        <button class="btn-primary" :disabled="testing" @click="runTest">
          {{ testing ? '测试中…' : '连通测试' }}
        </button>
      </div>

      <!-- 概要 -->
      <div class="sub-card">
        <div class="sub-title">基本信息</div>
        <div class="info-grid">
          <div class="info-row"><span class="ik">环境</span>
            <span class="iv"><span class="pill" :class="ds.env === '生产' ? 'err' : ds.env === '测试' ? 'warn' : 'info'">{{ ds.env || '-' }}</span></span>
          </div>
          <div class="info-row"><span class="ik">分组</span><span class="iv">{{ ds.group || '—' }}</span></div>
          <div class="info-row"><span class="ik">标签</span>
            <span class="iv">
              <span v-if="!ds.tags || ds.tags.length === 0" style="color:var(--text-3)">—</span>
              <span v-for="t in ds.tags" :key="t" class="tag-chip">{{ t }}</span>
            </span>
          </div>
          <div class="info-row"><span class="ik">负责人</span><span class="iv">{{ ds.owner || '—' }}</span></div>
          <div class="info-row"><span class="ik">创建时间</span><span class="iv mono">{{ ds.createdAt || '—' }}</span></div>
          <div class="info-row"><span class="ik">更新时间</span><span class="iv mono">{{ ds.updateTime || '—' }}</span></div>
        </div>
      </div>

      <!-- 连接信息 -->
      <div class="sub-card">
        <div class="sub-title">连接信息</div>
        <template v-if="ds.type !== 'file'">
          <div class="info-grid">
            <div class="info-row"><span class="ik">主机</span><span class="iv mono">{{ ds.host || '—' }}:{{ ds.port ?? '—' }}</span></div>
            <div class="info-row"><span class="ik">数据库</span><span class="iv mono">{{ ds.db || '—' }}</span></div>
            <div class="info-row"><span class="ik">用户名</span><span class="iv mono">{{ ds.user || '—' }}</span></div>
            <div class="info-row"><span class="ik">密码</span><span class="iv mono">{{ ds.pwd || '—' }}</span></div>
          </div>
          <div class="wiz-tip" style="margin-top:8px">密码明文存储与回显（内部系统口径，09-18 裁定）；万里 GreatDB 与 MySQL 同驱动、协议兼容。</div>
        </template>
        <template v-else>
          <div class="info-grid">
            <div v-for="row in fileParamsRows" :key="row.k" class="info-row">
              <span class="ik">{{ row.k }}</span><span class="iv mono">{{ row.v }}</span>
            </div>
          </div>
          <div class="wiz-tip" style="margin-top:8px">文件源路径收敛共享卷 /datara/files（宿主机 /mnt/lei/datara/files），越界路径后端拒绝。</div>
        </template>
      </div>

      <!-- 连通测试 + 历史 -->
      <div class="sub-card">
        <div class="sub-title">连通测试</div>
        <div v-if="testResult" class="banner" :class="testResult.status === 'online' ? 'banner-success' : 'banner-danger'">
          <span class="b-ico">{{ testResult.status === 'online' ? '✓' : '✗' }}</span>
          <span>
            {{ testResult.status === 'online'
              ? `连通成功（${testResult.elapsedMs}ms）：${testResult.message}`
              : `连通失败：${testResult.message}` }}
          </span>
        </div>
        <div v-else class="wiz-tip">点击右上角「连通测试」：连接型执行 connect + SELECT 1；文件型校验可读并解析头 5 行推断列数。</div>

        <div v-if="testHistory.length" class="probe-history">
          <div class="probe-history-title">测试历史（最近 {{ testHistory.length }} 次）</div>
          <div v-for="(e, i) in testHistory" :key="i" class="probe-row">
            <span class="pill" :class="e.status === 'online' ? 'ok' : 'err'">{{ e.status === 'online' ? '✓' : '✗' }}</span>
            <span class="mono" style="font-size:11.5px">{{ e.ts }}</span>
            <span style="color:var(--text-3);font-size:11.5px">{{ e.message }}（{{ e.elapsedMs }}ms）</span>
          </div>
        </div>
      </div>

      <!-- 库表树预览 -->
      <div class="sub-card">
        <div class="sub-title">库表树预览</div>
        <div v-if="treeLoading" class="empty-tip">加载中…</div>
        <div v-else-if="treeError" class="empty-tip">{{ treeError }}</div>

        <!-- 连接型：库/表/字段三级 -->
        <template v-else-if="tree && tree.kind === 'connection'">
          <div v-if="tree.databases.length === 0" class="empty-tip">无业务库（系统库已过滤）</div>
          <div v-for="d in tree.databases" :key="d.name" class="db-block">
            <div class="db-head" @click="toggleDb(d.name)">
              <span class="tri">{{ expandedDbs.has(d.name) ? '▾' : '▸' }}</span>
              <b>{{ d.name }}</b>
              <span class="pill info" style="margin-left:8px">{{ d.tables.length }} 表</span>
            </div>
            <div v-if="expandedDbs.has(d.name)" class="db-body">
              <div v-for="t in d.tables" :key="t.name" class="tbl-block">
                <div class="tbl-head">
                  <span>{{ t.name }}</span>
                  <span class="tbl-meta">
                    <span style="color:var(--text-3);font-size:11px">{{ t.columns.length }} 列</span>
                    <button class="op-btn" @click="router.push(`/meta/lineage?table=${t.name}`)">血缘</button>
                  </span>
                </div>
                <table class="col-tbl">
                  <thead><tr><th>字段</th><th>类型</th></tr></thead>
                  <tbody>
                    <tr v-for="c in t.columns" :key="c.name">
                      <td class="mono">{{ c.name }}</td>
                      <td style="color:var(--text-3)">{{ c.type }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div v-if="d.tables.length === 0" class="empty-tip">空库</div>
            </div>
          </div>
        </template>

        <!-- 文件型：schema + 抽样 -->
        <template v-else-if="tree && tree.kind === 'file'">
          <div class="wiz-tip" style="margin-bottom:8px">{{ tree.file }} · 抽样 {{ tree.schema.sampledRows }} 行</div>
          <table class="col-tbl" style="margin-bottom:12px">
            <thead><tr><th>字段</th><th>推断类型</th><th>空值率</th></tr></thead>
            <tbody>
              <tr v-for="c in tree.schema.columns" :key="c.name">
                <td class="mono">{{ c.name }}</td>
                <td style="color:var(--text-3)">{{ c.type }}</td>
                <td>{{ nullRateText(c.nullRate) }}</td>
              </tr>
            </tbody>
          </table>
          <div v-if="sampleHead.length" class="sample-wrap">
            <table class="col-tbl">
              <thead>
                <tr><th v-for="(h, i) in sampleHead" :key="i" class="mono">{{ h }}</th></tr>
              </thead>
              <tbody>
                <tr v-for="(row, ri) in sampleBody" :key="ri">
                  <td v-for="(cell, ci) in row" :key="ci">{{ cell }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ---- 顶栏 ---- */
.detail-head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}
.type-icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 13px;
  font-weight: 700;
  flex-shrink: 0;
}
.title-text { flex-shrink: 0; }
.spacer { flex: 1; }

/* ---- 按钮 ---- */
.op-btn {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 5px 12px;
  font-size: 12px;
  cursor: pointer;
  color: var(--text-2);
  white-space: nowrap;
}
.op-btn:hover { background: var(--primary-light); color: var(--primary); }
.btn-primary {
  background: var(--primary);
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 7px 14px;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
}
.btn-primary:hover { background: var(--primary-hover); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

/* ---- 子卡片 ---- */
.detail-shell { display: flex; flex-direction: column; }
.sub-card {
  margin: 12px 20px 12px;
  padding: 16px;
  background: var(--bg);
  border-radius: var(--radius);
  border: 1px solid var(--border);
}
.sub-title {
  font-size: 13px;
  font-weight: 700;
  margin-bottom: 12px;
  color: var(--text);
}
.detail-empty { margin: 12px; }
.mono { font-family: var(--font-mono, monospace); }

/* ---- 信息行 ---- */
.info-grid { display: flex; flex-direction: column; gap: 8px; }
.info-row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12.5px;
}
.ik {
  width: 110px;
  flex-shrink: 0;
  color: var(--text-3);
  font-weight: 500;
}
.iv { color: var(--text); display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.tag-chip {
  display: inline-flex;
  align-items: center;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 11px;
  background: var(--primary-light);
  color: var(--primary);
  font-weight: 500;
}
.wiz-tip{background:var(--card);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 10px;font-size:11.5px;color:var(--text-2)}

/* ---- banner / 历史 ---- */
.banner {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 6px;
  font-size: 12.5px;
}
.banner-success { background: var(--success-bg, #f0fdf4); color: var(--success, #15803d); }
.banner-danger { background: var(--danger-bg, #fef2f2); color: var(--danger, #b91c1c); }
.b-ico { font-weight: 700; flex-shrink: 0; }
.probe-history { margin-top: 12px; }
.probe-history-title {
  font-size: 12px;
  color: var(--text-2);
  font-weight: 600;
  margin-bottom: 6px;
}
.probe-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  border-bottom: 1px solid var(--border);
}
.probe-row:last-child { border-bottom: none; }

/* ---- 库表树 ---- */
.db-block { border: 1px solid var(--border); border-radius: var(--radius-sm); margin-bottom: 8px; background: var(--card); }
.db-head { display: flex; align-items: center; gap: 6px; padding: 9px 12px; cursor: pointer; font-size: 12.5px; }
.db-head:hover { color: var(--primary); }
.tri { color: var(--text-3); font-size: 11px; width: 12px; }
.db-body { padding: 0 12px 10px 30px; }
.tbl-block { margin-bottom: 8px; }
.tbl-head { display: flex; justify-content: space-between; padding: 5px 0; font-size: 12px; color: var(--text-2); }
.tbl-meta { display: flex; align-items: center; gap: 8px; }
.col-tbl { width: 100%; border-collapse: collapse; font-size: 11.5px; }
.col-tbl th { text-align: left; padding: 5px 8px; background: var(--bg); color: var(--text-3); border-bottom: 1px solid var(--border); font-weight: 600; }
.col-tbl td { padding: 4px 8px; border-bottom: 1px solid var(--border); }
.sample-wrap { max-height: 360px; overflow: auto; border: 1px solid var(--border); border-radius: var(--radius-sm); }
.empty-tip { padding: 14px 12px; color: var(--text-3); font-size: 12px; }
</style>
