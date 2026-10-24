<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { login } from '../services/rebuild/authApi'

const router = useRouter()
const route = useRoute()
const username = ref('')
const password = ref('')
const loading = ref(false)
const showPassword = ref(false)
const error = ref('')

async function submit() {
  error.value = ''
  if (!username.value.trim() || !password.value) {
    error.value = '请输入用户名与密码'
    return
  }
  loading.value = true
  try {
    await login(username.value.trim(), password.value)
    const redirect = typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/')
      ? route.query.redirect
      : '/'
    await router.replace(redirect)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '登录失败，请稍后重试'
  } finally {
    loading.value = false
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
      <form class="login-form" @submit.prevent="submit">
        <label>用户名<input v-model="username" autocomplete="username" placeholder="请输入用户名" autofocus /></label>
        <label>密码<div class="password-field"><input v-model="password" :type="showPassword ? 'text' : 'password'" autocomplete="current-password" placeholder="请输入密码" /><button type="button" @click="showPassword = !showPassword">{{ showPassword ? '隐藏' : '显示' }}</button></div></label>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <button class="submit" type="submit" :disabled="loading">{{ loading ? '登录中…' : '登 录' }}</button>
      </form>
      <p class="foot">会话由平台安全管理 · 登录后进入工作台</p>
    </section>
  </main>
</template>

<style scoped>
.login-wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,var(--primary-light,#eef5ff),var(--bg,#f7f9fc));padding:20px}
.login-card{width:400px;max-width:94vw;background:#fff;border:1px solid var(--border,#dfe5ef);border-radius:12px;box-shadow:0 8px 30px rgba(20,50,90,.1);padding:28px}
.brand{display:flex;align-items:center;gap:12px;margin-bottom:24px}.brand-mark{width:40px;height:40px;border-radius:10px;background:var(--primary,#2563eb);color:#fff;font-weight:700;font-size:20px;display:grid;place-items:center}.brand h1{font-size:17px;margin:0}.brand p{font-size:12px;color:var(--text-3,#7b8798);margin:3px 0 0}
.login-form label{display:block;color:var(--text-2,#536174);font-size:13px;margin:0 0 14px}.login-form input{box-sizing:border-box;width:100%;margin-top:6px;border:1px solid var(--border-strong,#cbd5e1);border-radius:6px;padding:10px 11px;font-size:13px;outline:none}.login-form input:focus{border-color:var(--primary,#2563eb)}
.password-field{position:relative}.password-field input{padding-right:54px}.password-field button{position:absolute;right:8px;bottom:8px;border:0;background:none;color:var(--text-3,#7b8798);font-size:11px;cursor:pointer}.error{margin:-3px 0 10px;color:#c0392b;font-size:12px}.submit{width:100%;border:0;border-radius:6px;padding:10px;background:var(--primary,#2563eb);color:#fff;font-size:14px;font-weight:600;cursor:pointer}.submit:disabled{opacity:.6;cursor:not-allowed}.foot{text-align:center;margin:18px 0 0;color:var(--text-3,#7b8798);font-size:11px}
</style>
