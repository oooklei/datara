<script setup lang="ts">
/**
 * M14 环境与依赖（/script/env）
 * 对齐 prototype/assets/pages/m14-script.js L295-344：
 * Python 环境表格（搜索）+ 新建环境抽屉（pandas/numpy 基础包）+
 * 安装包抽屉 + 克隆环境（确认）+ 启用/停用。操作按钮置顶（页头工具栏）。
 */
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { dataStore, ST } from '../../services/mock/dataStore'
import type { PyEnv, PyEnvPkg } from '../../services/types'
import ListFilterPanel from '../../components/ListFilterPanel.vue'

const envs = ref<PyEnv[]>([])
const keyword = ref('')
const filters = ref<Record<string, string>>({ status: '' })
const facets = [
  { key: 'status', label: '状态', options: [{ v: 'enabled', t: '已启用' }, { v: 'disabled', t: '已停用' }] },
]

async function reload() {
  // 必须展开为新数组：dataStore.save 原地修改数组，直接赋值不会触发 ref 更新
  envs.value = [...((await dataStore.list<PyEnv>('pyEnvs')) ?? [])]
}
onMounted(reload)

function stCls(s: string): string {
  return ST[s]?.cls ?? 'st-gray'
}
function stLabel(s: string): string {
  return ST[s]?.label ?? s
}

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return envs.value.filter((r) => {
    if (filters.value.status && r.status !== filters.value.status) return false
    if (!kw) return true
    return [r.id, r.name].some((s) => s.toLowerCase().includes(kw))
  })
})

/* ---- ID 取现有最大序号 +1：删除环境后再新建不会碰撞 ---- */
function nextId(): string {
  const seq = envs.value.reduce((m, e) => {
    const n = Number(String(e.id).replace(/^\D+/, ''))
    return Number.isFinite(n) && n > m ? n : m
  }, 0) + 1
  return 'VENV' + String(seq).padStart(2, '0')
}

/* ---- 新建环境 ---- */
const formVisible = ref(false)
const form = ref({ name: '', python: '3.10.4' })

function openCreate() {
  form.value = { name: '', python: '3.10.4' }
  formVisible.value = true
}

async function saveForm() {
  const name = form.value.name.trim()
  if (!name) {
    ElMessage.warning('请填写环境名称')
    return
  }
  const row: PyEnv = {
    id: nextId(),
    name,
    python: form.value.python,
    pkgs: [{ n: 'pandas', v: '2.1.1' }, { n: 'numpy', v: '1.26.0' }],
    status: 'enabled',
    used: 0,
  }
  envs.value.push(row)
  await dataStore.save('pyEnvs', row)
  ElMessage.success('环境已创建')
  formVisible.value = false
}

/* ---- 安装包 ---- */
const pkgVisible = ref(false)
const pkgTarget = ref<PyEnv | null>(null)
const pkgForm = ref({ name: '', v: '' })

function openAddPkg(e: PyEnv) {
  pkgTarget.value = e
  pkgForm.value = { name: '', v: '' }
  pkgVisible.value = true
}

async function savePkg() {
  const d = pkgTarget.value
  if (!d) return
  const n = pkgForm.value.name.trim()
  if (!n) {
    ElMessage.warning('请填写包名')
    return
  }
  const pkg: PyEnvPkg = { n, v: pkgForm.value.v.trim() || 'latest' }
  d.pkgs.push(pkg)
  await dataStore.save('pyEnvs', d)
  ElMessage.success('包 ' + n + ' 安装成功')
  pkgVisible.value = false
}

/* ---- 克隆环境 ---- */
async function cloneEnv(e: PyEnv) {
  try {
    await ElMessageBox.confirm('克隆「' + e.name + '」为新环境？', '克隆环境', { type: 'info' })
  } catch {
    return
  }
  const row: PyEnv = {
    id: nextId(),
    name: e.name + '-copy',
    python: e.python,
    pkgs: e.pkgs.map((p) => ({ ...p })), // 深拷贝包清单，避免克隆环境与源环境共享引用
    status: 'enabled',
    used: 0,
  }
  envs.value.push(row)
  await dataStore.save('pyEnvs', row)
  ElMessage.success('环境已克隆')
}

/* ---- 启用 / 停用 ---- */
async function toggleStatus(e: PyEnv) {
  e.status = e.status === 'enabled' ? 'disabled' : 'enabled'
  await dataStore.save('pyEnvs', e)
  ElMessage.success(e.status === 'enabled' ? '环境已启用' : '环境已停用')
  await reload()
}
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ListFilterPanel
      v-model:keyword="keyword"
      v-model:filters="filters"
      :facets="facets"
      :result-count="filtered.length"
      :total-count="envs.length"
      placeholder="搜索环境"
    />
    <div style="flex:1;min-width:0">
    <!-- 页头 + 顶部操作工具栏 -->
    <div class="card page-head">
      <div>
        <div class="ph-title">Python 环境与依赖</div>
        <div class="ph-desc">虚拟环境隔离管理：Python 版本 / 三方包清单 / 使用脚本数；支持包安装与环境克隆</div>
      </div>
      <span class="spacer" />
      <button class="tb-new" @click="openCreate">＋ 新建环境</button>
    </div>

    <!-- 环境列表 -->
    <div class="card" style="padding:16px">
      <div class="tbl-toolbar">
        <span class="card-title">环境列表</span>
        <span class="pill info">{{ filtered.length }} / {{ envs.length }}</span>
        <span class="spacer" />
      </div>
      <table class="tbl">
        <thead>
          <tr>
            <th>环境</th><th>包清单</th><th>使用脚本</th><th>状态</th><th style="width:190px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="e in filtered" :key="e.id">
            <td>
              <b>{{ e.name }}</b>
              <div style="font-size:11px;color:var(--text-3)">{{ e.id }} · Python {{ e.python }}</div>
            </td>
            <td>
              <span v-for="p in e.pkgs" :key="p.n" class="pkg mono">{{ p.n }} {{ p.v }}</span>
            </td>
            <td>{{ e.used }} 个</td>
            <td><span class="st" :class="stCls(e.status)"><span class="dot" />{{ stLabel(e.status) }}</span></td>
            <td>
              <button class="op-btn primary" @click="openAddPkg(e)">安装包</button>
              <button class="op-btn" @click="cloneEnv(e)">克隆</button>
              <button class="op-btn" @click="toggleStatus(e)">{{ e.status === 'enabled' ? '停用' : '启用' }}</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="filtered.length === 0" class="empty">未找到匹配的环境</div>
    </div>

    <!-- 新建环境抽屉 -->
    <el-drawer v-model="formVisible" title="新建 Python 环境" size="400px">
      <div class="form-grid">
        <label class="f-item">环境名称 *
          <input v-model="form.name" class="kw" style="width:100%" placeholder="如：py3-etl" />
        </label>
        <label class="f-item">Python 版本
          <select v-model="form.python" class="kw" style="width:100%">
            <option value="3.10.4">3.10.4</option>
            <option value="3.9.7">3.9.7</option>
            <option value="3.11.6">3.11.6</option>
          </select>
        </label>
        <div class="lock-tip">创建后自动安装 pandas/numpy 基础包；信创环境（鲲鹏920）使用 aarch64 轮子源。</div>
      </div>
      <div style="margin-top:16px;display:flex;gap:8px">
        <button class="tb-new" @click="saveForm">保存</button>
        <button class="op-btn" @click="formVisible = false">取消</button>
      </div>
    </el-drawer>

    <!-- 安装包抽屉 -->
    <el-drawer v-model="pkgVisible" :title="pkgTarget ? '安装包 - ' + pkgTarget.name : '安装包'" size="400px">
      <div class="form-grid">
        <label class="f-item">包名 *
          <input v-model="pkgForm.name" class="kw" style="width:100%" placeholder="如：scikit-learn" />
        </label>
        <label class="f-item">版本（可选）
          <input v-model="pkgForm.v" class="kw" style="width:100%" placeholder="如：1.3.2，留空装最新" />
        </label>
        <div class="lock-tip">pip 安装源：内网镜像（鲲鹏 aarch64），支持离线 whl 包。</div>
      </div>
      <div style="margin-top:16px;display:flex;gap:8px">
        <button class="tb-new" @click="savePkg">安装</button>
        <button class="op-btn" @click="pkgVisible = false">取消</button>
      </div>
    </el-drawer>
    </div>
  </div>
</template>

<style scoped>
.page-head{display:flex;align-items:center;gap:12px;padding:14px 16px;margin-bottom:14px}
.ph-title{font-weight:700;font-size:15px}
.ph-desc{font-size:12px;color:var(--text-3);margin-top:2px}
.spacer{flex:1}
.card-title{font-weight:700;font-size:14px}
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;padding:9px 10px;background:var(--bg);color:var(--text-2);font-weight:600;border-bottom:1px solid var(--border)}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--border)}
.tbl tr:hover td{background:var(--primary-light)}
.kw{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 10px;font-size:12.5px;width:190px;outline:none}
.kw:focus{border-color:var(--primary)}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease)}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
.op-btn.primary{color:var(--primary);border-color:rgba(22,104,220,.4);font-weight:600}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
.pkg{display:inline-block;border:1px solid var(--border-strong);border-radius:4px;padding:0 7px;font-size:11px;color:var(--text-2);margin:1px 4px 1px 0}
.form-grid{display:flex;flex-direction:column;gap:12px}
.f-item{display:flex;flex-direction:column;gap:5px;font-size:12.5px;color:var(--text-2)}
.lock-tip{background:var(--warn-bg);color:var(--warn);border-radius:var(--radius-sm);padding:8px 10px;font-size:11.5px}
</style>
