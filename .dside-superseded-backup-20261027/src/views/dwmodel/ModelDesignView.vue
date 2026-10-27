<template>
  <main class="design-page" aria-label="模型设计" data-model-design>
    <header class="page-head">
      <div><h1>模型设计</h1><p>字段定义、发布生命周期与物理化。</p></div>
      <button v-if="model" type="button" data-redraft :disabled="busy || model.status === 'draft'" @click="redraft">重新起草</button>
      <button v-if="model" type="button" data-publish :disabled="busy || model.status !== 'draft'" @click="publish">发布</button>
      <button v-if="model" type="button" data-ddl @click="previewDdl">DDL 预览</button>
      <button v-if="model" type="button" data-physicalize @click="physicalizeOpen = true">物理化</button>
    </header>

    <p v-if="error" role="alert" class="error" data-error>{{ error }}</p>
    <p v-if="busy" role="status" data-loading>正在加载…</p>
    <p v-else-if="!model" class="empty" data-empty>请先在列表中选择一个模型。</p>

    <template v-else>
      <section class="meta-card" data-model-meta>
        <dl>
          <div><dt>编码</dt><dd><code>{{ model.code }}</code></dd></div>
          <div><dt>名称</dt><dd>{{ model.name }}</dd></div>
          <div><dt>分层</dt><dd>{{ model.layer }}</dd></div>
          <div><dt>引擎</dt><dd>{{ model.engine }}</dd></div>
          <div><dt>状态</dt><dd>{{ model.status }}</dd></div>
          <div><dt>版本</dt><dd>v{{ model.version }}</dd></div>
          <div><dt>负责人</dt><dd>{{ model.owner || '—' }}</dd></div>
        </dl>
      </section>

      <section class="fields-card">
        <header>
          <h2>字段定义</h2>
          <button type="button" data-save-fields :disabled="saving" @click="saveFields">保存字段</button>
        </header>
        <table data-field-table>
          <thead>
            <tr>
              <th>名称</th><th>类型</th><th>长度</th><th>精度</th><th>可空</th>
              <th>默认值</th><th>注释</th><th>主键</th><th>分区</th><th>字典</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(field, index) in fields" :key="index" :data-field-row="index">
              <td><input v-model.trim="field.name" :data-field-name="index"></td>
              <td><input v-model.trim="field.dataType" data-field-type></td>
              <td><input v-model.number="field.length" type="number" data-field-length></td>
              <td><input v-model.number="field.precision" type="number" data-field-precision></td>
              <td><input v-model="field.nullable" type="checkbox" data-field-nullable></td>
              <td><input v-model.trim="field.defaultValue" data-field-default></td>
              <td><input v-model.trim="field.comment" data-field-comment></td>
              <td><input v-model="field.isPk" type="checkbox" data-field-pk></td>
              <td><input v-model="field.isPartition" type="checkbox" data-field-partition></td>
              <td><input v-model.trim="field.dictRef" data-field-dict></td>
            </tr>
            <tr v-if="fields.length === 0"><td colspan="10" data-fields-empty>暂无字段</td></tr>
          </tbody>
        </table>
      </section>
    </template>

    <section v-if="ddlOpen" class="dialog" data-ddl-dialog>
      <header><h2>DDL 预览 · {{ ddlPreview?.engine }}</h2><button type="button" @click="ddlOpen = false">关闭</button></header>
      <pre data-ddl-preview>{{ ddlPreview?.ddl || '—' }}</pre>
      <p v-if="ddlPreview?.notes?.length" class="notes">{{ ddlPreview.notes.join('；') }}</p>
    </section>

    <section v-if="physicalizeOpen" class="dialog" data-physicalize-dialog>
      <header><h2>物理化</h2><button type="button" @click="physicalizeOpen = false">关闭</button></header>
      <div class="form-grid">
        <label>引擎<input v-model.trim="phys.engine" data-phys-engine></label>
        <label>模式<select v-model="phys.mode" data-phys-mode>
          <option value="script">script（仅出脚本）</option>
          <option value="exec">exec（写库）</option>
        </select></label>
        <label>数据源 ID<input v-model.number="phys.dsId" type="number" data-phys-ds></label>
        <label>库名<input v-model.trim="phys.dbName" data-phys-db></label>
      </div>
      <p v-if="physResult" class="notes" data-phys-result>{{ physResult }}</p>
      <footer><button type="button" data-physicalize-confirm :disabled="saving || !phys.engine" @click="doPhysicalize">执行物理化</button></footer>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { modelApi, type ModelDetail, type ModelFieldRow, type ModelDdlPreview } from '../../services/rebuild/modelApi'

const props = defineProps<{ modelId?: number }>()
const route = useRoute()
const routeModelId = () => {
  const raw = route?.query?.modelId
  const value = Number(Array.isArray(raw) ? raw[0] : raw)
  return Number.isFinite(value) && value > 0 ? value : undefined
}
const targetId = computed(() => props.modelId ?? routeModelId())

const model = ref<ModelDetail | null>(null)
const fields = ref<ModelFieldRow[]>([])
const busy = ref(false)
const saving = ref(false)
const error = ref('')
const ddlOpen = ref(false)
const ddlPreview = ref<ModelDdlPreview | null>(null)
const physicalizeOpen = ref(false)
const physResult = ref('')
const phys = reactive({ engine: 'mysql', mode: 'script', dsId: undefined as number | undefined, dbName: '' })
const message = (cause: unknown) => cause instanceof Error ? cause.message : String(cause)

async function load() {
  const id = targetId.value
  if (!id) { model.value = null; fields.value = []; return }
  busy.value = true; error.value = ''
  try {
    const detail = await modelApi.detail(id)
    model.value = detail
    fields.value = detail.fields.map((field) => ({ ...field }))
  } catch (cause) { error.value = message(cause); model.value = null; fields.value = [] }
  finally { busy.value = false }
}

async function saveFields() {
  const id = targetId.value
  if (!id) return
  saving.value = true; error.value = ''
  try {
    const rev = await modelApi.updateFields(id, { rev: model.value?.version ?? 0, fields: fields.value })
    if (model.value) model.value.version = rev
  } catch (cause) { error.value = message(cause) }
  finally { saving.value = false }
}

async function publish() {
  const id = targetId.value
  if (!id) return
  busy.value = true; error.value = ''
  try { await modelApi.publish(id); await load() }
  catch (cause) { error.value = message(cause) }
  finally { busy.value = false }
}

async function redraft() {
  const id = targetId.value
  if (!id) return
  busy.value = true; error.value = ''
  try { await modelApi.redraft(id); await load() }
  catch (cause) { error.value = message(cause) }
  finally { busy.value = false }
}

async function previewDdl() {
  const id = targetId.value
  if (!id) return
  busy.value = true; error.value = ''
  try { ddlPreview.value = await modelApi.ddl(id, model.value?.engine); ddlOpen.value = true }
  catch (cause) { error.value = message(cause) }
  finally { busy.value = false }
}

async function doPhysicalize() {
  const id = targetId.value
  if (!id) return
  saving.value = true; error.value = ''
  try {
    const result = await modelApi.physicalize(id, {
      engine: phys.engine, mode: phys.mode, dsId: phys.dsId, dbName: phys.dbName || undefined,
    })
    physResult.value = result.script ?? (result.status ? `已执行 ${result.executed ?? 0} 条` : '完成')
  } catch (cause) { error.value = message(cause) }
  finally { saving.value = false }
}

onMounted(load)
</script>

<style scoped>
.design-page{max-width:1440px;margin:auto;padding:32px 24px;color:var(--text)}.page-head{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.page-head>div{margin-right:auto}.page-head h1{margin:0}.page-head p{margin:6px 0 0;color:var(--text-2)}button{padding:7px 10px}input,select{padding:6px 8px}.error{color:var(--danger)}.empty{color:var(--text-3)}.meta-card,.fields-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius-lg);padding:18px;margin-top:18px}.meta-card dl{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:0}.meta-card dt{color:var(--text-2);font-size:13px}.meta-card dd{margin:4px 0 0}.fields-card header{display:flex;align-items:center;justify-content:space-between}.fields-card h2{margin:0}table{width:100%;border-collapse:collapse;margin-top:14px}th,td{text-align:left;padding:8px;border-bottom:1px solid var(--border);font-size:13px}th{color:var(--text-2);font-weight:600}td input[type="text"],td input:not([type]){width:100%}.dialog{position:fixed;z-index:20;left:50%;top:50%;transform:translate(-50%,-50%);width:min(760px,calc(100vw - 48px));max-height:80vh;overflow:auto;background:var(--card);border:1px solid var(--border-strong);border-radius:var(--radius-lg);box-shadow:var(--shadow-lg);padding:20px}.dialog header,.dialog footer{display:flex;align-items:center;justify-content:space-between}.dialog h2{margin:0}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:18px 0}.form-grid label{display:flex;flex-direction:column;gap:6px}.dialog pre{white-space:pre-wrap;background:var(--sidebar);color:var(--sidebar-text);padding:16px;overflow:auto;border-radius:var(--radius)}.notes{color:var(--text-2)}
</style>
