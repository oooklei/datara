<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getToken } from '../services/http'
import { login } from '../services/rebuild/authApi'
import { listProjects } from '../services/rebuild/projectApi'

const router = useRouter()
const route = useRoute()
const status = ref('')
const checking = ref(false)
const username = ref('admin')
const password = ref('Admin@123')
const loggingIn = ref(false)
const showPassword = ref(false)
const demoAccounts = [
  { username: 'admin', password: 'Admin@123', role: '管理员' },
  { username: 'dev', password: 'Dev@123', role: '开发者' },
  { username: 'analyst', password: 'Analyst@123', role: '分析师' },
  { username: 'viewer', password: 'Viewer@123', role: '观察者' },
]

function safeRedirect() {
  const candidate = typeof route.query.redirect === 'string' ? route.query.redirect : ''
  return candidate.startsWith('/') && !candidate.startsWith('//') ? candidate : '/'
}

function fillAccount(account: (typeof demoAccounts)[number]) {
  username.value = account.username
  password.value = account.password
}

async function submitLogin() {
  status.value = ''
  if (!username.value.trim() || !password.value) {
    status.value = '请输入用户名与密码。'
    return
  }
  loggingIn.value = true
  try {
    await login(username.value.trim(), password.value)
    await router.replace(safeRedirect())
  } catch (cause) {
    status.value = cause instanceof Error ? cause.message : '登录失败，请检查用户名与密码。'
  } finally {
    loggingIn.value = false
  }
}

async function recheckSession() {
  status.value = ''
  if (!getToken()) {
    status.value = '尚未检测到有效会话，请由受控验证运行器完成注入后重试。'
    return
  }
  checking.value = true
  try {
    // A token-shaped string is not proof of a live server session.  Use the
    // smallest project-scoped read to detect expiry/revocation before leaving
    // the authentication boundary.
    await listProjects()
    await router.replace(safeRedirect())
  } catch {
    status.value = '会话已失效或无法验证，请由受控验证运行器重新注入短时令牌。'
  } finally {
    checking.value = false
  }
}
</script>

<template>
  <main class="login-wrap" aria-labelledby="login-title">
    <section class="login-card">
      <div class="brand">
        <span class="brand-mark" aria-hidden="true">D</span>
        <div><h1 id="login-title">Datara 数据治理平台</h1><p>统一登录 · 数据开发与治理工作台</p></div>
      </div>
      <form class="login-form" @submit.prevent="submitLogin">
        <label>用户名<input v-model="username" data-login-username autocomplete="username" autofocus /></label>
        <label>密码<span class="password-field"><input v-model="password" data-login-password :type="showPassword ? 'text' : 'password'" autocomplete="current-password" /><button type="button" @click="showPassword = !showPassword">{{ showPassword ? '隐藏' : '显示' }}</button></span></label>
        <button class="submit" type="submit" :disabled="loggingIn">{{ loggingIn ? '登录中…' : '登 录' }}</button>
      </form>
      <div class="demo-accounts" aria-label="演示账号">
        <p>演示账号（点击填充）</p>
        <button v-for="account in demoAccounts" :key="account.username" type="button" data-demo-account @click="fillAccount(account)"><span>{{ account.role }}</span><b>{{ account.username }}</b><code>{{ account.password }}</code></button>
      </div>
      <div class="session-guide">
        <p>也可由受控验证运行器注入短时令牌；令牌只驻留当前页面内存，不进入 URL 或浏览器存储。</p>
        <p v-if="status" class="status" role="status">{{ status }}</p>
        <button class="submit" type="button" data-recheck-session :disabled="checking" @click="recheckSession">{{ checking ? '检测中…' : '重新检测会话' }}</button>
      </div>
      <p class="foot">会话由平台安全管理 · 登录成功后进入工作台</p>
    </section>
  </main>
</template>

<style scoped>
.login-wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,var(--primary-light,#eef5ff),var(--bg,#f7f9fc));padding:20px}
.login-card{width:400px;max-width:94vw;background:#fff;border:1px solid var(--border,#dfe5ef);border-radius:12px;box-shadow:0 8px 30px rgba(20,50,90,.1);padding:28px}
.brand{display:flex;align-items:center;gap:12px;margin-bottom:24px}.brand-mark{width:40px;height:40px;border-radius:10px;background:var(--primary,#2563eb);color:#fff;font-weight:700;font-size:20px;display:grid;place-items:center}.brand h1{font-size:17px;margin:0}.brand p{font-size:12px;color:var(--text-3,#7b8798);margin:3px 0 0}
.login-form{display:grid;gap:14px}.login-form label{display:grid;gap:6px;color:var(--text-2,#536174);font-size:13px}.login-form input{box-sizing:border-box;width:100%;border:1px solid var(--border,#dfe5ef);border-radius:6px;padding:10px 11px;color:var(--text,#263244);outline:none}.login-form input:focus{border-color:var(--primary,#2563eb);box-shadow:0 0 0 3px rgba(37,99,235,.1)}.password-field{display:flex}.password-field input{border-radius:6px 0 0 6px}.password-field button{border:1px solid var(--border,#dfe5ef);border-left:0;border-radius:0 6px 6px 0;background:#fff;color:var(--primary,#2563eb);padding:0 12px;cursor:pointer}.demo-accounts{margin:18px 0;display:grid;grid-template-columns:1fr 1fr;gap:7px}.demo-accounts p{grid-column:1/-1;margin:0 0 2px;color:var(--text-3,#7b8798);font-size:12px}.demo-accounts button{display:grid;grid-template-columns:auto 1fr;gap:2px 7px;text-align:left;border:1px solid var(--border,#dfe5ef);border-radius:6px;background:#fff;padding:7px 8px;cursor:pointer}.demo-accounts button:hover{border-color:var(--primary,#2563eb)}.demo-accounts span{font-size:11px;color:var(--text-3,#7b8798)}.demo-accounts b{font-size:12px}.demo-accounts code{grid-column:1/-1;color:var(--text-2,#536174);font-size:11px}
.session-guide{display:grid;gap:12px;color:var(--text-2,#536174);font-size:13px;line-height:1.6}.session-guide p{margin:0}.status{padding:9px 10px;border-radius:6px;background:var(--primary-light,#eef5ff);color:var(--text,#263244)}.submit{width:100%;border:0;border-radius:6px;padding:10px;background:var(--primary,#2563eb);color:#fff;font-size:14px;font-weight:600;cursor:pointer}.submit:disabled{opacity:.65;cursor:wait}.foot{text-align:center;margin:18px 0 0;color:var(--text-3,#7b8798);font-size:11px}
</style>
