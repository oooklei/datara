<script setup lang="ts">
/**
 * 项目成员管理页（L3-04）。
 *
 * 票面锚：「members 三端点承接；owner/ADMIN 可管理」——权限闸门在后端（MANAGE_USER +
 * 域契约 can_manage_project），本页不做客户端权限判定，403 以错误态呈现。
 * 路由挂载归 L3-03（routes 冻结面零触碰，本件为可挂载视图组件）。
 */
import { onMounted, ref } from 'vue'
import {
  MEMBER_ROLES,
  addMember,
  listMembers,
  removeMember,
  updateMemberRole,
} from '../services/rebuild/memberApi'
import type { MemberEntry, MemberRole } from '../services/rebuild/memberApi'

const props = defineProps<{ projectId: number }>()

const loading = ref(true)
const error = ref('')
const members = ref<MemberEntry[]>([])

const newUsername = ref('')
const newRole = ref<MemberRole>('viewer')
const actionError = ref('')

async function reload(): Promise<void> {
  try {
    const page = await listMembers(props.projectId)
    members.value = page.list
    error.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : '成员列表加载失败'
  }
}

onMounted(async () => {
  await reload()
  loading.value = false
})

async function onAdd(): Promise<void> {
  const username = newUsername.value.trim()
  if (username === '') return
  try {
    await addMember(props.projectId, { username, role: newRole.value })
    newUsername.value = ''
    newRole.value = 'viewer'
    actionError.value = ''
    await reload()
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : '添加成员失败'
  }
}

async function onRoleChange(member: MemberEntry, event: Event): Promise<void> {
  const role = (event.target as HTMLSelectElement).value as MemberRole
  if (role === member.role) return
  try {
    await updateMemberRole(props.projectId, member.userId, role)
    member.role = role
    actionError.value = ''
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : '变更角色失败'
    await reload()
  }
}

async function onRemove(member: MemberEntry): Promise<void> {
  try {
    await removeMember(props.projectId, member.userId)
    actionError.value = ''
    await reload()
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : '移除成员失败'
  }
}
</script>

<template>
  <section class="project-members">
    <h2>项目成员</h2>

    <p v-if="loading" role="status" data-loading>加载中…</p>
    <p v-else-if="error" role="alert" data-list-error>{{ error }}</p>

    <template v-else>
      <form class="add-form" data-add-form @submit.prevent="onAdd">
        <input
          v-model="newUsername"
          data-username-input
          type="text"
          placeholder="用户名"
          aria-label="用户名"
        />
        <select v-model="newRole" data-role-input aria-label="角色">
          <option v-for="role in MEMBER_ROLES" :key="role" :value="role">{{ role }}</option>
        </select>
        <button type="submit" data-add-btn>添加成员</button>
      </form>
      <p v-if="actionError" role="alert" data-action-error>{{ actionError }}</p>

      <p v-if="members.length === 0" data-empty>暂无成员：请先添加项目成员</p>
      <table v-else class="member-table">
        <thead>
          <tr><th>用户 ID</th><th>角色</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr
            v-for="member in members"
            :key="member.userId"
            :data-member-id="member.userId"
          >
            <td data-member-user-id>{{ member.userId }}</td>
            <td>
              <select
                :value="member.role"
                data-role-select
                :aria-label="`成员 ${member.userId} 角色`"
                @change="onRoleChange(member, $event)"
              >
                <option v-for="role in MEMBER_ROLES" :key="role" :value="role">{{ role }}</option>
              </select>
            </td>
            <td>
              <button type="button" data-remove-btn @click="onRemove(member)">移除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </template>
  </section>
</template>

<style scoped>
.project-members {
  max-width: 720px;
}

.add-form {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.add-form input,
.add-form select {
  padding: 4px 8px;
}

.member-table {
  width: 100%;
  border-collapse: collapse;
}

.member-table th,
.member-table td {
  border: 1px solid #d9d9d9;
  padding: 6px 10px;
  text-align: left;
}
</style>
