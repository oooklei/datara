<script setup lang="ts">
/**
 * M16 运维操作（/dep/ops · 原型 m16-deploy.js #/dep/ops）
 * 高频运维动作卡片：滚动重启 / NTP 校准 / 磁盘清理 / 配置下发 / 健康巡检 / 立即备份；
 * 磁盘清理联动闭合 PA01 告警、立即备份写 dataStore.save('backups')；
 * 备份记录表（dataStore.backups）+ 最近运维记录时间线；操作留痕经 ElMessage 反馈。
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { dataStore, ST } from '../../services/mock/dataStore'
import { useAuthStore } from '../../stores/auth'
import type { Component, Backup, DeployAlarm, DeployLog } from '../../services/types'

const auth = useAuthStore()

const backups = ref<Backup[]>([])
const comps = ref<Component[]>([])
const alarms = ref<DeployAlarm[]>([])
const logs = ref<DeployLog[]>([])

const runningComps = computed(() => comps.value.filter((c) => c.status === 'running'))

async function reload() {
  // 必须展开为新数组：dataStore.save 原地修改数组，list 返回同一引用
  backups.value = [...((await dataStore.list<Backup>('backups')) ?? [])]
  comps.value = [...((await dataStore.list<Component>('components')) ?? [])]
  alarms.value = [...((await dataStore.list<DeployAlarm>('deployAlarms')) ?? [])]
  logs.value = [...((await dataStore.list<DeployLog>('deployLogs')) ?? [])]
}
onMounted(reload)

/* ---- 延时任务统一管理（页面卸载时清理，避免悬挂定时器） ---- */
let timers: number[] = []
function later(fn: () => void, ms: number): void {
  timers.push(window.setTimeout(fn, ms))
}
onUnmounted(() => {
  for (const t of timers) window.clearTimeout(t)
  timers = []
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

/* ---- 运维操作卡片 ---- */
interface OpDef {
  t: string
  d: string
  ico: string
  c: string
  fn: () => void
}
const OPS: OpDef[] = [
  { t: '滚动重启组件', d: '按节点逐台重启，避免服务中断', ico: '↻', c: '#d97706', fn: () => openRestart() },
  { t: 'NTP 时钟校准', d: '修复 node-03 时钟偏差 4.2s', ico: '⏱', c: '#1668dc', fn: opNtp },
  { t: '磁盘清理', d: '清理 BE 临时文件与旧日志（node-03 82%）', ico: '🗑', c: '#e5484d', fn: opDisk },
  { t: '配置下发', d: '修改组件参数并滚动生效', ico: '⚙', c: '#7c3aed', fn: openConfig },
  { t: '健康巡检', d: '全组件健康检查（端口/进程/读写）', ico: '✓', c: '#16a34a', fn: opCheck },
  { t: '备份立即执行', d: '手动触发配置库全量备份', ico: '⇩', c: '#0891b2', fn: backupNow },
]

/* ---- 滚动重启 ---- */
const rstVisible = ref(false)
const rstComp = ref('')
function openRestart(): void {
  if (!runningComps.value.length) {
    ElMessage.warning('暂无运行中组件')
    return
  }
  rstComp.value = runningComps.value[0]?.name ?? ''
  rstVisible.value = true
}
function goRestart(): void {
  const name = rstComp.value
  if (!name) {
    ElMessage.warning('请选择组件')
    return
  }
  const c = runningComps.value.find((x) => x.name === name)
  rstVisible.value = false
  ElMessage.info(`开始滚动重启 ${name}（${c ? c.nodes.length : 0} 节点）...`)
  later(() => ElMessage.success(`${name} 滚动重启完成，健康检查通过`), 1600)
}

/* ---- NTP 校准 ---- */
function opNtp(): void {
  ElMessage.info('正在对 node-03 执行 NTP 校准（chronyc makestep）...')
  later(() => ElMessage.success('校准完成：偏差 4.2s → 0.003s'), 1200)
}

/* ---- 磁盘清理（联动闭合 PA01 告警） ---- */
async function opDisk(): Promise<void> {
  try {
    await ElMessageBox.confirm('清理 BE 临时文件与 7 天前日志？预计释放 60GB（node-03），不影响业务数据。', '磁盘清理', {
      confirmButtonText: '确认清理', cancelButtonText: '取消', type: 'warning',
    })
  } catch {
    return
  }
  ElMessage.info('正在清理 BE 临时文件与旧日志...')
  later(async () => {
    const a = alarms.value.find((x) => x.id === 'PA01')
    if (a && a.status === 'pending') {
      await dataStore.save<DeployAlarm>('deployAlarms', { ...a, status: 'fixed' })
      await reload()
    }
    ElMessage.success('清理完成：磁盘使用率 82% → 61%')
  }, 1300)
}

/* ---- 配置下发 ---- */
const cfgVisible = ref(false)
const cfgComp = ref('')
const cfgBody = ref('')
const cfgRoll = ref(true)
function openConfig(): void {
  if (!runningComps.value.length) {
    ElMessage.warning('暂无运行中组件')
    return
  }
  cfgComp.value = runningComps.value[0]?.name ?? ''
  cfgBody.value = ''
  cfgRoll.value = true
  cfgVisible.value = true
}
function goConfig(): void {
  if (!cfgBody.value.trim()) {
    ElMessage.warning('请填写配置片段')
    return
  }
  cfgVisible.value = false
  ElMessage.success(`配置已下发至 ${cfgComp.value} 并${cfgRoll.value ? '滚动生效' : '生效'}`)
}

/* ---- 健康巡检 ---- */
const chkVisible = ref(false)
const chkNames = ref<string[]>([])
function opCheck(): void {
  ElMessage.info('正在执行全组件健康巡检...')
  later(() => {
    chkNames.value = runningComps.value.map((c) => c.name)
    chkVisible.value = true
  }, 1200)
}

/* ---- 立即备份（持久化 backups） ---- */
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

/* ---- 操作审计 ---- */
function exportAudit(): void {
  ElMessage.success(`操作审计已导出（近7日 ${12 + logs.value.length} 条）`)
}

/* ---- 备份下载 ---- */
function downloadBackup(b: Backup): void {
  ElMessage.success(`备份下载：${b.target}（${b.size}）已开始`)
}

/* ---- 最近运维记录（静态样例，对齐原型 UI.timeline） ---- */
const RECORDS = [
  { cls: 'ok', title: 'Kafka 分区再均衡完成', time: '2026-09-12 21:40', body: 'topic_order_pay 6 分区，由 王工 执行' },
  { cls: 'warn', title: 'Doris tablet 副本自动修复', time: '2026-09-12 21:38', body: 'tablet 10230 副本恢复健康（自愈）' },
  { cls: 'err', title: 'Doris FE 心跳超时（自恢复）', time: '2026-09-12 21:30', body: 'BE 10002 心跳超时重试成功，建议观察' },
  { cls: 'ok', title: 'Flink Checkpoint 恢复正常', time: '2026-09-12 17:45', body: 'SJ002 扩并行度 4→8 后 checkpoint 42s→8s' },
]
</script>

<template>
  <div class="page">
    <!-- 页头 + 顶部工具栏 -->
    <div class="page-head">
      <div>
        <div class="ph-title">运维操作</div>
        <div class="ph-desc">高频运维动作：组件重启 / NTP校准 / 磁盘清理 / 配置下发，操作留痕审计</div>
      </div>
      <div class="ph-btns">
        <button class="tb-new" @click="exportAudit">操作审计</button>
      </div>
    </div>

    <!-- 运维动作卡片 -->
    <div class="ops-grid">
      <div
        v-for="o in OPS" :key="o.t" class="op-card"
        :class="{ locked: !auth.can('deploy:ops') }"
        :title="auth.can('deploy:ops') ? '' : '当前角色无部署运维权限'"
        @click="auth.can('deploy:ops') ? o.fn() : undefined"
      >
        <span class="type-icon" :style="{ background: o.c }">{{ o.ico }}</span>
        <div>
          <b class="op-title">{{ o.t }}</b>
          <div class="op-desc">{{ o.d }}</div>
        </div>
      </div>
    </div>

    <!-- 备份记录 -->
    <div class="card" style="padding:16px;margin-bottom:14px">
      <div class="tbl-toolbar">
        <span class="sec-head">备份记录</span>
        <span class="pill info">{{ backups.length }} 条</span>
        <span class="spacer" />
        <button class="op-btn" @click="backupNow">立即备份</button>
      </div>
      <table class="tbl">
        <thead>
          <tr>
            <th>备份对象</th><th>时间</th><th>大小</th><th>方式</th><th>结果</th><th style="width:80px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in backups" :key="r.id">
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
      <div v-if="backups.length === 0" class="empty">暂无备份记录，点击「立即备份」手动触发</div>
    </div>

    <!-- 最近运维记录 -->
    <div class="card" style="padding:16px">
      <div style="font-weight:700;font-size:14px;margin-bottom:12px">最近运维记录</div>
      <div v-for="r in RECORDS" :key="r.title" class="tl-line" :class="r.cls">
        <span class="tl-dot" />
        <div style="flex:1">
          <b class="tl-title">{{ r.title }}</b>
          <div class="cell-sub">{{ r.body }}</div>
        </div>
        <span class="mono cell-sub">{{ r.time }}</span>
      </div>
    </div>

    <!-- 滚动重启抽屉 -->
    <el-drawer v-model="rstVisible" title="滚动重启组件" size="400px">
      <div class="f-cap">组件</div>
      <select v-model="rstComp" class="sel" style="width:100%">
        <option v-for="c in runningComps" :key="c.id" :value="c.name">{{ c.name }}</option>
      </select>
      <div class="lock-tip">滚动策略：逐节点重启，节点健康检查通过后再继续下一台。</div>
      <div style="margin-top:16px;display:flex;gap:8px">
        <button class="op-btn danger" @click="goRestart">确认重启</button>
        <button class="op-btn" @click="rstVisible = false">取消</button>
      </div>
    </el-drawer>

    <!-- 配置下发抽屉 -->
    <el-drawer v-model="cfgVisible" title="配置下发" size="420px">
      <div class="f-cap">组件</div>
      <select v-model="cfgComp" class="sel" style="width:100%;margin-bottom:12px">
        <option v-for="c in runningComps" :key="c.id" :value="c.name">{{ c.name }}</option>
      </select>
      <div class="f-cap">配置片段</div>
      <textarea v-model="cfgBody" class="note mono" rows="5" placeholder="如：be.conf&#10;mem_limit = 80%" />
      <label class="radio-line" style="margin-top:12px">
        <input type="checkbox" v-model="cfgRoll" />
        <span>滚动生效（逐节点重启）</span>
      </label>
      <div style="margin-top:16px;display:flex;gap:8px">
        <button class="tb-new" @click="goConfig">确认下发</button>
        <button class="op-btn" @click="cfgVisible = false">取消</button>
      </div>
    </el-drawer>

    <!-- 健康巡检结果弹窗 -->
    <el-dialog v-model="chkVisible" title="健康巡检结果" width="420px">
      <div v-for="n in chkNames" :key="n" class="chk-line">
        <span class="chk-ok">✓</span>
        <b>{{ n }}</b>
        <span class="cell-sub" style="margin-left:auto">端口/进程/读写 正常</span>
      </div>
      <div v-if="chkNames.length === 0" class="empty">暂无运行中组件</div>
      <template #footer>
        <button class="tb-new" @click="chkVisible = false">关闭</button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
/* ---- 页头 ---- */
.page-head{display:flex;align-items:flex-start;gap:16px;margin-bottom:14px}
.ph-title{font-size:17px;font-weight:700}
.ph-desc{font-size:12px;color:var(--text-3);margin-top:3px}
.ph-btns{margin-left:auto;display:flex;gap:8px;flex-shrink:0}
/* ---- 运维卡片 ---- */
.ops-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:14px}
.op-card{display:flex;align-items:center;gap:12px;background:var(--card);border:1px solid var(--border);border-radius:var(--radius-lg);padding:14px 16px;cursor:pointer;transition:border-color .15s,box-shadow .15s}
.op-card.locked{opacity:.55;cursor:not-allowed}
.op-card:hover{border-color:var(--primary);box-shadow:var(--shadow)}
.type-icon{width:38px;height:38px;border-radius:9px;display:flex;align-items:center;justify-content:center;color:#fff;font-size:15px;flex-shrink:0}
.op-title{font-size:13px}
.op-desc{font-size:11px;color:var(--text-3);margin-top:2px}
/* ---- 表格 ---- */
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;padding:9px 10px;background:var(--bg);color:var(--text-2);font-weight:600;border-bottom:1px solid var(--border)}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--border)}
.tbl tr:hover td{background:var(--primary-light)}
.cell-sub{font-size:11px;color:var(--text-3)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
.op-btn.danger{color:var(--danger);border-color:rgba(229,72,77,.35)}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease)}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
/* ---- 时间线 ---- */
.tl-line{display:flex;gap:10px;align-items:flex-start;padding:9px 2px;border-bottom:1px dashed var(--border)}
.tl-line:last-child{border-bottom:none}
.tl-dot{width:8px;height:8px;border-radius:50%;margin-top:6px;flex-shrink:0}
.tl-line.ok .tl-dot{background:var(--success)}
.tl-line.warn .tl-dot{background:var(--warn)}
.tl-line.err .tl-dot{background:var(--danger)}
.tl-title{font-size:12.5px}
/* ---- 抽屉 / 弹窗 ---- */
.f-cap{font-size:12.5px;color:var(--text-2);font-weight:600;margin-bottom:7px}
.sel{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 8px;font-size:12.5px;background:#fff;outline:none;color:var(--text-2)}
.lock-tip{font-size:11.5px;color:var(--text-2);background:var(--bg);border-radius:7px;padding:8px 11px;margin-top:12px}
.radio-line{display:flex;gap:8px;align-items:center;padding:7px 10px;border:1px solid var(--border);border-radius:7px;cursor:pointer;font-size:12.5px}
.note{width:100%;border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:8px 10px;font-size:12px;font-family:inherit;outline:none;resize:vertical}
.note:focus{border-color:var(--primary)}
.chk-line{display:flex;gap:9px;align-items:center;padding:8px 11px;border:1px solid var(--border);border-radius:var(--radius);margin-bottom:7px;font-size:12.5px}
.chk-ok{color:var(--success);font-weight:700}
</style>
