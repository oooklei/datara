<script setup lang="ts">
/**
 * M04 字段设计器（对齐 prototype m04-model.js #/model/design/:id）
 * 字段表格增删改（字段名/类型/长度/默认值/注释/主键/分区键），保存新版本，
 * DDL预览（按引擎方言生成）+ 导出DDL + 物理化建表，维度建模建议。
 * 数据：models（ModelField 编辑经 dataStore.save 持久化）。
 */
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { dataStore } from '../../services/mock/dataStore'
import type { Model, DwLayer, EngineType, ModelVersion } from '../../services/types'

const route = useRoute()
const router = useRouter()

const model = ref<Model | null>(null)
const notFound = ref(false)
const layers = ref<DwLayer[]>([])
const engines = ref<EngineType[]>([])

const TYPE_OPTIONS = ['BIGINT', 'VARCHAR', 'CHAR', 'DECIMAL', 'DATETIME', 'DATE', 'INT', 'TINYINT', 'DOUBLE', 'TEXT']

async function reload() {
  const id = String(route.params.id ?? '')
  const rows = (await dataStore.list<Model>('models')) ?? []
  const found = rows.find((m) => m.id === id) ?? null
  model.value = found
  notFound.value = !found
  if (!layers.value.length) layers.value = [...((await dataStore.list<DwLayer>('dwLayers')) ?? [])]
  if (!engines.value.length) engines.value = [...((await dataStore.list<EngineType>('engineTypes')) ?? [])]
}

onMounted(reload)
// hash 导航复用实例时按 :id 重新加载
watch(() => route.params.id, reload)

function goBack() {
  router.push('/model/list')
}

/* ---- 字段编辑（变更即持久化，对齐原型 onchange 即写库） ---- */
async function persist() {
  if (!model.value) return
  model.value.updatedAt = nowStr()
  await dataStore.save<Model>('models', model.value)
}
async function addField() {
  if (!model.value) return
  const n = `field_${model.value.fields.length + 1}`
  model.value.fields.push({ n, t: 'VARCHAR', len: 100, pk: false, pkPart: false, cmt: '', def: '' })
  await persist()
  ElMessage.success('已添加字段，请完善定义')
}
async function delField(i: number) {
  const m = model.value
  if (!m) return
  try {
    await ElMessageBox.confirm(`确认删除字段「${m.fields[i]?.n ?? ''}」？`, '删除字段', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
  } catch {
    return
  }
  m.fields.splice(i, 1)
  await persist()
  ElMessage.success('字段已删除')
}

/* ---- 保存新版本 ---- */
const verVisible = ref(false)
const verNote = ref('')

function openSaveVer() {
  if (!model.value) return
  verNote.value = ''
  verVisible.value = true
}
async function saveVersion() {
  const m = model.value
  if (!m) return
  if (!verNote.value.trim()) {
    ElMessage.warning('请填写变更说明')
    return
  }
  m.version += 1
  const now = nowStr()
  const v: ModelVersion = { v: m.version, date: now, author: '王工', note: verNote.value.trim(), status: '当前版本' }
  m.versions.forEach((x) => { x.status = '历史' })
  m.versions.push(v)
  m.updatedAt = now
  await dataStore.save<Model>('models', m)
  verVisible.value = false
  ElMessage.success(`已保存 v${m.version}，可到「版本管理」对比与回滚`)
}

/* ---- DDL 生成（按引擎方言） ---- */
const ddl = computed(() => (model.value ? genDdl(model.value, model.value.engine) : ''))
function genDdl(m: Model, engine: string): string {
  const isDoris = engine.indexOf('Doris') >= 0 || engine === '万里 GreatDB'
  const cols = m.fields.map((f) => {
    const len = String(f.len ?? '')
    const t = f.t + (len !== '' ? (len.charAt(0) === '(' ? len : `(${len})`) : '')
    return `  ${f.n} ${t}${f.cmt ? ` COMMENT '${f.cmt}'` : ''}`
  }).join(',\n')
  const part = m.fields.find((f) => f.pkPart)
  let s = `CREATE TABLE ${m.code} (\n${cols}\n)\n`
  if (part) s += `PARTITION BY ${part.n}\n`
  if (isDoris) {
    const pkField = m.fields.find((f) => f.pk) ?? m.fields[0]
    s += `DISTRIBUTED BY HASH(${pkField ? pkField.n : 'id'}) BUCKETS 10\nPROPERTIES("replication_num"="3");`
  } else {
    s += `COMMENT '${m.name}';`
  }
  return s
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
const physDdl = computed(() => (model.value ? genDdl(model.value, physEngine.value) : ''))

function openPhys() {
  if (!model.value) return
  physEngine.value = model.value.engine
  physMode.value = 'exec'
  physVisible.value = true
}
async function execPhys() {
  const m = model.value
  if (!m) return
  m.engine = physEngine.value
  m.status = 'published'
  m.updatedAt = nowStr()
  await dataStore.save<Model>('models', m)
  physVisible.value = false
  ElMessage.success(`建表成功：${m.code}（${m.engine}），模型已与ETL任务建立血缘关联`)
  await reload()
}

function statusOf(m: Model): { cls: string; label: string } {
  return m.status === 'draft' ? { cls: 'st-gray', label: '草稿' } : { cls: 'st-green', label: '已物理化' }
}
function layerColor(code: string): string {
  return layers.value.find((l) => l.code === code)?.color ?? '#64748b'
}
function aiTip() {
  ElMessage.info('AI 建表助手为独立模块入口，暂由后续迭代提供')
}
function nowStr(): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
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
              · {{ model.engine }} · v{{ model.version }} · {{ model.bizDomain }} · 负责人 {{ model.owner }}
            </div>
          </div>
          <span class="spacer" />
          <span class="st" :class="statusOf(model).cls"><span class="dot" />{{ statusOf(model).label }}</span>
          <button class="op-btn" @click="aiTip">✦ AI 建表助手</button>
          <button class="op-btn" @click="addField">+ 添加字段</button>
          <button class="op-btn" @click="openSaveVer">保存新版本</button>
          <button class="tb-new" @click="openPhys">物理化建表</button>
        </div>
      </div>

      <!-- 字段设计 -->
      <div class="card" style="padding:16px;margin-top:12px">
        <div class="tbl-toolbar">
          <span class="sec-head">字段设计</span>
          <span class="pill info">{{ model.fields.length }} 个字段</span>
          <span class="spacer" />
          <button class="op-btn" @click="addField">+ 添加字段</button>
        </div>
        <table class="tbl">
          <thead>
            <tr>
              <th style="width:44px">序</th><th>字段名 *</th><th>类型</th><th>长度/精度</th><th>默认值</th>
              <th>注释</th><th style="width:56px">主键</th><th style="width:64px">分区键</th><th style="width:60px">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(f, i) in model.fields" :key="i">
              <td>{{ i + 1 }}</td>
              <td><input v-model="f.n" class="cell-inp mono" style="width:150px" @change="persist" /></td>
              <td>
                <select v-model="f.t" class="cell-inp" style="width:130px" @change="persist">
                  <option v-for="t in TYPE_OPTIONS" :key="t" :value="t">{{ t }}</option>
                </select>
              </td>
              <td><input v-model="f.len" class="cell-inp mono" style="width:100px" @change="persist" /></td>
              <td><input v-model="f.def" class="cell-inp" style="width:90px" @change="persist" /></td>
              <td><input v-model="f.cmt" class="cell-inp" style="width:180px" @change="persist" /></td>
              <td style="text-align:center"><input v-model="f.pk" type="checkbox" @change="persist" /></td>
              <td style="text-align:center"><input v-model="f.pkPart" type="checkbox" @change="persist" /></td>
              <td><button class="op-btn danger" @click="delField(i)">删除</button></td>
            </tr>
          </tbody>
        </table>
        <div v-if="model.fields.length === 0" class="empty">暂无字段，点击「+ 添加字段」开始设计</div>
        <div class="hint">规范：字段命名 snake_case（NR-05），每层建模模板自动校验命名合规；修改即时保存。</div>
      </div>

      <!-- DDL预览 -->
      <div class="card" style="padding:16px;margin-top:12px">
        <div class="tbl-toolbar">
          <span class="sec-head">DDL预览（{{ model.engine }} 方言）</span>
          <span class="spacer" />
          <button class="op-btn" @click="download(model.code + '.sql', ddl)">⇩ 导出DDL</button>
        </div>
        <pre class="code-box">{{ ddl }}</pre>
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

    <!-- 保存新版本抽屉 -->
    <el-drawer v-model="verVisible" :title="'保存新版本 - ' + (model?.code ?? '')" size="400px">
      <div class="form-grid">
        <label class="f-item">变更说明 *
          <textarea v-model="verNote" class="kw" style="width:100%;resize:vertical" rows="3" placeholder="本次变更内容，将写入版本历史" />
        </label>
        <div class="hint">当前版本 v{{ model?.version ?? '-' }} → 保存后生成 v{{ (model?.version ?? 0) + 1 }}；历史版本支持对比与回滚</div>
      </div>
      <div style="margin-top:16px;display:flex;gap:8px">
        <button class="tb-new" @click="saveVersion">保存</button>
        <button class="op-btn" @click="verVisible = false">取消</button>
      </div>
    </el-drawer>

    <!-- 物理化建表弹窗 -->
    <el-dialog v-model="physVisible" :title="'物理化建表 - ' + (model?.code ?? '')" width="640px">
      <div class="form-grid">
        <label class="f-item">目标引擎
          <select v-model="physEngine" class="kw" style="width:100%">
            <option v-for="e in engines" :key="e.name" :value="e.name">{{ e.name }}（{{ e.ddl }}）</option>
          </select>
        </label>
        <label class="f-item">执行方式
          <select v-model="physMode" class="kw" style="width:100%">
            <option value="exec">直接执行建表</option>
            <option value="script">导出DDL脚本（手工执行）</option>
          </select>
        </label>
      </div>
      <div class="f-label">DDL预览（一键生成，可编辑）</div>
      <pre class="code-box">{{ physDdl }}</pre>
      <template #footer>
        <button class="op-btn" @click="physVisible = false">取消</button>
        <button v-if="physMode === 'script'" class="op-btn" @click="download((model?.code ?? 'model') + '.sql', physDdl)">⇩ 导出DDL</button>
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
.tbl-toolbar{display:flex;align-items:center;gap:10px;margin-bottom:12px}
.tbl-toolbar .spacer{flex:1}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease);flex-shrink:0}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
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
