<script setup lang="ts">
/**
 * M15 数据安全 · 权限管理（RBAC）
 * 用户→角色→权限三层：左列角色权限矩阵（admin/dev/analyst/viewer × 能力），
 * 右列用户账号表（许可上限/授权域/状态）；管理员可增改用户（许可/域/停启用）。
 * 数据密级说明条：公开/内部/机密/绝密 → 对应策略。
 */
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { dataStore } from '../../services/mock/dataStore'
import { useAuthStore, SECURITY_LEVELS } from '../../stores/auth'
import type { User } from '../../services/types'

const auth = useAuthStore()
const users = ref<User[]>([])

const ROLE_MATRIX = [
  { code: 'admin', roleName: '数据平台管理员', edit: '全部', approve: '√', deploy: '√', desc: '平台全部能力 + 全密级' },
  { code: 'dev', roleName: '数据开发', edit: '开发/治理', approve: '×', deploy: '×', desc: '画布/任务/规则编辑，审批与部署只读' },
  { code: 'analyst', roleName: '数据分析', edit: '×', approve: '×', deploy: '×', desc: '全局只读，按许可访问数据' },
  { code: 'viewer', roleName: '只读访客', edit: '×', approve: '×', deploy: '×', desc: '全局只读，仅公开数据' },
]

async function reload() {
  users.value = [...((await dataStore.list<User>('users')) ?? [])]
}
onMounted(reload)

const SEC_COLORS: Record<string, string> = {
  公开: '#16a34a', 内部: '#1668dc', 机密: '#d97706', 绝密: '#dc2626',
}

/* ---- 编辑弹层 ---- */
const dlg = ref(false)
const form = ref<User | null>(null)
const isNew = ref(false)

function openEdit(u?: User) {
  isNew.value = !u
  form.value = u
    ? { ...u, domains: [...u.domains] }
    : { id: 'U' + String(users.value.length + 1).padStart(3, '0'), name: '', role: 'dev', roleName: '数据开发', clearance: '内部', domains: [], status: 'enabled', lastLogin: '-' }
  dlg.value = true
}

async function save() {
  const f = form.value
  if (!f) return
  if (!f.name.trim()) { ElMessage.warning('请填写用户名'); return }
  if (isNew.value && users.value.some((u) => u.name === f.name.trim())) {
    ElMessage.warning('用户名已存在'); return
  }
  f.name = f.name.trim()
  await dataStore.save('users', f)
  dlg.value = false
  await reload()
  ElMessage.success(isNew.value ? '用户已创建' : '用户已更新')
}

async function toggleStatus(u: User) {
  if (!auth.can('user:manage')) { ElMessage.warning('仅数据平台管理员可操作'); return }
  u.status = u.status === 'enabled' ? 'disabled' : 'enabled'
  await dataStore.save('users', u)
  ElMessage.success(`「${u.name}」已${u.status === 'enabled' ? '启用' : '停用'}`)
}
</script>

<template>
  <div class="page">
    <!-- 密级说明条 -->
    <div class="card sec-banner">
      <span class="shield-ico">⛨</span>
      <span class="sec-head">数据分级分类</span>
      <span v-for="lv in SECURITY_LEVELS" :key="lv" class="lv-chip" :style="{ color: SEC_COLORS[lv] ?? '#999', background: (SEC_COLORS[lv] ?? '#999') + '14' }">
        <span class="lv-dot" :style="{ background: SEC_COLORS[lv] ?? '#999' }" />{{ lv }}
      </span>
      <span class="hint">行级控制：表密级 ≤ 用户许可上限方可访问；列级控制：敏感字段预览自动脱敏；访问全量审计。</span>
    </div>

    <!-- 角色权限矩阵 -->
    <div class="card" style="padding:16px;margin-bottom:14px">
      <div class="tbl-toolbar"><span class="sec-head">角色权限矩阵（用户 → 角色 → 权限）</span></div>
      <table class="tbl">
        <thead><tr><th>角色</th><th>编辑能力</th><th>审批/发布</th><th>部署运维</th><th>说明</th></tr></thead>
        <tbody>
          <tr v-for="r in ROLE_MATRIX" :key="r.code">
            <td><b>{{ r.roleName }}</b><span class="mono" style="margin-left:6px;color:var(--text-3);font-size:11px">{{ r.code }}</span></td>
            <td>{{ r.edit }}</td>
            <td><span :class="r.approve === '√' ? 'mark yes' : 'mark no'">{{ r.approve }}</span></td>
            <td><span :class="r.deploy === '√' ? 'mark yes' : 'mark no'">{{ r.deploy }}</span></td>
            <td style="color:var(--text-2)">{{ r.desc }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 用户账号表 -->
    <div class="card" style="padding:16px">
      <div class="tbl-toolbar">
        <span class="sec-head">用户账号（{{ users.length }}）</span>
        <span class="spacer" />
        <button class="tb-new" @click="openEdit()">＋ 新建用户</button>
      </div>
      <table class="tbl">
        <thead><tr><th>用户</th><th>角色</th><th>许可上限</th><th>授权业务域</th><th>状态</th><th>最近登录</th><th style="width:130px">操作</th></tr></thead>
        <tbody>
          <tr v-for="u in users" :key="u.id">
            <td><b>{{ u.name }}</b><span class="mono" style="margin-left:6px;color:var(--text-3);font-size:11px">{{ u.id }}</span></td>
            <td><span class="pill info">{{ u.roleName }}</span></td>
            <td><span class="pill" :style="{ background: (SEC_COLORS[u.clearance] ?? '#999') + '1a', color: SEC_COLORS[u.clearance] }">{{ u.clearance }}</span></td>
            <td style="color:var(--text-2)">{{ u.domains.length ? u.domains.join('、') : '全部' }}</td>
            <td>
              <span class="pill" :class="u.status === 'enabled' ? 'ok' : 'err'">{{ u.status === 'enabled' ? '启用' : '停用' }}</span>
            </td>
            <td class="mono" style="font-size:11.5px;color:var(--text-3)">{{ u.lastLogin }}</td>
            <td>
              <button class="op-btn primary" :disabled="!auth.can('user:manage')" @click="openEdit(u)">编辑</button>
              <button class="op-btn" :disabled="!auth.can('user:manage')" @click="toggleStatus(u)">{{ u.status === 'enabled' ? '停用' : '启用' }}</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 编辑弹层 -->
    <div v-if="dlg" class="mask" @click.self="dlg = false">
      <div class="dialog">
        <div class="dlg-title">{{ isNew ? '新建用户' : '编辑用户' }}</div>
        <div class="dlg-body">
          <div class="field"><label>用户名</label><input v-model="form!.name" placeholder="姓名/账号" /></div>
          <div class="field"><label>角色</label>
            <select v-model="form!.role">
              <option v-for="r in ROLE_MATRIX" :key="r.code" :value="r.code">{{ r.roleName }}</option>
            </select>
          </div>
          <div class="field"><label>数据许可上限</label>
            <select v-model="form!.clearance">
              <option v-for="lv in SECURITY_LEVELS" :key="lv" :value="lv">{{ lv }}</option>
            </select>
          </div>
          <div class="field"><label>授权业务域（不选=全部）</label>
            <div style="display:flex;gap:10px;flex-wrap:wrap">
              <label v-for="d in ['交易域','财务域','商品域','经营域','公共']" :key="d" style="font-size:12.5px;cursor:pointer">
                <input type="checkbox" :value="d" v-model="form!.domains" /> {{ d }}
              </label>
            </div>
          </div>
        </div>
        <div class="dlg-foot">
          <button class="btn-ghost" @click="dlg = false">取消</button>
          <button class="btn-primary" @click="save">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ---- 密级说明条 ---- */
.sec-banner{display:flex;align-items:center;gap:10px;padding:12px 16px;margin-bottom:14px;flex-wrap:wrap}
.shield-ico{width:30px;height:30px;border-radius:var(--radius);background:rgba(22,104,220,.1);color:var(--primary);display:inline-flex;align-items:center;justify-content:center;font-size:15px;flex-shrink:0}
.sec-banner .hint{color:var(--text-3);font-size:12px;margin-left:auto}
.lv-chip{display:inline-flex;align-items:center;gap:5px;border-radius:var(--radius-lg);padding:2px 10px;font-size:11.5px;font-weight:600}
.lv-dot{width:6px;height:6px;border-radius:50%}
/* ---- 区块标题（渐变竖条，与全站统一） ---- */
.sec-head{display:flex;align-items:center;gap:8px;font-weight:700;font-size:14px}
.sec-head::before{content:'';width:3px;height:14px;border-radius:2px;background:linear-gradient(180deg,var(--primary),var(--purple))}
/* ---- 矩阵 √/× 语义色 ---- */
.mark.yes{color:var(--success);font-weight:700}
.mark.no{color:var(--text-3)}
/* ---- 操作/新建按钮（全站标准态） ---- */
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;color:var(--text-2)}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.op-btn.primary{color:var(--primary);border-color:rgba(22,104,220,.4);font-weight:600}
.op-btn:disabled{opacity:.45;cursor:not-allowed}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease)}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
/* ---- 编辑弹层 ---- */
.mask{position:fixed;inset:0;background:rgba(15,23,42,.45);display:flex;align-items:center;justify-content:center;z-index:50}
.dialog{background:#fff;border-radius:var(--radius-xl);width:440px;box-shadow:var(--shadow-xl);overflow:hidden;animation:dlgIn var(--dur-base) var(--ease)}
@keyframes dlgIn{from{opacity:0;transform:translateY(10px) scale(.98)}to{opacity:1;transform:none}}
.dlg-title{font-weight:700;padding:14px 18px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px}
.dlg-title::before{content:'';width:3px;height:14px;border-radius:2px;background:linear-gradient(180deg,var(--primary),var(--purple))}
.dlg-body{padding:16px 18px;display:flex;flex-direction:column;gap:12px}
.field{display:flex;flex-direction:column;gap:5px}
.field label{font-size:12px;color:var(--text-2);font-weight:500}
.field input,.field select{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:7px 10px;font-size:13px;outline:none;transition:border-color var(--dur-fast) var(--ease),box-shadow var(--dur-fast) var(--ease)}
.field input:focus,.field select:focus{border-color:var(--primary);box-shadow:0 0 0 2px rgba(22,104,220,.1)}
.dlg-foot{padding:12px 18px;border-top:1px solid var(--border);display:flex;justify-content:flex-end;gap:8px;background:var(--bg)}
.btn-ghost{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;cursor:pointer;transition:all var(--dur-base) var(--ease)}
.btn-ghost:hover{border-color:var(--primary);color:var(--primary)}
.btn-primary{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease)}
.btn-primary:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
</style>
