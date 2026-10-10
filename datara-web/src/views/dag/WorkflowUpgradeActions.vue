<script setup lang="ts">
/**
 * 工作流列表行内「可选升级」入口：模板有新版本时渲染提示与差异预览动作。
 * 升级确认与画布回写主流程由 TemplateCenter 承担，本组件只负责列表行的轻量入口
 * （点击拉取 diff；差异渲染复用 store.upgradePreview，无本地状态镜像）。
 */
import { useTemplateStore } from '../../stores/templateStore'

const props = defineProps<{ workflowId: string }>()
const store = useTemplateStore()
</script>

<template>
  <span v-if="store.upgradeNotice?.upgradeAvailable" class="wf-upgrade-actions">
    <span class="notice-tag">可选升级</span>
    <span class="ver">v{{ store.upgradeNotice.currentVersion }} → v{{ store.upgradeNotice.latestVersion }}</span>
    <button data-testid="list-preview-upgrade" @click="store.previewUpgrade(props.workflowId)">查看差异</button>
  </span>
  <div v-if="store.upgradePreview" class="wf-upgrade-diff">
    <div v-for="item in store.upgradePreview.diff" :key="item.path" class="diff-row">
      <code>{{ item.path }}</code><span>{{ item.before }}</span><b>→</b><span>{{ item.after }}</span>
    </div>
  </div>
</template>

<style scoped>
.wf-upgrade-actions{display:inline-flex;align-items:center;gap:8px}
.notice-tag{color:#e6a23c;font-weight:600}
.ver{color:var(--text-3)}
button{cursor:pointer;border:1px solid var(--border);border-radius:4px;padding:3px 10px;background:#fff}
.wf-upgrade-diff{border:1px solid var(--border);border-radius:6px;padding:8px 10px;max-height:200px;overflow:auto}
.diff-row{display:grid;grid-template-columns:2fr 1fr auto 1fr;gap:8px;padding:3px 0;border-bottom:1px solid var(--border)}
</style>
