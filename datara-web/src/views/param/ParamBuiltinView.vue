<script setup lang="ts">
/**
 * M12 内置时间参数（/param/builtin）
 * 对齐 prototype/assets/pages/m12-param.js L68-84：
 * 只读说明表格（内置参数 / 说明 / 解析示例）+ 试算提示。操作按钮无需置顶（原型无新建类操作）。
 */
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { dataStore } from '../../services/mock/dataStore'
import ParamTree from './ParamTree.vue'
import type { BuiltinParam } from '../../services/types'

const rows = ref<BuiltinParam[]>([])
const keyword = ref('')

async function reload() {
  rows.value = [...((await dataStore.list<BuiltinParam>('builtinParams')) ?? [])]
}
onMounted(reload)

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return rows.value
  return rows.value.filter((r) => [r.name, r.desc].some((s) => s.toLowerCase().includes(kw)))
})

/* ---- 试算（基于业务日期 T-1） ---- */
function tryCalc(p: BuiltinParam) {
  ElMessage.info('试算 ' + p.name + ' → ' + p.eg + '（基于业务日期 T-1）')
}
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ParamTree @pick="(kw) => (keyword = kw)" />
    <div style="flex:1;min-width:0">
    <!-- 页头 -->
    <div class="card page-head">
      <div>
        <div class="ph-title">内置时间参数</div>
        <div class="ph-desc">调度内置时间变量：无需定义直接在 SQL/脚本中引用，按业务日期（T-1）解析</div>
      </div>
    </div>

    <!-- 内置参数一览 -->
    <div class="card" style="padding:16px">
      <div class="tbl-toolbar">
        <span class="card-title">内置参数一览（以业务日期 2026-09-11 为例）</span>
        <span class="pill info">{{ filtered.length }} / {{ rows.length }}</span>
        <span class="spacer" />
        <input v-model="keyword" class="kw" placeholder="搜索参数" />
      </div>
      <table class="tbl">
        <thead>
          <tr>
            <th style="width:200px">参数</th><th>说明</th><th>解析示例</th><th style="width:80px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in filtered" :key="p.name">
            <td><span class="mono"><b>{{ p.name }}</b></span></td>
            <td style="color:var(--text-2)">{{ p.desc }}</td>
            <td><span class="mono" style="color:var(--success)">{{ p.eg }}</span></td>
            <td><a @click="tryCalc(p)">试算</a></td>
          </tr>
        </tbody>
      </table>
      <div v-if="filtered.length === 0" class="empty">未找到匹配的内置参数</div>
    </div>
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
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
</style>
