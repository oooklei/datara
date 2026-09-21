<script setup lang="ts">
/**
 * M16 部署中心（/dep/center · 原型 m16-deploy.js #/dep/center + #/dep/wizard）
 * 统计卡 / 部署套件 / 部署拓扑预览 / 组件清单 / 备份管理；
 * 顶部工具栏「一键部署向导」内嵌 6 步向导（deployWizardSteps）：
 * 选组件 → 选节点 → 填配置 → 前置检查（precheckItems）→ 安装执行 → 健康检查；
 * 完成后 dataStore.save('components') 持久化上线状态；手动备份写 dataStore.save('backups')。
 */
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { dataStore, ST } from '../../services/mock/dataStore'
import type { Server, Component, Suite, PrecheckItem, Backup } from '../../services/types'

const router = useRouter()

const servers = ref<Server[]>([])
const comps = ref<Component[]>([])
const suites = ref<Suite[]>([])
const backups = ref<Backup[]>([])
const steps = ref<string[]>([])
const prechecks = ref<PrecheckItem[]>([])

async function reload() {
  // 必须展开为新数组：dataStore.save 原地修改数组，list 返回同一引用，
  // 直接赋值不会触发 ref 更新。
  servers.value = [...((await dataStore.list<Server>('servers')) ?? [])]
  comps.value = [...((await dataStore.list<Component>('components')) ?? [])]
  suites.value = [...((await dataStore.list<Suite>('suites')) ?? [])]
  backups.value = [...((await dataStore.list<Backup>('backups')) ?? [])]
  steps.value = [...((await dataStore.list<string>('deployWizardSteps')) ?? [])]
  prechecks.value = [...((await dataStore.list<PrecheckItem>('precheckItems')) ?? [])]
}
onMounted(reload)

/* ---- 延时任务统一管理（页面卸载/向导关闭时清理，避免悬挂定时器） ---- */
let timers: number[] = []
function later(fn: () => void, ms: number): void {
  timers.push(window.setTimeout(fn, ms))
}
function clearTimers(): void {
  for (const t of timers) window.clearTimeout(t)
  timers = []
}
onUnmounted(clearTimers)

/* ---- 统计 ---- */
const onlineSv = computed(() => servers.value.filter((s) => s.status === 'online'))
const runComps = computed(() => comps.value.filter((c) => c.status === 'running'))
const depSuites = computed(() => suites.value.filter((s) => s.status === 'deployed'))

/* ---- 组件清单筛选 ---- */
const cpKw = ref('')
const cpStatus = ref('')
const cpFiltered = computed(() => {
  const kw = cpKw.value.trim().toLowerCase()
  return comps.value.filter((r) => {
    if (cpStatus.value && r.status !== cpStatus.value) return false
    if (!kw) return true
    return [r.id, r.name, r.role].some((s) => s.toLowerCase().includes(kw))
  })
})

/* ---- 备份筛选 ---- */
const bkKw = ref('')
const bkFiltered = computed(() => {
  const kw = bkKw.value.trim().toLowerCase()
  if (!kw) return backups.value
  return backups.value.filter((r) => [r.id, r.target].some((s) => s.toLowerCase().includes(kw)))
})

function stCls(s: string): string {
  return ST[s]?.cls ?? 'st-gray'
}
function stLabel(s: string): string {
  return ST[s]?.label ?? s
}
function today(): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

/* ---- 套件 / 拓扑预览 ---- */
function nodeIp(n: string): string {
  return n.split('(')[0] ?? n
}
function suiteAction(s: Suite): void {
  if (s.status === 'deployed') ElMessage.info('套件已部署，可在集群监控中查看组件健康')
  else openWizard()
}
function locateNode(ip: string): void {
  const sv = servers.value.find((x) => x.ip === ip)
  ElMessage.info(`已定位 ${sv ? sv.name : ip}（${ip}），正在打开集群监控...`)
  router.push('/dep/monitor')
}
function goMonitor(): void {
  router.push('/dep/monitor')
}

/* ---- 组件操作 ---- */
function configComp(c: Component): void {
  ElMessage.info(`配置管理：修改 ${c.name} 参数（原型演示）`)
}
async function restartComp(c: Component): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确认重启 ${c.name}？重启期间依赖该组件的任务可能短暂失败，建议在业务低峰执行。`,
      '重启组件',
      { confirmButtonText: '确认重启', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  ElMessage.info(`正在滚动重启 ${c.name} ...`)
  later(() => ElMessage.success(`${c.name} 重启完成，健康检查通过`), 1500)
}

/* ---- 备份 ---- */
async function backupNow(): Promise<void> {
  ElMessage.info('正在执行手动备份（平台配置库）...')
  later(async () => {
    const seq =
      backups.value.reduce((m, b) => {
        const n = Number(String(b.id).replace(/^\D+/, ''))
        return Number.isFinite(n) && n > m ? n : m
      }, 0) + 1
    const row: Backup = {
      id: 'BK' + String(seq).padStart(2, '0'),
      target: '平台配置库（手动）',
      time: `${today()} 23:35`,
      size: '860MB',
      type: '手动',
      status: 'success',
    }
    await dataStore.save<Backup>('backups', row)
    ElMessage.success(`备份完成：860MB 已存至 /backup/${today()}`)
    await reload()
  }, 1200)
}
function backupPolicy(): void {
  ElMessage.info('备份策略：每日 03:00 全量，保留 30 天')
}
function downloadBackup(b: Backup): void {
  ElMessage.success(`备份下载：${b.target}（${b.size}）已开始`)
}

/* ================= 一键部署向导（内嵌 6 步） ================= */
const wizVisible = ref(false)
const step = ref(0)
const pickComp = ref('')
const pickNodes = ref<string[]>([])
const cfg = ref({ dir: '/opt/datara', data: '/data/dep', jdk: '/usr/lib/jdk1.8', port: '9092', auto: true, health: true })
const pcRows = ref<Array<{ item: string; detail: string; st: 'run' | 'ok' | 'warn' }>>([])
const inRows = ref<Array<{ name: string; ip: string; st: 'run' | 'ok' }>>([])
const pcDone = ref(false)
const inDone = ref(false)

const wizComps = computed(() => comps.value.filter((c) => c.status === 'undeploy'))
const wizComp = computed(() => comps.value.find((c) => c.id === pickComp.value) ?? null)
const wizNodes = computed(() =>
  pickNodes.value
    .map((nid) => servers.value.find((s) => s.id === nid))
    .filter((s): s is Server => !!s),
)

watch(wizVisible, (v) => {
  if (!v) clearTimers()
})

function openWizard(): void {
  step.value = 0
  pickComp.value = ''
  pickNodes.value = []
  cfg.value = { dir: '/opt/datara', data: '/data/dep', jdk: '/usr/lib/jdk1.8', port: '9092', auto: true, health: true }
  pcRows.value = []
  inRows.value = []
  pcDone.value = false
  inDone.value = false
  wizVisible.value = true
}

function goStep(s: number): void {
  step.value = s
  if (s === 3) startPrecheck()
  if (s === 4) startInstall()
}
function next(): void {
  if (step.value === 0) {
    if (!pickComp.value) {
      ElMessage.warning('请选择要部署的组件')
      return
    }
    goStep(1)
  } else if (step.value === 1) {
    if (!pickNodes.value.length) {
      ElMessage.warning('请至少选择 1 个在线节点')
      return
    }
    goStep(2)
  } else if (step.value === 2) {
    if (!cfg.value.dir.trim()) {
      ElMessage.warning('请填写安装目录')
      return
    }
    goStep(3)
  }
}
function startPrecheck(): void {
  pcRows.value = prechecks.value.map((it) => ({ item: it.item, detail: it.detail, st: 'run' as const }))
  pcDone.value = false
  prechecks.value.forEach((it, i) => {
    later(() => {
      const row = pcRows.value[i]
      if (row) row.st = it.result === 'pass' ? 'ok' : 'warn'
      if (i === prechecks.value.length - 1) pcDone.value = true
    }, 550 * (i + 1))
  })
}
function startInstall(): void {
  inRows.value = wizNodes.value.map((s) => ({ name: s.name, ip: s.ip, st: 'run' as const }))
  inDone.value = false
  inRows.value.forEach((row, i) => {
    later(() => {
      row.st = 'ok'
      if (i === inRows.value.length - 1) inDone.value = true
    }, 800 * (i + 1))
  })
}
async function finishDeploy(): Promise<void> {
  const c = wizComp.value
  if (!c) return
  const ips = wizNodes.value.map((s) => s.ip)
  await dataStore.save<Component>('components', {
    ...c,
    status: 'running',
    health: '健康',
    upDays: 1,
    cpu: 12 + Math.floor(Math.random() * 30),
    mem: 25 + Math.floor(Math.random() * 30),
    nodes: ips,
  })
  ElMessage.success(`${c.name} 部署完成并已上线`)
  wizVisible.value = false
  await reload()
}
function goMonitorFromWiz(): void {
  wizVisible.value = false
  router.push('/dep/monitor')
}
</script>

<template>
  <div class="page">
    <!-- 页头 + 顶部工具栏 -->
    <div class="page-head">
      <div>
        <div class="ph-title">一键部署中心</div>
        <div class="ph-desc">信创环境（麒麟V10/鲲鹏920/万里数据库）一键部署：套件编排 → 前置检查 → 安装执行 → 健康检查；支持备份与回滚</div>
      </div>
      <div class="ph-btns">
        <button class="tb-new" @click="openWizard">⚙ 一键部署向导</button>
      </div>
    </div>

    <!-- 统计卡 -->
    <div class="stat-grid4">
      <div class="stat-card">
        <span class="type-icon" style="background:#475569">⛅</span>
        <div><div class="stat-num">{{ onlineSv.length }}/{{ servers.length }}</div><div class="stat-label">节点在线</div></div>
      </div>
      <div class="stat-card">
        <span class="type-icon" style="background:var(--success)">✓</span>
        <div><div class="stat-num">{{ runComps.length }}</div><div class="stat-label">组件运行中</div></div>
      </div>
      <div class="stat-card">
        <span class="type-icon" style="background:#1668dc">📋</span>
        <div><div class="stat-num">{{ depSuites.length }}/{{ suites.length }}</div><div class="stat-label">套件已部署</div></div>
      </div>
      <div class="stat-card">
        <span class="type-icon" style="background:#d97706">⇩</span>
        <div><div class="stat-num">{{ backups.length }}</div><div class="stat-label">备份任务（全部成功）</div></div>
      </div>
    </div>

    <!-- 部署套件 -->
    <div class="card sec">
      <div class="sec-title">部署套件</div>
      <div class="grid2">
        <div v-for="s in suites" :key="s.id" class="suite-card">
          <span class="type-icon" :style="{ background: s.status === 'deployed' ? 'var(--success)' : '#8c94a6' }">{{ s.status === 'deployed' ? '✓' : '⊕' }}</span>
          <div style="flex:1">
            <b>{{ s.name }}</b>
            <div class="suite-desc">{{ s.comps }} · {{ s.desc }}</div>
            <div class="suite-foot">
              <span class="pill" :class="s.status === 'deployed' ? 'ok' : 'off'">{{ s.status === 'deployed' ? '已部署' : '未部署' }}</span>
              <button class="op-btn" @click="suiteAction(s)">{{ s.status === 'deployed' ? '查看' : '部署' }}</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 部署拓扑预览 -->
    <div class="card sec">
      <div class="sec-title">部署拓扑预览</div>
      <div class="sec-hint">已部署组件在集群节点上的分布全景；点击节点卡可跳转集群监控定位。</div>
      <div class="grid2">
        <div v-for="c in runComps" :key="c.id" class="topo-card">
          <div class="topo-head">
            <span class="type-icon sm" style="background:#0891b2">{{ c.name.slice(0, 2).toUpperCase() }}</span>
            <b class="topo-name">{{ c.name }}</b>
            <span class="topo-meta">v{{ c.version }} · {{ c.role }}</span>
            <span class="pill" :class="c.health === '健康' ? 'ok' : 'warn'" style="margin-left:auto">{{ c.health }}</span>
          </div>
          <div>
            <span v-for="n in c.nodes" :key="n" class="mono node-chip" @click="locateNode(nodeIp(n))">{{ n }}</span>
          </div>
        </div>
      </div>
      <div v-if="runComps.length === 0" class="empty">暂无运行中组件，请先执行部署</div>
    </div>

    <!-- 组件清单 -->
    <div class="card sec">
      <div class="tbl-toolbar">
        <span class="sec-title" style="margin:0">组件清单</span>
        <span class="pill info">{{ cpFiltered.length }} / {{ comps.length }}</span>
        <span class="spacer" />
        <input v-model="cpKw" class="kw" placeholder="搜索组件" />
        <select v-model="cpStatus" class="sel">
          <option value="">状态：全部</option>
          <option value="running">运行中</option>
          <option value="undeploy">未部署</option>
        </select>
      </div>
      <table class="tbl">
        <thead>
          <tr>
            <th>组件</th><th>角色</th><th>节点</th><th>CPU/内存</th><th>健康</th><th>运行天数</th><th style="width:180px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in cpFiltered" :key="r.id">
            <td>
              <b>{{ r.name }}</b>
              <div class="cell-sub">{{ r.id }} · {{ r.version !== '-' ? 'v' + r.version : '未安装' }}</div>
            </td>
            <td>{{ r.role }}</td>
            <td class="mono" style="font-size:11.5px">{{ r.nodes.length ? r.nodes.join('，') : '-' }}</td>
            <td>{{ r.status === 'running' ? `${r.cpu}% / ${r.mem}%` : '-' }}</td>
            <td>
              <span v-if="r.status === 'running'" class="pill" :class="r.health === '健康' ? 'ok' : 'warn'">{{ r.health }}</span>
              <span v-else class="pill off">未部署</span>
            </td>
            <td>{{ r.upDays ? `${r.upDays} 天` : '-' }}</td>
            <td>
              <button v-if="r.status === 'undeploy'" class="op-btn primary" @click="openWizard">部署</button>
              <template v-else>
                <button class="op-btn primary" @click="goMonitor">监控</button>
                <button class="op-btn" @click="configComp(r)">配置</button>
                <button class="op-btn danger" @click="restartComp(r)">重启</button>
              </template>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="cpFiltered.length === 0" class="empty">未找到匹配的组件，请调整筛选条件</div>
    </div>

    <!-- 备份管理 -->
    <div class="card sec">
      <div class="tbl-toolbar">
        <span class="sec-title" style="margin:0">备份管理</span>
        <span class="pill info">{{ bkFiltered.length }} / {{ backups.length }}</span>
        <span class="spacer" />
        <button class="op-btn" style="margin-right:6px" @click="backupNow">立即备份</button>
        <button class="op-btn" style="margin-right:8px" @click="backupPolicy">备份策略</button>
        <input v-model="bkKw" class="kw" placeholder="搜索备份对象" />
      </div>
      <table class="tbl">
        <thead>
          <tr>
            <th>备份对象</th><th>时间</th><th>大小</th><th>方式</th><th>结果</th><th style="width:80px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in bkFiltered" :key="r.id">
            <td>
              <b>{{ r.target }}</b>
              <div class="cell-sub mono">{{ r.id }}</div>
            </td>
            <td style="color:var(--text-2)">{{ r.time }}</td>
            <td>{{ r.size }}</td>
            <td>{{ r.type }}</td>
            <td><span class="st" :class="stCls(r.status)"><span class="dot" />{{ stLabel(r.status) }}</span></td>
            <td><button class="op-btn" @click="downloadBackup(r)">下载</button></td>
          </tr>
        </tbody>
      </table>
      <div v-if="bkFiltered.length === 0" class="empty">暂无备份记录，点击「立即备份」手动触发</div>
    </div>

    <!-- 一键部署向导（6 步） -->
    <el-dialog v-model="wizVisible" title="一键部署向导" width="780px" :close-on-click-modal="false">
      <div class="wiz-steps">
        <template v-for="(s, i) in steps" :key="s">
          <div class="ws" :class="{ on: i === step, done: i < step }">
            <span class="ws-dot">{{ i < step ? '✓' : i + 1 }}</span>
            <span class="ws-label">{{ s }}</span>
          </div>
          <div v-if="i < steps.length - 1" class="ws-line" :class="{ on: i < step }" />
        </template>
      </div>

      <!-- 步骤 0：选择组件 -->
      <div v-if="step === 0">
        <div class="banner info"><span class="b-ico">ℹ</span><span>以下为未部署组件；已部署组件可在集群监控中管理。</span></div>
        <div class="grid2">
          <div v-for="c in wizComps" :key="c.id" class="pick-card" :class="{ on: pickComp === c.id }" @click="pickComp = c.id">
            <span class="type-icon sm" style="background:#0891b2">{{ c.name.slice(0, 2).toUpperCase() }}</span>
            <div>
              <b>{{ c.name }}</b>
              <div class="pick-sub">{{ c.role }}（{{ c.version !== '-' ? 'v' + c.version : '待定版本' }}）</div>
            </div>
          </div>
        </div>
        <div v-if="wizComps.length === 0" class="empty">所有组件均已部署，无需安装</div>
        <div class="wiz-foot right">
          <button class="tb-new" :disabled="wizComps.length === 0" @click="next">下一步 →</button>
        </div>
      </div>

      <!-- 步骤 1：选择节点 -->
      <div v-if="step === 1">
        <div style="background:var(--info-bg);color:var(--info);border-radius:var(--radius-sm);padding:8px 10px;font-size:12px;margin-bottom:10px;line-height:1.6">
          SSH 连通性前置检查依据「运行时节点」页的 SSH 配置（主机/端口/用户/密钥，唯一权威源）执行探测；
          如需新增或调整 SSH 主机信息，请前往 <a style="cursor:pointer;text-decoration:underline" @click="router.push('/dep/runtime')">运行时节点</a>。
        </div>
        <label v-for="sv in servers" :key="sv.id" class="node-row" :class="{ off: sv.status !== 'online' }">
          <input type="checkbox" :value="sv.id" v-model="pickNodes" :disabled="sv.status !== 'online'" />
          <span class="node-name"><b>{{ sv.name }}</b>（{{ sv.ip }}）</span>
          <span class="node-spec">{{ sv.cpu }}/{{ sv.mem }}/{{ sv.disk }} · {{ sv.os }} · {{ sv.role }}</span>
          <span class="st" :class="sv.status === 'online' ? 'st-green' : 'st-gray'" style="margin-left:auto">
            <span class="dot" />{{ sv.status === 'online' ? '在线' : '离线' }}
          </span>
        </label>
        <div class="wiz-foot">
          <button class="op-btn" @click="goStep(0)">← 上一步</button>
          <button class="tb-new" @click="next">下一步 →</button>
        </div>
      </div>

      <!-- 步骤 2：填写配置 -->
      <div v-if="step === 2">
        <div class="f-grid">
          <label class="f-item">安装目录 *<input v-model="cfg.dir" /></label>
          <label class="f-item">数据目录 *<input v-model="cfg.data" /></label>
          <label class="f-item">JDK 路径<input v-model="cfg.jdk" /></label>
          <label class="f-item">组件端口<input v-model="cfg.port" /></label>
          <label class="f-item switch"><input type="checkbox" v-model="cfg.auto" />自动启动与开机自启</label>
          <label class="f-item switch"><input type="checkbox" v-model="cfg.health" />部署后自动执行健康检查</label>
        </div>
        <div class="lock-tip">配置将渲染为各组件 yaml/conf 并分发至所选节点；信创环境自动匹配 aarch64 二进制包。</div>
        <div class="wiz-foot">
          <button class="op-btn" @click="goStep(1)">← 上一步</button>
          <button class="tb-new" @click="next">前置检查 →</button>
        </div>
      </div>

      <!-- 步骤 3：前置检查 -->
      <div v-if="step === 3">
        <div v-for="p in pcRows" :key="p.item" class="checker" :class="p.st">
          <span>{{ p.st === 'run' ? '◌' : p.st === 'ok' ? '✓' : '⚠' }}</span>
          <b>{{ p.item }}</b>
          <span class="ck-detail">{{ p.st === 'run' ? '检查中...' : p.detail }}</span>
        </div>
        <div class="wiz-foot">
          <button class="op-btn" @click="goStep(2)">← 上一步</button>
          <button class="tb-new" :disabled="!pcDone" @click="goStep(4)">开始安装 →</button>
        </div>
      </div>

      <!-- 步骤 4：安装执行 -->
      <div v-if="step === 4">
        <div class="banner info">
          <span class="b-ico">ℹ</span>
          <span>正在向 {{ inRows.length }} 个节点分发并安装 {{ wizComp?.name ?? '' }}（滚动安装，节点逐台执行）...</span>
        </div>
        <div v-for="r in inRows" :key="r.ip" class="checker" :class="r.st">
          <span>{{ r.st === 'ok' ? '✓' : '◌' }}</span>
          <b>{{ r.name }}（{{ r.ip }}）</b>
          <span class="ck-detail">{{ r.st === 'ok' ? '安装完成 · 服务启动成功' : '排队中...' }}</span>
        </div>
        <div class="wiz-foot right">
          <button v-if="inDone" class="tb-new" @click="goStep(5)">健康检查 →</button>
        </div>
      </div>

      <!-- 步骤 5：健康检查 -->
      <div v-if="step === 5">
        <div class="banner ok"><span class="b-ico">✓</span><span>部署完成！组件已上线并纳入监控，健康检查全部通过。</span></div>
        <div class="checker ok"><span>✓</span><b>服务端口监听</b><span class="ck-detail">正常</span></div>
        <div class="checker ok"><span>✓</span><b>集群元数据注册</b><span class="ck-detail">正常</span></div>
        <div class="checker ok"><span>✓</span><b>样例读写测试</b><span class="ck-detail">通过</span></div>
        <div class="wiz-foot">
          <button class="tb-new" @click="finishDeploy">完成并返回部署中心</button>
          <button class="op-btn" @click="goMonitorFromWiz">前往集群监控</button>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
/* ---- 页头 / 统计 ---- */
.page-head{display:flex;align-items:flex-start;gap:16px;margin-bottom:14px}
.ph-title{font-size:17px;font-weight:700}
.ph-desc{font-size:12px;color:var(--text-3);margin-top:3px}
.ph-btns{margin-left:auto;display:flex;gap:8px;flex-shrink:0}
.stat-grid4{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:14px}
.stat-card{display:flex;align-items:center;gap:12px;background:var(--card);border:1px solid var(--border);border-radius:var(--radius-lg);padding:13px 15px}
.type-icon{width:36px;height:36px;border-radius:9px;display:flex;align-items:center;justify-content:center;color:#fff;font-size:14px;flex-shrink:0}
.type-icon.sm{width:28px;height:28px;font-size:10px;border-radius:7px}
.stat-num{font-size:19px;font-weight:700;line-height:1.25}
.stat-label{font-size:11.5px;color:var(--text-3)}
/* ---- 区块卡片 ---- */
.sec{padding:16px;margin-bottom:14px}
.sec-title{font-weight:700;font-size:13.5px;margin-bottom:10px}
.sec-hint{font-size:11.5px;color:var(--text-3);margin:-4px 0 10px}
.grid2{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}
.suite-card{display:flex;align-items:flex-start;gap:12px;border:1px solid var(--border);border-radius:9px;padding:12px 14px}
.suite-desc{font-size:11.5px;color:var(--text-3);margin:4px 0 8px}
.suite-foot{display:flex;gap:8px;align-items:center}
.topo-card{border:1px solid var(--border);border-radius:9px;padding:11px 12px}
.topo-head{display:flex;align-items:center;gap:8px;margin-bottom:9px}
.topo-name{font-size:12.5px}
.topo-meta{font-size:11px;color:var(--text-3)}
.node-chip{display:inline-block;padding:3px 9px;margin:0 6px 6px 0;border:1px solid var(--border);border-radius:var(--radius-sm);font-size:11px;background:#f8fafc;cursor:pointer}
.node-chip:hover{border-color:var(--primary);color:var(--primary)}
/* ---- 表格 / 工具栏 ---- */
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;padding:9px 10px;background:var(--bg);color:var(--text-2);font-weight:600;border-bottom:1px solid var(--border)}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--border)}
.tbl tr:hover td{background:var(--primary-light)}
.cell-sub{font-size:11px;color:var(--text-3)}
.kw{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 10px;font-size:12.5px;width:180px;outline:none}
.kw:focus{border-color:var(--primary)}
.sel{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 8px;font-size:12.5px;background:#fff;outline:none;color:var(--text-2)}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease)}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
.tb-new:disabled{opacity:.5;cursor:not-allowed}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
.op-btn.primary{color:var(--primary);border-color:rgba(22,104,220,.4);font-weight:600}
.op-btn.danger{color:var(--danger);border-color:rgba(229,72,77,.35)}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
/* ---- 向导 ---- */
.wiz-steps{display:flex;align-items:center;margin-bottom:16px}
.ws{display:flex;align-items:center;gap:6px;flex-shrink:0}
.ws-dot{width:22px;height:22px;border-radius:50%;border:1.5px solid var(--border-strong);color:var(--text-3);font-size:11px;display:flex;align-items:center;justify-content:center;background:#fff}
.ws-label{font-size:12px;color:var(--text-3);white-space:nowrap}
.ws.on .ws-dot{border-color:var(--primary);background:var(--primary);color:#fff}
.ws.on .ws-label{color:var(--primary);font-weight:600}
.ws.done .ws-dot{border-color:var(--success);background:var(--success);color:#fff}
.ws.done .ws-label{color:var(--success)}
.ws-line{flex:1;height:1.5px;background:var(--border);margin:0 8px}
.ws-line.on{background:var(--success)}
.wiz-foot{display:flex;justify-content:space-between;margin-top:16px}
.wiz-foot.right{justify-content:flex-end}
.banner{display:flex;gap:8px;align-items:flex-start;border-radius:var(--radius);padding:9px 12px;font-size:12.5px;margin-bottom:12px}
.banner.info{background:var(--info-bg);color:var(--info)}
.banner.ok{background:var(--success-bg);color:var(--success)}
.b-ico{font-weight:700}
.pick-card{display:flex;align-items:center;gap:11px;border:1px solid var(--border);border-radius:9px;padding:11px 13px;cursor:pointer}
.pick-card:hover{border-color:var(--primary)}
.pick-card.on{border-color:var(--primary);box-shadow:0 0 0 2px var(--primary-light)}
.pick-sub{font-size:11px;color:var(--text-3)}
.node-row{display:flex;gap:9px;align-items:center;padding:10px 12px;border:1px solid var(--border);border-radius:var(--radius);margin-bottom:8px;cursor:pointer}
.node-row.off{opacity:.65;cursor:not-allowed}
.node-name{font-size:12.5px;white-space:nowrap}
.node-spec{font-size:11px;color:var(--text-3)}
.f-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;max-width:680px}
.f-item{display:flex;flex-direction:column;gap:5px;font-size:12.5px;color:var(--text-2)}
.f-item input[type='text'],.f-item input:not([type]){border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 9px;font-size:12.5px;outline:none}
.f-item input:focus{border-color:var(--primary)}
.f-item.switch{flex-direction:row;align-items:center;gap:7px;cursor:pointer}
.lock-tip{font-size:11.5px;color:var(--text-2);background:var(--bg);border-radius:7px;padding:8px 11px;margin-top:12px;max-width:680px}
.checker{display:flex;gap:9px;align-items:center;padding:8px 11px;border:1px solid var(--border);border-radius:var(--radius);margin-bottom:7px;font-size:12.5px}
.checker.run{color:var(--text-2)}
.checker.ok{border-color:rgba(22,163,74,.35);background:var(--success-bg)}
.checker.ok>span:first-child{color:var(--success);font-weight:700}
.checker.warn{border-color:rgba(217,119,6,.35);background:var(--warn-bg)}
.checker.warn>span:first-child{color:var(--warn);font-weight:700}
.ck-detail{margin-left:auto;font-size:11.5px;color:var(--text-3);text-align:right}
</style>
