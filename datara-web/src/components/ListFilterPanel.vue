<script setup lang="ts">
/**
 * ListFilterPanel：列表页主窗口左侧搜索/筛选栏。
 * 约定：主窗口为列表的页面，左侧固定 220px 面板承载 搜索关键字 + 各筛选 facet，
 * 顶部工具栏只保留动作按钮（新建/导出等，遵循"操作按钮在顶部"的既有约定）。
 * 契约：
 *  - v-model:keyword   关键字（string，'' 为空）
 *  - v-model:filters   各 facet 当前值（Record<key,string>，'' 为全部）
 *  - facets            筛选定义 [{key,label,options:[{v,t}]}]
 *  - resultCount/totalCount 可选，底部显示命中数
 * facet 点击已选中项 = 取消（回到"全部"）；重置按钮一键清空。
 */
import { computed } from 'vue'

export interface FacetOption {
  v: string
  t: string
}
export interface Facet {
  key: string
  label: string
  options: FacetOption[]
}

const props = defineProps<{
  keyword: string
  filters: Record<string, string>
  facets: Facet[]
  placeholder?: string
  resultCount?: number
  totalCount?: number
}>()

const emit = defineEmits<{
  (e: 'update:keyword', v: string): void
  (e: 'update:filters', v: Record<string, string>): void
}>()

function setKw(ev: Event) {
  emit('update:keyword', (ev.target as HTMLInputElement).value)
}
function setF(key: string, v: string) {
  emit('update:filters', { ...props.filters, [key]: v })
}
function toggleF(key: string, v: string) {
  setF(key, props.filters[key] === v ? '' : v)
}
function reset() {
  emit('update:keyword', '')
  emit('update:filters', Object.fromEntries(props.facets.map((f) => [f.key, ''])))
}
const dirty = computed(
  () => props.keyword.trim() !== '' || props.facets.some((f) => props.filters[f.key]),
)
</script>

<template>
  <aside class="lfp">
    <div class="lfp-block">
      <div class="lfp-label">搜索</div>
      <input
        class="lfp-kw"
        :value="keyword"
        :placeholder="placeholder ?? '搜索关键字'"
        @input="setKw"
      />
    </div>
    <div v-for="f in facets" :key="f.key" class="lfp-block">
      <div class="lfp-label">{{ f.label }}</div>
      <div class="lfp-opts">
        <button class="lfp-opt" :class="{ on: !filters[f.key] }" @click="setF(f.key, '')">全部</button>
        <button
          v-for="o in f.options"
          :key="o.v"
          class="lfp-opt"
          :class="{ on: filters[f.key] === o.v }"
          @click="toggleF(f.key, o.v)"
        >{{ o.t }}</button>
      </div>
    </div>
    <div class="lfp-foot">
      <span v-if="resultCount !== undefined && totalCount !== undefined">
        {{ resultCount }} / {{ totalCount }} 条
      </span>
      <span v-else />
      <button v-if="dirty" class="lfp-reset" @click="reset">重置筛选</button>
    </div>
  </aside>
</template>

<style scoped>
.lfp{width:220px;flex-shrink:0;background:#fff;border:1px solid var(--border);border-radius:var(--radius-lg);padding:14px 12px;display:flex;flex-direction:column;gap:14px;align-self:flex-start;position:sticky;top:12px}
.lfp-label{font-size:11px;color:var(--text-3);font-weight:600;margin-bottom:6px;letter-spacing:.5px}
.lfp-kw{width:100%;box-sizing:border-box;border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 8px;font-size:12.5px;outline:none}
.lfp-kw:focus{border-color:var(--primary)}
.lfp-opts{display:flex;flex-wrap:wrap;gap:5px}
.lfp-opt{border:1px solid var(--border-strong);background:#fff;border-radius:999px;padding:2px 9px;font-size:11.5px;color:var(--text-2);cursor:pointer}
.lfp-opt:hover{border-color:var(--primary);color:var(--primary)}
.lfp-opt.on{background:var(--primary);border-color:var(--primary);color:#fff}
.lfp-foot{display:flex;align-items:center;justify-content:space-between;font-size:11px;color:var(--text-3);border-top:1px dashed var(--border);padding-top:10px;margin-top:auto}
.lfp-reset{border:none;background:none;color:var(--primary);font-size:11.5px;cursor:pointer;padding:0}
.lfp-reset:hover{text-decoration:underline}
</style>
