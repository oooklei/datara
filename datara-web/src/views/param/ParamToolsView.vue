<script setup lang="ts">
/**
 * M12 引用检测与参数预览（/param/tools）
 * 对齐 prototype/assets/pages/m12-param.js L111-143：
 * 双面板（1.4fr/1fr）：左「引用检测结果」（文件/引用参数/结果/说明，失败可去修复）；
 * 右「参数解析预览」（优先级：节点 > 工作流 > 环境组 > 全局）+ 未定义引用告警 + 去参数管理修复。
 * 顶部「重新扫描」按钮（页头工具栏）。
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { dataStore, ST } from '../../services/mock/dataStore'
import ParamTree from './ParamTree.vue'
import type { RefCheckResult, ParamPreview } from '../../services/types'

const router = useRouter()

const refRows = ref<RefCheckResult[]>([])
const previewRows = ref<ParamPreview[]>([])
const scanning = ref(false)
const keyword = ref('')

/* 左树 pick 过滤：按文件名或引用参数包含关键字 */
const filteredRefRows = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return refRows.value
  return refRows.value.filter(
    (r) => r.file.toLowerCase().includes(kw) || r.refs.some((x) => x.toLowerCase().includes(kw)),
  )
})

async function reload() {
  // 必须展开为新数组：dataStore.save 原地修改数组，直接赋值不会触发 ref 更新
  refRows.value = [...((await dataStore.list<RefCheckResult>('refCheckResult')) ?? [])]
  previewRows.value = [...((await dataStore.list<ParamPreview>('paramPreview')) ?? [])]
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

function stCls(result: string): string {
  return ST[result === 'pass' ? 'pass' : 'reject']?.cls ?? 'st-gray'
}
function stLabel(result: string): string {
  return ST[result === 'pass' ? 'pass' : 'reject']?.label ?? result
}

/* ---- 未定义引用：未出现在参数解析预览中的引用（用于告警条） ---- */
const failRows = computed(() => refRows.value.filter((r) => r.result !== 'pass'))
const undefinedRefs = computed(() => {
  const defined = new Set(previewRows.value.map((p) => p.name))
  const out = new Set<string>()
  for (const r of failRows.value) {
    for (const ref of r.refs) {
      const n = ref.replace(/^\$\{/, '').replace(/\}$/, '')
      if (!defined.has(n)) out.add(ref)
    }
  }
  return [...out].join('、')
})

/* ---- 重新扫描 ---- */
function scan() {
  if (scanning.value) return
  scanning.value = true
  ElMessage.info('正在扫描 ETL 任务 / 脚本中的参数引用...')
  later(() => {
    scanning.value = false
    const refs = refRows.value.reduce((n, r) => n + r.refs.length, 0)
    ElMessage.warning(
      '扫描完成：' + refRows.value.length + ' 个文件 / ' + refs + ' 个参数引用 / ' + failRows.value.length + ' 个未定义',
    )
  }, 900)
}

/* ---- 行操作 ---- */
function fixRow(r: RefCheckResult) {
  ElMessage.warning('已定位 ' + r.file + '：' + undefinedRefs.value + ' 未定义，请在全局参数中新增')
  router.push('/param/global')
}
function detailRow(r: RefCheckResult) {
  ElMessage.info(r.detail)
}
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ParamTree @pick="(kw) => (keyword = kw)" />
    <div style="flex:1;min-width:0">
    <!-- 页头 + 顶部操作工具栏 -->
    <div class="card page-head">
      <div>
        <div class="ph-title">引用检测与参数预览</div>
        <div class="ph-desc">发布前校验：扫描 SQL/脚本中的 ${参数} 引用是否已定义；并按解析优先级预览最终值</div>
      </div>
      <span class="spacer" />
      <button class="tb-new" :disabled="scanning" @click="scan">▶ 重新扫描</button>
    </div>

    <!-- 双面板 -->
    <div class="grid2">
      <!-- 左：引用检测结果 -->
      <div class="card" style="padding:16px">
        <div class="tbl-toolbar">
          <span class="card-title">引用检测结果</span>
          <span class="pill info">{{ filteredRefRows.length }} / {{ refRows.length }} 个文件</span>
          <span v-if="failRows.length" class="pill err">{{ failRows.length }} 个未定义</span>
          <span class="spacer" />
          <input v-model="keyword" class="kw" placeholder="搜索文件/参数" />
        </div>
        <table class="tbl">
          <thead>
            <tr>
              <th>文件/任务</th><th>引用参数</th><th>结果</th><th>说明</th><th style="width:80px">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in filteredRefRows" :key="r.file">
              <td style="font-weight:600">{{ r.file }}</td>
              <td>
                <span v-for="x in r.refs" :key="x" class="ref-tag mono">{{ x }}</span>
              </td>
              <td><span class="st" :class="stCls(r.result)"><span class="dot" />{{ stLabel(r.result) }}</span></td>
              <td><span style="font-size:11.5px;color:var(--text-2)">{{ r.detail }}</span></td>
              <td>
                <button v-if="r.result === 'fail'" class="op-btn danger" @click="fixRow(r)">去修复</button>
                <button v-else class="op-btn" @click="detailRow(r)">详情</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="refRows.length === 0" class="empty">暂无检测结果，点击右上角「重新扫描」</div>
        <div v-else-if="filteredRefRows.length === 0" class="empty">未找到匹配的文件/参数引用</div>
      </div>

      <!-- 右：参数解析预览 -->
      <div class="card" style="padding:16px">
        <div class="tbl-toolbar">
          <span class="card-title">参数解析预览</span>
          <span class="pill info">优先级：节点 &gt; 工作流 &gt; 环境组 &gt; 全局</span>
        </div>
        <table class="tbl">
          <thead>
            <tr>
              <th>参数</th><th>作用域</th><th>解析值</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in previewRows" :key="p.name">
              <td><span class="mono">{{ '${' + p.name + '}' }}</span></td>
              <td style="color:var(--text-2)">{{ p.scope }}</td>
              <td><span class="mono" style="color:var(--success)">{{ p.value }}</span></td>
            </tr>
          </tbody>
        </table>
        <div v-if="previewRows.length === 0" class="empty">暂无参数预览数据</div>

        <div v-if="undefinedRefs" class="warn-banner">
          <span class="b-ico">⚠</span>
          <span>存在 {{ failRows.length }} 个未定义引用（{{ undefinedRefs }}），请在「全局参数」新增或修正拼写，否则任务执行将失败。</span>
        </div>
        <button class="tb-new" style="margin-top:12px" @click="router.push('/param/global')">去参数管理修复</button>
      </div>
    </div>
    </div>
  </div>
</template>

<style scoped>
.page-head{display:flex;align-items:center;gap:12px;padding:14px 16px;margin-bottom:14px}
.ph-title{font-weight:700;font-size:15px}
.ph-desc{font-size:12px;color:var(--text-3);margin-top:2px}
.spacer{flex:1}
.grid2{display:grid;grid-template-columns:1.4fr 1fr;gap:16px;align-items:flex-start}
.card-title{font-weight:700;font-size:14px}
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;padding:9px 10px;background:var(--bg);color:var(--text-2);font-weight:600;border-bottom:1px solid var(--border)}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--border);vertical-align:top}
.tbl tr:hover td{background:var(--primary-light)}
.ref-tag{display:inline-block;border:1px solid var(--border-strong);border-radius:4px;padding:0 6px;font-size:11px;color:var(--text-2);margin:1px 4px 1px 0}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease)}
.kw{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 10px;font-size:12.5px;width:190px;outline:none}
.kw:focus{border-color:var(--primary)}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
.tb-new:disabled{opacity:.6;cursor:default}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
.op-btn.danger{color:var(--danger);border-color:rgba(229,72,77,.35)}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.warn-banner{display:flex;gap:8px;align-items:flex-start;background:var(--warn-bg);color:var(--warn);border-radius:var(--radius-sm);padding:8px 10px;font-size:11.5px;margin-top:12px}
.b-ico{font-weight:700;flex-shrink:0}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
</style>
