<script setup lang="ts">
/**
 * M04 字段设计器（对齐 prototype m04-model.js #/model/design/:id）
 * 字段表格增删改（本地编辑 + 「保存」全量提交，乐观锁 8006 冲突提示刷新），
 * 发布后字段冻结（只读态），DDL 预览（后端按引擎方言生成）+ 导出 + 物理化建表，维度建模建议。
 * 数据：modelApi + datasourceApi（真实后端；isMock 时服务内部走演示文档）。
 */
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getModel, saveFields, publishModel, getDdl, physicalize, getModelDicts,
  type ModelDetail, type ModelDicts,
} from '../../services/modelApi'
import { listDataSources, type DsRow } from '../../services/datasourceApi'
import { useAuthStore } from '../../stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const model = ref<ModelDetail | null>(null)
const rev = ref(1)
/** demo 形状行（模板字段表格沿用 {n,t,len,pk,pkPart,cmt,def}；加载契约→demo，保存反向适配） */
const rows = ref<{ n: string; t: string; len: string | number; pk: boolean; pkPart: boolean; cmt: string; def: string }[]>([])
const notFound = ref(false)
const dicts = ref<ModelDicts>({ layers: [], domains: [], engines: [] })
const datasources = ref<DsRow[]>([])
const userName = ref(auth.account?.name ?? auth.current.name)

const layers = computed(() => dicts.value.layers)
const engines = computed(() => dicts.value.engines)
/** 非草稿（已发布/已物理化/已投产）字段冻结，全页只读 */
const locked = computed(() => !!model.value && model.value.status !== 'draft')

const TYPE_OPTIONS = ['BIGINT', 'VARCHAR', 'CHAR', 'DECIMAL', 'DATETIME', 'DATE', 'INT', 'TINYINT', 'DOUBLE', 'TEXT']

/* reload 竞态序号：hash 导航复用实例/操作触发的并发 reload 后写胜出（晚到响应丢弃） */
let reloadSeq = 0

async function reload() {
  const seq = ++reloadSeq
  const id = String(route.params.id ?? '')
  try {
    const d = await getModel(id)
    if (seq !== reloadSeq) return
    model.value = d
    rev.value = d.version
    rows.value = d.fields.map((f) => ({
      n: f.name, t: f.dataType, len: f.length, pk: f.isPk, pkPart: f.isPartition, cmt: f.comment, def: f.defaultValue,
    }))
    notFound.value = false
  } catch {
    if (seq !== reloadSeq) return
    model.value = null
    notFound.value = true
    return
  }
  void refreshDdl()
  if (!dicts.value.layers.length || !datasources.value.length) {
    try {
      const [ds, srcs] = await Promise.all([getModelDicts(), listDataSources()])
      if (seq !== reloadSeq) return
      dicts.value = ds
      datasources.value = srcs
    } catch (e) {
      if (seq === reloadSeq) ElMessage.error((e as Error).message)
    }
  }
}

onMounted(reload)
// hash 导航复用实例时按 :id 重新加载
watch(() => route.params.id, reload)

function goBack() {
  router.push('/model/list')
}

/* ---- 字段编辑（只改本地 rows；「保存」全量提交 + 乐观锁） ---- */
function addField() {
  rows.value.push({ n: `field_${rows.value.length + 1}`, t: 'VARCHAR', len: 100, pk: false, pkPart: false, cmt: '', def: '' })
  ElMessage.success('已添加字段，请完善定义后点击「保存」')
}
async function delField(i: number) {
  try {
    await ElMessageBox.confirm(`确认删除字段「${rows.value[i]?.n ?? ''}」？`, '删除字段', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
  } catch {
    return
  }
  rows.value.splice(i, 1)
}
async function persist() {
  if (!model.value) return
  const fields = rows.value.map((r) => ({
    name: r.n, dataType: r.t, length: String(r.len ?? ''), precision: '',
    nullable: true, defaultValue: r.def, comment: r.cmt,
    isPk: r.pk, isPartition: r.pkPart, dictRef: '',
  }))
  try {
    const r = await saveFields(model.value.id, { rev: rev.value, fields })
    rev.value = r.rev
    ElMessage.success('字段已保存')
    void refreshDdl()
  } catch (e) {
    const err = e as Error & { code?: number; data?: { currentRev?: number } }
    if (err.code === 8006) {
      ElMessageBox.confirm('字段已被他人更新，是否刷新至最新版本？', '乐观锁冲突', {
        confirmButtonText: '刷新', cancelButtonText: '取消', type: 'warning',
      }).then(reload).catch(() => undefined)
      return
    }
    ElMessage.error(err.message)
  }
}

/* ---- 发布（仅草稿；发布后字段冻结，需开新修订才能再改） ---- */
async function doPublish() {
  if (!model.value) return
  try {
    await ElMessageBox.confirm('发布后字段将冻结，需开新修订才能再次修改。确认发布？', '发布模型', {
      confirmButtonText: '发布', cancelButtonText: '取消', type: 'warning',
    })
  } catch {
    return
  }
  try {
    await publishModel(model.value.id)
    ElMessage.success('已发布')
    await reload()
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

/* ---- DDL 预览（后端生成，页面预览与物理化弹窗共用 getDdl） ---- */
const ddlText = ref('')
const ddlNotes = ref<string[]>([])
let ddlSeq = 0

async function refreshDdl(engineId?: string) {
  const m = model.value
  if (!m) return
  const seq = ++ddlSeq
  try {
    const r = await getDdl(m.id, engineId)
    if (seq !== ddlSeq) return
    ddlText.value = r.ddl
    ddlNotes.value = r.notes
  } catch (e) {
    if (seq !== ddlSeq) return
    ddlText.value = ''
    ddlNotes.value = []
    ElMessage.error((e as Error).message)
  }
}
function download(name: string, content: string) {
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  URL.revokeObjectURL(url)
}

/* ---- 物理化建表 / 重新物理化 ---- */
const physVisible = ref(false)
const physMode = ref('exec')
const physEngine = ref('')
const physDsId = ref<number | null>(null)
const physDb = ref('')
const physDdl = ref('')
const physDsOptions = computed(() =>
  datasources.value.filter((d) => d.type === 'mysql' || d.type === 'greatdb'))

function ddlOf(name: string): string {
  return engines.value.find((e) => e.name === name)?.ddl ?? 'mysql'
}

async function loadPhysDdl() {
  const m = model.value
  if (!m) return
  const myEngine = physEngine.value
  try {
    const r = await getDdl(m.id, ddlOf(myEngine))
    if (myEngine !== physEngine.value) return
    physDdl.value = r.ddl
  } catch (e) {
    if (myEngine !== physEngine.value) return
    physDdl.value = ''
    ElMessage.error((e as Error).message)
  }
}

async function openPhys() {
  const m = model.value
  if (!m) return
  physEngine.value = m.engine
  physMode.value = 'exec'
  /* 预填数据源：不属于连接型（mysql/greatdb）时置空，避免 select 空白无提示 */
  physDsId.value = physDsOptions.value.some((d) => d.id === m.dsId) ? m.dsId : null
  physDb.value = m.dbName ?? ''
  physVisible.value = true
  await loadPhysDdl()
}

async function execPhys() {
  const m = model.value
  if (!m) return
  if (!physDsId.value) {
    ElMessage.warning('请选择目标数据源')
    return
  }
  try {
    await physicalize(m.id, {
      engine: ddlOf(physEngine.value),
      dsId: physDsId.value,
      dbName: physDb.value || undefined,
      mode: 'exec',
      ddl: physDdl.value || undefined,
    })
    physVisible.value = false
    ElMessage.success('物理化建表成功')
    await reload()
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

async function downloadScript() {
  const m = model.value
  if (!m) return
  try {
    const r = await physicalize(m.id, { engine: ddlOf(physEngine.value), mode: 'script' })
    if (!r.script) {
      ElMessage.warning('后端未返回脚本，无法下载')
      return
    }
    download((m.code || 'model') + '.sql', r.script)
    ElMessage.success('DDL 脚本已生成并下载')
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

function statusOf(m: ModelDetail): { cls: string; label: string } {
  if (m.status === 'draft') return { cls: 'st-gray', label: '草稿' }
  if (m.status === 'published') return { cls: 'st-blue', label: '已发布' }
  if (m.status === 'built') return { cls: 'st-green', label: '已物理化' }
  return { cls: 'st-green', label: '已投产' }
}
function layerColor(code: string): string {
  return layers.value.find((l) => l.code === code)?.color ?? '#64748b'
}
function aiTip() {
  ElMessage.info('AI 建表助手为独立模块入口，暂由后续迭代提供')
}
</script>

<template>
  <div class="page">
    <!-- 空态 -->
    <div v-if="notFound" class="card" style="padding:48px;text-align:center;color:var(--text-3)">
      <div style="font-size:14px;margin-bottom:6px">模型不存在</div>
      <button class="tb-new" style="margin-top:10px" @click="goBack">返回列表</button>
    </div>

    <template v-if="model">
      <!-- 页头：返回 + 标题 + 顶部操作按钮 -->
      <div class="card head-card">
        <div class="head-top">
          <button class="op-btn" @click="goBack">← 数仓建模</button>
          <div>
            <div class="head-title mono">{{ model.code }}</div>
            <div class="head-sub">
              {{ model.name }} ·
              <span class="tag" :style="{ background: layerColor(model.layer) + '22', color: layerColor(model.layer) }">{{ model.layer }}</span>
              · {{ model.engine }} · v{{ model.version }} · {{ model.bizDomain }} · 负责人 {{ model.owner || userName }}
            </div>
          </div>
          <span class="spacer" />
          <span class="st" :class="statusOf(model).cls"><span class="dot" />{{ statusOf(model).label }}</span>
          <button class="op-btn" @click="aiTip">✦ AI 建表助手</button>
          <button v-if="!locked" class="op-btn" @click="addField">+ 添加字段</button>
          <button class="op-btn" :disabled="locked" @click="persist">保存</button>
          <button v-if="model.status === 'draft'" class="op-btn" @click="doPublish">发布</button>
          <button class="tb-new" @click="openPhys">物理化建表</button>
        </div>
      </div>

      <!-- 字段设计 -->
      <div class="card" style="padding:16px;margin-top:12px">
        <div class="tbl-toolbar">
          <span class="sec-head">字段设计</span>
          <span class="pill info">{{ rows.length }} 个字段</span>
          <span class="spacer" />
          <button v-if="!locked" class="op-btn" @click="addField">+ 添加字段</button>
        </div>
        <table class="tbl">
          <thead>
            <tr>
              <th style="width:44px">序</th><th>字段名 *</th><th>类型</th><th>长度/精度</th><th>默认值</th>
              <th>注释</th><th style="width:56px">主键</th><th style="width:64px">分区键</th><th style="width:60px">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(f, i) in rows" :key="i">
              <td>{{ i + 1 }}</td>
              <td><input v-model="f.n" class="cell-inp mono" style="width:150px" :disabled="locked" /></td>
              <td>
                <select v-model="f.t" class="cell-inp" style="width:130px" :disabled="locked">
                  <option v-for="t in TYPE_OPTIONS" :key="t" :value="t">{{ t }}</option>
                </select>
              </td>
              <td><input v-model="f.len" class="cell-inp mono" style="width:100px" :disabled="locked" /></td>
              <td><input v-model="f.def" class="cell-inp" style="width:90px" :disabled="locked" /></td>
              <td><input v-model="f.cmt" class="cell-inp" style="width:180px" :disabled="locked" /></td>
              <td style="text-align:center"><input v-model="f.pk" type="checkbox" :disabled="locked" /></td>
              <td style="text-align:center"><input v-model="f.pkPart" type="checkbox" :disabled="locked" /></td>
              <td><button v-if="!locked" class="op-btn danger" @click="delField(i)">删除</button></td>
            </tr>
          </tbody>
        </table>
        <div v-if="rows.length === 0" class="empty">{{ locked ? '暂无字段' : '暂无字段，点击「+ 添加字段」开始设计' }}</div>
        <div class="hint">规范：字段命名 snake_case（NR-05），每层建模模板自动校验命名合规；修改后点击顶部「保存」提交（乐观锁并发保护）。</div>
      </div>

      <!-- DDL预览 -->
      <div class="card" style="padding:16px;margin-top:12px">
        <div class="tbl-toolbar">
          <span class="sec-head">DDL预览（{{ model.engine }} 方言，后端生成）</span>
          <span class="spacer" />
          <button class="op-btn" @click="download(model.code + '.sql', ddlText)">⇩ 导出DDL</button>
        </div>
        <pre class="code-box">{{ ddlText }}</pre>
        <div v-if="ddlNotes.length" class="hint">{{ ddlNotes.join('；') }}</div>
      </div>

      <!-- 维度建模建议 -->
      <div class="card" style="padding:16px;margin-top:12px">
        <div class="tbl-toolbar"><span class="sec-head">维度建模建议（自动识别）</span></div>
        <div class="sug-grid">
          <div class="sug-card">
            <b>星型模型</b>
            <div class="hint">事实表 {{ model.code }} 关联维度 dim_user / dim_product；当前库已识别 2 个维度关联</div>
          </div>
          <div class="sug-card">
            <b>雪花模型</b>
            <div class="hint">dim_user → dim_org 二级维度，可接受1层雪花</div>
          </div>
          <div class="sug-card">
            <b>宽表模型</b>
            <div class="hint">ADS层 ads_kpi_report 建议采用宽表冗余常用维度</div>
          </div>
        </div>
      </div>
    </template>

    <!-- 物理化建表弹窗 -->
    <el-dialog v-model="physVisible" :title="(model?.status === 'draft' ? '物理化建表' : '重新物理化') + ' - ' + (model?.code ?? '')" width="640px">
      <div class="form-grid" v-if="model">
        <label class="f-item">目标引擎
          <select v-model="physEngine" class="kw" style="width:100%" @change="loadPhysDdl">
            <option v-for="e in engines" :key="e.name" :value="e.name">{{ e.name }}（{{ e.ddl }}）</option>
          </select>
        </label>
        <label class="f-item">目标数据源（仅 MySQL/GreatDB）*
          <select v-model="physDsId" class="kw" style="width:100%">
            <option :value="null" disabled>请选择数据源</option>
            <option v-for="d in physDsOptions" :key="d.id" :value="d.id">{{ d.name }}（{{ d.type }} · {{ d.host ?? '-' }}）</option>
          </select>
        </label>
        <label class="f-item">目标库名
          <input v-model="physDb" class="kw mono" style="width:100%" placeholder="留空使用数据源默认库" />
        </label>
        <label class="f-item">执行方式
          <select v-model="physMode" class="kw" style="width:100%">
            <option value="exec">直接执行建表</option>
            <option value="script">导出DDL脚本（手工执行）</option>
          </select>
        </label>
      </div>
      <div class="f-label">DDL 预览（后端生成）</div>
      <pre class="code-box">{{ physDdl }}</pre>
      <template #footer>
        <button class="op-btn" @click="physVisible = false">取消</button>
        <button v-if="physMode === 'script'" class="op-btn" @click="downloadScript">⇩ 导出DDL</button>
        <button class="tb-new" @click="execPhys">执行建表</button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.head-card{padding:16px}
.head-top{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.head-title{font-size:16px;font-weight:700}
.head-sub{color:var(--text-3);font-size:12px;margin-top:2px;display:flex;align-items:center;gap:4px;flex-wrap:wrap}
.spacer{flex:1}
.hint{color:var(--text-3);font-size:11.5px;margin-top:8px}
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;padding:9px 10px;background:var(--bg);color:var(--text-2);font-weight:600;border-bottom:1px solid var(--border)}
.tbl td{padding:7px 10px;border-bottom:1px solid var(--border)}
.tbl tr:hover td{background:var(--primary-light)}
.cell-inp{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:4px 8px;font-size:12px;outline:none;background:#fff;color:var(--text)}
.cell-inp:focus{border-color:var(--primary)}
.cell-inp:disabled{background:var(--bg);color:var(--text-3)}
.tbl-toolbar{display:flex;align-items:center;gap:10px;margin-bottom:12px}
.tbl-toolbar .spacer{flex:1}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease);flex-shrink:0}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
.op-btn:disabled{opacity:.5;cursor:not-allowed}
.op-btn.danger{color:var(--danger);border-color:rgba(229,72,77,.35)}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.tag{display:inline-block;border-radius:4px;padding:1px 8px;font-size:11.5px;font-weight:600}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
.code-box{font-family:ui-monospace,Consolas,monospace;font-size:11.5px;background:#0d1424;color:#9fb2d0;border-radius:var(--radius);padding:12px;line-height:1.7;white-space:pre-wrap;max-height:280px;overflow:auto;margin:0}
.sug-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.sug-card{border:1px solid var(--border);border-radius:var(--radius);padding:12px 14px;font-size:12.5px}
.form-grid{display:flex;flex-direction:column;gap:12px}
.f-item{display:flex;flex-direction:column;gap:5px;font-size:12.5px;color:var(--text-2)}
.f-label{font-size:12px;color:var(--text-2);margin:12px 0 6px;font-weight:600}
</style>
