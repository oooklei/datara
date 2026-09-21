<script setup lang="ts">
/**
 * M06 流处理作业列表（todo 17）
 * 对齐 prototype/assets/pages/m06-stream.js `#/stream/list`（L6-42）：
 * 作业表格（关键字 + 状态筛选，吞吐/延迟、Checkpoint 列）；顶部工具栏：新建流作业 + 资源概览；
 * 行操作：设计器(/stream/design/:id) / 详情(/stream/detail/:id) / 暂停·恢复·启动 / 停止。
 * 下方窗口计算、时间语义参考卡与核心能力说明（dataStore.windows / timeSemantics）。
 * F56d 双态：real 走 streamApi —— 列表 listStreamJobs()，行字段映射 StreamJobRow（引擎无的字段
 * 显示 '-'，status 原样展示）；启停接 startStreamJob/stopStreamJob（start 用 docId，stop 用 job id）；
 * 详情路由参数 = job.id（数字，详情页 GET /stream-jobs/{id} 同口径）；新建为 mock 专有 real 下禁用。
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { dataStore, ST } from '../../services/mock/dataStore'
import { isMock, listStreamJobs, startStreamJob, stopStreamJob } from '../../services'
import ListFilterPanel from '../../components/ListFilterPanel.vue'
import type { DbUser, StreamJob, StreamWindow, TimeSemantics } from '../../services/types'

const router = useRouter()

const props = defineProps<{ embed?: boolean }>()
const emit = defineEmits<{ (e: 'open', id: string): void }>()
/** F56d：real 行携带 docId（启动流任务用画布文档 id；mock 无此概念） */
type Row = StreamJob & { docId?: string }
const rows = ref<Row[]>([])
const windows = ref<StreamWindow[]>([])
const timeSemantics = ref<TimeSemantics[]>([])
const user = ref<DbUser | null>(null)

const keyword = ref('')
const filters = ref<Record<string, string>>({ type: '', status: '' })
/* F56d：状态筛选随双态 —— real 为引擎状态机（status 原样展示） */
const statusOptions = isMock
  ? [
      { v: 'running', t: '运行中' },
      { v: 'paused', t: '已暂停' },
      { v: 'stopped', t: '已停止' },
    ]
  : [
      { v: 'starting', t: 'starting' },
      { v: 'running', t: 'running' },
      { v: 'reconnecting', t: 'reconnecting' },
      { v: 'stopped', t: 'stopped' },
      { v: 'failed', t: 'failed' },
    ]
const facets = [
  { key: 'type', label: '类型', options: [{ v: 'Flink SQL', t: 'Flink SQL' }, { v: 'CDC采集', t: 'CDC采集' }] },
  { key: 'status', label: '状态', options: statusOptions },
]

const filtered = computed<Row[]>(() => {
  const kw = keyword.value.trim().toLowerCase()
  return rows.value.filter((r) => {
    if (filters.value.type && r.type !== filters.value.type) return false
    if (filters.value.status && r.status !== filters.value.status) return false
    if (!kw) return true
    return [r.name, r.type, r.source, r.sink, r.owner].some((s) => s.toLowerCase().includes(kw))
  })
})

async function reload() {
  if (isMock) {
    // 必须展开为新数组：dataStore.save 原地修改数组，list 返回同一引用，
    // 直接赋值不会触发 ref 更新（filtered 计算属性会停留在旧值）。
    rows.value = [...((await dataStore.list<StreamJob>('streamJobs')) ?? [])]
    return
  }
  /* F56d real：t_stream_job + Redis 指标镜像合并行 → 表格行模型；
     引擎指标键（worker/stream/engine.py）：ratePerSec/totalIn/totalOut（速率/累计输入/累计输出）；
     引擎无的数据链路/Checkpoint/并行度等字段显示 '-'；status 原样展示 */
  try {
    const jobs = await listStreamJobs({ pageSize: 200 })
    rows.value = jobs.map((j) => ({
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
    }))
  } catch (e) {
    ElMessage.error('流任务列表加载失败：' + errMsg(e) + '（检查后端服务与登录态）')
  }
}

function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

onMounted(async () => {
  await reload()
  if (!isMock) return
  windows.value = (await dataStore.list<StreamWindow>('windows')) ?? []
  timeSemantics.value = (await dataStore.list<TimeSemantics>('timeSemantics')) ?? []
  user.value = await dataStore.get<DbUser>('user')
})

/* ---- ST 徽标 / 千分位 / 类型配色 ---- */
function stCls(s: string): string {
  return ST[s]?.cls ?? 'st-gray'
}
function stLabel(s: string): string {
  return ST[s]?.label ?? s
}
function fmt(n: number): string {
  return n.toLocaleString('en-US')
}

/* ---- 行操作 ---- */
function goDesign(j: Row) {
  /* embed（任务中心「看列表」弹窗）：行内「可视化编排」不跳路由，emit 由任务中心切换内嵌画布；
     F56d real：编排目标是画布文档（docId），非流任务记录 id */
  const target = j.docId ?? j.id
  if (props.embed) { emit('open', target); return }
  router.push(`/stream/design/${target}`)
}
function goDetail(j: Row) {
  /* F56d：详情路由参数 = 流任务 id（数字），详情页 GET /stream-jobs/{id} 同口径 */
  router.push(`/stream/detail/${j.id}`)
}
async function pauseJob(j: Row) {
  if (!isMock) { ElMessage.info('流引擎不支持暂停，请使用「停止」'); return }
  j.status = 'paused'
  await dataStore.save<StreamJob>('streamJobs', j)
  await reload()
  ElMessage.info('作业已暂停（State保留，可恢复）')
}
async function resumeJob(j: Row) {
  /* F56d real：恢复 = 以画布 docId 重新提交（引擎从位点续跑） */
  if (!isMock) {
    try {
      ElMessage.info('提交引擎重启中 …')
      await startStreamJob(j.docId ?? j.id)
      await reload()
      ElMessage.success('作业已重新提交运行')
    } catch (e) {
      ElMessage.error('启动失败：' + errMsg(e))
    }
    return
  }
  j.status = 'running'
  await dataStore.save<StreamJob>('streamJobs', j)
  await reload()
  ElMessage.success('作业已从最近Checkpoint恢复运行')
}
async function stopJob(j: Row) {
  try {
    await ElMessageBox.confirm(`确认停止作业「${j.name}」？停止后将释放Slot资源；可选保留Savepoint用于恢复。`, '停止作业', {
      confirmButtonText: '停止', cancelButtonText: '取消', type: 'warning',
    })
  } catch {
    return
  }
  /* F56d real：停止走后端广播（stop 用流任务 id） */
  if (!isMock) {
    try {
      await stopStreamJob(Number(j.id))
      await reload()
      ElMessage.success('作业已停止')
    } catch (e) {
      ElMessage.error('停止失败：' + errMsg(e))
    }
    return
  }
  j.status = 'stopped'
  await dataStore.save<StreamJob>('streamJobs', j)
  await reload()
  ElMessage.success('作业已停止')
}
async function startJob(j: Row) {
  /* F56d real：启动走后端（start 用画布 docId，同画布先停再起幂等） */
  if (!isMock) {
    try {
      ElMessage.info('提交引擎中：解析画布 spec → 启动流线程 …')
      await startStreamJob(j.docId ?? j.id)
      await reload()
      ElMessage.success('作业已提交（starting → running 由引擎上报）')
    } catch (e) {
      ElMessage.error('启动失败：' + errMsg(e))
    }
    return
  }
  ElMessage.info('作业启动中：提交Flink集群 → 初始化State → 运行')
  setTimeout(async () => {
    j.status = 'running'
    await dataStore.save<StreamJob>('streamJobs', j)
    await reload()
    ElMessage.success('作业已运行')
  }, 1000)
}
function showResource() {
  ElMessage.info('集群资源：Flink TaskManager 2/2 正常，Slot 使用 14/16')
}

/* ---- 新建流作业 ---- */
const createVisible = ref(false)
const jName = ref('')
const jType = ref('Flink SQL')
const jSrc = ref('Kafka: topic_order_pay')
const jSink = ref('Doris: dwd_order_pay_rt')
const jPara = ref(4)
const jCk = ref('60s')
const jSql = ref(
  'INSERT INTO dwd_order_pay_rt\nSELECT pay_id, order_id, user_id, pay_amount, pay_status,\n       TO_DATE(pay_time) AS dt\nFROM kafka_order_pay\nWHERE pay_amount IS NOT NULL;',
)
const typeOptions = [
  { v: 'Flink SQL', t: 'Flink SQL 流计算（推荐）' },
  { v: 'CDC采集', t: 'CDC 实时采集（Binlog/WAL → Kafka）' },
]
const srcOptions = ['Kafka: topic_order_pay', 'Kafka: topic_iot_heartbeat', 'MySQL Binlog: biz_test.inventory']
const sinkOptions = ['Doris: dwd_order_pay_rt', 'Kafka: topic_inventory_cdc', '打印控制台']
const paraOptions = [1, 2, 4, 8]
const ckOptions = ['30s', '60s', '120s']

function openCreate() {
  /* F56d：流任务由流设计器画布「启动」生成（一画布一流任务），real 不提供本地新建 */
  if (!isMock) { ElMessage.info('流任务由流设计器画布「启动」生成（一画布一流任务），real 模式不提供本地新建'); return }
  jName.value = ''
  jType.value = 'Flink SQL'
  jSrc.value = 'Kafka: topic_order_pay'
  jSink.value = 'Doris: dwd_order_pay_rt'
  jPara.value = 4
  jCk.value = '60s'
  jSql.value = 'INSERT INTO dwd_order_pay_rt\nSELECT pay_id, order_id, user_id, pay_amount, pay_status,\n       TO_DATE(pay_time) AS dt\nFROM kafka_order_pay\nWHERE pay_amount IS NOT NULL;'
  createVisible.value = true
}

function nowMinute(): string {
  const d = new Date()
  const p = (x: number) => String(x).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

async function saveCreate() {
  if (!jName.value.trim()) {
    ElMessage.warning('请填写作业名称')
    return
  }
  const all = (await dataStore.list<StreamJob>('streamJobs')) ?? []
  const maxN = all.reduce((m, r) => {
    const n = parseInt(r.id.replace(/\D/g, ''), 10)
    return Number.isFinite(n) && n > m ? n : m
  }, 0)
  const job: StreamJob = {
    id: `SJ${String(maxN + 1).padStart(3, '0')}`,
    name: jName.value.trim(),
    type: jType.value,
    source: jSrc.value,
    sink: jSink.value,
    status: 'stopped',
    checkpoint: { interval: jCk.value, mode: 'Exactly-Once', backend: 'RocksDB', lastOk: '-', successRate: '-' },
    metrics: { tps: 0, latency: '-', inTotal: 0, outTotal: 0, watermark: '-' },
    sql: jSql.value,
    owner: user.value?.name ?? '王工',
    parallelism: jPara.value,
    uptime: '-',
    createdAt: nowMinute(),
  }
  await dataStore.save<StreamJob>('streamJobs', job)
  createVisible.value = false
  ElMessage.success(`流作业已创建（${job.id}），点击「启动」运行`)
  await reload()
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
      placeholder="搜索作业/Topic/Sink"
    />
    <div style="flex:1;min-width:0">
    <div class="card" style="padding:16px">
      <div class="tbl-toolbar">
        <span class="sec-head">流数据处理</span>
        <span class="pill info">{{ filtered.length }} / {{ rows.length }}</span>
        <span class="spacer" />
        <button class="tb-new" style="margin-right:8px" @click="openCreate">＋ 新建流作业</button>
        <button class="op-btn" @click="showResource">资源概览</button>
      </div>

      <table class="tbl">
        <thead>
          <tr>
            <th>作业</th><th>数据链路</th><th>吞吐/延迟</th><th>Checkpoint</th><th>状态</th><th style="width:250px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in filtered" :key="r.id">
            <td>
              <a @click="goDetail(r)"><b>{{ r.name }}</b></a>
              <div style="font-size:11px;color:var(--text-3)">{{ r.id }} · {{ r.type }} · 负责人 {{ r.owner }}</div>
            </td>
            <td>
              <div class="mono" style="font-size:11px">{{ r.source }}</div>
              <div class="mono" style="font-size:11px;color:var(--primary)">→ {{ r.sink }}</div>
            </td>
            <td>
              <span class="mono">{{ fmt(r.metrics.tps) }} 条/s</span>
              <div style="font-size:11px;color:var(--text-3)">端到端 {{ r.metrics.latency }}</div>
            </td>
            <td>
              <template v-if="r.checkpoint.interval !== '-'">
                <span style="font-size:12px">{{ r.checkpoint.interval }} · {{ r.checkpoint.mode }}</span>
                <div style="font-size:11px;color:var(--text-3)">成功率 {{ r.checkpoint.successRate }}</div>
              </template>
              <span v-else style="color:var(--text-3)">-</span>
            </td>
            <td><span class="st" :class="stCls(r.status)"><span class="dot" />{{ stLabel(r.status) }}</span></td>
            <td>
              <div>
                <button class="op-btn primary" @click="goDesign(r)">可视化编排</button>
                <button class="op-btn" @click="goDetail(r)">详情</button>
                <button v-if="r.status === 'running'" class="op-btn" @click="pauseJob(r)">暂停</button>
                <button v-else-if="r.status === 'paused'" class="op-btn" @click="resumeJob(r)">恢复</button>
                <button v-else class="op-btn" @click="startJob(r)">启动</button>
                <button v-if="r.status !== 'stopped'" class="op-btn danger" @click="stopJob(r)">停止</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-if="filtered.length === 0" class="empty">未找到匹配的流作业，请调整筛选条件</div>
    </div>

    <!-- 窗口 / 时间语义参考 -->
    <div class="grid-2" style="margin-top:14px">
      <div class="card" style="padding:16px">
        <div class="tbl-toolbar"><span style="font-weight:700;font-size:13.5px">窗口计算（Flink SQL）</span></div>
        <table class="tbl">
          <thead><tr><th>窗口类型</th><th>说明</th><th>示例</th></tr></thead>
          <tbody>
            <tr v-for="w in windows" :key="w.name">
              <td>{{ w.name }}</td>
              <td style="color:var(--text-2)">{{ w.desc }}</td>
              <td class="mono" style="font-size:11.5px">{{ w.eg }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="card" style="padding:16px">
        <div class="tbl-toolbar"><span style="font-weight:700;font-size:13.5px">时间语义与水位线</span></div>
        <table class="tbl">
          <thead><tr><th>时间语义</th><th>说明</th><th>适用</th></tr></thead>
          <tbody>
            <tr v-for="w in timeSemantics" :key="w.name">
              <td>{{ w.name }}</td>
              <td style="color:var(--text-2)">{{ w.desc }}</td>
              <td>{{ w.use }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 核心能力说明 -->
    <div class="card" style="padding:16px;margin-top:14px">
      <div class="tbl-toolbar"><span style="font-weight:700;font-size:13.5px">核心能力说明</span></div>
      <div class="cap-grid">
        <div class="cap-item"><b>实时数据采集</b><div class="f-help">CDC捕获Binlog/WAL变更、日志实时采集、IoT接入</div></div>
        <div class="cap-item"><b>状态管理</b><div class="f-help">Keyed/Operator State，RocksDB状态后端支撑大状态</div></div>
        <div class="cap-item"><b>Checkpoint容错</b><div class="f-help">周期Checkpoint，Exactly-Once精确一次，故障自动恢复</div></div>
        <div class="cap-item"><b>实时预览</b><div class="f-help">调试时实时查看中间结果，降低SQL开发门槛</div></div>
      </div>
      <div class="banner-warn-box">⚠ CEP 复杂事件处理、实时风控/用户行为/实时推荐等业务场景已明确移出 P0（后期迭代）。</div>
    </div>
    </div>

    <!-- 新建流作业 -->
    <el-dialog v-model="createVisible" title="新建流处理作业" width="560px">
      <div class="form-grid">
        <div class="field">
          <label>作业名称 <i class="req">*</i></label>
          <input v-model="jName" placeholder="如：订单支付实时入仓" />
        </div>
        <div class="field">
          <label>作业类型</label>
          <select v-model="jType">
            <option v-for="o in typeOptions" :key="o.v" :value="o.v">{{ o.t }}</option>
          </select>
        </div>
        <div class="field">
          <label>数据源</label>
          <select v-model="jSrc">
            <option v-for="o in srcOptions" :key="o" :value="o">{{ o }}</option>
          </select>
        </div>
        <div class="field">
          <label>写入目标</label>
          <select v-model="jSink">
            <option v-for="o in sinkOptions" :key="o" :value="o">{{ o }}</option>
          </select>
        </div>
        <div class="wiz-row">
          <div class="field">
            <label>并行度</label>
            <select v-model.number="jPara">
              <option v-for="n in paraOptions" :key="n" :value="n">{{ n }}</option>
            </select>
          </div>
          <div class="field">
            <label>Checkpoint间隔</label>
            <select v-model="jCk">
              <option v-for="o in ckOptions" :key="o" :value="o">{{ o === '60s' ? '60秒（推荐）' : o === '30s' ? '30秒' : '120秒' }}</option>
            </select>
          </div>
        </div>
        <div class="field">
          <label>Flink SQL</label>
          <textarea v-model="jSql" rows="7" class="sql-area" />
          <div class="f-help">支持窗口函数（TUMBLE/HOP/SESSION）、事件时间与Watermark</div>
        </div>
      </div>
      <template #footer>
        <button class="op-btn" @click="createVisible = false">取消</button>
        <button class="tb-new" @click="saveCreate">创建</button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;padding:9px 10px;background:var(--bg);color:var(--text-2);font-weight:600;border-bottom:1px solid var(--border)}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--border)}
.tbl tr:hover td{background:var(--primary-light)}
.kw{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 10px;font-size:12.5px;width:200px;outline:none}
.kw:focus{border-color:var(--primary)}
.sel{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 8px;font-size:12.5px;background:#fff;outline:none;color:var(--text-2)}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease)}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
.op-btn.primary{color:var(--primary);border-color:rgba(22,104,220,.4);font-weight:600}
.op-btn.danger{color:var(--danger);border-color:rgba(229,72,77,.35)}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
.tag{display:inline-block;border-radius:4px;padding:1px 8px;font-size:11.5px;font-weight:600}
.f-help{font-size:11px;color:var(--text-3);margin-top:4px}
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.cap-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.cap-item{border:1px solid var(--border);border-radius:var(--radius);padding:12px 14px;font-size:12.5px}
.banner-warn-box{background:var(--warn-bg);border:1px solid rgba(217,119,6,.3);border-radius:var(--radius-sm);padding:9px 12px;font-size:12.5px;color:var(--warn);margin-top:12px}
.form-grid{display:flex;flex-direction:column;gap:12px}
.field label{display:block;font-size:12px;color:var(--text-2);margin-bottom:4px;font-weight:600}
.field input,.field select{width:100%;border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:7px 10px;font-size:12.5px;outline:none;background:#fff;color:var(--text)}
.field input:focus,.field select:focus{border-color:var(--primary)}
.wiz-row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.sql-area{width:100%;border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:8px 10px;font-family:ui-monospace,SFMono-Regular,Consolas,Menlo,monospace;font-size:12px;line-height:1.7;resize:vertical;outline:none;background:#f8fafc;color:var(--text)}
.sql-area:focus{border-color:var(--primary)}
.req{color:var(--danger);font-style:normal}
</style>
