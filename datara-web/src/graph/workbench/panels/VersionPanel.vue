<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { VersionMeta } from '../../../services/types'
import { graphService, isMock } from '../../../services'
import { useGraphStore } from '../../../stores/graph'

const props = defineProps<{ docId: string }>()
const store = useGraphStore()
const versions = ref<VersionMeta[]>([])

onMounted(async () => {
  versions.value = await graphService.listVersions(props.docId)
})

async function rollback(v: number) {
  const doc = await graphService.rollback(props.docId, v)
  store.setDoc(doc) // 回滚已在服务层持久化，不置脏
  ElMessage.success(isMock ? `已回滚到版本 v${v}（mock：恢复历史快照）` : `已回滚到版本 v${v}（已追加新版本快照）`)
}
</script>

<template>
  <div>
    <div v-if="versions.length === 0" style="padding:14px;text-align:center;color:var(--text-3);font-size:12px">
      暂无历史版本。每次「保存」都会生成一个新版本（mock 持久化，刷新浏览器仍在）。
    </div>
    <div
      v-for="v in versions" :key="v.version"
      style="display:flex;align-items:center;gap:8px;padding:8px 6px;border-bottom:1px dashed var(--border);font-size:12px"
    >
      <span class="pill info">v{{ v.version }}</span>
      <span style="flex:1">
        {{ v.updatedAt.slice(0, 16).replace('T', ' ') }} · {{ v.operator }}
        <span v-if="v.remark" style="color:var(--text-3)"> · {{ v.remark }}</span>
      </span>
      <button
        style="border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:3px 9px;font-size:11px;cursor:pointer"
        @click="rollback(v.version)"
      >回滚</button>
    </div>
  </div>
</template>
