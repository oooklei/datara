<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import {
  createUser,
  listUsers,
  updateUserPassword,
  updateUserRole,
  updateUserStatus,
  USER_ROLES,
  type PlatformUser,
} from '../../services/rebuild/userApi'
import type { AuthRole } from '../../services/rebuild/authApi'

const rows = ref<PlatformUser[]>([])
const loading = ref(false)
const error = ref('')
const feedback = ref('')
const form = reactive({ username: '', password: '', role: 'viewer' as AuthRole })

const message = (cause: unknown) => cause instanceof Error ? cause.message : String(cause)

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try { rows.value = (await listUsers()).list }
  catch (cause) { error.value = message(cause) }
  finally { loading.value = false }
}

async function submit(): Promise<void> {
  if (!form.username.trim() || !form.password) return
  error.value = ''
  try {
    await createUser({ username: form.username.trim(), password: form.password, role: form.role })
    feedback.value = `用户 ${form.username.trim()} 已创建`
    form.username = ''; form.password = ''; form.role = 'viewer'
    await load()
  } catch (cause) { error.value = message(cause) }
}

async function changeRole(row: PlatformUser, event: Event): Promise<void> {
  const role = (event.target as HTMLSelectElement).value as AuthRole
  error.value = ''
  try { await updateUserRole(row.id, role); row.role = role; feedback.value = `${row.username} 角色已更新` }
  catch (cause) { error.value = message(cause); (event.target as HTMLSelectElement).value = row.role }
}

async function toggleStatus(row: PlatformUser): Promise<void> {
  const status = row.status === 'enabled' ? 'disabled' : 'enabled'
  error.value = ''
  try { await updateUserStatus(row.id, status); row.status = status; feedback.value = `${row.username} 状态已更新` }
  catch (cause) { error.value = message(cause) }
}

async function resetPassword(row: PlatformUser): Promise<void> {
  const password = globalThis.prompt?.(`为 ${row.username} 设置新密码`)
  if (!password) return
  try { await updateUserPassword(row.id, password); feedback.value = `${row.username} 密码已更新，会话已撤销` }
  catch (cause) { error.value = message(cause) }
}

onMounted(load)
</script>

<template>
  <div class="users" data-user-management>
    <form class="user-create" data-user-create @submit.prevent="submit">
      <input v-model="form.username" data-new-username placeholder="用户名" autocomplete="off" />
      <input v-model="form.password" data-new-password type="password" placeholder="初始密码" autocomplete="new-password" />
      <select v-model="form.role" aria-label="新用户角色"><option v-for="role in USER_ROLES" :key="role">{{ role }}</option></select>
      <button type="submit">创建用户</button>
    </form>
    <p v-if="feedback" role="status" class="ok">{{ feedback }}</p>
    <div v-if="error" role="alert" class="error"><span>{{ error }}</span><button type="button" @click="load">重试</button></div>
    <p v-if="loading">用户加载中…</p>
    <p v-else-if="!error && rows.length === 0" class="empty">暂无平台用户</p>
    <div v-else class="table-wrap">
      <table>
        <thead><tr><th>账号</th><th>角色</th><th>状态</th><th>创建时间</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id" :data-user-row="row.id">
            <td><b>{{ row.username }}</b><small>#{{ row.id }}</small></td>
            <td><select :value="row.role" :data-user-role="row.id" @change="changeRole(row, $event)"><option v-for="role in USER_ROLES" :key="role">{{ role }}</option></select></td>
            <td><span :class="['status', row.status]">{{ row.status === 'enabled' ? '启用' : '停用' }}</span></td>
            <td>{{ row.createdAt || '—' }}</td>
            <td class="actions"><button type="button" :data-user-status="row.id" @click="toggleStatus(row)">{{ row.status === 'enabled' ? '停用' : '启用' }}</button><button type="button" @click="resetPassword(row)">重置密码</button></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.users{display:grid;gap:12px}.user-create{display:grid;grid-template-columns:1fr 1fr 150px auto;gap:8px}.user-create input,.user-create select,td select{border:1px solid var(--border);border-radius:6px;background:var(--card);color:var(--text);padding:8px}.users button{border:1px solid var(--border);border-radius:6px;background:var(--card);color:var(--primary);padding:7px 10px;cursor:pointer}.user-create button{border-color:var(--primary);background:var(--primary);color:var(--on-primary,#fff)}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse}th,td{padding:9px;border-bottom:1px solid var(--border);text-align:left;font-size:12px}td:first-child{display:grid}td small{color:var(--text-3)}.actions{display:flex;gap:5px}.status{padding:2px 7px;border-radius:10px}.status.enabled,.ok{color:var(--success)}.status.disabled,.error{color:var(--danger)}.error{display:flex;justify-content:space-between}.empty{color:var(--text-3)}
@media(max-width:760px){.user-create{grid-template-columns:1fr 1fr}.table-wrap{max-width:100%}}
</style>
