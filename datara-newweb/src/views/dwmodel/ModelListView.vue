<template>
  <main class="model-page" aria-label="数仓建模">
    <header class="page-head">
      <div><h1>数仓建模</h1><p>管理模型定义、生命周期与 DDL 预览。</p></div>
      <input v-model.trim="filters.keyword" data-keyword placeholder="搜索编码或名称" @keyup.enter="reload">
      <select v-model="filters.status" data-status @change="reload">
        <option value="">全部状态</option><option value="draft">草稿</option><option value="published">已发布</option><option value="built">已构建</option>
      </select>
      <button type="button" data-search @click="reload">查询</button>
      <button type="button" data-create @click="beginCreate">新建模型</button>
    </header>

    <p v-if="error" role="alert" class="error" data-error>{{ error }}</p>
    <p v-if="busy" role="status">正在加载…</p>
    <table v-else data-model-list>
      <thead><tr><th>编码</th><th>名称</th><th>分层</th><th>业务域</th><th>引擎</th><th>状态</th><th>版本</th><th>负责人</th><th>操作</th></tr></thead>
      <tbody>
        <tr v-for="row in rows" :key="row.id" :data-model-id="row.id">
          <td><code>{{ row.code }}</code></td><td>{{ row.name }}</td><td>{{ row.layer }}</td><td>{{ row.bizDomain || '—' }}</td>
          <td>{{ row.engine }}</td><td>{{ row.status }}</td><td>v{{ row.version }}</td><td>{{ row.owner || '—' }}</td>
          <td class="actions">
            <button type="button" @click="beginEdit(row)">编辑</button>
            <button v-if="row.status === 'draft'" type="button" @click="publish(row)">发布</button>
            <button v-else type="button" @click="redraft(row)">重新起草</button>
            <button type="button" @click="previewDdl(row)">DDL</button>
            <button type="button" class="danger" @click="remove(row)">删除</button>
          </td>
        </tr>
        <tr v-if="rows.length === 0"><td colspan="9">暂无模型</td></tr>
      </tbody>
    </table>

    <section v-if="editorOpen" class="dialog" data-model-editor>
      <header><h2>{{ editingId === null ? '新建模型' : '编辑模型' }}</h2><button type="button" @click="editorOpen=false">关闭</button></header>
      <div class="form-grid">
        <label>名称<input v-model.trim="draft.name" data-field-name></label>
        <label>编码<input v-model.trim="draft.code" :disabled="editingId !== null" data-field-code></label>
        <label>分层<select v-model="draft.layer" :disabled="editingId !== null"><option v-for="layer in layers" :key="layer" :value="layer">{{ layer }}</option></select></label>
        <label>引擎<select v-model="draft.engine" :disabled="editingId !== null"><option v-for="engine in engines" :key="engine" :value="engine">{{ engine }}</option></select></label>
        <label>业务域<input v-model.trim="draft.bizDomain" :disabled="editingId !== null"></label>
        <label v-if="editingId !== null">负责人<input v-model.trim="draft.owner"></label>
        <label v-if="editingId !== null" class="wide">备注<textarea v-model.trim="draft.remark" rows="3"></textarea></label>
      </div>
      <footer><button type="button" data-save :disabled="saving || !draft.name || !draft.code" @click="save">保存</button></footer>
    </section>

    <section v-if="ddlOpen" class="dialog" data-ddl-dialog>
      <header><h2>DDL 预览 · {{ ddlModelName }}</h2><button type="button" @click="ddlOpen=false">关闭</button></header>
      <pre>{{ ddlText }}</pre>
    </section>
  </main>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { modelApi, type ModelRow } from '../../services/rebuild/modelApi'

const rows = ref<ModelRow[]>([])
const busy = ref(false)
const saving = ref(false)
const error = ref('')
const editorOpen = ref(false)
const ddlOpen = ref(false)
const editingId = ref<number | null>(null)
const ddlText = ref('')
const ddlModelName = ref('')
const layers = ['ODS', 'DWD', 'DWS', 'ADS', 'DIM']
const engines = ['mysql', 'doris', 'greatdb']
const filters = reactive({ keyword: '', status: '' })
const draft = reactive({ name: '', code: '', layer: 'DWD', engine: 'mysql', bizDomain: '', owner: '', remark: '' })
const message = (cause: unknown) => cause instanceof Error ? cause.message : String(cause)

async function reload() {
  busy.value = true; error.value = ''
  try { rows.value = (await modelApi.list({ keyword: filters.keyword, status: filters.status, page: 1, size: 100 })).list }
  catch (cause) { error.value = message(cause); rows.value = [] }
  finally { busy.value = false }
}

function resetDraft() { Object.assign(draft, { name: '', code: '', layer: 'DWD', engine: 'mysql', bizDomain: '', owner: '', remark: '' }) }
function beginCreate() { editingId.value = null; resetDraft(); editorOpen.value = true }
function beginEdit(row: ModelRow) {
  editingId.value = row.id
  Object.assign(draft, { name: row.name, code: row.code, layer: row.layer, engine: row.engine, bizDomain: row.bizDomain, owner: row.owner, remark: row.remark })
  editorOpen.value = true
}

async function save() {
  saving.value = true; error.value = ''
  try {
    if (editingId.value === null) await modelApi.create({ name: draft.name, code: draft.code, layer: draft.layer, engine: draft.engine, bizDomain: draft.bizDomain })
    else await modelApi.update(editingId.value, { name: draft.name, owner: draft.owner, remark: draft.remark })
    editorOpen.value = false
    await reload()
  } catch (cause) { error.value = message(cause) }
  finally { saving.value = false }
}

async function publish(row: ModelRow) { try { await modelApi.publish(row.id); await reload() } catch (cause) { error.value = message(cause) } }
async function redraft(row: ModelRow) { try { await modelApi.redraft(row.id); await reload() } catch (cause) { error.value = message(cause) } }
async function remove(row: ModelRow) {
  if (!window.confirm(`确认删除模型“${row.name}”？`)) return
  try { await modelApi.remove(row.id); await reload() } catch (cause) { error.value = message(cause) }
}
async function previewDdl(row: ModelRow) {
  try {
    const preview = await modelApi.ddl(row.id, row.engine)
    ddlModelName.value = row.name; ddlText.value = preview.ddl; ddlOpen.value = true
  } catch (cause) { error.value = message(cause) }
}

onMounted(reload)
</script>

<style scoped>
.model-page{max-width:1440px;margin:auto;padding:32px 24px;color:var(--text)}.page-head{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.page-head>div{margin-right:auto}.page-head h1{margin:0}.page-head p{margin:6px 0 0;color:var(--text-2)}input,select,textarea,button{padding:7px 10px}table{width:100%;border-collapse:collapse;background:var(--card);margin-top:18px}th,td{text-align:left;padding:10px;border-bottom:1px solid var(--border)}.actions{display:flex;gap:6px;flex-wrap:wrap}.danger,.error{color:var(--danger)}.dialog{position:fixed;z-index:20;left:50%;top:50%;transform:translate(-50%,-50%);width:min(760px,calc(100vw - 48px));max-height:80vh;overflow:auto;background:var(--card);border:1px solid var(--border-strong);border-radius:var(--radius-lg);box-shadow:var(--shadow-lg);padding:20px}.dialog header,.dialog footer{display:flex;align-items:center;justify-content:space-between}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:18px 0}.form-grid label{display:flex;flex-direction:column;gap:6px}.form-grid .wide{grid-column:1/-1}.dialog pre{white-space:pre-wrap;background:var(--sidebar);color:var(--sidebar-text);padding:16px;overflow:auto}
</style>
