<script setup lang="ts">
/**
 * GlobalParamDrawer（I10 G3）：全局参数管理抽屉。
 * - env 三分组（dev/staging/prod）参数 CRUD（api/params.py /params/global）
 * - 内置时间参数 14 项预览（store.builtinPreview，dayjs 镜像 vars_render.py）+ date(N) 函数式说明
 * - 加载后写回 store.setGlobalParams 供 Monaco `${` 补全使用
 */
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useIdeStore, ENV_LIST, type EnvKey } from '../../../stores/ideStore'
import {
  listGlobalParams, createGlobalParam, updateGlobalParam, deleteGlobalParam,
  type GlobalParamRow,
} from '../../../services/ideApi'

const store = useIdeStore()

const visible = defineModel<boolean>({ default: false })

const activeEnv = ref<EnvKey>('dev')
const loading = ref(false)
const rows = computed(() => store.globalParams[activeEnv.value])

const PARAM_TYPES = ['string', 'number', 'boolean']

const editVisible = ref(false)
const editSaving = ref(false)
const editingId = ref<number | null>(null) // null=新增
const editForm = ref({ name: '', value: '', type: 'string', desc: '' })

async function loadParams(): Promise<void> {
  loading.value = true
  try {
    const all = await listGlobalParams()
    for (const e of ENV_LIST) {
      store.setGlobalParams(e, all.filter((r) => r.env === e))
    }
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '全局参数加载失败')
  } finally {
    loading.value = false
  }
}

watch(visible, (v) => {
  if (v) void loadParams()
})

function openCreate(): void {
  editingId.value = null
  editForm.value = { name: '', value: '', type: 'string', desc: '' }
  editVisible.value = true
}

function openEdit(row: GlobalParamRow): void {
  editingId.value = row.id
  editForm.value = { name: row.name, value: row.value, type: row.type || 'string', desc: row.desc ?? '' }
  editVisible.value = true
}

async function saveEdit(): Promise<void> {
  const f = editForm.value
  const name = f.name.trim()
  if (!/^[A-Za-z_][\w]*$/.test(name)) {
    ElMessage.warning('参数名须以字母/下划线开头，仅含字母数字下划线')
    return
  }
  if (f.value.trim() === '') {
    ElMessage.warning('参数值不能为空')
    return
  }
  editSaving.value = true
  try {
    const body = { name, value: f.value.trim(), type: f.type, env: activeEnv.value, desc: f.desc.trim() || null }
    if (editingId.value === null) {
      await createGlobalParam(body)
      ElMessage.success(`参数 ${name} 已创建（${activeEnv.value}）`)
    } else {
      await updateGlobalParam(editingId.value, body)
      ElMessage.success(`参数 ${name} 已更新`)
    }
    editVisible.value = false
    await loadParams()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '保存失败')
  } finally {
    editSaving.value = false
  }
}

async function removeParam(row: GlobalParamRow): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认删除参数「${row.name}」（${row.env}）？引用它的脚本将在渲染时报错。`, '删除参数', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteGlobalParam(row.id)
    ElMessage.success('参数已删除')
    await loadParams()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '删除失败')
  }
}
</script>

<template>
  <el-drawer v-model="visible" title="全局参数管理" size="640px" append-to-body>
    <div class="gp-body">
      <!-- env 分组 -->
      <el-tabs v-model="activeEnv">
        <el-tab-pane v-for="e in ENV_LIST" :key="e" :name="e">
          <template #label>
            <span class="env-tab">{{ e }}<i class="env-n">{{ store.globalParams[e].length }}</i></span>
          </template>
        </el-tab-pane>
      </el-tabs>

      <div class="gp-toolbar">
        <span class="gp-hint">SQL 中以 <code class="mono">{{ '${' }}参数名{{ '}' }}</code> 引用；按 env 隔离解析</span>
        <span class="spacer" />
        <button class="tb-new" @click="openCreate">＋ 新增参数（{{ activeEnv }}）</button>
      </div>

      <div v-if="loading" class="gp-empty">加载中…</div>
      <div v-else-if="rows.length === 0" class="gp-empty">该环境暂无全局参数</div>
      <div v-else class="gp-list">
        <div v-for="r in rows" :key="r.id" class="gp-row">
          <span class="gp-name mono">{{ r.name }}</span>
          <span class="gp-val mono" :title="r.value">{{ r.value }}</span>
          <span class="gp-type">{{ r.type }}</span>
          <span class="gp-desc" :title="r.desc ?? ''">{{ r.desc || '-' }}</span>
          <span class="gp-acts">
            <button class="op-btn" @click="openEdit(r)">编辑</button>
            <button class="op-btn danger" @click="removeParam(r)">删除</button>
          </span>
        </div>
      </div>

      <!-- 内置时间参数 14 项 -->
      <div class="gp-builtin">
        <div class="gp-bt">内置时间参数（渲染时按当前系统时间解析，无需维护）</div>
        <div class="gp-bgrid">
          <div v-for="b in store.builtinPreview" :key="b.name" class="gp-bitem">
            <span class="mono bname">${{ '{' + b.name + '}' }}</span>
            <span class="mono bval" :title="b.value">{{ b.value }}</span>
            <span class="bdesc">{{ b.desc }}</span>
          </div>
          <div class="gp-bitem">
            <span class="mono bname">${date(N)}</span>
            <span class="mono bval">T+N 偏移</span>
            <span class="bdesc">函数式日期：date(0)=今日，date(-1)=T-1（YYYY-MM-DD）</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 编辑弹窗 -->
    <el-dialog v-model="editVisible" :title="editingId === null ? `新增参数（${activeEnv}）` : '编辑参数'" width="440px" append-to-body>
      <div class="form-grid">
        <span class="fg-k">参数名</span><input v-model="editForm.name" class="kw mono" placeholder="如 shop_id" />
        <span class="fg-k">参数值</span><input v-model="editForm.value" class="kw mono" placeholder="参数值（按字符串存储）" />
        <span class="fg-k">类型</span>
        <select v-model="editForm.type" class="sel">
          <option v-for="t in PARAM_TYPES" :key="t" :value="t">{{ t }}</option>
        </select>
        <span class="fg-k">说明</span><input v-model="editForm.desc" class="kw" placeholder="用途说明（可选）" />
      </div>
      <template #footer>
        <button class="op-btn" @click="editVisible = false">取消</button>
        <button class="tb-new" :disabled="editSaving" @click="saveEdit">{{ editSaving ? '保存中…' : '保存' }}</button>
      </template>
    </el-dialog>
  </el-drawer>
</template>

<style scoped>
.gp-body{display:flex;flex-direction:column;gap:10px;font-size:12.5px}
.env-tab{display:inline-flex;align-items:center;gap:5px}
.env-n{font-style:normal;font-size:10.5px;background:var(--primary-light);color:var(--primary);border-radius:8px;padding:0 6px;line-height:16px}
.gp-toolbar{display:flex;align-items:center;gap:8px}
.gp-hint{color:var(--ide-text-3);font-size:11.5px}
.gp-hint code{background:var(--ide-bg);padding:1px 4px;border-radius:3px}
.spacer{flex:1}
.gp-empty{padding:24px;text-align:center;color:var(--ide-text-3)}
.gp-list{display:flex;flex-direction:column;gap:6px;max-height:280px;overflow:auto;border:1px solid var(--ide-border);border-radius:var(--radius-sm);padding:8px}
.gp-row{display:flex;align-items:center;gap:8px;padding:6px 8px;border:1px solid var(--ide-border);border-radius:var(--radius-sm)}
.gp-name{font-weight:700;min-width:110px;color:var(--ide-text)}
.gp-val{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--success)}
.gp-type{font-size:10.5px;color:var(--ide-text-3);border:1px solid var(--ide-border);border-radius:3px;padding:0 5px}
.gp-desc{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--ide-text-3);font-size:11.5px}
.gp-acts{display:flex;gap:4px;flex-shrink:0}
.op-btn.danger{color:var(--danger)}
/* 内置参数 */
.gp-builtin{border:1px dashed var(--ide-border-strong);border-radius:var(--radius-sm);padding:10px}
.gp-bt{font-weight:600;color:var(--ide-text-2);margin-bottom:8px;font-size:12px}
.gp-bgrid{display:grid;grid-template-columns:1fr 1fr;gap:6px 12px}
.gp-bitem{display:grid;grid-template-columns:auto 1fr;gap:2px 8px;align-items:baseline}
.bname{font-weight:600;color:var(--primary);font-size:11.5px}
.bval{font-size:11px;color:var(--success);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bdesc{grid-column:1 / -1;font-size:10.5px;color:var(--ide-text-3)}
/* 表单 */
.form-grid{display:grid;grid-template-columns:70px 1fr;gap:10px;align-items:center;font-size:12.5px}
.fg-k{color:var(--ide-text-3)}
.kw{border:1px solid var(--ide-border-strong);border-radius:var(--radius-sm);padding:5px 9px;font-size:12.5px;background:var(--ide-input);color:var(--ide-text);outline:none;width:100%}
.sel{border:1px solid var(--ide-border-strong);border-radius:var(--radius-sm);padding:5px 8px;font-size:12.5px;background:var(--ide-input);color:var(--ide-text)}
</style>
