<template>
  <div class="system-admin" aria-label="系统管理">
    <section class="system-block" aria-label="项目成员管理">
      <h2>项目成员管理</h2>
      <p class="system-hint">项目内成员增删与角色调整；owner/ADMIN 可管理（权限闸门在后端，403 呈现为错误态）。</p>
      <ProjectMembersView :project-id="projectId" />
    </section>
    <section class="system-block" aria-label="平台权限矩阵">
      <h2>平台权限矩阵</h2>
      <p class="system-hint">四角色 × 权限点只读快照（权威源后端 identity/contracts.py）。</p>
      <PermissionMatrixView />
    </section>
  </div>
</template>

<script setup lang="ts">
/**
 * T4（D-05 / §5A.11 项目成员管理）：系统管理段（/p/:projectId/system）承载页。
 *
 * 七段菜单契约为冻结面（projectMenu.contract.test.ts 七段恒为 7），成员管理
 * 依设计定位「项目权限与安全配置」组合进 system 段，零破坏段序与 data-seg 锚；
 * ProjectMembersView 为 L3-04 既有组件（prop 驱动），此处只补 UI 入口。
 */
import PermissionMatrixView from '../PermissionMatrixView.vue'
import ProjectMembersView from '../ProjectMembersView.vue'

defineProps<{ projectId: number }>()
</script>

<style scoped>
/* 设计令牌：由全局 styles/theme.css 的 :root 提供（§4.4.3 风格统一），本文件不再就地重复定义。 */
.system-admin {
  max-width: 1280px;
  margin: 0 auto;
  padding: 24px;
  display: grid;
  gap: 28px;
}

.system-block h2 {
  margin: 0 0 4px;
  font-size: 18px;
}

.system-hint {
  margin: 0 0 12px;
  color: var(--text-secondary);
  font-size: 13px;
}
</style>
