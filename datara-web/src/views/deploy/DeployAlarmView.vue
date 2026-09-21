<script setup lang="ts">
/**
 * M16 告警管理（/dep/alarm · 原型 m16-deploy.js #/dep/alarm）
 * 基础设施告警列表（dataStore.deployAlarms）：关键字 + 级别/状态筛选；
 * 行操作：处置（抽屉：处置方式 + 处置说明 → status=fixed 持久化）/ 屏蔽（status=ignored）
 * / 解除屏蔽 / 详情；顶部工具栏「运维操作」跳转。
 * 通知渠道（抽屉）：邮件 SMTP / 短信网关参数配置 + 发送测试（模拟回执），
 * 测试成功同时写入站内消息（notifications），演示「渠道动作 → 消息中心」闭环。
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import ListFilterPanel from '../../components/ListFilterPanel.vue'
import type { Facet } from '../../components/ListFilterPanel.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { dataStore, ST } from '../../services/mock/dataStore'
import { localTime } from '../../services/mock/timeUtil'
import type { CollectionKey, DeployAlarm, Notification } from '../../services/types'

const router = useRouter()

const rows = ref<DeployAlarm[]>([])
const keyword = ref('')
const filters = ref<Record<string, string>>({ level: '', status: '' })

const LEVELS = [
  { v: 'err', t: '严重' },
  { v: 'warn', t: '警告' },
  { v: 'info', t: '提示' },
]
const STATUS_OPTS = [
  { v: 'pending', t: '待处理' },
  { v: 'fixed', t: '已恢复' },
  { v: 'ignored', t: '已忽略' },
]
const LEVEL_LABEL: Record<string, string> = { err: '严重', warn: '警告', info: '提示' }

/* ---- 左侧筛选面板 facets ---- */
const facets = computed<Facet[]>(() => [
  { key: 'level', label: '级别', options: LEVELS },
  { key: 'status', label: '状态', options: STATUS_OPTS },
])

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return rows.value.filter((r) => {
    if (filters.value.level && r.level !== filters.value.level) return false
    if (filters.value.status && r.status !== filters.value.status) return false
    if (!kw) return true
    return [r.id, r.comp, r.title, r.desc].some((s) => s.toLowerCase().includes(kw))
  })
})

/* ---- 统计 ---- */
const pendingCount = computed(() => rows.value.filter((a) => a.status === 'pending').length)
const fixedCount = computed(() => rows.value.filter((a) => a.status === 'fixed').length)

async function reload() {
  // 必须展开为新数组：dataStore.save 原地修改数组，list 返回同一引用
  rows.value = [...((await dataStore.list<DeployAlarm>('deployAlarms')) ?? [])]
}
onMounted(reload)

function levelPill(l: string): string {
  return l === 'err' ? 'err' : l === 'warn' ? 'warn' : 'off'
}
function levelLabel(l: string): string {
  return LEVEL_LABEL[l] ?? l
}
/* pending→待处理 fixed→已恢复（对齐原型 st('recovered')） ignored→已忽略 */
function statusSt(s: string): { cls: string; label: string } {
  const key = s === 'fixed' ? 'recovered' : s
  return { cls: ST[key]?.cls ?? 'st-gray', label: ST[key]?.label ?? s }
}
function goOps(): void {
  router.push('/dep/ops')
}

/* ---- 处置（抽屉） ---- */
const handleVisible = ref(false)
const handleRow = ref<DeployAlarm | null>(null)
const handleWay = ref('auto')
const handleNote = ref('')
const WAYS = [
  { v: 'auto', t: '确认自恢复（记录观察）' },
  { v: 'scale', t: '扩容/清理（磁盘清理、并行度调整）' },
  { v: 'ticket', t: '转运维工单' },
]

function openHandle(a: DeployAlarm): void {
  handleRow.value = a
  handleWay.value = 'auto'
  handleNote.value = ''
  handleVisible.value = true
}
async function saveHandle(): Promise<void> {
  const a = handleRow.value
  if (!a) return
  if (!handleNote.value.trim()) {
    ElMessage.warning('请填写处置说明')
    return
  }
  await dataStore.save<DeployAlarm>('deployAlarms', { ...a, status: 'fixed' })
  handleVisible.value = false
  ElMessage.success('告警已处置并恢复，观察期 24h')
  await reload()
}

/* ---- 屏蔽 / 解除屏蔽 ---- */
async function ignoreAlarm(a: DeployAlarm): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认屏蔽告警「${a.title}」？屏蔽后不再进入待处理列表。`, '屏蔽告警', {
      confirmButtonText: '确认屏蔽', cancelButtonText: '取消', type: 'warning',
    })
  } catch {
    return
  }
  await dataStore.save<DeployAlarm>('deployAlarms', { ...a, status: 'ignored' })
  ElMessage.success(`告警「${a.title}」已屏蔽`)
  await reload()
}
async function unignoreAlarm(a: DeployAlarm): Promise<void> {
  await dataStore.save<DeployAlarm>('deployAlarms', { ...a, status: 'pending' })
  ElMessage.success(`告警「${a.title}」已恢复为待处理`)
  await reload()
}

/* ---- 详情（已恢复/已忽略） ---- */
const detailVisible = ref(false)
const detailRow = ref<DeployAlarm | null>(null)
function openDetail(a: DeployAlarm): void {
  detailRow.value = a
  detailVisible.value = true
}

/* ============================================================
 * 告警通知渠道配置（邮件 SMTP / 短信网关；飞书/钉钉规划中占位）
 * 集合 'channelCfg' 为单对象集合：get 读取回填 / save 按 id 原地替换。
 * 测试发送为原型模拟（setTimeout 延时 + 固定回执编号，不用随机数），
 * 成功后写一条站内消息（notifications，id 用 Date.now()）形成闭环。
 * ============================================================ */
/** 渠道配置结构（与 dataStore 'channelCfg' 契约一致） */
interface ChannelCfg {
  mail: { host: string; port: number; ssl: boolean; account: string; password: string; sender: string }
  sms: { provider: string; accessKey: string; secret: string; sign: string; template: string }
}
/** 抽屉打开读不到配置时的默认值（与契约 seed 结构逐字一致） */
const DEFAULT_CHANNEL_CFG: ChannelCfg = {
  mail: { host: 'smtp.datara.cn', port: 465, ssl: true, account: 'notify@datara.cn', password: '******', sender: 'notify@datara.cn' },
  sms: { provider: '阿里云', accessKey: 'LTAI5t***', secret: '******', sign: '数据治理平台', template: 'SMS_466150001' },
}
/** 主控稍后会在 CollectionKey union 中补充 'channelCfg'，此处先断言兼容（不改 types.ts） */
const COL_CHANNEL = 'channelCfg' as unknown as CollectionKey

const chVisible = ref(false)
const chSaving = ref(false)
const chCfg = ref<ChannelCfg>(JSON.parse(JSON.stringify(DEFAULT_CHANNEL_CFG)))

/** 打开渠道抽屉：读取已保存配置回填，读不到用默认结构 */
async function openChannel(): Promise<void> {
  chVisible.value = true
  const saved = await dataStore.get<ChannelCfg>(COL_CHANNEL)
  chCfg.value = JSON.parse(JSON.stringify(saved ?? DEFAULT_CHANNEL_CFG))
}

/** 保存渠道配置（全平台告警规则共用） */
async function saveChannel(): Promise<void> {
  const m = chCfg.value.mail
  const s = chCfg.value.sms
  if (!m.host.trim()) { ElMessage.warning('SMTP 服务器不能为空'); return }
  if (!m.port || m.port < 1 || m.port > 65535) { ElMessage.warning('端口需在 1-65535 之间'); return }
  if (!m.password.trim()) { ElMessage.warning('SMTP 授权码不能为空'); return }
  if (!s.accessKey.trim()) { ElMessage.warning('短信 AccessKey 不能为空'); return }
  if (!s.sign.trim()) { ElMessage.warning('短信签名不能为空'); return }
  if (!s.template.trim()) { ElMessage.warning('短信模板 Code 不能为空'); return }
  chSaving.value = true
  await dataStore.save(COL_CHANNEL, JSON.parse(JSON.stringify(chCfg.value)))
  chSaving.value = false
  ElMessage.success('渠道配置已保存（全平台告警规则共用）')
}

/* ---- 测试发送（模拟投递：固定回执编号 + 固定耗时，成功后写站内消息） ---- */
/** 测试回执展示结构 */
interface TestReceipt { to: string; refId: string; cost: string; note: string }
const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const MAIL_MSG_ID = 'MSG-20260914-0001'
const SMS_BIZ_ID = 'BI20260914XXX'

const testMailTo = ref('duty@datara.cn')
const mailTesting = ref(false)
const mailReceipt = ref<TestReceipt | null>(null)

/** 发送测试邮件：email 校验 → 模拟 800ms → 回执区 + 站内消息 */
async function sendTestMail(): Promise<void> {
  const to = testMailTo.value.trim()
  if (!EMAIL_RE.test(to)) { ElMessage.warning('请输入正确的测试邮箱地址'); return }
  mailTesting.value = true
  mailReceipt.value = null
  await sleep(800)
  mailReceipt.value = { to, refId: MAIL_MSG_ID, cost: '耗时 823ms', note: '已投递至 SMTP 服务器，等待对方服务器回执' }
  mailTesting.value = false
  await dataStore.save<Notification>('notifications', {
    id: Date.now(), icon: '📨', cls: 'info', title: '测试邮件已发送',
    desc: `通道 ${chCfg.value.mail.host}:${chCfg.value.mail.port} 验证通过，回执 ${MAIL_MSG_ID}`,
    time: localTime(),
  })
  ElMessage.success(`测试邮件已发送，回执 ${MAIL_MSG_ID}`)
}

const testSmsTo = ref('138****8001')
const smsTesting = ref(false)
const smsReceipt = ref<TestReceipt | null>(null)

/** 脱敏占位代表内置默认号码；其余按 11 位真实号码送校验 */
function resolveSmsTarget(): string {
  const v = testSmsTo.value.trim()
  return v.includes('*') ? '13812348001' : v
}
/** 手机号脱敏展示：保留前 3 后 4 */
function maskPhone(p: string): string {
  return p.length === 11 ? `${p.slice(0, 3)}****${p.slice(7)}` : p
}

/** 发送测试短信：11 位校验 → 模拟 600ms → 回执区 + 站内消息 */
async function sendTestSms(): Promise<void> {
  const target = resolveSmsTarget()
  if (!/^1\d{10}$/.test(target)) { ElMessage.warning('请输入 11 位测试手机号'); return }
  smsTesting.value = true
  smsReceipt.value = null
  await sleep(600)
  smsReceipt.value = { to: maskPhone(target), refId: SMS_BIZ_ID, cost: '计费 1 条', note: '网关已受理' }
  smsTesting.value = false
  await dataStore.save<Notification>('notifications', {
    id: Date.now(), icon: '📨', cls: 'info', title: '测试短信已发送',
    desc: `通道 ${chCfg.value.sms.provider}短信网关验证通过，回执 ${SMS_BIZ_ID}`,
    time: localTime(),
  })
  ElMessage.success(`测试短信已发送，回执 ${SMS_BIZ_ID}`)
}
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ListFilterPanel
      v-model:keyword="keyword"
      v-model:filters="filters"
      :facets="facets"
      placeholder="搜索告警"
      :result-count="filtered.length"
      :total-count="rows.length"
    />
    <div style="flex:1;min-width:0">
    <!-- 页头 + 顶部工具栏 -->
    <div class="page-head">
      <div>
        <div class="ph-title">部署运维告警</div>
        <div class="ph-desc">基础设施告警：磁盘/消费积压/Checkpoint 等，待处理告警需闭环处置</div>
      </div>
      <div class="ph-btns">
        <button class="op-btn ch-entry" @click="openChannel">通知渠道</button>
        <button class="tb-new" @click="goOps">运维操作</button>
      </div>
    </div>

    <!-- 统计卡 -->
    <div class="stat-grid3">
      <div class="stat-card">
        <span class="type-icon" style="background:#d97706">⚑</span>
        <div><div class="stat-num">{{ pendingCount }}</div><div class="stat-label">待处理告警</div></div>
      </div>
      <div class="stat-card">
        <span class="type-icon" style="background:var(--success)">✓</span>
        <div><div class="stat-num">{{ fixedCount }}</div><div class="stat-label">已恢复</div></div>
      </div>
      <div class="stat-card">
        <span class="type-icon" style="background:#475569">⇩</span>
        <div><div class="stat-num">{{ rows.length }}</div><div class="stat-label">告警总数（今日）</div></div>
      </div>
    </div>

    <!-- 告警列表 -->
    <div class="card" style="padding:16px">
      <div class="tbl-toolbar">
        <span class="sec-head">告警列表</span>
        <span class="pill info">{{ filtered.length }} / {{ rows.length }}</span>
        <span class="spacer" />
      </div>

      <table class="tbl">
        <thead>
          <tr>
            <th>告警</th><th>组件</th><th>级别</th><th>时间</th><th>渠道</th><th>状态</th><th style="width:210px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in filtered" :key="r.id">
            <td>
              <b>{{ r.title }}</b>
              <div class="cell-sub">{{ r.id }} · {{ r.desc }}</div>
            </td>
            <td><span class="pill info">{{ r.comp }}</span></td>
            <td><span class="pill" :class="levelPill(r.level)">{{ levelLabel(r.level) }}</span></td>
            <td style="color:var(--text-2)">{{ r.time }}</td>
            <td>{{ r.channel }}</td>
            <td>
              <span class="st" :class="statusSt(r.status).cls"><span class="dot" />{{ statusSt(r.status).label }}</span>
            </td>
            <td>
              <template v-if="r.status === 'pending'">
                <button class="op-btn primary" @click="openHandle(r)">处置</button>
                <button class="op-btn" @click="ignoreAlarm(r)">屏蔽</button>
              </template>
              <template v-else-if="r.status === 'ignored'">
                <button class="op-btn primary" @click="openDetail(r)">详情</button>
                <button class="op-btn" @click="unignoreAlarm(r)">解除屏蔽</button>
              </template>
              <template v-else>
                <button class="op-btn primary" @click="openDetail(r)">详情</button>
              </template>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-if="filtered.length === 0" class="empty">
        未找到匹配的告警，请调整筛选条件
      </div>
    </div>

    <!-- 处置抽屉 -->
    <el-drawer v-model="handleVisible" :title="handleRow ? `告警处置 - ${handleRow.title}` : '告警处置'" size="440px">
      <div v-if="handleRow">
        <div class="banner warn"><span class="b-ico">⚠</span><span>{{ handleRow.desc }}</span></div>
        <div class="banner info"><span class="b-ico">📨</span><span>处置完成后将按告警规则渠道「{{ handleRow.channel }}」推送通知（渠道配置见顶部工具栏「通知渠道」）</span></div>
        <div class="f-cap">处置方式</div>
        <label v-for="w in WAYS" :key="w.v" class="radio-line">
          <input type="radio" :value="w.v" v-model="handleWay" />
          <span>{{ w.t }}</span>
        </label>
        <div class="f-cap" style="margin-top:14px">处置说明 *</div>
        <textarea v-model="handleNote" class="note" rows="3" placeholder="如：已执行磁盘清理，使用率 82% → 61%" />
        <div style="margin-top:16px;display:flex;gap:8px">
          <button class="tb-new" @click="saveHandle">完成处置</button>
          <button class="op-btn" @click="handleVisible = false">取消</button>
        </div>
      </div>
    </el-drawer>

    <!-- 详情弹窗 -->
    <el-dialog v-model="detailVisible" :title="detailRow ? `告警详情 - ${detailRow.title}` : '告警详情'" width="480px">
      <div v-if="detailRow">
        <div class="d-grid">
          <div>告警编号：<span class="mono">{{ detailRow.id }}</span></div>
          <div>级别：<span class="pill" :class="levelPill(detailRow.level)">{{ levelLabel(detailRow.level) }}</span></div>
          <div>组件：<span class="pill info">{{ detailRow.comp }}</span></div>
          <div>时间：<span style="color:var(--text-2)">{{ detailRow.time }}</span></div>
          <div>渠道：{{ detailRow.channel }}</div>
          <div>状态：{{ statusSt(detailRow.status).label }}</div>
        </div>
        <div class="d-cap">告警描述</div>
        <div class="d-desc">{{ detailRow.desc }}</div>
      </div>
      <template #footer>
        <button class="tb-new" @click="detailVisible = false">关闭</button>
      </template>
    </el-dialog>

    <!-- 通知渠道配置抽屉（邮件 SMTP / 短信网关；飞书/钉钉规划中占位） -->
    <el-drawer v-model="chVisible" title="告警通知渠道配置" size="560px">
      <!-- 邮件（SMTP） -->
      <div class="ch-card">
        <div class="ch-head">
          <span class="ch-name">邮件（SMTP）</span>
          <span class="pill info">已启用</span>
        </div>
        <div class="ch-grid">
          <div>
            <div class="f-cap">SMTP 服务器</div>
            <input v-model="chCfg.mail.host" class="ch-inp" placeholder="如 smtp.datara.cn" />
          </div>
          <div>
            <div class="f-cap">端口</div>
            <input v-model.number="chCfg.mail.port" class="ch-inp" type="number" min="1" max="65535" placeholder="465" />
          </div>
          <div>
            <div class="f-cap">SSL 加密</div>
            <el-switch v-model="chCfg.mail.ssl" />
          </div>
          <div>
            <div class="f-cap">账号</div>
            <input v-model="chCfg.mail.account" class="ch-inp" placeholder="notify@datara.cn" />
          </div>
          <div>
            <div class="f-cap">授权码</div>
            <el-input v-model="chCfg.mail.password" type="password" show-password placeholder="******" />
          </div>
          <div>
            <div class="f-cap">发件人</div>
            <input v-model="chCfg.mail.sender" class="ch-inp" placeholder="notify@datara.cn" />
          </div>
        </div>
        <div class="f-cap" style="margin-top:12px">发送测试</div>
        <div class="ch-test">
          <input v-model="testMailTo" class="ch-inp" placeholder="测试邮箱，如 duty@datara.cn" />
          <button class="tb-new" :disabled="mailTesting" @click="sendTestMail">{{ mailTesting ? '发送中…' : '发送测试邮件' }}</button>
        </div>
        <div v-if="mailReceipt" class="ch-receipt">
          <div class="ch-rc-top">
            <span class="pill ok">SENT</span>
            <span class="mono ch-rc-id">{{ mailReceipt.refId }}</span>
            <span class="ch-rc-cost">{{ mailReceipt.cost }}</span>
          </div>
          <div class="ch-rc-note">收件 {{ mailReceipt.to }} · {{ mailReceipt.note }}</div>
        </div>
      </div>

      <!-- 短信网关 -->
      <div class="ch-card">
        <div class="ch-head">
          <span class="ch-name">短信网关</span>
          <span class="pill info">已启用</span>
        </div>
        <div class="ch-grid">
          <div>
            <div class="f-cap">服务商</div>
            <el-select v-model="chCfg.sms.provider" style="width:100%">
              <el-option label="阿里云" value="阿里云" />
              <el-option label="华为云" value="华为云" />
              <el-option label="自定义HTTP" value="自定义HTTP" />
            </el-select>
          </div>
          <div>
            <div class="f-cap">AccessKey</div>
            <input v-model="chCfg.sms.accessKey" class="ch-inp" placeholder="LTAI5t***" />
          </div>
          <div>
            <div class="f-cap">Secret</div>
            <el-input v-model="chCfg.sms.secret" type="password" show-password placeholder="******" />
          </div>
          <div>
            <div class="f-cap">短信签名</div>
            <input v-model="chCfg.sms.sign" class="ch-inp" placeholder="数据治理平台" />
          </div>
          <div>
            <div class="f-cap">模板 Code</div>
            <input v-model="chCfg.sms.template" class="ch-inp" placeholder="SMS_466150001" />
          </div>
        </div>
        <div class="f-cap" style="margin-top:12px">发送测试</div>
        <div class="ch-test">
          <input v-model="testSmsTo" class="ch-inp" placeholder="11 位手机号，默认 138****8001" />
          <button class="tb-new" :disabled="smsTesting" @click="sendTestSms">{{ smsTesting ? '发送中…' : '发送测试短信' }}</button>
        </div>
        <div v-if="smsReceipt" class="ch-receipt">
          <div class="ch-rc-top">
            <span class="pill ok">SENT</span>
            <span class="mono ch-rc-id">{{ smsReceipt.refId }}</span>
            <span class="ch-rc-cost">{{ smsReceipt.cost }}</span>
          </div>
          <div class="ch-rc-note">收件 {{ smsReceipt.to }} · {{ smsReceipt.note }}</div>
        </div>
      </div>

      <!-- 规划中渠道占位（不做配置） -->
      <div class="ch-card ch-plan">
        <div class="ch-head">
          <span class="ch-name">飞书机器人 Webhook</span>
          <span class="pill off">规划中</span>
        </div>
        <div class="ch-plan-desc">飞书群机器人推送告警，下版本开放配置</div>
      </div>
      <div class="ch-card ch-plan">
        <div class="ch-head">
          <span class="ch-name">钉钉机器人</span>
          <span class="pill off">规划中</span>
        </div>
        <div class="ch-plan-desc">钉钉群机器人推送告警，下版本开放配置</div>
      </div>

      <div style="margin-top:16px;display:flex;gap:8px">
        <button class="tb-new" :disabled="chSaving" @click="saveChannel">保存配置</button>
        <button class="op-btn" @click="chVisible = false">取消</button>
      </div>
    </el-drawer>
    </div>
  </div>
</template>

<style scoped>
/* ---- 页头 / 统计 ---- */
.page-head{display:flex;align-items:flex-start;gap:16px;margin-bottom:14px}
.ph-title{font-size:17px;font-weight:700}
.ph-desc{font-size:12px;color:var(--text-3);margin-top:3px}
.ph-btns{margin-left:auto;display:flex;gap:8px;flex-shrink:0}
.stat-grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:14px}
.stat-card{display:flex;align-items:center;gap:12px;background:var(--card);border:1px solid var(--border);border-radius:var(--radius-lg);padding:13px 15px}
.type-icon{width:36px;height:36px;border-radius:9px;display:flex;align-items:center;justify-content:center;color:#fff;font-size:14px;flex-shrink:0}
.stat-num{font-size:19px;font-weight:700;line-height:1.25}
.stat-label{font-size:11.5px;color:var(--text-3)}
/* ---- 表格 ---- */
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;padding:9px 10px;background:var(--bg);color:var(--text-2);font-weight:600;border-bottom:1px solid var(--border)}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--border)}
.tbl tr:hover td{background:var(--primary-light)}
.cell-sub{font-size:11px;color:var(--text-3)}
.kw{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 10px;font-size:12.5px;width:200px;outline:none}
.kw:focus{border-color:var(--primary)}
.sel{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 8px;font-size:12.5px;background:#fff;outline:none;color:var(--text-2)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
.op-btn.primary{color:var(--primary);border-color:rgba(22,104,220,.4);font-weight:600}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease)}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
/* ---- 处置抽屉 ---- */
.banner{display:flex;gap:8px;align-items:flex-start;border-radius:var(--radius);padding:9px 12px;font-size:12.5px;margin-bottom:14px}
.banner.warn{background:var(--warn-bg);color:var(--warn)}
.b-ico{font-weight:700}
.f-cap{font-size:12.5px;color:var(--text-2);font-weight:600;margin-bottom:7px}
.radio-line{display:flex;gap:8px;align-items:center;padding:7px 10px;border:1px solid var(--border);border-radius:7px;margin-bottom:7px;cursor:pointer;font-size:12.5px}
.note{width:100%;border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:8px 10px;font-size:12.5px;font-family:inherit;outline:none;resize:vertical}
.note:focus{border-color:var(--primary)}
/* ---- 详情 ---- */
.d-grid{display:grid;grid-template-columns:1fr 1fr;gap:7px 20px;font-size:12.5px;margin-bottom:14px}
.d-cap{font-size:12px;color:var(--text-2);font-weight:600;margin-bottom:6px}
.d-desc{background:var(--bg);border-radius:var(--radius);padding:10px 12px;font-size:12.5px;color:var(--text-2);line-height:1.7}
.banner.info{background:var(--info-bg);color:var(--info)}
/* ---- 通知渠道配置抽屉 ---- */
.ch-entry{padding:7px 14px;font-size:12.5px;border-radius:var(--radius-sm)}
.ch-card{border:1px solid var(--border);border-radius:9px;padding:13px 14px;margin-bottom:12px;background:var(--card)}
.ch-plan{background:var(--bg);opacity:.75}
.ch-head{display:flex;align-items:center;gap:8px;margin-bottom:10px}
.ch-name{font-weight:700;font-size:13px}
.ch-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px 14px}
.ch-inp{width:100%;border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:7px 10px;font-size:12.5px;outline:none;background:#fff;color:var(--text-2)}
.ch-inp:focus{border-color:var(--primary)}
.ch-test{display:flex;gap:8px}
.ch-test .ch-inp{flex:1;min-width:0}
.ch-test .tb-new{flex-shrink:0}
.ch-receipt{margin-top:9px;border:1px dashed var(--border-strong);border-radius:var(--radius);padding:9px 11px;background:var(--bg)}
.ch-rc-top{display:flex;align-items:center;gap:8px}
.ch-rc-id{font-size:12px;color:var(--text-2)}
.ch-rc-cost{margin-left:auto;font-size:11.5px;color:var(--text-3)}
.ch-rc-note{margin-top:6px;font-size:11.5px;color:var(--text-3)}
.ch-plan-desc{font-size:12px;color:var(--text-3)}
.tb-new:disabled{opacity:.6;cursor:not-allowed}
</style>
