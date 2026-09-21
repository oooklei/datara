<script setup lang="ts">
/**
 * M03 数据源注册/编辑向导（I4 §3.3 接真）
 * 三步：① 类型选择（mysql/greatdb/file）→ ② 连接参数 / 文件参数动态表单 → ③ 保存并测试。
 * - greatdb 表单提示「MySQL 协议兼容」；file 表单=格式/路径选择器（GET /datasources/files）/编码/分隔符/表头/sheet。
 * - 编辑模式（editRow 传入）：预填除密码外的全量字段；密码留空 = 保持原密码（后端语义），
 *   避免旧值/短密码被静默重放；密码框支持眼睛图标切换明文/密文查看。
 * - 完成 = 保存 + 连通测试（POST /{id}/test），结果 banner 展示；失败可返回改参重试（创建后重试走测试接口）。
 */
import { ref, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { View, Hide } from '@element-plus/icons-vue'
import {
  createDataSource, updateDataSource, testDataSource, listDataFiles,
  type DsRow, type DsBody, type DsTestResult,
} from '../../services/datasourceApi'
import { dsTypeColor, dsTypeShort } from '../../services/mock/dsUtils'

const visible = defineModel<boolean>('visible', { default: false })
const props = defineProps<{ editRow?: DsRow | null }>()
const emit = defineEmits<{ saved: [] }>()

const step = ref(0)
const steps = ['选择类型', '连接信息', '保存并测试']
const isEdit = computed(() => !!props.editRow)

/** 窗口标题：注册流程输入数据源名称后，后续所有步骤标题带上名称（如「注册数据源:dpkg-mysql-src」） */
const dialogTitle = computed(() => {
  if (isEdit.value) return '编辑数据源'
  const n = name.value.trim()
  return n ? `注册数据源:${n}` : '注册数据源'
})

/* ---- ① 类型 ---- */
interface TypeCard { code: string; name: string; port: number; group: string; tip?: string }
const DS_TYPES: TypeCard[] = [
  { code: 'mysql', name: 'MySQL', port: 3306, group: '连接型数据库' },
  { code: 'greatdb', name: '万里 GreatDB', port: 3316, group: '连接型数据库', tip: 'MySQL 协议兼容' },
  { code: 'file', name: '文件源', port: 0, group: '文件源', tip: 'CSV / TXT / Excel' },
]
const pickedType = ref<string>('')
const name = ref('')

/* ---- ② 连接参数（mysql/greatdb） ---- */
const host = ref('')
const port = ref<number>(3306)
const db = ref('')
const user = ref('')
const pwd = ref('')
const showPwd = ref(false)
const env = ref('生产')
const group = ref('数仓')

const envOptions = ['生产', '测试', '开发']
const groupOptions = ['交易域', '经营域', '财务域', '商品域', '数仓', '消息', '公共']

/* ---- ② 文件参数（file） ---- */
const fFormat = ref('csv')
const fPath = ref('')
const fEncoding = ref('utf-8')
const fDelimiter = ref(',')
const fHeader = ref(true)
const fSheet = ref('')
const filePickerVisible = ref(false)
const fileList = ref<string[]>([])
const fileListLoading = ref(false)

const encodingOptions = ['utf-8', 'gbk', 'gb18030']
const formatOptions = [
  { v: 'csv', t: 'CSV（逗号分隔）' },
  { v: 'txt', t: 'TXT（自定义分隔符）' },
  { v: 'excel', t: 'Excel（.xlsx）' },
]

/* ---- ③ 保存并测试 ---- */
const saving = ref(false)
const testing = ref(false)
const savedId = ref<number | null>(null)
const testResult = ref<DsTestResult | null>(null)

watch(visible, (v) => {
  if (v) reset()
})

function reset() {
  step.value = 0
  savedId.value = null
  testResult.value = null
  saving.value = false
  testing.value = false
  name.value = ''
  host.value = ''
  port.value = 3306
  db.value = ''
  user.value = ''
  pwd.value = ''
  showPwd.value = false
  env.value = '生产'
  group.value = '数仓'
  fFormat.value = 'csv'
  fPath.value = ''
  fEncoding.value = 'utf-8'
  fDelimiter.value = ','
  fHeader.value = true
  fSheet.value = ''
  const r = props.editRow
  if (r) {
    step.value = 1 // 编辑直接进参数步
    pickedType.value = r.type
    name.value = r.name
    host.value = r.host ?? ''
    port.value = r.port ?? 3306
    db.value = r.db ?? ''
    user.value = r.user ?? ''
    // 密码不预填：留空 = 保持原密码（防短密码/旧值被静默重放）
    env.value = r.env ?? '生产'
    group.value = r.group ?? '数仓'
    const p = (r.params ?? {}) as Record<string, unknown>
    fFormat.value = String(p.format ?? 'csv')
    fPath.value = String(p.path ?? '')
    fEncoding.value = String(p.encoding ?? 'utf-8')
    fDelimiter.value = String(p.delimiter ?? ',')
    fHeader.value = String(p.header ?? 'true') !== 'false' && p.header !== false
    fSheet.value = p.sheet == null ? '' : String(p.sheet)
  } else {
    pickedType.value = ''
  }
}

function pickType(t: TypeCard) {
  pickedType.value = t.code
  if (t.port > 0) port.value = t.port
}

function next() {
  if (step.value === 0) {
    if (!pickedType.value) {
      ElMessage.warning('请先选择数据源类型')
      return
    }
    if (!name.value.trim()) {
      ElMessage.warning('请填写数据源名称')
      return
    }
    step.value = 1
  } else if (step.value === 1) {
    if (pickedType.value !== 'file' && !host.value.trim()) {
      ElMessage.warning('请填写主机地址')
      return
    }
    if (pickedType.value === 'file' && !fPath.value.trim()) {
      ElMessage.warning('请填写或选择文件路径')
      return
    }
    step.value = 2
  }
}

function prev() {
  if (step.value > 0) step.value--
}

/* ---- 文件路径选择器（GET /datasources/files） ---- */
async function openFilePicker() {
  filePickerVisible.value = true
  fileListLoading.value = true
  try {
    fileList.value = await listDataFiles()
  } catch (err) {
    fileList.value = []
    ElMessage.error(err instanceof Error ? err.message : '共享卷文件清单获取失败')
  } finally {
    fileListLoading.value = false
  }
}

function pickFile(p: string) {
  fPath.value = p
  filePickerVisible.value = false
}

function buildBody(): DsBody {
  const body: DsBody = {
    name: name.value.trim(),
    type: pickedType.value,
    env: env.value,
    group: group.value,
    tags: [],
  }
  if (pickedType.value === 'file') {
    body.params = {
      format: fFormat.value,
      path: fPath.value.trim(),
      encoding: fEncoding.value,
      delimiter: fDelimiter.value || ',',
      header: fHeader.value,
      sheet: fSheet.value.trim() || undefined,
    }
  } else {
    body.host = host.value.trim()
    body.port = port.value
    body.db = db.value.trim()
    body.user = user.value.trim()
    // pwd 仅在有输入时携带：编辑留空 = 保持原密码（后端语义）；新建留空 = 空密码
    if (pwd.value) body.pwd = pwd.value
  }
  return body
}

async function runTest(id: number): Promise<DsTestResult> {
  testing.value = true
  try {
    const res = await testDataSource(id)
    testResult.value = res
    return res
  } finally {
    testing.value = false
  }
}

/* ---- 保存并测试 ---- */
async function saveAndTest() {
  if (saving.value || testing.value) return
  saving.value = true
  try {
    const body = buildBody()
    let id: number
    if (isEdit.value && props.editRow) {
      await updateDataSource(props.editRow.id, body)
      id = props.editRow.id
    } else if (savedId.value !== null) {
      // 本会话已创建（首次测试离线后回退改参）：更新已存行再重测，
      // 避免重复调用新建接口触发后端「数据源名称已存在」误报。
      await updateDataSource(savedId.value, body)
      id = savedId.value
    } else {
      const row = await createDataSource(body)
      id = row.id
      savedId.value = id
    }
    const res = await runTest(id)
    if (res.status === 'online') {
      ElMessage.success(`已保存并测试在线（${res.elapsedMs}ms）`)
      visible.value = false
      emit('saved')
    } else {
      ElMessage.warning('已保存，但连通测试失败，可调整参数重试')
    }
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '保存失败')
  } finally {
    saving.value = false
  }
}

/** 创建后测试失败场景：仅重测（不再重复创建） */
async function retestOnly() {
  if (savedId.value === null || testing.value) return
  try {
    const res = await runTest(savedId.value)
    if (res.status === 'online') {
      ElMessage.success('连通在线')
      visible.value = false
      emit('saved')
    }
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '测试失败')
  }
}
</script>

<template>
  <el-dialog v-model="visible" :title="dialogTitle" width="640px" :close-on-click-modal="false" draggable>
    <el-steps :active="step" align-center finish-status="success" style="margin-bottom:18px">
      <el-step v-for="(s, i) in steps" :key="i" :title="s" />
    </el-steps>

    <!-- ① 类型选择 -->
    <div v-if="step === 0">
      <div class="wiz-tip">类型框架（I4 §3.1）：MySQL / 万里 GreatDB（同驱动 MySQL 协议兼容）/ 文件源（共享卷 /datara/files）。</div>
      <template v-for="g in ['连接型数据库', '文件源']" :key="g">
        <div class="wiz-group">{{ g }}</div>
        <div class="wiz-grid">
          <div
            v-for="t in DS_TYPES.filter((x) => x.group === g)"
            :key="t.code"
            class="wiz-card"
            :class="{ picked: pickedType === t.code }"
            @click="pickType(t)"
          >
            <span class="type-icon" :style="{ background: dsTypeColor(t.code) }">{{ dsTypeShort(t.name) }}</span>
            <div>
              <b style="font-size:13px">{{ t.name }}</b>
              <div style="font-size:11px;color:var(--text-3)">
                {{ t.tip || `默认端口 ${t.port}` }}
              </div>
            </div>
          </div>
        </div>
      </template>
      <div class="field" style="margin-top:14px">
        <label>数据源名称</label>
        <input v-model="name" placeholder="如：万里GreatDB-生产业务库" />
      </div>
    </div>

    <!-- ② 连接参数 -->
    <div v-else-if="step === 1" class="wiz-form">
      <template v-if="pickedType !== 'file'">
        <div v-if="pickedType === 'greatdb'" class="wiz-tip">万里 GreatDB 与 MySQL 同驱动：MySQL 协议兼容，默认端口 3316。</div>
        <div class="field">
          <label>主机地址</label>
          <input v-model="host" placeholder="IP或域名" />
        </div>
        <div class="wiz-row">
          <div class="field">
            <label>端口</label>
            <input v-model.number="port" type="number" />
          </div>
          <div class="field">
            <label>数据库名</label>
            <input v-model="db" placeholder="如：gdb_biz" />
          </div>
        </div>
        <div class="wiz-row">
          <div class="field">
            <label>用户名</label>
            <input v-model="user" placeholder="如：datara_ro" />
          </div>
          <div class="field">
            <label>密码</label>
            <div class="pwd-wrap">
              <input
                v-model="pwd"
                :type="showPwd ? 'text' : 'password'"
                :placeholder="isEdit ? '留空则保持原密码' : '请输入密码'"
                autocomplete="new-password"
              />
              <button
                type="button"
                class="pwd-eye"
                :title="showPwd ? '隐藏密码' : '显示密码'"
                @click="showPwd = !showPwd"
              >
                <el-icon><View v-if="!showPwd" /><Hide v-else /></el-icon>
              </button>
            </div>
          </div>
        </div>
      </template>

      <!-- 文件参数动态表单（I4 §3.3） -->
      <template v-else>
        <div class="wiz-tip">文件源：仅允许共享卷 /datara/files 下的相对路径（越界路径后端拒绝）。CSV/TXT 流式逐行解析；Excel（.xlsx）read_only 流式。</div>
        <div class="wiz-row">
          <div class="field">
            <label>文件格式</label>
            <select v-model="fFormat">
              <option v-for="o in formatOptions" :key="o.v" :value="o.v">{{ o.t }}</option>
            </select>
          </div>
          <div class="field">
            <label>编码</label>
            <select v-model="fEncoding">
              <option v-for="e in encodingOptions" :key="e" :value="e">{{ e }}</option>
            </select>
          </div>
        </div>
        <div class="field">
          <label>文件路径（/datara/files 相对路径）</label>
          <div style="display:flex;gap:8px">
            <input v-model="fPath" placeholder="如：orders_20260901.csv" style="flex:1" />
            <button class="op-btn" @click="openFilePicker">浏览…</button>
          </div>
        </div>
        <div class="wiz-row">
          <div class="field">
            <label>分隔符（CSV/TXT；支持多字符）</label>
            <input v-model="fDelimiter" placeholder="如：, 或 | 或 \t" />
          </div>
          <div class="field">
            <label>首行为表头</label>
            <el-switch v-model="fHeader" />
          </div>
        </div>
        <div v-if="fFormat === 'excel'" class="field">
          <label>Sheet 名（留空取第一个）</label>
          <input v-model="fSheet" placeholder="如：Sheet1" />
        </div>
      </template>

      <div class="wiz-row" style="margin-top:8px">
        <div class="field">
          <label>环境</label>
          <select v-model="env">
            <option v-for="e in envOptions" :key="e" :value="e">{{ e }}</option>
          </select>
        </div>
        <div class="field">
          <label>业务分组</label>
          <select v-model="group">
            <option v-for="g in groupOptions" :key="g" :value="g">{{ g }}</option>
          </select>
        </div>
      </div>
      <div class="wiz-tip">凭证安全管理能力在 P0 范围外（一期暂缓）；密码明文存储与回显（内部系统口径，09-18 裁定）。</div>
    </div>

    <!-- ③ 保存并测试 -->
    <div v-else class="wiz-form">
      <div class="sub-summary">
        <div class="sum-row"><span class="ik">类型</span><span>{{ pickedType }}</span></div>
        <div class="sum-row"><span class="ik">名称</span><span>{{ name || '-' }}</span></div>
        <div class="sum-row" v-if="pickedType !== 'file'">
          <span class="ik">目标</span><span class="mono">{{ host }}:{{ port }} / {{ db || '-' }}</span>
        </div>
        <div class="sum-row" v-else>
          <span class="ik">文件</span><span class="mono">/datara/files/{{ fPath }}</span>
        </div>
      </div>

      <div style="margin-top:14px;display:flex;gap:10px;align-items:center">
        <button class="tb-new" :disabled="saving || testing" @click="saveAndTest">
          {{ saving ? '保存中…' : testing ? '测试中…' : (isEdit ? '保存修改并测试' : (savedId !== null ? '保存并重新测试' : '完成注册并测试')) }}
        </button>
        <button v-if="savedId !== null && testResult" class="op-btn" :disabled="testing" @click="retestOnly">
          重新测试
        </button>
      </div>

      <div v-if="testResult" class="banner" :class="testResult.status === 'online' ? 'banner-success' : 'banner-danger'" style="margin-top:12px">
        <span class="b-ico">{{ testResult.status === 'online' ? '✓' : '✗' }}</span>
        <span>
          {{ testResult.status === 'online'
            ? `连通成功（${testResult.elapsedMs}ms）：${testResult.message}`
            : `连通失败：${testResult.message}` }}
        </span>
      </div>
      <div v-if="testResult && testResult.status === 'offline' && savedId !== null" class="wiz-tip" style="margin-top:10px">
        数据源已注册（#{{ savedId }}），可返回上一步调整参数后点「重新测试」。
      </div>
    </div>

    <template #footer>
      <button v-if="step > 0" class="op-btn" @click="prev">← 上一步</button>
      <button v-if="step < 2" class="tb-new" @click="next">下一步 →</button>
      <button v-else class="op-btn" @click="visible = false">关闭</button>
    </template>

    <!-- 共享卷文件选择器 -->
    <el-dialog v-model="filePickerVisible" title="选择共享卷文件（/datara/files）" width="480px" append-to-body>
      <div v-if="fileListLoading" class="empty-tip">加载中…</div>
      <div v-else-if="fileList.length === 0" class="empty-tip">共享卷暂无文件（宿主机 /mnt/lei/datara/files）</div>
      <div v-else class="file-list">
        <div v-for="p in fileList" :key="p" class="file-item mono" @click="pickFile(p)">{{ p }}</div>
      </div>
    </el-dialog>
  </el-dialog>
</template>

<style scoped>
.type-icon{width:36px;height:36px;border-radius:9px;display:flex;align-items:center;justify-content:center;color:#fff;font-size:14px;flex-shrink:0}
.wiz-tip{background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 10px;font-size:11.5px;color:var(--text-2);margin-bottom:10px}
.wiz-group{font-size:12px;color:var(--text-3);margin:10px 0 6px;font-weight:600}
.wiz-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.wiz-card{display:flex;gap:9px;align-items:center;border:1px solid var(--border-strong);border-radius:var(--radius);padding:10px;cursor:pointer;background:#fff}
.wiz-card:hover{border-color:var(--primary)}
.wiz-card.picked{border-color:var(--primary);box-shadow:0 0 0 2px rgba(22,104,220,.15)}
.wiz-form{max-width:640px}
.wiz-row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.field label{display:block;font-size:12px;color:var(--text-2);margin-bottom:4px;font-weight:600}
.field input,.field select{width:100%;border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:7px 10px;font-size:12.5px;outline:none;background:#fff;color:var(--text-1)}
.field input:focus,.field select:focus{border-color:var(--primary)}
.pwd-wrap{position:relative}
.pwd-wrap input{padding-right:36px}
.pwd-eye{position:absolute;right:4px;top:50%;transform:translateY(-50%);border:none;background:none;cursor:pointer;color:var(--text-3);padding:4px;display:flex;align-items:center}
.pwd-eye:hover{color:var(--primary)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:7px 12px;font-size:12px;cursor:pointer;color:var(--text-2)}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.op-btn:disabled{opacity:.55;cursor:not-allowed}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:8px 16px;font-size:12.5px;font-weight:500;cursor:pointer}
.tb-new:hover{background:var(--primary-hover)}
.tb-new:disabled{opacity:.55;cursor:not-allowed}
.sub-summary{background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px 12px}
.sum-row{display:flex;gap:10px;font-size:12.5px;padding:3px 0}
.sum-row .ik{width:48px;color:var(--text-3);flex-shrink:0}
.banner{display:flex;gap:8px;align-items:center;border-radius:var(--radius-sm);padding:10px 12px;font-size:12.5px}
.banner-success{background:#f0fdf4;border:1px solid #bbf7d0;color:#15803d}
.banner-danger{background:#fef2f2;border:1px solid #fecaca;color:#b91c1c}
.b-ico{font-weight:700}
.file-list{max-height:320px;overflow:auto}
.file-item{padding:7px 10px;border-bottom:1px solid var(--border);font-size:12px;cursor:pointer}
.file-item:hover{background:var(--primary-light);color:var(--primary)}
.empty-tip{padding:28px 12px;text-align:center;color:var(--text-3);font-size:12.5px}
.mono{font-family:var(--font-mono, monospace)}
</style>
