<script setup lang="ts">
import { onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useTemplateStore } from '../../stores/templateStore'
import { useGraphStore } from '../../stores/graph'

const props = defineProps<{ workflowId?: string }>()
const emit = defineEmits<{ (e: 'created', payload: { id: string; name: string; code?: number }): void }>()
const store = useTemplateStore()
const graphStore = useGraphStore()
onMounted(async () => { await store.load(); if (props.workflowId) await store.checkUpgrade(props.workflowId) })
watch(() => props.workflowId, async (id) => { if (id) await store.checkUpgrade(id) })
async function instantiate(id: number, fallbackName: string) {
  try {
    const { value } = await ElMessageBox.prompt('新工作流名称（可选）', '从模板新建', { inputPlaceholder: fallbackName })
    const row = await store.instantiate(id, value || fallbackName)
    emit('created', { ...row, name: value || fallbackName })
    ElMessage.success('已从模板创建工作流草稿')
  } catch { /* cancelled */ }
}
async function confirmUpgrade() {
  if (!props.workflowId) return
  await ElMessageBox.confirm('确认用最新模板覆盖当前工作流草稿？该升级为可选操作。', '确认升级', { type: 'warning' })
  const doc = await store.confirmUpgrade(props.workflowId)
  if (doc && graphStore.doc?.id === props.workflowId) graphStore.setDoc(doc)
  ElMessage.success('模板升级完成')
}
</script>

<template>
  <div class="template-center">
    <div v-if="store.upgradeNotice?.upgradeAvailable" class="upgrade-notice">
      <strong>可选升级</strong><span>当前模板 v{{ store.upgradeNotice.currentVersion }}，最新 v{{ store.upgradeNotice.latestVersion }}；不会自动覆盖工作流。</span>
      <button data-testid="preview-upgrade" @click="workflowId && store.previewUpgrade(workflowId)">diff 预览</button><button class="primary" data-testid="confirm-upgrade" @click="confirmUpgrade">确认升级</button>
    </div>
    <div v-if="store.upgradePreview" class="diff-preview">
      <div v-for="item in store.upgradePreview.diff" :key="item.path" class="diff-row"><code>{{ item.path }}</code><span>{{ item.before }}</span><b>→</b><span>{{ item.after }}</span></div>
    </div>
    <div class="template-grid">
      <article v-for="item in store.templates" :key="item.id" class="template-card">
        <div><strong>{{ item.name }}</strong> <span>v{{ item.version }}</span></div><div class="muted">{{ item.category || '未分类' }} · {{ item.description || '暂无说明' }}</div>
        <button class="primary" @click="instantiate(item.id, item.name)">从模板新建</button>
      </article>
      <div v-if="!store.loading && !store.templates.length" class="empty">暂无模板，可在任务编排列表使用“另存为模板”。</div>
    </div>
  </div>
</template>

<style scoped>
.template-center{padding:16px;display:flex;flex-direction:column;gap:12px}.upgrade-notice{padding:12px;border:1px solid #e6a23c;background:#fdf6ec;border-radius:6px;display:flex;gap:10px;align-items:center}.template-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}.template-card{border:1px solid var(--border);border-radius:6px;padding:14px;display:flex;flex-direction:column;gap:10px}.muted,.empty{color:var(--text-3)}button{cursor:pointer;border:1px solid var(--border);border-radius:4px;padding:5px 10px;background:#fff}.primary{background:var(--primary);color:#fff;border-color:var(--primary)}.diff-preview{border:1px solid var(--border);padding:10px;max-height:260px;overflow:auto}.diff-row{display:grid;grid-template-columns:2fr 1fr auto 1fr;gap:8px;padding:4px;border-bottom:1px solid var(--border)}
</style>
