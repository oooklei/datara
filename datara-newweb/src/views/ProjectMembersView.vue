<script setup lang="ts">
/**
 * 项目成员管理页（P1 对齐）。
 *
 * 后端权限闸门：只有 admin 可管理成员（MANAGE_USER），非 admin 调接口直接 403。
 * 本页不做客户端权限判定（避免与后端漂移），403 以错误态呈现。
 *
 * P1 变更：
 *   - 表格展示 username / 状态 / 加入时间 / 项目角色（不再只渲染数字 user_id）
 *   - 角色下拉用项目角色词形（inherit / viewer / operator），从 /project-roles 端点动态拉取
 *   - 存量成员的 role 可能是平台角色词形（admin/developer/...），前端统一展示 projectRole
 */
import { computed, onMounted, ref, watch } from 'vue'
import {
  PROJECT_ROLE_LABELS,
  PROJECT_ROLES,
  addMember,
  listMembers,
  listProjectRoles,
  removeMember,
  updateMemberRole,
} from '../services/rebuild/memberApi'
import type { MemberEntry, MemberRole, ProjectRoleCatalogEntry } from '../services/rebuild/memberApi'

const props = defineProps<{ projectId: number }>()

const loading = ref(true)
const error = ref('')
const members = ref<MemberEntry[]>([])
const roleCatalog = ref<ProjectRoleCatalogEntry[]>([])
const rolesLoaded = ref(false)

const newUsername = ref('')
const newRole = ref<MemberRole>('inherit')
const actionError = ref('')
const filterKeyword = ref('')

const displayMembers = computed(() => {
  const keyword = filterKeyword.value.toLowerCase().trim()
  if (!keyword) return members.value
  return members.value.filter((m) =>
    m.username.toLowerCase().includes(keyword) ||
    (m.projectRole ?? m.role).toLowerCase().includes(keyword) ||
    String(m.userId).includes(keyword),
  )
})

let requestSeq = 0

async function reload(): Promise<void> {
  const requestId = ++requestSeq
  loading.value = true
  members.value = []
  try {
    const page = await listMembers(props.projectId)
    if (requestId !== requestSeq) return
    members.value = page.list
    error.value = ''
  } catch (err) {
    if (requestId !== requestSeq) return
    error.value = err instanceof Error ? err.message : '成员列表加载失败'
  } finally {
    if (requestId === requestSeq) loading.value = false
  }
}

async function loadRoleCatalog(): Promise<void> {
  try {
    roleCatalog.value = await listProjectRoles()
    rolesLoaded.value = true
  } catch {
    // 端点不可用时降级到常量
    roleCatalog.value = PROJECT_ROLES.map((value) => ({
      value, label: PROJECT_ROLE_LABELS[value],
      inheritsPlatform: value === 'inherit', permissions: null,
    }))
    rolesLoaded.value = true
  }
}

function displayRole(entry: MemberEntry): string {
  const value = entry.projectRole ?? (entry.role as MemberRole)
  return PROJECT_ROLE_LABELS[value as MemberRole] ?? value
}

function formatJoinedAt(iso: string | null): string {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  } catch {
    return iso
  }
}

onMounted(() => {
  void loadRoleCatalog()
})

watch(
  () => props.projectId,
  () => {
    actionError.value = ''
    void reload()
  },
  { immediate: true },
)

async function onAdd(): Promise<void> {
  const username = newUsername.value.trim()
  if (!username) return
  try {
    await addMember(props.projectId, { username, role: newRole.value })
    newUsername.value = ''
    newRole.value = 'inherit'
    actionError.value = ''
    await reload()
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : '添加成员失败'
  }
}

async function onRoleChange(member: MemberEntry, event: Event): Promise<void> {
  const role = (event.target as HTMLSelectElement).value as MemberRole
  if (role === (member.projectRole ?? member.role)) return
  try {
    const result = await updateMemberRole(props.projectId, member.userId, role)
    member.role = result.role
    member.projectRole = result.projectRole
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
          <option
            v-for="role in roleCatalog"
            :key="role.value"
            :value="role.value"
          >{{ role.label }}</option>
        </select>
        <button type="submit" data-add-btn>添加成员</button>
      </form>
      <p v-if="actionError" role="alert" data-action-error>{{ actionError }}</p>

      <div v-if="members.length > 0" class="members-toolbar">
        <input v-model.trim="filterKeyword" data-filter-keyword placeholder="搜索用户名或角色">
      </div>
      <p v-if="members.length === 0" data-empty>暂无成员：请先添加项目成员</p>
      <table v-else class="member-table">
        <thead>
          <tr><th>用户名</th><th>用户 ID</th><th>状态</th><th>加入时间</th><th>项目角色</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr
            v-for="member in displayMembers"
            :key="member.userId"
            :data-member-id="member.userId"
          >
            <td data-member-username>{{ member.username }}</td>
            <td data-member-user-id>{{ member.userId }}</td>
            <td>
              <span :class="['status-badge', member.status]">{{
                member.status === 'enabled' ? '启用' : member.status === 'disabled' ? '停用' : member.status
              }}</span>
            </td>
            <td>{{ formatJoinedAt(member.joinedAt) }}</td>
            <td>
              <select
                :value="member.projectRole ?? member.role"
                data-role-select
                :aria-label="`成员 ${member.username} 角色`"
                @change="onRoleChange(member, $event)"
              >
                <option
                  v-for="role in roleCatalog"
                  :key="role.value"
                  :value="role.value"
                >{{ role.label }}</option>
              </select>
            </td>
            <td>
              <button type="button" data-remove-btn @click="onRemove(member)">移除</button>
            </td>
          </tr>
          <tr v-if="displayMembers.length === 0"><td colspan="6">无匹配成员</td></tr>
        </tbody>
      </table>
    </template>
  </section>
</template>

<style scoped>
.project-members { max-width: 900px; }

.add-form {
  display: flex; gap: 8px; margin-bottom: 12px;
}
.add-form input, .add-form select { padding: 4px 8px; }

.members-toolbar { margin-bottom: 10px; }

.member-table {
  width: 100%; border-collapse: collapse;
}
.member-table th, .member-table td {
  border: 1px solid var(--border); padding: 6px 10px; text-align: left;
}

.status-badge {
  display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 12px;
}
.status-badge.enabled { background: var(--bg-2, #e8f5e9); color: var(--text-success, #2e7d32); }
.status-badge.disabled { background: var(--bg-2, #ffebee); color: var(--text-danger, #c62828); }
</style>
