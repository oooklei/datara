<script setup lang="ts">
/** U5 ER 画布：数仓建模表实体关系编辑 */
import { erProfile } from '../graph/profiles'
import GraphWorkbench from '../graph/workbench/GraphWorkbench.vue'
</script>

<template>
  <GraphWorkbench :profile="erProfile" doc-id="er_dw" />
</template>
