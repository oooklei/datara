<script setup lang="ts">
/**
 * 新建工作流对话框（GraphWorkbench 页面功能扩展）：
 * - 入口：GraphWorkbench 工具栏「＋ 新建工作流」（hostManaged 任务编排画布）+ 任务中心空态按钮；
 * - 字段：名称（必填）/ 所属分类（根目录 + 内置同步/ETL/流 + 自定义目录）/ 备注（落 v1 版本快照）；
 * - real：POST /workflow-definitions（name/tags/remark）后端落库；mock：newWorkflowDoc + graphService.save；
 * - 创建成功 emit('created')，由宿主（TaskCenterView）开画布 Tab、刷新候选池并广播目录刷新。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { createDefinition, graphService, isMock, listCategories } from '../../services'
import { newWorkflowDoc } from '../../services/mock/seed'
import type { DagProfileType } from '../../stores/dagTabs'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'created', payload: { id: string; name: string; type: DagProfileType; code?: number }): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const form = ref({ name: '', category: '', remark: '' })
const cats = ref<{ name: string; builtin: boolean }[]>([])
const submitting = ref(false)

/** 分类 → 标签（根目录 = 空标签 = 普通工作流）；内置目录名即标签（同步/ETL/流） */
const BUILTIN_LABELS = ['同步', 'ETL', '流']
function tagsOf(category: string): string[] {
  return category ? [category] : []
}
function typeOfTag(category: string): DagProfileType {
  if (category === '同步') return 'sync'
  if (category === 'ETL') return 'etl'
  if (category === '流') return 'stream'
  return 'wf'
}

watch(() => props.modelValue, (on) => {
  if (!on) return
  form.value = { name: '', category: '', remark: '' }
  if (isMock) { cats.value = BUILTIN_LABELS.map((n) => ({ name: n, builtin: true })) }
  else {
    void listCategories()
      .then((r) => { cats.value = r.map((c) => ({ name: c.name, builtin: c.builtin })) })
      .catch(() => { cats.value = BUILTIN_LABELS.map((n) => ({ name: n, builtin: true })) }) // 分类失败不阻断创建
  }
})

async function submit() {
  const name = form.value.name.trim()
  if (!name) { ElMessage.warning('工作流名称不能为空'); return }
  submitting.value = true
  try {
    const category = form.value.category
    if (isMock) {
      const id = `wf_${Date.now().toString(36)}`
      await graphService.save(newWorkflowDoc(id, name))
      emit('created', { id, name, type: 'wf' })
    } else {
      const created = await createDefinition(name, { tags: tagsOf(category), remark: form.value.remark })
      emit('created', { id: created.id, name, type: typeOfTag(category), code: created.code })
    }
    ElMessage.success(`工作流「${name}」已创建，已打开画布`)
    visible.value = false
  } catch (e) {
    ElMessage.error('创建失败：' + (e instanceof Error ? e.message : String(e)))
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <el-dialog v-model="visible" title="新建工作流" width="480px" append-to-body destroy-on-close>
    <div class="wfc-form">
      <div class="field">
        <label>名称 <span class="req">*</span></label>
        <input v-model="form.name" placeholder="工作流名称（必填）" maxlength="64" @keydown.enter.prevent="submit" />
      </div>
      <div class="field">
        <label>所属分类</label>
        <select v-model="form.category">
          <option value="">根目录（普通工作流）</option>
          <option v-for="c in cats" :key="c.name" :value="c.name">{{ c.name }}{{ c.builtin ? '' : '（自定义）' }}</option>
        </select>
        <div class="hint">选择分类即打对应标签，画布视角与 Palette 目录按标签归组</div>
      </div>
      <div class="field">
        <label>备注</label>
        <textarea v-model="form.remark" rows="3" placeholder="创建说明（可选，记录在工作流 v1 版本快照）" maxlength="200" />
      </div>
    </div>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :disabled="submitting" @click="submit">创建并编排</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.wfc-form{display:flex;flex-direction:column;gap:12px}
.field{display:flex;flex-direction:column;gap:4px}
.field label{font-size:11.5px;color:var(--text-2);font-weight:600}
.field .req{color:var(--danger)}
.field input,.field select,.field textarea{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 8px;font-size:12.5px;outline:none;font-family:inherit;resize:vertical}
.field input:focus,.field select:focus,.field textarea:focus{border-color:var(--primary)}
.hint{font-size:11px;color:var(--text-3)}
</style>
