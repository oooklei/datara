<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getToken } from '../services/http'
import { listProjects } from '../services/rebuild/projectApi'

const router = useRouter()
const route = useRoute()
const status = ref('')
const checking = ref(false)

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
    const candidate = typeof route.query.redirect === 'string' ? route.query.redirect : ''
    const redirect = candidate.startsWith('/') && !candidate.startsWith('//') ? candidate : '/'
    await router.replace(redirect)
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
      <div class="session-guide">
        <p>此入口仅接受受控验证运行器注入的短时令牌。</p>
        <p>验证 key 仅在服务端换取令牌；令牌只驻留当前页面内存，不进入 URL 或浏览器存储。</p>
        <p v-if="status" class="status" role="status">{{ status }}</p>
        <button class="submit" type="button" data-recheck-session :disabled="checking" @click="recheckSession">{{ checking ? '检测中…' : '重新检测会话' }}</button>
      </div>
      <p class="foot">会话由平台安全管理 · 注入成功后进入工作台</p>
    </section>
  </main>
</template>

<style scoped>
.login-wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,var(--primary-light,#eef5ff),var(--bg,#f7f9fc));padding:20px}
.login-card{width:400px;max-width:94vw;background:#fff;border:1px solid var(--border,#dfe5ef);border-radius:12px;box-shadow:0 8px 30px rgba(20,50,90,.1);padding:28px}
.brand{display:flex;align-items:center;gap:12px;margin-bottom:24px}.brand-mark{width:40px;height:40px;border-radius:10px;background:var(--primary,#2563eb);color:#fff;font-weight:700;font-size:20px;display:grid;place-items:center}.brand h1{font-size:17px;margin:0}.brand p{font-size:12px;color:var(--text-3,#7b8798);margin:3px 0 0}
.session-guide{display:grid;gap:12px;color:var(--text-2,#536174);font-size:13px;line-height:1.6}.session-guide p{margin:0}.status{padding:9px 10px;border-radius:6px;background:var(--primary-light,#eef5ff);color:var(--text,#263244)}.submit{width:100%;border:0;border-radius:6px;padding:10px;background:var(--primary,#2563eb);color:#fff;font-size:14px;font-weight:600;cursor:pointer}.submit:disabled{opacity:.65;cursor:wait}.foot{text-align:center;margin:18px 0 0;color:var(--text-3,#7b8798);font-size:11px}
</style>
