<script setup lang="ts">
/**
 * F5 登录页：四角色账号提示 + 登录表单。
 * 风格与既有页面一致（card/sec-head/pill 类名约定）；登录成功跳 '/'。
 */
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()

const userName = ref('')
const pwd = ref('')
const loading = ref(false)
const showPwd = ref(false)

/** 四账号提示（install.sh 初始账号；密码可被环境变量覆盖，此处为默认值） */
const accounts = [
  { user: 'admin', pwd: 'Admin@123', role: '管理员', cls: 'info' },
  { user: 'dev', pwd: 'Dev@123', role: '开发', cls: 'purple' },
  { user: 'analyst', pwd: 'Analyst@123', role: '分析师', cls: 'warn' },
  { user: 'viewer', pwd: 'Viewer@123', role: '观察者', cls: 'ok' },
]

async function onLogin() {
  if (!userName.value.trim() || !pwd.value) {
    ElMessage.warning('请输入用户名与密码')
    return
  }
  loading.value = true
  try {
    await auth.login(userName.value.trim(), pwd.value)
    ElMessage.success(`欢迎，${auth.account?.name ?? userName.value}`)
    router.replace('/')
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '登录失败')
  } finally {
    loading.value = false
  }
}

function fill(u: string, p: string) {
  userName.value = u
  pwd.value = p
}
</script>

<template>
  <div class="login-wrap">
    <div class="login-card">
      <div class="lg-brand">
        <span class="lg-mark">D</span>
        <div>
          <div class="lg-title">Datara 数据治理平台</div>
          <div class="lg-sub">统一登录 · 四角色权限（I1 平台基座）</div>
        </div>
      </div>

      <div class="lg-form">
        <div class="lg-row">
          <label class="lg-label">用户名</label>
          <input v-model="userName" class="lg-input" placeholder="如 admin" @keyup.enter="onLogin" />
        </div>
        <div class="lg-row">
          <label class="lg-label">密码</label>
          <input
            v-model="pwd" class="lg-input" :type="showPwd ? 'text' : 'password'"
            placeholder="请输入密码" @keyup.enter="onLogin"
          />
          <button class="lg-eye" type="button" @click="showPwd = !showPwd">{{ showPwd ? '隐藏' : '显示' }}</button>
        </div>
        <button class="lg-submit" :disabled="loading" @click="onLogin">{{ loading ? '登录中…' : '登 录' }}</button>
      </div>

      <div class="sec-head" style="margin:18px 0 8px">演示账号（点击填充）</div>
      <div class="lg-accs">
        <button v-for="a in accounts" :key="a.user" class="lg-acc" type="button" @click="fill(a.user, a.pwd)">
          <span class="pill" :class="a.cls">{{ a.role }}</span>
          <b class="mono">{{ a.user }}</b>
          <span class="mono lg-pwd">{{ a.pwd }}</span>
        </button>
      </div>
      <div class="lg-foot">登录即代表同意平台使用规范 · 会话有效期 24h</div>
    </div>
  </div>
</template>

<style scoped>
.login-wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,var(--primary-light),var(--bg));padding:20px}
.login-card{width:400px;max-width:94vw;background:#fff;border:1px solid var(--border);border-radius:var(--radius-lg,10px);box-shadow:var(--shadow,0 8px 30px rgba(0,0,0,.08));padding:26px 28px}
.lg-brand{display:flex;align-items:center;gap:12px;margin-bottom:20px}
.lg-mark{width:40px;height:40px;border-radius:10px;background:var(--primary);color:#fff;font-weight:700;font-size:20px;display:flex;align-items:center;justify-content:center}
.lg-title{font-size:17px;font-weight:700}
.lg-sub{font-size:11.5px;color:var(--text-3);margin-top:2px}
.lg-row{display:flex;align-items:center;gap:8px;margin-bottom:12px;position:relative}
.lg-label{width:52px;flex-shrink:0;font-size:12.5px;color:var(--text-2);text-align:right}
.lg-input{flex:1;border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:9px 11px;font-size:13px;outline:none;color:var(--text)}
.lg-input:focus{border-color:var(--primary)}
.lg-eye{position:absolute;right:8px;border:none;background:none;font-size:11px;color:var(--text-3);cursor:pointer}
.lg-submit{width:100%;border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:10px 0;font-size:13.5px;font-weight:600;cursor:pointer;margin-top:4px}
.lg-submit:hover{background:var(--primary-hover)}
.lg-submit:disabled{opacity:.6;cursor:not-allowed}
.sec-head{font-weight:700;font-size:13px}
.lg-accs{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.lg-acc{display:flex;align-items:center;gap:6px;border:1px solid var(--border-strong);background:var(--bg);border-radius:var(--radius-sm);padding:7px 9px;font-size:11.5px;cursor:pointer}
.lg-acc:hover{border-color:var(--primary)}
.lg-pwd{color:var(--text-3);font-size:10.5px;margin-left:auto}
.lg-foot{margin-top:16px;text-align:center;font-size:10.5px;color:var(--text-3)}
.pill{display:inline-flex;align-items:center;padding:1px 8px;border-radius:var(--radius-lg,999px);font-size:10.5px;font-weight:500}
.pill.info{background:var(--info-bg);color:var(--info)}
.pill.purple{background:#f1eaff;color:var(--purple)}
.pill.warn{background:var(--warn-bg);color:var(--warn)}
.pill.ok{background:var(--success-bg);color:var(--success)}
.mono{font-family:ui-monospace,Consolas,monospace}
</style>
