<script setup lang="ts">
/**
 * M16→I7 运行时节点（/dep/runtime，F53/F55 接真改造）
 * - 节点表接真：GET /api/v1/monitor/nodes（master/worker=ZK live+Redis psutil 指标；ssh=t_ssh_node）
 *   30s 轮询自动刷新（设计文档 §3.4）
 * - SSH 节点管理（F53）：注册/编辑/删除/手动探活 → /api/v1/ssh-nodes（标签供 C14 派发路由）
 * - 原 M16 mock 通道（dataStore/runtimeNodes、资源随机采样、分发策略）删除
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '../../stores/auth'
import {
  fetchMonitorNodes, listSshNodes, createSshNode, updateSshNode, deleteSshNode, probeSshNode,
  type MonitorNodeRow, type SshNodeRow,
} from '../../services/graphApi'
import ListFilterPanel from '../../components/ListFilterPanel.vue'

const auth = useAuthStore()

const nodes = ref<MonitorNodeRow[]>([])
const zkAvailable = ref(true)
const keyword = ref('')
const filters = ref<Record<string, string>>({ module: '', heartbeat: '' })
const facets = [
  { key: 'module', label: '类型', options: [{ v: 'master', t: 'master' }, { v: 'worker', t: 'worker' }, { v: 'ssh', t: 'ssh' }] },
  { key: 'heartbeat', label: '状态', options: [{ v: 'online', t: '在线' }, { v: 'offline', t: '离线' }] },
]

/* ---- 30s 轮询（定时器统一管理，卸载清理防泄漏） ---- */
const timers = new Set<number>()
function later(fn: () => void, ms: number) {
  const id = window.setTimeout(() => {
    timers.delete(id)
    fn()
  }, ms)
  timers.add(id)
}
onBeforeUnmount(() => {
  for (const id of timers) window.clearTimeout(id)
  timers.clear()
})

async function reload() {
  try {
    const r = await fetchMonitorNodes()
    nodes.value = r.nodes
    zkAvailable.value = r.zkAvailable
  } catch {
    /* 后端未就绪保留上次数据，下轮重试 */
  }
  later(reload, 30_000)
}
onMounted(reload)

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return nodes.value.filter((r) => {
    if (filters.value.module && r.module !== filters.value.module) return false
    if (filters.value.heartbeat && r.heartbeat !== filters.value.heartbeat) return false
    if (!kw) return true
    return [r.node, ...r.tags].some((s) => s.toLowerCase().includes(kw))
  })
})

const stat = computed(() => ({
  total: nodes.value.length,
  online: nodes.value.filter((n) => n.heartbeat === 'online').length,
  sshOffline: nodes.value.filter((n) => n.module === 'ssh' && n.heartbeat === 'offline').length,
}))

const moduleLabel: Record<string, string> = { master: 'Master 主控', worker: 'Worker 执行', ssh: 'SSH 节点' }
function barCls(v: number | null): string {
  if (v == null) return 'good'
  return v >= 85 ? 'bad' : v >= 70 ? 'warn' : 'good'
}

/* ---- SSH 节点注册 / 编辑（F53：标签 = C14「执行节点标签」下拉数据源） ---- */
const formVisible = ref(false)
const editing = ref<SshNodeRow | null>(null)
const form = ref({ name: '', host: '', port: 22, sshUser: 'root', credKind: '密码', cred: '', tags: '', enabled: true })

function openCreate() {
  editing.value = null
  form.value = { name: '', host: '', port: 22, sshUser: 'root', credKind: '密码', cred: '', tags: '', enabled: true }
  formVisible.value = true
}
function openEdit(n: SshNodeRow) {
  editing.value = n
  form.value = {
    name: n.name, host: n.host, port: n.port, sshUser: n.sshUser,
    credKind: (n.cred ?? '').startsWith('-----BEGIN') ? '私钥' : '密码',
    cred: n.cred ?? '', tags: n.tags.join(','), enabled: n.enabled,
  }
  formVisible.value = true
}
function parseTags(): string[] {
  return form.value.tags.split(/[,，;；]/).map((t) => t.trim()).filter(Boolean)
}
async function saveForm() {
  const name = form.value.name.trim()
  const host = form.value.host.trim()
  if (!name) return ElMessage.warning('请填写节点名称')
  if (!host) return ElMessage.warning('请填写主机地址')
  if (!form.value.port || form.value.port < 1 || form.value.port > 65535) return ElMessage.warning('请填写有效 SSH 端口（1-65535）')
  if (!form.value.sshUser.trim()) return ElMessage.warning('请填写 SSH 用户')
  const body = {
    name, host, port: form.value.port, sshUser: form.value.sshUser.trim(),
    cred: form.value.cred, tags: parseTags(), enabled: form.value.enabled,
  }
  try {
    if (editing.value) await updateSshNode(editing.value.id, body)
    else await createSshNode(body)
  } catch (e) {
    ElMessage.error('保存失败：' + (e instanceof Error ? e.message : '未知错误'))
    return
  }
  ElMessage.success(editing.value ? 'SSH 节点已更新' : 'SSH 节点已注册')
  formVisible.value = false
  await reload()
  await loadSshRows()
}

/* ---- 手动探活 / 删除（仅 ssh 行） ---- */
const sshRows = ref<SshNodeRow[]>([])
async function loadSshRows() {
  try {
    sshRows.value = await listSshNodes()
  } catch { /* 探活行映射缺失时仅影响操作按钮 */ }
}
function sshRowOf(nodeName: string): SshNodeRow | null {
  return sshRows.value.find((r) => r.name === nodeName) ?? null
}
async function probe(n: MonitorNodeRow) {
  const row = sshRowOf(n.node)
  if (!row) return ElMessage.warning('节点行数据未加载，稍后重试')
  ElMessage.info('正在 SSH 探活 ' + row.host + ' ...')
  try {
    const r = await probeSshNode(row.id)
    if (r.ok) ElMessage.success('探活通过：' + r.message)
    else ElMessageBox.alert(r.message, '探活失败', { type: 'error' }).catch(() => {})
  } catch (e) {
    ElMessage.error('探活请求失败：' + (e instanceof Error ? e.message : '未知错误'))
  }
  await reload()
}
async function removeNode(n: MonitorNodeRow) {
  const row = sshRowOf(n.node)
  if (!row) return
  try {
    await ElMessageBox.confirm('确认删除 SSH 节点「' + n.node + '」？带该标签的 ssh 任务将无可用执行节点。', '删除确认', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
  } catch {
    return
  }
  await deleteSshNode(row.id)
  ElMessage.success('节点已删除')
  await reload()
  await loadSshRows()
}
onMounted(loadSshRows)
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ListFilterPanel
      v-model:keyword="keyword"
      v-model:filters="filters"
      :facets="facets"
      :result-count="filtered.length"
      :total-count="nodes.length"
      placeholder="搜索节点/标签"
    />
    <div style="flex:1;min-width:0">
    <!-- 页头 + 顶部操作按钮 -->
    <div class="card page-head">
      <div>
        <div class="ph-title">运行时节点</div>
        <div class="ph-desc">
          master/worker 经 ZK 注册 + psutil 指标（10s 上报 / 90s 过期）；SSH 节点经注册表 + 探活线程（30s/节点，连续 3 次失败离线）。
          SSH 节点标签供画布 SSH 脚本节点「执行节点标签」路由（健康匹配 → 轮转 → 失败策略）。
        </div>
      </div>
      <span class="spacer" />
      <button v-if="auth.canEdit" class="tb-new" @click="openCreate">＋ 注册 SSH 节点</button>
    </div>

    <!-- 统计卡 -->
    <div class="stat-grid4">
      <div class="stat-card"><span class="type-icon" style="background:var(--primary)">⛫</span><div><div class="stat-num">{{ stat.total }}</div><div class="stat-label">节点总数</div></div></div>
      <div class="stat-card"><span class="type-icon" style="background:var(--success)">●</span><div><div class="stat-num">{{ stat.online }}</div><div class="stat-label">在线节点</div></div></div>
      <div class="stat-card"><span class="type-icon" style="background:var(--warn)">⚠</span><div><div class="stat-num">{{ stat.sshOffline }}</div><div class="stat-label">SSH 离线</div></div></div>
      <div class="stat-card"><span class="type-icon" style="background:var(--cyan)">⇄</span><div><div class="stat-num" style="font-size:14px;padding-top:6px">{{ zkAvailable ? 'ZK 已连接' : 'ZK 不可用' }}</div><div class="stat-label">注册中心状态</div></div></div>
    </div>

    <!-- 节点列表 -->
    <div class="card" style="padding:16px;margin-top:12px">
      <div class="tbl-toolbar">
        <span class="card-title">节点列表</span>
        <span class="pill info">{{ filtered.length }} / {{ nodes.length }}</span>
        <span class="pill" :class="zkAvailable ? 'off' : 'warn'" style="font-size:10.5px">30s 自动刷新</span>
        <span class="spacer" />
      </div>
      <table class="tbl">
        <thead>
          <tr>
            <th>类型</th><th>节点</th><th>CPU</th><th>内存</th><th>磁盘</th><th>最近心跳</th><th>状态</th><th style="width:210px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="n in filtered" :key="n.module + ':' + n.node">
            <td><span class="pill" :class="n.module === 'master' ? 'info' : n.module === 'worker' ? 'off' : 'warn'">{{ moduleLabel[n.module] ?? n.module }}</span></td>
            <td>
              <b class="mono" style="font-size:12px">{{ n.node }}</b>
              <div v-if="n.tags.length" style="display:flex;gap:4px;flex-wrap:wrap;margin-top:3px">
                <span v-for="t in n.tags" :key="t" class="pill off" style="font-size:10px">{{ t }}</span>
              </div>
            </td>
            <td>
              <template v-if="n.cpu != null"><div class="res-row"><div class="res-bar"><div :class="barCls(n.cpu)" :style="{ width: n.cpu + '%' }" /></div><span class="mono">{{ n.cpu }}%</span></div></template>
              <span v-else style="color:var(--text-3)">-</span>
            </td>
            <td>
              <template v-if="n.mem != null">
                <div class="res-row"><div class="res-bar"><div :class="barCls(n.mem)" :style="{ width: n.mem + '%' }" /></div><span class="mono">{{ n.mem }}%</span></div>
                <div style="font-size:10px;color:var(--text-3)">{{ n.memUsedMb }} / {{ n.memTotalMb }} MB</div>
              </template>
              <span v-else style="color:var(--text-3)">-</span>
            </td>
            <td>
              <template v-if="n.disk != null"><div class="res-row"><div class="res-bar"><div :class="barCls(n.disk)" :style="{ width: n.disk + '%' }" /></div><span class="mono">{{ n.disk }}%</span></div></template>
              <span v-else style="color:var(--text-3)">-</span>
            </td>
            <td style="color:var(--text-2)">{{ n.lastSeen ?? (n.heartbeat === 'online' ? '会话内' : '-') }}</td>
            <td><span class="st" :class="n.heartbeat === 'online' ? 'st-green' : 'st-red'"><span class="dot" />{{ n.heartbeat === 'online' ? '在线' : n.heartbeat === 'offline' ? '离线' : '未知' }}</span></td>
            <td>
              <template v-if="n.module === 'ssh'">
                <button class="op-btn primary" @click="probe(n)">探活</button>
                <button v-if="auth.canEdit && sshRowOf(n.node)" class="op-btn" @click="openEdit(sshRowOf(n.node)!)">编辑</button>
                <button v-if="auth.canEdit" class="op-btn danger" @click="removeNode(n)">删除</button>
              </template>
              <span v-else style="color:var(--text-3);font-size:11px">自动注册</span>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="filtered.length === 0" class="empty">暂无注册节点（master/worker 启动后自动注册；SSH 节点经右上角按钮注册）</div>
    </div>

    <!-- 注册 / 编辑 SSH 节点抽屉（F53） -->
    <el-drawer v-model="formVisible" :title="editing ? '编辑 SSH 节点 - ' + editing.name : '注册 SSH 节点'" size="460px">
      <div class="form-tip">标签用于画布 SSH 脚本节点按「执行节点标签」路由：探活通过（online）且启用（enabled）的节点参与轮转；多个节点同标签时连接失败自动转派下一个。</div>
      <div class="form-grid">
        <label class="f-item">节点名称 *
          <input v-model="form.name" class="kw" style="width:100%" placeholder="如：etl-node-01" />
        </label>
        <label class="f-item">主机地址 *
          <input v-model="form.host" class="kw" style="width:100%" placeholder="如：192.168.1.9" />
        </label>
        <label class="f-item">SSH 端口 *
          <input v-model.number="form.port" type="number" class="kw" style="width:100%" />
        </label>
        <label class="f-item">SSH 用户 *
          <input v-model="form.sshUser" class="kw" style="width:100%" placeholder="如：root" />
        </label>
        <label class="f-item">凭证类型
          <select v-model="form.credKind" class="kw" style="width:100%">
            <option value="密码">密码</option>
            <option value="私钥">私钥（PEM 内容）</option>
          </select>
        </label>
        <label v-if="form.credKind === '密码'" class="f-item">密码
          <input v-model="form.cred" type="password" class="kw" style="width:100%" placeholder="留空=无认证" />
        </label>
        <label v-else class="f-item">私钥内容
          <textarea v-model="form.cred" rows="5" class="kw" style="width:100%;font-family:monospace" placeholder="-----BEGIN RSA PRIVATE KEY-----" />
        </label>
        <label class="f-item">执行节点标签（逗号分隔）
          <input v-model="form.tags" class="kw" style="width:100%" placeholder="如：etl,bigdata" />
        </label>
        <label class="f-item bool-row">
          <input v-model="form.enabled" type="checkbox" />
          <span>启用（停用后派发路由自动剔除）</span>
        </label>
      </div>
      <div style="margin-top:16px;display:flex;gap:8px">
        <button class="tb-new" @click="saveForm">保存</button>
        <button class="op-btn" @click="formVisible = false">取消</button>
      </div>
    </el-drawer>
    </div>
  </div>
</template>

<style scoped>
.page-head{display:flex;align-items:center;gap:10px;padding:14px 16px}
.ph-title{font-weight:700;font-size:15px}
.ph-desc{font-size:12px;color:var(--text-3);margin-top:2px;max-width:640px}
.spacer{flex:1}
.stat-grid4{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:12px}
.stat-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);box-shadow:var(--shadow);padding:14px 16px;display:flex;gap:10px;align-items:center}
.type-icon{width:34px;height:34px;border-radius:var(--radius);color:#fff;display:flex;align-items:center;justify-content:center;font-size:15px;flex-shrink:0}
.stat-num{font-size:22px;font-weight:700;line-height:1.2}
.stat-label{font-size:11.5px;color:var(--text-3)}
.card-title{font-weight:700;font-size:14px}
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;padding:9px 10px;background:var(--bg);color:var(--text-2);font-weight:600;border-bottom:1px solid var(--border)}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--border);vertical-align:top}
.tbl tr:hover td{background:var(--primary-light)}
.tbl-toolbar{display:flex;align-items:center;gap:10px;margin-bottom:12px}
.kw{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 10px;font-size:12.5px;width:190px;outline:none}
.kw:focus{border-color:var(--primary)}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease)}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
.op-btn.primary{color:var(--primary);border-color:rgba(22,104,220,.4);font-weight:600}
.op-btn.danger{color:var(--danger);border-color:rgba(229,72,77,.35)}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
/* 资源状态 mini 条 */
.res-row{display:flex;align-items:center;gap:5px;font-size:10.5px;color:var(--text-3)}
.res-bar{width:64px;height:6px;border-radius:3px;background:#eef1f6;overflow:hidden;flex:none}
.res-bar>div{height:100%;border-radius:3px}
.res-bar .good{background:var(--success)}
.res-bar .warn{background:var(--warn)}
.res-bar .bad{background:var(--danger)}
.res-row .mono{width:34px;text-align:right;color:var(--text-2)}
/* 表单 */
.form-tip{background:var(--info-bg);color:var(--info);border-radius:var(--radius-sm);padding:8px 10px;font-size:12px;margin-bottom:14px;line-height:1.6}
.form-grid{display:flex;flex-direction:column;gap:12px}
.f-item{display:flex;flex-direction:column;gap:5px;font-size:12.5px;color:var(--text-2)}
.bool-row{flex-direction:row;align-items:center;gap:8px}
</style>
