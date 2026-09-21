<script setup lang="ts">
/**
 * M14 脚本库（/script/list）
 * 对齐 prototype/assets/pages/m14-script.js L7-293：
 * 脚本表格（搜索/语言/状态筛选）+ 新建/编辑抽屉（行号编辑器 + 运行测试/语法检查）+
 * 执行（本地/SSH，写 execLogs）+ 脚本查看（执行历史）+ 发布/启停/删除 + 执行日志表（详情/重跑）。
 * 操作按钮置顶（页头工具栏）。
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { dataStore, ST } from '../../services/mock/dataStore'
import { localTime } from '../../services/mock/timeUtil'
import type { Script, PyEnv, RemoteNode, ExecLog } from '../../services/types'
import ListFilterPanel from '../../components/ListFilterPanel.vue'

const router = useRouter()

const scripts = ref<Script[]>([])
const logs = ref<ExecLog[]>([])
const pyEnvs = ref<PyEnv[]>([])
const remoteNodes = ref<RemoteNode[]>([])
const userName = ref('王工')

async function reload() {
  // 必须展开为新数组：dataStore.save 原地修改数组，直接赋值不会触发 ref 更新
  scripts.value = [...((await dataStore.list<Script>('scripts')) ?? [])]
  const ls = [...((await dataStore.list<ExecLog>('execLogs')) ?? [])]
  ls.sort((a, b) => (a.id < b.id ? 1 : -1)) // 新日志在前（id 含日期与序号，可直接字典序比较）
  logs.value = ls
  pyEnvs.value = [...((await dataStore.list<PyEnv>('pyEnvs')) ?? [])]
  remoteNodes.value = [...((await dataStore.list<RemoteNode>('remoteNodes')) ?? [])]
  const u = await dataStore.get<{ name: string; role: string }>('user')
  if (u?.name) userName.value = u.name
}
onMounted(reload)

/* ---- 定时器统一管理（组件卸载时清理，避免泄漏） ---- */
const timers = new Set<number>()
function later(fn: () => void, ms: number) {
  const id = window.setTimeout(() => {
    timers.delete(id)
    fn()
  }, ms)
  timers.add(id)
}
onBeforeUnmount(() => {
  for (const id of timers) window.clearTimeout(id)
  timers.clear()
})

/* ---- ST 状态徽标 ---- */
function stCls(s: string): string {
  return ST[s]?.cls ?? 'st-gray'
}
function stLabel(s: string): string {
  return ST[s]?.label ?? s
}
function langPill(lang: string): string {
  return lang === 'Python' ? 'info' : lang === 'Shell' ? 'ok' : 'warn'
}

/* ---- 筛选（主列表走左侧筛选面板；执行日志区保留原筛选） ---- */
const keyword = ref('')
const filters = ref<Record<string, string>>({ lang: '', status: '' })
const logKeyword = ref('')
const logStatus = ref('')

const facets = [
  { key: 'lang', label: '语言', options: [{ v: 'Python', t: 'Python' }, { v: 'Shell', t: 'Shell' }, { v: 'Java', t: 'Java' }] },
  { key: 'status', label: '状态', options: [{ v: 'published', t: '已发布' }, { v: 'draft', t: '草稿' }, { v: 'disabled', t: '已停用' }] },
]

const filteredScripts = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return scripts.value.filter((r) => {
    if (filters.value.lang && r.lang !== filters.value.lang) return false
    if (filters.value.status && r.status !== filters.value.status) return false
    if (!kw) return true
    return [r.id, r.name, r.lang].some((s) => s.toLowerCase().includes(kw))
  })
})
const filteredLogs = computed(() => {
  const kw = logKeyword.value.trim().toLowerCase()
  return logs.value.filter((r) => {
    if (logStatus.value && r.status !== logStatus.value) return false
    if (!kw) return true
    return [r.id, r.script, r.mode].some((s) => s.toLowerCase().includes(kw))
  })
})

/* ---- 新建 / 编辑脚本抽屉（行号编辑器） ---- */
const formVisible = ref(false)
const editing = ref<Script | null>(null)
const form = ref({ name: '', lang: 'Python', venv: 'py3-data', code: '' })

const lineNums = computed(() => {
  const n = form.value.code.split('\n').length
  return Array.from({ length: n }, (_, i) => i + 1).join('\n')
})
const gutterEl = ref<HTMLElement | null>(null)
function syncGutter(e: Event) {
  const t = e.target as HTMLTextAreaElement
  if (gutterEl.value) gutterEl.value.scrollTop = t.scrollTop
}

/* 编辑器工具条输出（运行测试 / 语法检查结果） */
interface LintIssue {
  line: number // 0 表示全局问题
  msg: string
}
type TestOut =
  | { kind: 'run' }
  | { kind: 'ok'; title: string; note: string; text?: string; hint?: string }
  | { kind: 'issues'; issues: LintIssue[] }
const testOut = ref<TestOut | null>(null)

function openCreate() {
  editing.value = null
  form.value = { name: '', lang: 'Python', venv: pyEnvs.value[0]?.name ?? 'py3-data', code: '' }
  testOut.value = null
  formVisible.value = true
}
function openEdit(s: Script) {
  editing.value = s
  form.value = { name: s.name, lang: s.lang, venv: 'py3-data', code: s.code }
  testOut.value = null
  formVisible.value = true
}

function today(): string {
  return localTime().slice(0, 10)
}

async function saveForm() {
  const name = form.value.name.trim()
  if (!name || !form.value.code.trim()) {
    ElMessage.warning('请填写脚本名称与内容')
    return
  }
  if (editing.value) {
    Object.assign(editing.value, { name, lang: form.value.lang, code: form.value.code, updated: today(), venv: form.value.venv })
    await dataStore.save('scripts', editing.value)
    ElMessage.success('脚本已保存')
  } else {
    // ID 取现有最大序号 +1：删除脚本后再新建不会碰撞
    const nextSeq = scripts.value.reduce((m, s) => {
      const n = Number(String(s.id).replace(/^\D+/, ''))
      return Number.isFinite(n) && n > m ? n : m
    }, 0) + 1
    const row: Script = {
      id: 'SC' + String(nextSeq).padStart(3, '0'),
      name,
      lang: form.value.lang,
      status: 'draft',
      owner: userName.value,
      updated: today(),
      code: form.value.code,
    }
    Object.assign(row, { venv: form.value.venv }) // venv 为原型扩展字段（类型契约未定义），随行持久化
    scripts.value.push(row)
    await dataStore.save('scripts', row)
    ElMessage.success('脚本已保存（草稿），可发布后执行')
  }
  formVisible.value = false
}

/* ---- 工具条：▶ 运行测试（沙箱试跑，不产生正式日志） ---- */
function runTest() {
  if (!form.value.code.trim()) {
    ElMessage.warning('请先填写脚本内容')
    return
  }
  if (form.value.lang === 'Java') {
    ElMessage.warning('Java 编译执行排后（P0 范围外），仅支持查看')
    return
  }
  testOut.value = { kind: 'run' }
  later(() => {
    const log =
      '[TEST 23:40:01] [INFO] 参数注入完成：env=prod / dw_user=datara_etl / biz_date=2026-09-11\n' +
      '[TEST 23:40:02] [INFO] 开始执行 ' + form.value.lang + ' 脚本（沙箱）...\n' +
      '[TEST 23:40:06] [OK] 退出码 0，测试通过（结果不写入执行日志）'
    testOut.value = {
      kind: 'ok',
      title: '运行测试通过',
      note: '耗时 ' + (2 + Math.floor(Math.random() * 4)) + 's',
      text: log,
    }
    ElMessage.success('测试通过：退出码 0')
  }, 900)
}

/* ---- 工具条：✓ 语法检查（Python/Shell 关键提示，对齐原型检查项） ---- */
function lintCode() {
  const code = form.value.code
  const lang = form.value.lang
  if (!code.trim()) {
    ElMessage.warning('请先填写脚本内容')
    return
  }
  if (lang === 'Java') {
    ElMessage.warning('Java 语法检查排后（P0 范围外），当前仅支持查看')
    return
  }
  const issues: LintIssue[] = []
  const lines = code.split('\n')
  let depth = 0
  let openLine = 0
  for (let i = 0; i < lines.length; i++) {
    const ln = lines[i].replace(/#.*$/, '')
    const bo = (ln.match(/\(/g) ?? []).length
    const bc = (ln.match(/\)/g) ?? []).length
    if (depth === 0 && bo > bc) openLine = i + 1
    depth += bo - bc
    if (depth < 0) {
      issues.push({ line: i + 1, msg: '圆括号不匹配：多余的 ")"' })
      depth = 0
    }
    const s = ln.trim()
    if (!s) continue
    if (lang === 'Python') {
      if (/\b(if|elif|else|for|while|def|class|try|except|finally|with)\b/.test(s) && !s.includes(':'))
        issues.push({ line: i + 1, msg: 'Python 语句块缺少冒号 ":"' })
    } else if (lang === 'Shell') {
      if (/^if\s/.test(s) && !/;\s*then$/.test(s) && !/\bthen\b/.test(s))
        issues.push({ line: i + 1, msg: 'if 语句缺少 then（建议写成 if ...; then）' })
    }
  }
  if (depth > 0) issues.push({ line: openLine, msg: '第 ' + openLine + ' 行的 "(" 未闭合' })
  if (lang === 'Python') {
    if ((code.match(/\bdef\b/g) ?? []).length > 0 && !code.includes('return') && !code.includes('print'))
      issues.push({ line: 0, msg: '函数缺少输出/返回，建议补充 return 或日志打印' })
  } else if (lang === 'Shell') {
    const ifs = (code.match(/\bif\b/g) ?? []).length
    const fis = (code.match(/\bfi\b/g) ?? []).length
    const dos = (code.match(/\bdo\b/g) ?? []).length
    const dones = (code.match(/\bdone\b/g) ?? []).length
    if (ifs !== fis) issues.push({ line: 0, msg: 'if/fi 不配对：if ' + ifs + ' 个，fi ' + fis + ' 个' })
    if (dos !== dones) issues.push({ line: 0, msg: 'do/done 不配对：do ' + dos + ' 个，done ' + dones + ' 个' })
  }
  if (!issues.length) {
    testOut.value = {
      kind: 'ok',
      title: '语法检查通过',
      note: lang + ' · ' + lines.length + ' 行',
      hint:
        lang === 'Python'
          ? '检查项：括号配对 / 冒号 / 缩进；提示：${biz_date} 等参数在执行时注入，无需转义。'
          : '检查项：括号配对 / if-fi / do-done 配对；提示：引用变量请使用 "$var" 防空格拆词。',
    }
    ElMessage.success('语法检查通过')
  } else {
    testOut.value = { kind: 'issues', issues }
    ElMessage.warning('语法检查发现 ' + issues.length + ' 个疑似问题')
  }
}

/* ---- 查看（代码 + 执行历史） ---- */
const viewVisible = ref(false)
const viewScript = ref<Script | null>(null)
const viewLogs = computed(() => {
  const s = viewScript.value
  if (!s) return []
  return logs.value.filter((l) => l.script.startsWith(s.id + ' ')).slice(0, 5)
})
const viewTotal = computed(() => {
  const s = viewScript.value
  if (!s) return 0
  return logs.value.filter((l) => l.script.startsWith(s.id + ' ')).length
})
function logSummary(l: ExecLog): string {
  const lines = l.content.split('\n')
  const hit = lines.find((x) => x.includes('[ERROR]') || x.includes('[OK]')) ?? lines[0] ?? ''
  return hit.slice(0, 48)
}
function openView(s: Script) {
  viewScript.value = s
  viewVisible.value = true
}
function runFromView() {
  const s = viewScript.value
  if (!s) return
  viewVisible.value = false
  openRun(s)
}

/* ---- 发布 / 启停 / 删除 ---- */
async function publish(s: Script) {
  try {
    await ElMessageBox.confirm('发布「' + s.name + '」？发布后可在执行/被工作流脚本节点引用。', '发布脚本', { type: 'info' })
  } catch {
    return
  }
  s.status = 'published'
  await dataStore.save('scripts', s)
  ElMessage.success('脚本已发布')
  await reload()
}

async function toggleStatus(s: Script) {
  s.status = s.status === 'disabled' ? 'enabled' : 'disabled'
  await dataStore.save('scripts', s)
  ElMessage.success(s.status === 'disabled' ? '脚本已停用' : '脚本已启用')
  await reload()
}

async function removeScript(s: Script) {
  try {
    await ElMessageBox.confirm('确认删除脚本「' + s.name + '」？该操作不可恢复。', '删除确认', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
  } catch {
    return
  }
  await dataStore.remove('scripts', s.id)
  ElMessage.success('脚本已删除')
  await reload()
}

/* ---- 执行（本地/SSH，写 execLogs） ---- */
const runVisible = ref(false)
const runTarget = ref<Script | null>(null)
const runForm = ref({ mode: '本地执行', node: '', args: '' })
// 模拟原型 lastExecFail 交替：首次成功、失败后重跑成功
const lastFail = ref<Record<string, boolean>>({})

function openRun(s: Script) {
  if (s.lang === 'Java') {
    ElMessage.warning('Java 编译执行排后（P0 范围外），仅支持查看')
    return
  }
  runTarget.value = s
  runForm.value = { mode: '本地执行', node: remoteNodes.value[0]?.name ?? '', args: '' }
  runVisible.value = true
}

function nextLogId(): string {
  const d = localTime().slice(0, 10).replace(/-/g, '')
  let max = 0
  for (const l of logs.value) {
    if (!l.id.startsWith('LOG' + d)) continue
    const m = /^LOG\d{8}-(\d+)$/.exec(l.id)
    if (m) max = Math.max(max, Number(m[1]))
  }
  return 'LOG' + d + '-' + String(max + 1).padStart(3, '0')
}

async function confirmRun() {
  const s = runTarget.value
  if (!s) return
  const mode = runForm.value.mode
  const node = remoteNodes.value.find((n) => n.name === runForm.value.node)
  if (mode === '远程执行(SSH)' && node && node.status !== 'online') {
    ElMessageBox.alert(
      '远程节点「' + node.name + '」离线（最近心跳 ' + node.lastPing + '），请选择其他节点或检查网络/VPN。',
      '节点不可达', { type: 'error' },
    ).catch(() => {})
    return
  }
  runVisible.value = false
  ElMessage.info('正在' + mode + '「' + s.name + '」（' + (mode === '远程执行(SSH)' ? runForm.value.node : '本地') + '）...')
  later(async () => {
    const ok = !lastFail.value[s.id]
    const log: ExecLog = {
      id: nextLogId(),
      script: s.id + ' ' + s.name,
      mode: mode + (mode === '远程执行(SSH)' && node ? ': ' + node.ip : ''),
      status: ok ? 'success' : 'failed',
      start: localTime(),
      dur: ok ? '4s' : '12s',
      content: ok
        ? '[INFO] 参数注入完成（env/dw_user/biz_date）\n[INFO] 开始执行 ' + s.lang + ' 脚本...\n[OK] 执行完成，退出码 0'
        : '[INFO] 开始执行...\n[ERROR] FileNotFoundError: 上游分区不存在\n[WARN] 退出码 1，已触发告警（邮件+短信）',
    }
    logs.value.unshift(log)
    await dataStore.save('execLogs', log)
    lastFail.value[s.id] = !ok
    runResult.value = log
    resultVisible.value = true
    if (ok) ElMessage.success('执行成功')
    else ElMessage.error('执行失败')
  }, 900)
}

const resultVisible = ref(false)
const runResult = ref<ExecLog | null>(null)

/* ---- 日志详情 / 重跑 ---- */
const logVisible = ref(false)
const logTarget = ref<ExecLog | null>(null)
function openLog(l: ExecLog) {
  logTarget.value = l
  logVisible.value = true
}

async function rerun(l: ExecLog) {
  try {
    await ElMessageBox.confirm('重新执行「' + l.script + '」？生成新的执行日志。', '重跑脚本', { type: 'info' })
  } catch {
    return
  }
  const sid = l.script.split(' ')[0]
  lastFail.value[sid] = false
  ElMessage.success('重跑已触发')
}
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ListFilterPanel
      v-model:keyword="keyword"
      v-model:filters="filters"
      :facets="facets"
      :result-count="filteredScripts.length"
      :total-count="scripts.length"
      placeholder="搜索脚本"
    />
    <div style="flex:1;min-width:0">
    <!-- 页头 + 顶部操作工具栏 -->
    <div class="card page-head">
      <div>
        <div class="ph-title">脚本任务</div>
        <div class="ph-desc">在线脚本开发与托管：Python / Shell（Java 编译执行排后），支持本地执行与远程 SSH 执行，参数引用 ${global_param}</div>
      </div>
      <span class="spacer" />
      <button class="tb-new" @click="openCreate">＋ 新建脚本</button>
      <button class="op-btn" @click="router.push('/script/env')">环境与依赖</button>
    </div>

    <!-- 脚本列表 -->
    <div class="card" style="padding:16px;margin-bottom:14px">
      <div class="tbl-toolbar">
        <span class="card-title">脚本列表</span>
        <span class="pill info">{{ filteredScripts.length }} / {{ scripts.length }}</span>
        <span class="spacer" />
      </div>
      <table class="tbl">
        <thead>
          <tr>
            <th>脚本</th><th>语言</th><th>状态</th><th>负责人</th><th>更新日期</th><th style="width:260px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in filteredScripts" :key="s.id">
            <td>
              <a @click="openView(s)"><b>{{ s.name }}</b></a>
              <div style="font-size:11px;color:var(--text-3)">{{ s.id }} · {{ s.lang }}</div>
            </td>
            <td><span class="pill" :class="langPill(s.lang)">{{ s.lang }}</span></td>
            <td><span class="st" :class="stCls(s.status)"><span class="dot" />{{ stLabel(s.status) }}</span></td>
            <td>{{ s.owner }}</td>
            <td style="color:var(--text-2)">{{ s.updated }}</td>
            <td>
              <button class="op-btn primary" @click="openView(s)">查看</button>
              <button class="op-btn" @click="openRun(s)">执行</button>
              <button class="op-btn" @click="openEdit(s)">编辑</button>
              <button v-if="s.status === 'draft'" class="op-btn" @click="publish(s)">发布</button>
              <button class="op-btn" @click="toggleStatus(s)">{{ s.status === 'disabled' ? '启用' : '停用' }}</button>
              <button class="op-btn danger" @click="removeScript(s)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="filteredScripts.length === 0" class="empty">未找到匹配的脚本，请调整搜索或筛选条件</div>
    </div>

    <!-- 执行日志 -->
    <div class="card" style="padding:16px">
      <div class="tbl-toolbar">
        <span class="card-title">执行日志</span>
        <span class="pill info">{{ filteredLogs.length }} / {{ logs.length }}</span>
        <span class="spacer" />
        <input v-model="logKeyword" class="kw" placeholder="搜索日志" />
        <select v-model="logStatus" class="sel">
          <option value="">结果：全部</option>
          <option value="success">成功</option>
          <option value="failed">失败</option>
        </select>
      </div>
      <table class="tbl">
        <thead>
          <tr>
            <th>日志</th><th>方式</th><th>开始</th><th>耗时</th><th>结果</th><th style="width:120px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="l in filteredLogs" :key="l.id">
            <td>
              <a @click="openLog(l)"><b class="mono" style="font-size:12px">{{ l.id }}</b></a>
              <div style="font-size:11px;color:var(--text-3)">{{ l.script }}</div>
            </td>
            <td style="color:var(--text-2)">{{ l.mode }}</td>
            <td style="color:var(--text-2)">{{ l.start }}</td>
            <td>{{ l.dur }}</td>
            <td><span class="st" :class="stCls(l.status)"><span class="dot" />{{ stLabel(l.status) }}</span></td>
            <td>
              <button class="op-btn primary" @click="openLog(l)">日志</button>
              <button v-if="l.status === 'failed'" class="op-btn" @click="rerun(l)">重跑</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="filteredLogs.length === 0" class="empty">暂无执行日志，执行脚本后此处记录</div>
    </div>

    <!-- 新建 / 编辑脚本抽屉 -->
    <el-drawer v-model="formVisible" :title="editing ? '编辑脚本 - ' + editing.name : '新建脚本'" size="640px">
      <div class="form-grid">
        <div class="fg-2">
          <label class="f-item">脚本名称 *
            <input v-model="form.name" class="kw" style="width:100%" placeholder="如：脏数据隔离清理" />
          </label>
          <label class="f-item">语言
            <select v-model="form.lang" class="kw" style="width:100%">
              <option value="Python">Python（本地/远程SSH）</option>
              <option value="Shell">Shell（本地/远程SSH）</option>
              <option value="Java">Java（查看为主，编译执行排后）</option>
            </select>
          </label>
        </div>
        <label class="f-item">Python 环境（Python脚本）
          <select v-model="form.venv" class="kw" style="width:100%">
            <option v-for="v in pyEnvs" :key="v.id" :value="v.name">{{ v.name }}（Py{{ v.python }} · {{ v.pkgs.length }}包）</option>
            <option value="-">不适用</option>
          </select>
        </label>
        <div class="f-item">
          <span>脚本内容 *</span>
          <div class="editor-bar">
            <button class="op-btn" @click="runTest">▶ 运行测试</button>
            <button class="op-btn" @click="lintCode">✓ 语法检查</button>
            <span class="bar-hint">{{ form.lang }} 关键语法提示 · 参数注入 ${env} / ${dw_user} / ${biz_date}</span>
          </div>
          <div class="code-wrap">
            <pre ref="gutterEl" class="mono gutter">{{ lineNums }}</pre>
            <textarea v-model="form.code" class="code-area mono" wrap="off" spellcheck="false" @input="syncGutter" @scroll="syncGutter" />
          </div>
          <template v-if="testOut">
            <div v-if="testOut.kind === 'run'" class="checker run">
              <span>⏳</span><b>运行测试中...</b><span class="ck-note">{{ form.lang }} · 本地容器沙箱（只读权限）</span>
            </div>
            <template v-else-if="testOut.kind === 'ok'">
              <div class="checker ok">
                <span>✓</span><b>{{ testOut.title }}</b><span class="ck-note">{{ testOut.note }}</span>
              </div>
              <pre v-if="testOut.text" class="mono ck-log">{{ testOut.text }}</pre>
              <div v-if="testOut.hint" class="ck-hint">ℹ {{ testOut.hint }}</div>
            </template>
            <template v-else>
              <div class="checker err"><span>✗</span><b>发现 {{ testOut.issues.length }} 个疑似问题</b></div>
              <div v-for="(x, i) in testOut.issues" :key="i" class="checker err">
                <span>·</span><b>{{ x.line ? '第 ' + x.line + ' 行' : '全局' }}</b><span>{{ x.msg }}</span>
              </div>
            </template>
          </template>
        </div>
        <div class="lock-tip">参数引用：${env} / ${dw_user} 等全局参数与 ${biz_date} 内置时间参数在执行时注入；Java 脚本当前仅支持在线查看。</div>
      </div>
      <div style="margin-top:16px;display:flex;gap:8px">
        <button class="tb-new" @click="saveForm">保存</button>
        <button class="op-btn" @click="formVisible = false">取消</button>
      </div>
    </el-drawer>

    <!-- 脚本查看（代码 + 执行历史） -->
    <el-dialog v-model="viewVisible" :title="viewScript ? '脚本查看 - ' + viewScript.name + '（' + viewScript.lang + '）' : ''" width="720px">
      <template v-if="viewScript">
        <pre class="mono ck-log" style="max-height:300px">{{ viewScript.code }}</pre>
        <div class="sec-title">执行历史（最近 {{ viewLogs.length }} 条 / 共 {{ viewTotal }} 条）</div>
        <table v-if="viewLogs.length" class="tbl">
          <thead>
            <tr><th>时间</th><th>方式</th><th>结果</th><th>耗时</th><th>日志摘要</th></tr>
          </thead>
          <tbody>
            <tr v-for="l in viewLogs" :key="l.id">
              <td style="color:var(--text-2)">{{ l.start }}</td>
              <td style="color:var(--text-3)">{{ l.mode }}</td>
              <td><span class="st" :class="stCls(l.status)"><span class="dot" />{{ stLabel(l.status) }}</span></td>
              <td>{{ l.dur }}</td>
              <td>
                <span class="mono" style="font-size:11px">{{ logSummary(l) }}…</span>
                <a @click="openLog(l)">详情</a>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else style="font-size:12px;color:var(--text-3);padding:6px 0">暂无执行记录，点击右上角「执行」运行一次</div>
      </template>
      <template #footer>
        <button class="op-btn" @click="viewVisible = false">关闭</button>
        <button v-if="viewScript" class="tb-new" style="margin-left:8px" @click="runFromView">执行</button>
      </template>
    </el-dialog>

    <!-- 执行抽屉 -->
    <el-drawer v-model="runVisible" :title="runTarget ? '执行脚本 - ' + runTarget.name : '执行脚本'" size="440px">
      <div class="form-grid">
        <label class="f-item">执行方式
          <select v-model="runForm.mode" class="kw" style="width:100%">
            <option value="本地执行">本地执行（平台容器）</option>
            <option value="远程执行(SSH)">远程执行（SSH 节点）</option>
          </select>
        </label>
        <label class="f-item">远程节点
          <select v-model="runForm.node" class="kw" style="width:100%">
            <option v-for="n in remoteNodes" :key="n.id" :value="n.name">{{ n.name }}（{{ n.ip }} · {{ n.status === 'online' ? '在线' : '离线' }}）</option>
          </select>
        </label>
        <label class="f-item">参数覆盖（可选）
          <input v-model="runForm.args" class="kw" style="width:100%" placeholder="如：biz_date=2026-09-11" />
        </label>
      </div>
      <div style="margin-top:16px;display:flex;gap:8px">
        <button class="tb-new" @click="confirmRun">▶ 立即执行</button>
        <button class="op-btn" @click="runVisible = false">取消</button>
      </div>
    </el-drawer>

    <!-- 执行结果 -->
    <el-dialog v-model="resultVisible" title="执行结果" width="640px">
      <div v-if="runResult">
        <div class="checker" :class="runResult.status === 'success' ? 'ok' : 'err'">
          <span>{{ runResult.status === 'success' ? '✓' : '✗' }}</span>
          <b>{{ runResult.status === 'success' ? '执行成功' : '执行失败' }}</b>
          <span class="ck-note">耗时 {{ runResult.dur }}</span>
        </div>
        <pre class="mono ck-log" style="max-height:260px">{{ runResult.content }}</pre>
      </div>
      <template #footer>
        <button class="op-btn" @click="resultVisible = false">关闭</button>
      </template>
    </el-dialog>

    <!-- 日志详情 -->
    <el-dialog v-model="logVisible" :title="logTarget ? '执行日志 - ' + logTarget.id : ''" width="640px">
      <div v-if="logTarget" class="desc-grid">
        <span class="d-k">脚本</span><span>{{ logTarget.script }}</span>
        <span class="d-k">方式</span><span>{{ logTarget.mode }}</span>
        <span class="d-k">开始</span><span>{{ logTarget.start }}</span>
        <span class="d-k">耗时</span><span>{{ logTarget.dur }}</span>
        <span class="d-k">结果</span>
        <span><span class="st" :class="stCls(logTarget.status)"><span class="dot" />{{ stLabel(logTarget.status) }}</span></span>
      </div>
      <pre v-if="logTarget" class="mono ck-log" style="max-height:280px">{{ logTarget.content }}</pre>
      <template #footer>
        <button class="op-btn" @click="logVisible = false">关闭</button>
      </template>
    </el-dialog>
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
.sel{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 8px;font-size:12.5px;background:#fff;outline:none;color:var(--text-2)}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease)}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
.op-btn.primary{color:var(--primary);border-color:rgba(22,104,220,.4);font-weight:600}
.op-btn.danger{color:var(--danger);border-color:rgba(229,72,77,.35)}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
.form-grid{display:flex;flex-direction:column;gap:12px}
.fg-2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.f-item{display:flex;flex-direction:column;gap:5px;font-size:12.5px;color:var(--text-2)}
.editor-bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:6px}
.bar-hint{font-size:11px;color:var(--text-3);margin-left:auto}
.code-wrap{display:flex;border:1px solid var(--border-strong);border-radius:var(--radius);overflow:hidden}
.gutter{margin:0;flex-shrink:0;min-width:38px;padding:10px 6px 10px 10px;text-align:right;background:#0a1120;color:#44546e;font-size:12px;line-height:1.8;border-right:1px solid #1c2a44;user-select:none;overflow:hidden}
.code-area{flex:1;min-width:0;border:none;outline:none;resize:vertical;background:#0d1424;color:#9fb2d0;font-size:12px;line-height:1.8;padding:10px 12px;min-height:240px;white-space:pre;overflow:auto}
.checker{display:flex;gap:8px;align-items:center;padding:6px 10px;border-radius:var(--radius-sm);font-size:12px;margin-top:8px}
.checker.ok{background:var(--success-bg);color:var(--success)}
.checker.err{background:var(--danger-bg);color:var(--danger)}
.checker.run{background:var(--info-bg);color:var(--info)}
.ck-note{margin-left:auto;font-size:11px}
.ck-log{background:#0d1424;color:#9fb2d0;border-radius:var(--radius);padding:10px 12px;font-size:11.5px;line-height:1.7;max-height:180px;overflow:auto;margin:8px 0 0;white-space:pre-wrap}
.ck-hint{margin-top:8px;background:var(--info-bg);color:var(--info);border-radius:var(--radius-sm);padding:6px 10px;font-size:11.5px}
.lock-tip{background:var(--warn-bg);color:var(--warn);border-radius:var(--radius-sm);padding:8px 10px;font-size:11.5px}
.sec-title{font-weight:700;font-size:12.5px;margin:14px 0 8px;color:var(--text)}
.desc-grid{display:grid;grid-template-columns:64px 1fr;gap:6px 10px;font-size:12.5px;margin-bottom:12px}
.desc-grid .d-k{color:var(--text-3)}
</style>
