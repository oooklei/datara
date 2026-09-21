<script setup lang="ts">
/**
 * U3 流设计器：实时链路编排（路由参数 = 文档 id）。
 * 流任务（如 SJ001-004）无预置图文档时，从任务定义（source/sink/sql）派生用例链路并保存，
 * 画布打开即可编辑且用户修改随保存持久化；找不到任务则渲染空画布。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { streamProfile } from '../graph/profiles'
import GraphWorkbench from '../graph/workbench/GraphWorkbench.vue'
import { buildStreamDoc } from '../graph/model/deriveDoc'
import { graphService, isMock } from '../services'
import { dataStore } from '../services/mock/dataStore'
import type { StreamJob } from '../services/types'

/** 双用法：独立路由 /stream/design/:id（route.params.id）或任务中心内嵌（props.docId，配合 :key 强刷） */
const props = defineProps<{ docId?: string }>()
const route = useRoute()
const curId = computed(() => props.docId ?? String(route.params.id ?? ''))
const ready = ref(false)

async function prepare(id: string) {
  if (!id) return
  ready.value = false
  const doc = await graphService.get(id)
  /* F56d：从 mock 流任务定义派生画布仅 mock 模式执行；real 候选池保证 doc 已落库，无图则渲染空画布 */
  if (isMock && (!doc || doc.nodes.length === 0)) {
    const jobs = await dataStore.list<StreamJob>('streamJobs')
    const j = jobs.find((x) => x.id === id)
    const derived = j ? buildStreamDoc(j) : null
    if (derived) await graphService.save(derived, '从任务定义派生用例流图')
  }
  ready.value = true
}

onMounted(() => { if (curId.value) prepare(curId.value) })
watch(curId, (id) => { if (id) prepare(id) })
</script>

<template>
  <GraphWorkbench v-if="ready" :key="curId" :profile="streamProfile" :doc-id="curId" />
</template>
