<template>
  <div class="system-admin" aria-label="系统管理">
    <section v-if="isAdmin" class="system-block system-links" aria-label="系统能力" data-system-links>
      <h1>系统管理</h1>
      <nav><RouterLink to="/open/key">API Key</RouterLink><RouterLink to="/open/api">API 管理</RouterLink><RouterLink to="/sec/audit">访问审计</RouterLink></nav>
    </section>
    <section v-if="isAdmin" class="system-block" aria-label="平台用户管理">
      <h2>平台用户管理</h2>
      <p class="system-hint">账号创建、角色、启停和密码生命周期；权限与最后管理员保护由后端强制执行。</p>
      <UserManagementView />
    </section>
    <p v-else class="system-notice" data-admin-required>平台用户、API Key、API 与 LLM 配置仅管理员可操作；当前账号可查看权限矩阵。</p>
    <section v-if="projectId !== undefined" class="system-block" aria-label="项目成员管理">
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
 * 五组 19 项菜单契约为冻结面（projectMenu.contract.test.ts 五组恒 19），成员管理
 * 不挂项目功能段（systemAdminView.contract.test.ts 锚定 seg='system' 落 404），
 * 由 /sys 与 /p/:projectId/system 双路由承载（后者 projectId 透传点亮成员区块，
 * AppShell 项目切换器「成员管理」入口直达）；ProjectMembersView 为 L3-04
 * 既有组件（prop 驱动），此处只补 UI 入口。
 */
import { computed } from 'vue'
import PermissionMatrixView from '../PermissionMatrixView.vue'
import ProjectMembersView from '../ProjectMembersView.vue'
import UserManagementView from './UserManagementView.vue'
import { authAccount } from '../../services/rebuild/authApi'

defineProps<{ projectId?: number }>()
const isAdmin = computed(() => authAccount.value?.role === 'admin')
</script>

<style scoped>
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
.system-links h1{margin:0}.system-links nav{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}.system-links a{padding:8px 12px;border:1px solid var(--border);border-radius:7px;background:var(--card);color:var(--primary);text-decoration:none}
.system-notice{margin:0;padding:12px;border:1px solid var(--border);border-radius:8px;background:var(--card);color:var(--text-2)}

.system-hint {
  margin: 0 0 12px;
  color: var(--text-secondary, var(--text-2));
  font-size: 13px;
}
</style>
