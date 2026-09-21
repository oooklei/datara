<script setup lang="ts">
/**
 * M14 远程执行节点 SSH（/script/remote）
 * 对齐 prototype/assets/pages/m14-script.js L347-393：
 * 节点表格（搜索/IP）+ 从运行时节点导入 + 测试连接（在线成功/离线失败提示）+ 删除（二次确认）。操作按钮置顶（页头工具栏）。
 * SSH 注册表收编（批次四）：SSH 主机信息统一由「运行时节点」页（/dep/runtime）注册与维护，
 * 本页为唯一权威源的消费方——节点仅可从运行时节点导入，编辑仅支持改名；远程文件管理（仅 SSH 模式）。
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { dataStore } from '../../services/mock/dataStore'
import { localTime } from '../../services/mock/timeUtil'
import type { RemoteNode, RuntimeNode } from '../../services/types'
import ListFilterPanel from '../../components/ListFilterPanel.vue'

const router = useRouter()
const nodes = ref<RemoteNode[]>([])
/** 运行时节点注册表（/dep/runtime 维护，SSH 主机信息唯一权威源） */
const rtNodes = ref<RuntimeNode[]>([])
const keyword = ref('')
const filters = ref<Record<string, string>>({ status: '' })
const facets = [
  { key: 'status', label: '状态', options: [{ v: 'online', t: '在线' }, { v: 'offline', t: '离线' }] },
]

async function reload() {
  // 必须展开为新数组：dataStore.save 原地修改数组，直接赋值不会触发 ref 更新
  nodes.value = [...((await dataStore.list<RemoteNode>('remoteNodes')) ?? [])]
  rtNodes.value = [...((await dataStore.list<RuntimeNode>('runtimeNodes')) ?? [])]
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

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return nodes.value.filter((r) => {
    if (filters.value.status && r.status !== filters.value.status) return false
    if (!kw) return true
    return [r.id, r.name, r.ip].some((s) => s.toLowerCase().includes(kw))
  })
})

function stCls(status: string): string {
  return status === 'online' ? 'st-green' : 'st-red'
}
function stLabel(status: string): string {
  return status === 'online' ? '成功' : '失败'
}

/* ---- ID 取现有最大序号 +1：删除节点后再新建不会碰撞 ---- */
function nextId(): string {
  const seq = nodes.value.reduce((m, n) => {
    const v = Number(String(n.id).replace(/^\D+/, ''))
    return Number.isFinite(v) && v > m ? v : m
  }, 0) + 1
  return 'RN' + String(seq).padStart(2, '0')
}

/* ---- 添加（从运行时节点导入）/ 编辑节点 ---- */
const formVisible = ref(false)
const editing = ref<RemoteNode | null>(null)
const form = ref({ name: '', ip: '', port: 22, auth: '密钥' })

/** SSH 注册表收编：可导入 = 运行时节点中的远程节点，排除已导入（按 host=ip 判重） */
const rtRemote = computed(() =>
  rtNodes.value.filter((r) => r.kind === '远程' && !nodes.value.some((n) => n.ip === r.host)),
)
const rtVisible = ref(false)
const rtPick = ref('')

function openImport() {
  if (rtRemote.value.length === 0) {
    ElMessageBox.confirm('所有已注册的远程节点均已导入。是否前往「运行时节点」页注册新节点？', '提示', {
      confirmButtonText: '前往注册', cancelButtonText: '取消', type: 'info',
    }).then(() => router.push('/dep/runtime')).catch(() => {})
    return
  }
  rtPick.value = ''
  rtVisible.value = true
}

async function confirmImport() {
  const r = rtNodes.value.find((x) => x.id === rtPick.value)
  if (!r) {
    ElMessage.warning('请选择要导入的运行时节点')
    return
  }
  const row: RemoteNode = {
    id: nextId(),
    name: r.name,
    ip: r.host,
    os: r.os,
    mode: 'SSH',
    auth: r.auth,
    status: r.status,
    lastPing: localTime(),
    scripts: 0,
  }
  nodes.value.push(row)
  await dataStore.save('remoteNodes', row)
  rtVisible.value = false
  ElMessage.success('已导入节点「' + r.name + '」')
}

function openEdit(n: RemoteNode) {
  editing.value = n
  form.value = { name: n.name, ip: n.ip, port: 22, auth: n.auth }
  formVisible.value = true
}

async function saveForm() {
  // 编辑：SSH 主机信息唯一权威源在「运行时节点」页，本页仅可修改节点名称
  if (!editing.value) return
  const name = form.value.name.trim()
  if (!name) {
    ElMessage.warning('请填写节点名称')
    return
  }
  Object.assign(editing.value, { name })
  await dataStore.save('remoteNodes', editing.value)
  ElMessage.success('节点已保存（SSH 主机信息请在「运行时节点」页维护）')
  formVisible.value = false
}

/* ---- 测试连接 ---- */
function ping(n: RemoteNode) {
  ElMessage.info('正在 SSH 连接 ' + n.ip + ' ...')
  later(() => {
    if (n.status === 'online') {
      ElMessage.success('连接成功：' + n.os + ' · 认证通过 · 耗时 ' + (20 + Math.floor(Math.random() * 80)) + ' ms')
    } else {
      ElMessageBox.alert(
        'SSH 连接 ' + n.ip + ' 超时。节点最近心跳 ' + n.lastPing + '，请检查网络/VPN 通道。',
        '连接失败', { type: 'error' },
      ).catch(() => {})
    }
  }, 700)
}

/* ---- 删除 ---- */
async function removeNode(n: RemoteNode) {
  try {
    await ElMessageBox.confirm('确认删除节点「' + n.name + '」？该操作不可恢复。', '删除确认', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
  } catch {
    return
  }
  await dataStore.remove('remoteNodes', n.id)
  ElMessage.success('节点已删除')
  await reload()
}

/* ============================================================
 * 远程文件管理（设计方案第15章：SSH 模式目录浏览/上传/下载/版本）
 * 注：目录结构与版本号为写死的 mock 数据；仅支持 SSH 模式。
 * ============================================================ */

/** 远程文件树节点：kind=dir 目录（children）/ kind=file 文件（ext 类型徽标 + 版本） */
interface RNode {
  name: string
  path: string
  kind: 'dir' | 'file'
  ext?: string
  size?: string
  mtime?: string
  versions?: { v: string; time: string; size: string }[]
  children?: RNode[]
}

/** 支持的远程脚本文件类型（上传白名单与执行白名单共用） */
const UPLOAD_EXTS = ['sh', 'py', 'java', 'jar', 'sql']

/** mock 远程目录结构（时间/大小均为写死字符串） */
function makeTree(): RNode[] {
  return [
    {
      name: 'scripts', path: '/home/datara/scripts', kind: 'dir',
      children: [
        {
          name: 'clean_dirty.sh', path: '/home/datara/scripts/clean_dirty.sh', kind: 'file', ext: 'sh',
          size: '2.1 KB', mtime: '2026-09-11 15:20',
          versions: [
            { v: 'v1', time: '2026-09-05 10:12', size: '1.8 KB' },
            { v: 'v2', time: '2026-09-11 15:20', size: '2.1 KB' },
          ],
        },
        {
          name: 'extract_dm_check.py', path: '/home/datara/scripts/extract_dm_check.py', kind: 'file', ext: 'py',
          size: '3.9 KB', mtime: '2026-09-10 18:05',
          versions: [
            { v: 'v1', time: '2026-09-06 09:40', size: '3.4 KB' },
            { v: 'v2', time: '2026-09-10 18:05', size: '3.9 KB' },
          ],
        },
        {
          name: 'backup_config.sh', path: '/home/datara/scripts/backup_config.sh', kind: 'file', ext: 'sh',
          size: '1.5 KB', mtime: '2026-09-08 08:45',
          versions: [
            { v: 'v1', time: '2026-08-28 11:00', size: '1.2 KB' },
            { v: 'v2', time: '2026-09-08 08:45', size: '1.5 KB' },
          ],
        },
        {
          name: 'partition_precreate.py', path: '/home/datara/scripts/partition_precreate.py', kind: 'file', ext: 'py',
          size: '3.1 KB', mtime: '2026-09-12 10:15',
          versions: [
            { v: 'v1', time: '2026-09-01 14:30', size: '2.7 KB' },
            { v: 'v2', time: '2026-09-12 10:15', size: '3.1 KB' },
          ],
        },
        {
          name: 'sync_check.sql', path: '/home/datara/scripts/sync_check.sql', kind: 'file', ext: 'sql',
          size: '1.1 KB', mtime: '2026-09-09 13:10',
          versions: [
            { v: 'v1', time: '2026-09-02 16:22', size: '0.9 KB' },
            { v: 'v2', time: '2026-09-09 13:10', size: '1.1 KB' },
          ],
        },
      ],
    },
    {
      name: 'lib', path: '/home/datara/lib', kind: 'dir',
      children: [
        {
          name: 'udf_risk_score.jar', path: '/home/datara/lib/udf_risk_score.jar', kind: 'file', ext: 'jar',
          size: '132 KB', mtime: '2026-09-07 17:40',
          versions: [
            { v: 'v1', time: '2026-08-20 09:00', size: '128 KB' },
            { v: 'v2', time: '2026-09-07 17:40', size: '132 KB' },
          ],
        },
        {
          name: 'udf_text-1.0.jar', path: '/home/datara/lib/udf_text-1.0.jar', kind: 'file', ext: 'jar',
          size: '98 KB', mtime: '2026-09-07 17:41',
          versions: [
            { v: 'v1', time: '2026-08-20 09:00', size: '96 KB' },
            { v: 'v2', time: '2026-09-07 17:41', size: '98 KB' },
          ],
        },
      ],
    },
    {
      name: 'ods', path: '/data/ods', kind: 'dir',
      children: [
        {
          name: 'dt=2026-09-11', path: '/data/ods/dt=2026-09-11', kind: 'dir',
          children: [
            {
              name: 'part-0000.parquet', path: '/data/ods/dt=2026-09-11/part-0000.parquet', kind: 'file', ext: 'parquet',
              size: '45.2 MB', mtime: '2026-09-11 23:50',
              versions: [
                { v: 'v1', time: '2026-09-11 23:50', size: '45.2 MB' },
                { v: 'v2', time: '2026-09-11 23:58', size: '45.2 MB' },
              ],
            },
          ],
        },
        {
          name: 'dt=2026-09-12', path: '/data/ods/dt=2026-09-12', kind: 'dir',
          children: [
            {
              name: 'part-0000.parquet', path: '/data/ods/dt=2026-09-12/part-0000.parquet', kind: 'file', ext: 'parquet',
              size: '44.8 MB', mtime: '2026-09-12 23:55',
              versions: [
                { v: 'v1', time: '2026-09-12 23:55', size: '44.8 MB' },
                { v: 'v2', time: '2026-09-12 23:59', size: '44.8 MB' },
              ],
            },
            {
              name: 'part-0001.parquet', path: '/data/ods/dt=2026-09-12/part-0001.parquet', kind: 'file', ext: 'parquet',
              size: '43.6 MB', mtime: '2026-09-12 23:56',
              versions: [
                { v: 'v1', time: '2026-09-12 23:56', size: '43.6 MB' },
                { v: 'v2', time: '2026-09-12 23:59', size: '43.6 MB' },
              ],
            },
          ],
        },
      ],
    },
  ]
}

/** 文件树（ref 深层响应式：上传 push 后视图自动更新） */
const tree = ref<RNode[]>(makeTree())
/** 各目录展开状态（path -> 是否展开） */
const expanded = ref<Record<string, boolean>>({ '/home/datara/scripts': true })
/** 当前目录（面包屑 + 上传目标），默认 scripts 目录 */
const currentDir = ref('/home/datara/scripts')
/** 文件管理抽屉开关与目标节点 */
const fmVisible = ref(false)
const fmNode = ref<RemoteNode | null>(null)

function openFiles(n: RemoteNode) {
  fmNode.value = n
  fmVisible.value = true
}

/** 按完整路径查找目录节点（找不到返回 null） */
function findDir(path: string): RNode | null {
  let found: RNode | null = null
  const walk = (list: RNode[]) => {
    for (const nd of list) {
      if (found) return
      if (nd.path === path) { found = nd; return }
      if (nd.children) walk(nd.children)
    }
  }
  walk(tree.value)
  return found
}

/** 文件扩展名（无后缀返回空串） */
function extOf(name: string): string {
  const i = name.lastIndexOf('.')
  return i < 0 ? '' : name.slice(i + 1).toLowerCase()
}

/** 展开或折叠目录，并把当前目录切到该目录 */
function toggleDir(nd: RNode) {
  if (nd.kind !== 'dir') return
  expanded.value[nd.path] = !expanded.value[nd.path]
  currentDir.value = nd.path
}

/** 扁平化可见行：依据 expanded 状态展开目录，目录/文件统一成行渲染（避免递归组件） */
const fmRows = computed<{ node: RNode; depth: number }[]>(() => {
  const rows: { node: RNode; depth: number }[] = []
  const walk = (list: RNode[], depth: number) => {
    for (const nd of list) {
      rows.push({ node: nd, depth })
      if (nd.kind === 'dir' && expanded.value[nd.path]) walk(nd.children ?? [], depth + 1)
    }
  }
  walk(tree.value, 0)
  return rows
})

/** 面包屑分段：/ + 逐级路径；exists 标记树中是否存在该目录节点（可点击） */
const crumbs = computed(() => {
  const segs = currentDir.value.split('/').filter(Boolean)
  const list: { label: string; path: string; exists: boolean; last: boolean }[] = [
    { label: '/', path: '', exists: false, last: false },
  ]
  let p = ''
  for (let i = 0; i < segs.length; i++) {
    p += '/' + segs[i]
    list.push({ label: segs[i], path: p, exists: !!findDir(p), last: i === segs.length - 1 })
  }
  return list
})

/** 面包屑点击：切到该级目录并展开 */
function crumbClick(c: { path: string; exists: boolean }) {
  if (!c.exists) return
  currentDir.value = c.path
  expanded.value[c.path] = true
}

/** 仅 .sh/.py 可远程执行 */
function canRun(f: RNode): boolean {
  return f.ext === 'sh' || f.ext === 'py'
}

/** mock 文件内容（按扩展名给不同注释风格） */
function mockContent(f: RNode): string {
  switch (f.ext) {
    case 'sh': return '#!/bin/bash\n# mock file content of ' + f.name
    case 'py': return '#!/usr/bin/env python3\n# mock file content of ' + f.name
    case 'sql': return '-- mock file content of ' + f.name
    case 'java': return '// mock file content of ' + f.name
    default: return 'mock binary content of ' + f.name
  }
}

/** 下载：Blob + 临时 a 标签触发，1s 后 revoke 释放 Blob URL（避免内存泄漏） */
function downloadFile(f: RNode) {
  const mime = f.ext === 'jar' || f.ext === 'parquet' ? 'application/octet-stream' : 'text/plain;charset=utf-8'
  const blob = new Blob([mockContent(f)], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = f.name
  a.click()
  later(() => URL.revokeObjectURL(url), 1000)
  ElMessage.success('已下载 ' + f.name + '（mock 内容）')
}

/** 远程执行（模拟）：仅 .sh/.py */
function runFile(f: RNode) {
  if (!canRun(f)) return
  ElMessage.success('已提交远程执行：' + f.path + '（' + (fmNode.value?.name ?? '') + '）')
}

/** 字节数格式化为可读大小 */
function fmtSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

/* ---- 上传：选择文件后追加进当前目录的文件列表 ---- */
const fileInput = ref<HTMLInputElement | null>(null)
function triggerUpload() {
  fileInput.value?.click()
}
function onUpload(e: Event) {
  const input = e.target as HTMLInputElement
  const f = input.files?.[0]
  if (!f) return
  const ext = extOf(f.name)
  if (!UPLOAD_EXTS.includes(ext)) {
    ElMessage.warning('仅支持 .sh / .py / .java / .jar / .sql 类型文件')
  } else {
    const dir = findDir(currentDir.value) ?? tree.value[0]
    dir.children!.push({
      name: f.name,
      path: dir.path + '/' + f.name,
      kind: 'file',
      ext,
      size: fmtSize(f.size),
      mtime: localTime(),
      versions: [{ v: 'v1', time: localTime(), size: fmtSize(f.size) }],
    })
    expanded.value[dir.path] = true
    ElMessage.success('已上传至 ' + dir.path + '/')
  }
  input.value = '' // 清空以允许重复选择同一文件
}
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ListFilterPanel
      v-model:keyword="keyword"
      v-model:filters="filters"
      :facets="facets"
      :result-count="filtered.length"
      :total-count="nodes.length"
      placeholder="搜索节点/IP"
    />
    <div style="flex:1;min-width:0">
    <!-- 页头 + 顶部操作工具栏 -->
    <div class="card page-head">
      <div>
        <div class="ph-title">远程执行节点（SSH）</div>
        <div class="ph-desc">脚本可在远程主机执行；SSH 主机信息统一由「运行时节点」页注册与维护（唯一权威源），本页从其导入节点并执行脚本/管理文件</div>
      </div>
      <span class="spacer" />
      <button class="op-btn" @click="router.push('/dep/runtime')">运行时节点页</button>
      <button class="tb-new" @click="openImport">＋ 从运行时节点导入</button>
    </div>

    <!-- 节点列表 -->
    <div class="card" style="padding:16px">
      <div class="tbl-toolbar">
        <span class="card-title">节点列表</span>
        <span class="pill info">{{ filtered.length }} / {{ nodes.length }}</span>
        <span class="spacer" />
      </div>
      <table class="tbl">
        <thead>
          <tr>
            <th>节点</th><th>IP</th><th>认证</th><th>最近心跳</th><th>脚本数</th><th>状态</th><th style="width:230px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="n in filtered" :key="n.id">
            <td>
              <b>{{ n.name }}</b>
              <div style="font-size:11px;color:var(--text-3)">{{ n.id }} · {{ n.os }}</div>
            </td>
            <td><span class="mono" style="font-size:11.5px">{{ n.ip }}</span></td>
            <td style="color:var(--text-2)">{{ n.auth }}</td>
            <td style="color:var(--text-2)">{{ n.lastPing }}</td>
            <td>{{ n.scripts }}</td>
            <td><span class="st" :class="stCls(n.status)"><span class="dot" />{{ stLabel(n.status) }}</span></td>
            <td>
              <button class="op-btn" @click="openFiles(n)">文件</button>
              <button class="op-btn primary" @click="ping(n)">测试连接</button>
              <button class="op-btn" @click="openEdit(n)">编辑</button>
              <button class="op-btn danger" @click="removeNode(n)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="filtered.length === 0" class="empty">未找到匹配的节点</div>
    </div>

    <!-- 编辑节点抽屉（SSH 主机信息只读：唯一权威源在运行时节点页） -->
    <el-drawer v-model="formVisible" :title="'编辑节点 - ' + (editing?.name ?? '')" size="440px">
      <div class="form-tip">SSH 主机信息（IP/端口/认证/目录）由「运行时节点」页统一维护（唯一权威源），本页仅支持修改节点名称。</div>
      <div class="form-grid">
        <label class="f-item">节点名称 *
          <input v-model="form.name" class="kw" style="width:100%" placeholder="如：脚本备份节点" />
        </label>
        <div class="f-item">IP 地址
          <span class="ro-val mono">{{ form.ip }}</span>
        </div>
        <div class="f-item">SSH 端口
          <span class="ro-val">22（在运行时节点页维护）</span>
        </div>
        <div class="f-item">认证方式
          <span class="ro-val">{{ form.auth }}</span>
        </div>
      </div>
      <div style="margin-top:16px;display:flex;gap:8px">
        <button class="tb-new" @click="saveForm">保存</button>
        <button class="op-btn" @click="formVisible = false">取消</button>
      </div>
    </el-drawer>

    <!-- 从运行时节点导入弹窗（SSH 注册表收编：节点来源唯一化） -->
    <el-dialog v-model="rtVisible" title="从运行时节点导入" width="540px">
      <div class="form-tip">SSH 主机信息统一在「运行时节点」页（部署运维 → 运行时节点）注册与维护；导入后本页仅做脚本远程执行视角展示，主机信息变更请前往该页。</div>
      <label class="f-item">
        选择运行时节点（远程）
        <select v-model="rtPick" class="kw" style="width:100%">
          <option value="" disabled>请选择要导入的远程节点</option>
          <option v-for="r in rtRemote" :key="r.id" :value="r.id">
            {{ r.name }}（{{ r.user }}@{{ r.host }}:{{ r.port }} · {{ r.status === 'online' ? '在线' : '离线' }}）
          </option>
        </select>
      </label>
      <div style="margin-top:16px;display:flex;gap:8px;justify-content:flex-end">
        <button class="op-btn" @click="router.push('/dep/runtime')">前往运行时节点页</button>
        <button class="op-btn" @click="rtVisible = false">取消</button>
        <button class="tb-new" @click="confirmImport">导入</button>
      </div>
    </el-dialog>

    <!-- 远程文件管理抽屉（仅 SSH 模式；目录树/上传/下载/版本为 mock 实现） -->
    <el-drawer v-model="fmVisible" :title="'远程文件管理 - ' + (fmNode?.name ?? '')" size="640px">
      <div v-if="fmNode">
        <!-- 节点信息条 -->
        <div class="fm-info">
          <b>{{ fmNode.name }}</b>
          <span class="mono" style="font-size:11.5px;color:var(--text-2)">{{ fmNode.ip }}</span>
          <span style="color:var(--text-3)">{{ fmNode.os }}</span>
          <span class="pill off">{{ fmNode.mode }} 模式</span>
          <span class="pill" :class="fmNode.status === 'online' ? 'ok' : 'err'">{{ fmNode.status === 'online' ? '在线' : '离线' }}</span>
        </div>
        <!-- 模式说明行 -->
        <div class="fm-note">当前支持 SSH 模式；Agent 模式规划中。</div>

        <!-- 面包屑 + 上传 -->
        <div class="fm-bar">
          <span class="crumb">
            <template v-for="(c, i) in crumbs" :key="c.path || 'root'">
              <span
                class="seg" :class="{ plain: !c.exists, last: c.last }"
                @click="crumbClick(c)"
              >{{ c.label }}</span>
              <span v-if="i < crumbs.length - 1" class="sep">/</span>
            </template>
          </span>
          <span class="spacer" />
          <button class="tb-new fm-upload-btn" @click="triggerUpload">上传文件</button>
          <input
            ref="fileInput" type="file" accept=".sh,.py,.java,.jar,.sql"
            style="display:none" @change="onUpload"
          />
        </div>

        <!-- 目录树（扁平行渲染，depth 控制缩进） -->
        <div class="fm-tree">
          <div
            v-for="row in fmRows" :key="row.node.path"
            class="fm-row" :class="{ dir: row.node.kind === 'dir' }"
            :style="{ paddingLeft: 10 + row.depth * 18 + 'px' }"
            @click="toggleDir(row.node)"
          >
            <span class="fm-caret">{{ row.node.kind === 'dir' ? (expanded[row.node.path] ? '▾' : '▸') : '' }}</span>
            <span class="fm-name" :class="{ mono: row.node.kind === 'file' }">{{ row.node.name }}</span>
            <span v-if="row.node.kind === 'file' && row.node.ext" class="ft" :class="'ft-' + row.node.ext">{{ row.node.ext }}</span>
            <span v-if="row.node.kind === 'file'" class="fm-meta">{{ row.node.size }} · {{ row.node.mtime }}</span>
            <span class="spacer" />
            <span v-if="row.node.kind === 'file'" class="fm-ops" @click.stop>
              <button class="op-btn" @click="downloadFile(row.node)">下载</button>
              <button v-if="canRun(row.node)" class="op-btn primary" @click="runFile(row.node)">执行</button>
              <el-popover placement="left" :width="280" trigger="click">
                <template #reference>
                  <button class="op-btn">版本</button>
                </template>
                <div v-for="ver in row.node.versions" :key="ver.v" class="fm-ver">
                  <span class="pill off">{{ ver.v }}</span>
                  <span class="fm-ver-time">{{ ver.time }}</span>
                  <span class="fm-ver-size">{{ ver.size }}</span>
                  <span v-if="ver.v === row.node.versions![row.node.versions!.length - 1].v" class="pill info">当前</span>
                </div>
              </el-popover>
            </span>
          </div>
        </div>
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
.op-btn.danger{color:var(--danger);border-color:rgba(229,72,77,.35)}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
.form-grid{display:flex;flex-direction:column;gap:12px}
.f-item{display:flex;flex-direction:column;gap:5px;font-size:12.5px;color:var(--text-2)}
.form-tip{background:var(--info-bg);color:var(--info);border-radius:var(--radius-sm);padding:8px 10px;font-size:12px;margin-bottom:14px;line-height:1.6}
.ro-val{border:1px dashed var(--border);border-radius:var(--radius-sm);padding:6px 10px;font-size:12.5px;background:var(--bg);color:var(--text-2)}

/* ---------- 远程文件管理抽屉 ---------- */
.fm-info{display:flex;align-items:center;gap:8px;font-size:12.5px;flex-wrap:wrap}
.fm-note{margin:8px 0 12px;font-size:11.5px;color:var(--text-3);background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);padding:6px 10px}
.fm-bar{display:flex;align-items:center;gap:6px;margin-bottom:10px;flex-wrap:wrap}
.fm-upload-btn{padding:5px 12px;font-size:12px}
.crumb{font-size:12.5px;color:var(--text-3);min-width:0;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.crumb .seg{cursor:pointer;color:var(--primary)}
.crumb .seg:hover{text-decoration:underline}
.crumb .seg.plain{cursor:default;color:var(--text-3)}
.crumb .seg.plain:hover{text-decoration:none}
.crumb .seg.last{color:var(--text);font-weight:600;cursor:default}
.crumb .seg.last:hover{text-decoration:none}
.crumb .sep{margin:0 4px;color:var(--border-strong)}
.fm-tree{border:1px solid var(--border);border-radius:var(--radius);background:#fff;overflow:hidden}
.fm-row{display:flex;align-items:center;gap:6px;padding:7px 10px;border-bottom:1px solid var(--border);font-size:12.5px;min-height:33px}
.fm-row:last-child{border-bottom:none}
.fm-row.dir{cursor:pointer;font-weight:600}
.fm-row.dir:hover{background:var(--primary-light)}
.fm-caret{width:12px;flex:none;color:var(--text-3);font-size:10px;line-height:1}
.fm-name{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.fm-name.mono{font-size:11.5px}
.fm-meta{flex:none;font-size:11px;color:var(--text-3)}
.fm-ops{flex:none;display:flex;align-items:center;gap:4px}
.fm-ops .op-btn{margin-right:0}
/* 文件类型徽标：.sh 灰 / .py 蓝 / .java 橙 / .jar 紫 / .sql 青 / .parquet 粉 */
.ft{flex:none;font-size:10px;font-weight:600;line-height:16px;padding:0 6px;border-radius:4px;letter-spacing:.3px}
.ft-sh{background:#eef1f6;color:var(--text-3)}
.ft-py{background:var(--info-bg);color:var(--info)}
.ft-java{background:var(--warn-bg);color:var(--warn)}
.ft-jar{background:#f1e9ff;color:var(--purple)}
.ft-sql{background:#e0f5f8;color:var(--cyan)}
.ft-parquet{background:#fde7f1;color:#db2777}
/* 版本 popover 行 */
.fm-ver{display:flex;align-items:center;gap:8px;font-size:11.5px;padding:5px 0;border-bottom:1px dashed var(--border)}
.fm-ver:last-child{border-bottom:none}
.fm-ver-time{color:var(--text-2)}
.fm-ver-size{color:var(--text-3);font-size:11px}
</style>
