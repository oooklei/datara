<script setup lang="ts">
/**
 * M06 流作业详情（todo 18）
 * 对齐 prototype/assets/pages/m06-stream.js `#/stream/detail/:id`（L72-144）：
 * 顶栏（返回列表 / 作业标题 / 暂停·启动按钮 / 状态徽标）
 * + 四页签：SQL开发 / 运行拓扑与指标 / Checkpoint与状态 / 实时数据预览。
 * useRoute() 读 id；SQL 与 Checkpoint 配置修改均 dataStore.save 持久化。
 * F56d 双态：real 路由参数 = 流任务 id（数字）→ GET /stream-jobs/{id}（指标键
 * ratePerSec/totalIn/totalOut 映射，引擎无的字段显示 '-'，status 原样展示）；
 * 启动接 startStreamJob（画布 docId）；日志 getStreamLogs（实时预览抽屉 real 态展示日志尾）；
 * SQL/Checkpoint 在线编辑与演示采样为 mock 专有，real 下禁用并提示。
 */
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { dataStore, ST } from '../../services/mock/dataStore'
import { isMock, getStreamJob, startStreamJob, getStreamLogs } from '../../services'
import { localTime } from '../../services/mock/timeUtil'
import type { StreamJob, StreamWindow, TimeSemantics } from '../../services/types'

const route = useRoute()
const router = useRouter()

/** F56d：real 行携带 docId（启动流任务用画布文档 id；mock 无此概念） */
type JobRow = StreamJob & { docId?: string }
const job = ref<JobRow | null>(null)
const notFound = ref(false)
const windows = ref<StreamWindow[]>([])
const timeSemantics = ref<TimeSemantics[]>([])
const tab = ref('sql')

/* StreamJobRow → 表格行模型（同 StreamListView 口径；引擎指标键见 worker/stream/engine.py _metrics_tick） */
function mapJobRow(j: Awaited<ReturnType<typeof getStreamJob>>): JobRow {
  return {
    id: String(j.id),
    docId: j.docId,
    name: j.name,
    type: 'Flink',
    source: '-',
    sink: '-',
    status: j.status,
    checkpoint: { interval: '-', mode: '-', backend: '-', lastOk: '-', successRate: '-' },
    metrics: {
      tps: Number(j.metrics?.ratePerSec ?? 0) || 0,
      latency: '-',
      inTotal: Number(j.metrics?.totalIn ?? 0) || 0,
      outTotal: Number(j.metrics?.totalOut ?? 0) || 0,
      watermark: '-',
    },
    sql: '',
    owner: '-',
    parallelism: 0,
    uptime: '-',
    createdAt: j.updatedAt,
  }
}

async function reload() {
  const id = String(route.params.id ?? '')
  if (isMock) {
    const all = (await dataStore.list<StreamJob>('streamJobs')) ?? []
    const found = all.find((x) => x.id === id) ?? null
    job.value = found
    notFound.value = !found
    if (found) {
      sqlText.value = found.sql
      ckInt.value = found.checkpoint.interval === '-' ? '60s' : found.checkpoint.interval
      ckMode.value = found.checkpoint.mode === '-' ? 'Exactly-Once' : found.checkpoint.mode
      ckBe.value = found.checkpoint.backend
    }
    return
  }
  /* F56d real：按流任务数字 id 拉详情（列表「详情」跳转同口径） */
  try {
    const j = await getStreamJob(Number(id))
    job.value = mapJobRow(j)
    notFound.value = false
  } catch {
    job.value = null
    notFound.value = true
  }
}

onMounted(async () => {
  await reload()
  if (!isMock) return
  windows.value = (await dataStore.list<StreamWindow>('windows')) ?? []
  timeSemantics.value = (await dataStore.list<TimeSemantics>('timeSemantics')) ?? []
})

// 同一组件实例在 /stream/detail/:id 间切换（hash 导航复用实例）时重新加载
watch(() => route.params.id, reload)

/* ---- ST 徽标 / 千分位 ---- */
function stCls(s: string): string {
  return ST[s]?.cls ?? 'st-gray'
}
function stLabel(s: string): string {
  return ST[s]?.label ?? s
}
function fmt(n: number): string {
  return n.toLocaleString('en-US')
}

/* ---- 顶栏操作：暂停 / 启动 ---- */
async function pauseJob() {
  const j = job.value
  if (!j) return
  /* F56d：流引擎不支持暂停（仅 start/stop），real 下提示 */
  if (!isMock) { ElMessage.info('流引擎不支持暂停，请在列表页使用「停止」'); return }
  j.status = 'paused'
  await dataStore.save<StreamJob>('streamJobs', j)
  ElMessage.info('作业已暂停（State保留，可恢复）')
}
async function startJob() {
  const j = job.value
  if (!j) return
  /* F56d real：启动走后端（start 用画布 docId，同画布先停再起幂等） */
  if (!isMock) {
    try {
      ElMessage.info('提交引擎中：解析画布 spec → 启动流线程 …')
      await startStreamJob(j.docId ?? j.id)
      await reload()
      ElMessage.success('作业已提交（starting → running 由引擎上报）')
    } catch (e) {
      ElMessage.error('启动失败：' + (e instanceof Error ? e.message : String(e)))
    }
    return
  }
  ElMessage.info('作业启动中：提交Flink集群 → 初始化State → 运行')
  setTimeout(async () => {
    const cur = job.value
    if (!cur) return
    cur.status = 'running'
    await dataStore.save<StreamJob>('streamJobs', cur)
    ElMessage.success('作业已运行')
  }, 1000)
}

/* ---- ① SQL开发 ---- */
const sqlText = ref('')
function fmtSql() {
  ElMessage.success('SQL格式化完成')
}
function checkSql() {
  ElMessage.success('语法校验通过，产出表 dwd_order_pay_rt 已解析')
}
async function saveSql() {
  const j = job.value
  if (!j) return
  /* F56d：SQL 由流设计器画布 spec 生成（画布保存即生效），real 不提供在线编辑 */
  if (!isMock) { ElMessage.info('流任务 SQL 由流设计器画布生成，请在画布中编辑并保存（启动即生效）'); return }
  j.sql = sqlText.value
  await dataStore.save<StreamJob>('streamJobs', j)
  ElMessage.success('已保存并应用（作业将重启生效）')
}

/* ---- ③ Checkpoint 配置 ---- */
const ckInt = ref('60s')
const ckMode = ref('Exactly-Once')
const ckBe = ref('RocksDB')
const ckIntOptions = ['30s', '60s', '120s']
const ckModeOptions = [
  { v: 'Exactly-Once', t: 'Exactly-Once（精确一次，推荐）' },
  { v: 'At-Least-Once', t: 'At-Least-Once' },
]
const ckBeOptions = [
  { v: 'RocksDB', t: 'RocksDB（大状态，推荐）' },
  { v: 'HashMap', t: 'HashMap（小状态）' },
]
async function saveCk() {
  const j = job.value
  if (!j) return
  /* F56d：Checkpoint 参数由引擎固定（Redis 指标通道），real 不提供编辑 */
  if (!isMock) { ElMessage.info('Checkpoint 参数由流引擎固定管理，real 模式不提供在线编辑'); return }
  j.checkpoint.interval = ckInt.value
  j.checkpoint.mode = ckMode.value
  j.checkpoint.backend = ckBe.value
  await dataStore.save<StreamJob>('streamJobs', j)
  ElMessage.success('Checkpoint配置已保存，重启作业后生效')
}

/* ---- Checkpoint 运行记录（演示数据，与原型一致；real 引擎未上报该指标显示空态） ---- */
interface CkRecord { id: string; t: string; d: string; s: string; size: string }
const ckRecords = ref<CkRecord[]>(isMock
  ? [
      { id: 'ck-12846', t: '22:28:40', d: '2.1s', s: '完成', size: '186MB' },
      { id: 'ck-12845', t: '22:27:40', d: '6.0s', s: '完成', size: '186MB' },
      { id: 'ck-12844', t: '22:26:40', d: '1.8s', s: '完成', size: '185MB' },
    ]
  : [])

/* ---- ④ 实时数据预览（演示数据，与原型一致；real 走引擎 SSE/轮询通道不提供模拟采样） ---- */
interface PreviewRow { pay_id: number; amount: number; ch: string; st: number }
const previewRows = ref<PreviewRow[]>(isMock
  ? [
      { pay_id: 20260911220301, amount: 299.0, ch: 'ALIPAY', st: 1 },
      { pay_id: 20260911220302, amount: 1299.0, ch: 'WECHAT', st: 1 },
      { pay_id: 20260911220303, amount: 88.5, ch: 'UNIONPAY', st: 1 },
      { pay_id: 20260911220304, amount: -10.0, ch: 'WECHAT', st: 1 },
      { pay_id: 20260911220305, amount: 4299.0, ch: 'BANK', st: 0 },
    ]
  : [])
function startSample() {
  if (!isMock) { ElMessage.info('实时数据预览走引擎数据通道（/stream-jobs/{id}/data SSE），real 模式不提供模拟采样'); return }
  ElMessage.warning('实时采样中：已捕获 5 条（含 1 条异常：pay_amount=-10.00）')
}
function stopSample() {
  ElMessage.info('采样已停止')
}
function markAbnormal(_r: PreviewRow) {
  ElMessage.warning('异常样例：负值数据，建议在SQL中过滤 pay_amount>0')
}

/* ---- ⑤ 实时预览抽屉（mock：流式数据演示；real：流任务日志尾 getStreamLogs） ---- */
interface RtRow { offset: number; t: string; key: string; value: string; latency: number | string }
const previewOpen = ref(false)
const rtRows = ref<RtRow[]>([])
/* 确定性常数与伪数据：不用 Math.random，保证每次打开展示一致 */
const RT_TPS = 1240
const RT_EVENTS = [
  { key: 'u_1001', value: '299.00' },
  { key: 'u_1002', value: '1299.00' },
  { key: 'u_1003', value: '88.50' },
  { key: 'u_1004', value: '4299.00' },
  { key: 'u_1005', value: '59.90' },
  { key: 'u_1006', value: '12.00' },
]
const RT_LATENCIES = [12, 18, 24, 36, 47, 58, 80, 15] // 处理延迟 12~80ms 循环取值
const RT_MAX_ROWS = 50 // 表格最多保留 50 行，超出移除最旧（防内存增长）
let rtTimer: ReturnType<typeof setInterval> | null = null
let rtOffset = 884200
let rtIdx = 0

/* 事件时间列在 localTime（分钟级）基础上补秒，流数据按秒产生 */
function evTime(d: Date): string {
  return `${localTime(d)}:${String(d.getSeconds()).padStart(2, '0')}`
}

function appendRtRow() {
  const ev = RT_EVENTS[rtIdx % RT_EVENTS.length]
  const lat = RT_LATENCIES[rtIdx % RT_LATENCIES.length]
  rtIdx += 1
  rtOffset += 1
  rtRows.value.push({ offset: rtOffset, t: evTime(new Date()), key: ev.key, value: ev.value, latency: lat })
  if (rtRows.value.length > RT_MAX_ROWS) {
    rtRows.value.splice(0, rtRows.value.length - RT_MAX_ROWS)
  }
}

/* F56d real：拉日志尾填充表格（Redis List Last-500 尾部，时间倒序返回） */
async function loadLogs() {
  if (!job.value) return
  try {
    const lines = await getStreamLogs(Number(job.value.id), RT_MAX_ROWS)
    /* 日志行格式：YYYY-MM-DD HH:MM:SS [LEVEL] 消息（worker/stream/engine.py _log） */
    rtRows.value = lines.map((line, i) => {
      const m = /^(\S+ \S+) \[([A-Z]+)\] (.*)$/.exec(line)
      return { offset: i + 1, t: m?.[1] ?? '-', key: m?.[2] ?? '-', value: m?.[3] ?? line, latency: '-' }
    })
  } catch { /* 日志通道未就绪时留空，不阻断抽屉 */ }
}

function startRt() {
  stopRt()
  if (isMock) {
    appendRtRow() // 打开立即出一条，便于查看
    rtTimer = setInterval(appendRtRow, 2000) // 每 2s 追加一行
  } else {
    loadLogs()
  }
}

function stopRt() {
  if (rtTimer !== null) {
    clearInterval(rtTimer)
    rtTimer = null
  }
}

/* 抽屉关闭时停止定时器；组件卸载兜底清理（防内存泄漏） */
onUnmounted(stopRt)
</script>

<template>
  <div class="page">
    <!-- 空态 -->
    <div v-if="notFound" class="card" style="padding:16px">
      <div style="text-align:center;color:var(--text-3);padding:48px 0">
        <div style="font-size:36px;margin-bottom:8px">🔍</div>
        <div style="font-size:14px;margin-bottom:4px">作业不存在</div>
        <div style="font-size:12px">请检查作业 ID 是否正确，或返回列表重新选择。</div>
        <button class="tb-new" style="margin-top:16px" @click="router.push('/stream/list')">返回列表</button>
      </div>
    </div>

    <template v-else>
      <!-- 顶栏：返回 + 标题 + 操作 -->
      <div class="card" style="padding:16px">
        <div class="detail-head">
          <button class="op-btn" @click="router.push('/stream/list')">← 流处理作业</button>
          <div class="title-text">
            <b style="font-size:15px">{{ job?.name }}</b>
            <div class="mono" style="color:var(--text-3);font-size:11.5px">
              {{ job?.id }} · {{ job?.type }} · {{ job?.source }} → {{ job?.sink }} · 并行度 {{ job?.parallelism }} · 运行时长 {{ job?.uptime }}
            </div>
          </div>
          <span class="spacer" />
          <button class="op-btn rt-toggle" @click="previewOpen = true">▶ 实时预览</button>
          <button v-if="job?.status === 'running'" class="op-btn" @click="pauseJob">暂停</button>
          <button v-else class="tb-new" @click="startJob">▶ 启动</button>
          <span v-if="job" class="st" :class="stCls(job.status)"><span class="dot" />{{ stLabel(job.status) }}</span>
        </div>
      </div>

      <!-- 页签面板 -->
      <div class="card" style="padding:16px;margin-top:14px">
        <el-tabs v-model="tab">
          <!-- ① SQL开发 -->
          <el-tab-pane label="SQL开发" name="sql">
            <div class="editor-toolbar">
              <b style="font-size:12.5px">Flink SQL</b>
              <span class="spacer" />
              <button class="op-btn" @click="fmtSql">格式化</button>
              <button class="op-btn" @click="checkSql">校验</button>
              <button class="tb-new" @click="saveSql">保存并生效</button>
            </div>
            <textarea v-model="sqlText" class="sql-area" rows="10" />
            <div class="grid-2" style="margin-top:14px">
              <div class="sub-card">
                <div class="sub-title" style="margin-bottom:8px">窗口参考</div>
                <div v-for="w in windows" :key="w.name" class="kv-row">
                  <span class="k">{{ w.name }}</span>
                  <span class="v">{{ w.desc }}；例：{{ w.eg }}</span>
                </div>
              </div>
              <div class="sub-card">
                <div class="sub-title" style="margin-bottom:8px">时间语义</div>
                <div v-for="w in timeSemantics" :key="w.name" class="kv-row">
                  <span class="k">{{ w.name }}</span>
                  <span class="v">{{ w.desc }}；适用：{{ w.use }}</span>
                </div>
              </div>
            </div>
          </el-tab-pane>

          <!-- ② 运行拓扑与指标 -->
          <el-tab-pane label="运行拓扑与指标" name="metrics">
            <div class="sub-card">
              <div class="sub-title" style="margin-bottom:10px">运行指标</div>
              <div class="stat-cards">
                <div class="stat-card"><b class="sv">{{ fmt(job?.metrics.tps ?? 0) }}</b><span class="sl">当前吞吐（条/s）</span></div>
                <div class="stat-card"><b class="sv" style="font-size:16px">{{ job?.metrics.latency ?? '-' }}</b><span class="sl">端到端延迟</span></div>
                <div class="stat-card"><b class="sv" style="font-size:16px">{{ fmt(job?.metrics.inTotal ?? 0) }}</b><span class="sl">累计输入</span></div>
                <div class="stat-card"><b class="sv" style="font-size:16px">{{ fmt(job?.metrics.outTotal ?? 0) }}</b><span class="sl">累计输出</span></div>
              </div>
              <div class="kv-row" style="margin-top:10px">
                <span class="k">Watermark</span><span class="v mono">{{ job?.metrics.watermark }}</span>
              </div>
              <div class="kv-row">
                <span class="k">时间语义</span><span class="v">事件时间（Event Time）+ Watermark 乱序容忍 4s</span>
              </div>
            </div>
            <div class="sub-card" style="margin-top:14px">
              <div class="sub-title" style="margin-bottom:10px">执行拓扑（Source → 算子 → Sink）</div>
              <div class="dag-wrap">
                <svg class="dag-svg" viewBox="0 0 820 170" width="100%" height="170">
                  <g>
                    <rect class="n-box" x="30" y="50" width="130" height="60" rx="8" />
                    <text x="95" y="76" text-anchor="middle" font-size="11" fill="#5b6478">Source</text>
                    <text x="95" y="95" text-anchor="middle" font-size="12" font-weight="600">Kafka Topic</text>
                  </g>
                  <line class="dag-edge" x1="160" y1="80" x2="215" y2="80" />
                  <g>
                    <rect class="n-box" x="215" y="50" width="150" height="60" rx="8" />
                    <text x="290" y="76" text-anchor="middle" font-size="11" fill="#5b6478">FlatMap/Filter</text>
                    <text x="290" y="95" text-anchor="middle" font-size="12" font-weight="600">并行度 {{ job?.parallelism ?? 1 }}</text>
                  </g>
                  <line class="dag-edge" x1="365" y1="80" x2="420" y2="80" />
                  <g>
                    <rect class="n-box" x="420" y="50" width="150" height="60" rx="8" />
                    <text x="495" y="76" text-anchor="middle" font-size="11" fill="#5b6478">Keyed Process</text>
                    <text x="495" y="95" text-anchor="middle" font-size="12" font-weight="600">RocksDB State</text>
                  </g>
                  <line class="dag-edge" x1="570" y1="80" x2="625" y2="80" />
                  <g>
                    <rect class="n-box" x="625" y="50" width="130" height="60" rx="8" />
                    <text x="690" y="76" text-anchor="middle" font-size="11" fill="#5b6478">Sink</text>
                    <text x="690" y="95" text-anchor="middle" font-size="12" font-weight="600">Doris Stream Load</text>
                  </g>
                </svg>
              </div>
            </div>
          </el-tab-pane>

          <!-- ③ Checkpoint与状态 -->
          <el-tab-pane label="Checkpoint与状态" name="ckpt">
            <div class="sub-card">
              <div class="sub-title" style="margin-bottom:10px">Checkpoint 配置</div>
              <div class="form-grid">
                <div class="field">
                  <label>间隔</label>
                  <select v-model="ckInt">
                    <option v-for="o in ckIntOptions" :key="o" :value="o">{{ o }}</option>
                  </select>
                </div>
                <div class="field">
                  <label>语义</label>
                  <select v-model="ckMode">
                    <option v-for="o in ckModeOptions" :key="o.v" :value="o.v">{{ o.t }}</option>
                  </select>
                </div>
                <div class="field">
                  <label>状态后端</label>
                  <select v-model="ckBe">
                    <option v-for="o in ckBeOptions" :key="o.v" :value="o.v">{{ o.t }}</option>
                  </select>
                </div>
              </div>
              <button class="tb-new" @click="saveCk">保存配置</button>
            </div>
            <div class="sub-card" style="margin-top:14px">
              <div class="sub-title" style="margin-bottom:10px">Checkpoint 运行记录</div>
              <table class="tbl">
                <thead>
                  <tr><th>Checkpoint</th><th>完成时间</th><th>耗时</th><th>状态</th><th>State大小</th></tr>
                </thead>
                <tbody>
                  <tr v-for="r in ckRecords" :key="r.id">
                    <td><span class="mono">{{ r.id }}</span></td>
                    <td class="mono">{{ r.t }}</td>
                    <td>{{ r.d }}</td>
                    <td><span class="st" :class="stCls('success')"><span class="dot" />{{ stLabel('success') }}</span></td>
                    <td class="mono">{{ r.size }}</td>
                  </tr>
                </tbody>
              </table>
              <div style="margin-top:10px;font-size:12px;color:var(--text-2)">
                成功率 {{ job?.checkpoint.successRate }} · 最近成功 {{ job?.checkpoint.lastOk }} · 故障自动恢复：从最近完成Checkpoint恢复State
              </div>
            </div>
          </el-tab-pane>

          <!-- ④ 实时数据预览 -->
          <el-tab-pane label="实时数据预览" name="preview">
            <div class="sub-card">
              <div class="sub-title" style="margin-bottom:10px">实时数据预览（调试）</div>
              <div style="display:flex;gap:8px;margin-bottom:10px;align-items:center">
                <button class="tb-new" @click="startSample">▶ 开始采样</button>
                <button class="op-btn" @click="stopSample">停止采样</button>
                <span style="font-size:12px;color:var(--text-3)">采样最新 20 条进入流的数据</span>
              </div>
              <table class="tbl">
                <thead>
                  <tr><th>pay_id</th><th>pay_amount</th><th>pay_channel</th><th>pay_status</th><th style="width:110px">操作</th></tr>
                </thead>
                <tbody>
                  <tr v-for="r in previewRows" :key="r.pay_id">
                    <td><span class="mono">{{ r.pay_id }}</span></td>
                    <td><span class="mono" :style="{ color: r.amount < 0 ? 'var(--danger)' : 'inherit' }">{{ r.amount.toFixed(2) }}</span></td>
                    <td>{{ r.ch }}</td>
                    <td>
                      <span class="st" :class="stCls(r.st ? 'success' : 'failed')">
                        <span class="dot" />{{ stLabel(r.st ? 'success' : 'failed') }}
                      </span>
                    </td>
                    <td>
                      <button v-if="r.amount < 0" class="op-btn danger" @click="markAbnormal(r)">标记异常</button>
                      <span v-else style="color:var(--text-3)">-</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>

      <!-- 实时预览抽屉：mock 流式数据表（offset/事件时间/key/value/延迟），打开后每 2s 追加一行 -->
      <el-drawer
        v-model="previewOpen"
        :title="job ? `实时预览 - ${job.name}` : '实时预览'"
        size="620px"
        @open="startRt"
        @closed="stopRt"
      >
        <div class="sub-card">
          <div class="rt-head">
            <b style="font-size:12.5px">{{ isMock ? '流式数据（mock）' : '流任务日志（最近 50 条）' }}</b>
            <span class="st" :class="stCls('success')"><span class="dot" />Watermark 正常 · 延迟 5s</span>
            <span class="spacer" />
            <span class="mono" style="font-size:12px;color:var(--text-2)">TPS {{ fmt(isMock ? RT_TPS : Number(job?.metrics.tps ?? 0)) }}</span>
          </div>
          <table class="tbl">
            <thead>
              <tr><th>offset</th><th>事件时间</th><th>key</th><th>value</th><th>处理延迟ms</th></tr>
            </thead>
            <tbody>
              <tr v-for="r in rtRows" :key="r.offset">
                <td><span class="mono">{{ r.offset }}</span></td>
                <td class="mono">{{ r.t }}</td>
                <td class="mono">{{ r.key }}</td>
                <td class="mono">{{ r.value }}</td>
                <td class="mono">{{ r.latency }}</td>
              </tr>
              <tr v-if="rtRows.length === 0">
                <td colspan="5" style="text-align:center;color:var(--text-3);padding:24px 0">{{ isMock ? '等待流式数据…' : '暂无日志（任务运行后由引擎写入）' }}</td>
              </tr>
            </tbody>
          </table>
          <div style="margin-top:10px;font-size:12px;color:var(--text-3)">
            {{ isMock
              ? '每 2s 追加一行，最多保留 ' + RT_MAX_ROWS + ' 条（超出移除最旧）；关闭抽屉即停止采样。'
              : '展示引擎日志尾（Redis Last-500），打开抽屉即拉取最新内容。' }}
          </div>
        </div>
      </el-drawer>
    </template>
  </div>
</template>

<style scoped>
.detail-head{display:flex;gap:12px;align-items:center}
.title-text{display:flex;flex-direction:column;gap:2px}
.spacer{flex:1}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease)}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
.op-btn.danger{color:var(--danger);border-color:rgba(229,72,77,.35)}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.editor-toolbar{display:flex;gap:8px;align-items:center;margin-bottom:10px}
.sql-area{width:100%;border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:8px 10px;font-family:ui-monospace,SFMono-Regular,Consolas,Menlo,monospace;font-size:12px;line-height:1.7;resize:vertical;outline:none;background:#f8fafc;color:var(--text)}
.sql-area:focus{border-color:var(--primary)}
.sub-card{border:1px solid var(--border);border-radius:var(--radius);padding:12px 14px}
.sub-title{font-weight:700;font-size:13px;color:var(--text)}
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.kv-row{display:flex;gap:12px;padding:6px 0;font-size:12.5px;border-bottom:1px dashed var(--border)}
.kv-row:last-child{border-bottom:none}
.kv-row .k{color:var(--text-3);flex-shrink:0;width:150px}
.kv-row .v{color:var(--text)}
.stat-cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.stat-card{border:1px solid var(--border);border-radius:var(--radius);padding:12px 14px;display:flex;flex-direction:column;gap:2px}
.sv{font-size:20px;line-height:1.3}
.sl{font-size:11px;color:var(--text-3)}
.form-grid{max-width:520px;display:flex;flex-direction:column;gap:12px;margin-bottom:12px}
.field label{display:block;font-size:12px;color:var(--text-2);margin-bottom:4px;font-weight:600}
.field select{width:100%;border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:7px 10px;font-size:12.5px;outline:none;background:#fff;color:var(--text)}
.field select:focus{border-color:var(--primary)}
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;padding:9px 10px;background:var(--bg);color:var(--text-2);font-weight:600;border-bottom:1px solid var(--border)}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--border)}
.tbl tr:hover td{background:var(--primary-light)}
.dag-wrap{border:1px solid var(--border);border-radius:var(--radius);background:#fbfcfe;overflow-x:auto}
.dag-svg .n-box{fill:#fff;stroke:var(--border-strong);stroke-width:1.5}
.dag-svg .dag-edge{stroke:var(--border-strong);stroke-width:1.5;marker-end:none}
/* 实时预览抽屉 */
.rt-head{display:flex;gap:10px;align-items:center;margin-bottom:10px}
.rt-toggle{color:var(--primary);border-color:var(--primary)}
.rt-toggle:hover{background:var(--primary);color:#fff}
</style>
