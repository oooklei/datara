<script setup lang="ts">
/**
 * M12 全局参数（/param/global）
 * 对齐 prototype/assets/pages/m12-param.js L7-65：
 * 参数表格（搜索/加密筛选）+ 新建/编辑抽屉（参数名/值/类型/敏感加密/说明）+
 * 引用任务（扫描 ETL SQL 与脚本中的 ${参数} 引用）+ 删除（二次确认）。操作按钮置顶（页头工具栏）。
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { dataStore } from '../../services/mock/dataStore'
import { localTime } from '../../services/mock/timeUtil'
import ParamTree from './ParamTree.vue'
import type { GlobalParam, EtlTask, Script } from '../../services/types'

const router = useRouter()

const params = ref<GlobalParam[]>([])
const envName = ref('prod')
const keyword = ref('')
const encFilter = ref('')

async function reload() {
  // 必须展开为新数组：dataStore.save 原地修改数组，直接赋值不会触发 ref 更新
  params.value = [...((await dataStore.list<GlobalParam>('globalParams')) ?? [])]
  const env = await dataStore.get<string>('env')
  if (env) envName.value = env
}
onMounted(reload)

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return params.value.filter((p) => {
    if (encFilter.value === 'enc' && !p.encrypt) return false
    if (encFilter.value === 'plain' && p.encrypt) return false
    if (!kw) return true
    return [p.id, p.name, p.desc].some((s) => s.toLowerCase().includes(kw))
  })
})

/* ---- 新建 / 编辑参数 ---- */
const formVisible = ref(false)
const editing = ref<GlobalParam | null>(null)
const form = ref({ name: '', value: '', type: '文本', encrypt: false, desc: '' })

function openCreate() {
  editing.value = null
  form.value = { name: '', value: '', type: '文本', encrypt: false, desc: '' }
  formVisible.value = true
}
function openEdit(p: GlobalParam) {
  editing.value = p
  form.value = { name: p.name, value: p.encrypt ? '******' : p.value, type: p.type, encrypt: p.encrypt, desc: p.desc }
  formVisible.value = true
}

async function saveForm() {
  const name = form.value.name.trim()
  if (!name) {
    ElMessage.warning('请填写参数名')
    return
  }
  if (!editing.value && params.value.some((p) => p.name === name)) {
    ElMessage.error('参数名已存在')
    return
  }
  if (editing.value) {
    // 加密参数界面脱敏：值输入框保持 ****** 时沿用原值
    Object.assign(editing.value, {
      name,
      value: form.value.value === '******' ? editing.value.value : form.value.value,
      type: form.value.type,
      encrypt: form.value.encrypt,
      desc: form.value.desc,
      updatedAt: localTime().slice(0, 10),
    })
    await dataStore.save('globalParams', editing.value)
    ElMessage.success('参数已保存')
  } else {
    // ID 取现有最大序号 +1：删除参数后再新建不会碰撞
    const nextSeq = params.value.reduce((m, p) => {
      const n = Number(String(p.id).replace(/^\D+/, ''))
      return Number.isFinite(n) && n > m ? n : m
    }, 0) + 1
    const row: GlobalParam = {
      id: 'GP' + String(nextSeq).padStart(2, '0'),
      name,
      value: form.value.encrypt ? '******' : form.value.value,
      type: form.value.type,
      encrypt: form.value.encrypt,
      desc: form.value.desc,
      env: envName.value,
      updatedAt: localTime().slice(0, 10),
    }
    params.value.push(row)
    await dataStore.save('globalParams', row)
    ElMessage.success('参数已创建：脚本/SQL 中通过 ${' + name + '} 引用')
  }
  formVisible.value = false
}

/* ---- 引用任务（懒加载 ETL/脚本集合再扫描，避免挂载期多余计算） ---- */
interface RefRow {
  id: string
  n: string
}
const refVisible = ref(false)
const refName = ref('')
const refRows = ref<RefRow[]>([])

async function openRefs(name: string) {
  refName.value = name
  const token = '${' + name + '}'
  const [etls, scripts] = await Promise.all([
    dataStore.list<EtlTask>('etlTasks'),
    dataStore.list<Script>('scripts'),
  ])
  const rows: RefRow[] = []
  for (const t of etls) {
    if (t.sql && t.sql.includes(token)) rows.push({ id: t.id, n: t.id + ' ' + t.name + '（SQL任务）' })
  }
  for (const s of scripts) {
    if (s.code.includes(token)) rows.push({ id: s.id, n: s.id + ' ' + s.name + '（脚本）' })
  }
  refRows.value = rows
  refVisible.value = true
}

function goTools() {
  refVisible.value = false
  router.push('/param/tools')
}

/* ---- 删除 ---- */
async function removeParam(p: GlobalParam) {
  try {
    await ElMessageBox.confirm(
      '确认删除参数「${' + p.name + '}」？引用该参数的任务执行时将报「参数未定义」错误，请先确认无引用。',
      '删除参数', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  await dataStore.remove('globalParams', p.id)
  ElMessage.info('参数已删除')
  await reload()
}
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ParamTree @pick="(kw) => (keyword = kw)" />
    <div style="flex:1;min-width:0">
    <!-- 页头 + 顶部操作工具栏 -->
    <div class="card page-head">
      <div>
        <div class="ph-title">全局参数</div>
        <div class="ph-desc">跨任务共享的键值参数：敏感参数加密存储（界面脱敏），执行时按当前环境注入</div>
      </div>
      <span class="spacer" />
      <button class="tb-new" @click="openCreate">＋ 新建参数</button>
    </div>

    <!-- 参数列表 -->
    <div class="card" style="padding:16px">
      <div class="tbl-toolbar">
        <span class="card-title">参数列表</span>
        <span class="pill info">{{ filtered.length }} / {{ params.length }}</span>
        <span class="spacer" />
        <input v-model="keyword" class="kw" placeholder="搜索参数" />
        <select v-model="encFilter" class="sel">
          <option value="">加密：全部</option>
          <option value="enc">加密</option>
          <option value="plain">明文</option>
        </select>
      </div>
      <table class="tbl">
        <thead>
          <tr>
            <th>参数名</th><th>值</th><th>类型</th><th>说明</th><th>更新日期</th><th style="width:180px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in filtered" :key="p.id">
            <td>
              <span class="mono"><b>{{ '${' + p.name + '}' }}</b></span>
              <div style="font-size:11px;color:var(--text-3)">{{ p.id }}</div>
            </td>
            <td>
              <template v-if="p.encrypt">
                <span class="mono">******</span>
                <span class="pill warn" style="margin-left:4px">已加密</span>
              </template>
              <span v-else class="mono">{{ p.value }}</span>
            </td>
            <td>{{ p.type }}</td>
            <td style="color:var(--text-2)">{{ p.desc }}</td>
            <td style="color:var(--text-2)">{{ p.updatedAt }}</td>
            <td>
              <button class="op-btn primary" @click="openEdit(p)">编辑</button>
              <button class="op-btn" @click="openRefs(p.name)">引用任务</button>
              <button class="op-btn danger" @click="removeParam(p)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="filtered.length === 0" class="empty">未找到匹配的参数</div>
    </div>

    <!-- 新建 / 编辑参数抽屉 -->
    <el-drawer v-model="formVisible" :title="editing ? '编辑参数 - ' + editing.name : '新建全局参数'" size="440px">
      <div class="form-grid">
        <div class="fg-2">
          <label class="f-item">参数名 *
            <input v-model="form.name" class="kw" style="width:100%" placeholder="如：doris_host" />
          </label>
          <label class="f-item">类型
            <select v-model="form.type" class="kw" style="width:100%">
              <option>文本</option><option>数值</option><option>布尔</option><option>JSON</option>
            </select>
          </label>
        </div>
        <label class="f-item">值
          <input v-model="form.value" class="kw" style="width:100%" />
        </label>
        <label class="f-item switch-row">
          <span>敏感加密存储（界面脱敏）</span>
          <el-switch v-model="form.encrypt" />
        </label>
        <div v-if="form.encrypt" class="f-help">加密后值以 ****** 展示，执行时解密注入</div>
        <label class="f-item">说明
          <textarea v-model="form.desc" class="kw" style="width:100%;resize:vertical" rows="2" />
        </label>
      </div>
      <div style="margin-top:16px;display:flex;gap:8px">
        <button class="tb-new" @click="saveForm">保存</button>
        <button class="op-btn" @click="formVisible = false">取消</button>
      </div>
    </el-drawer>

    <!-- 参数引用任务 -->
    <el-dialog v-model="refVisible" :title="'参数引用 - ${' + refName + '}'" width="520px">
      <table v-if="refRows.length" class="tbl">
        <thead>
          <tr><th>引用位置</th><th style="width:90px">操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="r in refRows" :key="r.id">
            <td>{{ r.n }}</td>
            <td><a @click="goTools">引用检测</a></td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty" style="padding:20px 0">{{ '暂无引用：ETL 任务与脚本中未发现 ${' + refName + '}' }}</div>
      <template #footer>
        <button class="op-btn" @click="refVisible = false">关闭</button>
      </template>
    </el-dialog>
    </div>
  </div>
</template>

<style scoped>
.page-head{display:flex;align-items:center;gap:12px;padding:14px 16px;margin-bottom:14px}
.ph-title{font-weight:700;font-size:15px}
.ph-desc{font-size:12px;color:var(--text-3);margin-top:2px}
.spacer{flex:1}
.card-title{font-weight:700;font-size:14px}
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;padding:9px 10px;background:var(--bg);color:var(--text-2);font-weight:600;border-bottom:1px solid var(--border)}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--border)}
.tbl tr:hover td{background:var(--primary-light)}
.kw{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 10px;font-size:12.5px;width:190px;outline:none}
.kw:focus{border-color:var(--primary)}
.sel{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 8px;font-size:12.5px;background:#fff;outline:none;color:var(--text-2)}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease)}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
.op-btn.primary{color:var(--primary);border-color:rgba(22,104,220,.4);font-weight:600}
.op-btn.danger{color:var(--danger);border-color:rgba(229,72,77,.35)}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
.form-grid{display:flex;flex-direction:column;gap:12px}
.fg-2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.f-item{display:flex;flex-direction:column;gap:5px;font-size:12.5px;color:var(--text-2)}
.switch-row{flex-direction:row;align-items:center;justify-content:space-between}
.f-help{font-size:11.5px;color:var(--text-3);margin-top:-6px}
</style>
