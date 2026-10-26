<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getToken } from '../services/http'

const router = useRouter()
const route = useRoute()
const status = ref('')

async function recheckSession() {
  status.value = ''
  if (!getToken()) {
    status.value = '尚未检测到有效会话，请由受控验证运行器完成注入后重试。'
    return
  }
  const redirect = typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/')
    ? route.query.redirect
    : '/'
  await router.replace(redirect)
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
        <button class="submit" type="button" data-recheck-session @click="recheckSession">重新检测会话</button>
      </div>
      <p class="foot">会话由平台安全管理 · 注入成功后进入工作台</p>
    </section>
  </main>
</template>

<style scoped>
/* 设计令牌：由全局 styles/theme.css 的 :root 提供（§4.4.3 风格统一），本文件无 fallback 十六进制。 */
.login-wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,var(--primary-light),var(--bg));padding:20px}
.login-card{width:400px;max-width:94vw;background:var(--card);border:1px solid var(--border);border-radius:12px;box-shadow:0 8px 30px rgba(20,50,90,.1);padding:28px}
.brand{display:flex;align-items:center;gap:12px;margin-bottom:24px}.brand-mark{width:40px;height:40px;border-radius:var(--radius-lg);background:var(--primary);color:var(--card);font-weight:700;font-size:20px;display:grid;place-items:center}.brand h1{font-size:17px;margin:0}.brand p{font-size:12px;color:var(--text-3);margin:3px 0 0}
.session-guide{display:grid;gap:12px;color:var(--text-2);font-size:13px;line-height:1.6}.session-guide p{margin:0}.status{padding:9px 10px;border-radius:var(--radius-sm);background:var(--primary-light);color:var(--text)}.submit{width:100%;border:0;border-radius:var(--radius-sm);padding:10px;background:var(--primary);color:var(--card);font-size:14px;font-weight:600;cursor:pointer}.foot{text-align:center;margin:18px 0 0;color:var(--text-3);font-size:11px}
</style>
