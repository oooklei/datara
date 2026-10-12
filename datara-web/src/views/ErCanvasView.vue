<script setup lang="ts">
/** U5 ER 画布：数仓建模表实体关系编辑。
 *  I18 Task 13b 真实联调：real 模式由壳层安装 erAdapter（graphStore.load/save 接管 /models/er，
 *  节点=真实模型、边=真实关系、拖拽落位/关系增删随保存持久化）；
 *  mock 模式不安装适配器，保持原 dataStore 种子路径（行为零改动）。 */
import { onUnmounted } from 'vue'
import { erProfile } from '../graph/profiles'
import GraphWorkbench from '../graph/workbench/GraphWorkbench.vue'
import { isMock } from '../services'
import { useGraphStore } from '../stores/graph'
import { installErAdapter } from './erAdapter'

/* 安装须在子组件 GraphWorkbench onMounted（内部 graphStore.load）之前——父 setup 同步执行满足；
 * 卸载即恢复，保证其他 workbench 使用方（/dag 等）load/save 语义不受影响 */
const restore = isMock ? null : installErAdapter(useGraphStore())
onUnmounted(() => restore?.())
</script>

<template>
  <GraphWorkbench :profile="erProfile" doc-id="er_dw" />
</template>
