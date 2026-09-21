<script setup lang="ts">
/**
 * M12 参数导航树（参数模块左侧树目录，类 DolphinScheduler 参数导航）
 * 四个分类：全局参数 / 内置时间参数 / 环境参数组 / 引用检测与预览。
 * （工作流变量已迁入 DAG 工作台「变量」页签，管理与使用分离）
 * 分类行可展开收起并跳转对应路由；点击子项：已在目标页则 emit('pick') 供父页过滤，否则仅跳转。
 * 树数据组件内自加载（onMounted 并行取四个集合，一次取齐避免串行往返）。
 */
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { dataStore } from '../../services/mock/dataStore'
import type { GlobalParam, BuiltinParam, EnvGroup, RefCheckResult } from '../../services/types'

const emit = defineEmits<{ (e: 'pick', kw: string): void }>()
const route = useRoute()
const router = useRouter()

interface CatNode {
  key: string
  label: string
  path: string
  children: string[]
}

const cats = ref<CatNode[]>([])
const expanded = ref<Record<string, boolean>>({ global: true, builtin: true, env: true, tools: true })
const kw = ref('')

/* F56a 同壳单入口：活跃分类由 query.tab 判定（旧路径 /param/builtin 等已 redirect，path 不再区分页签） */
const activeTab = computed(() => {
  const t = String(route.query.tab ?? 'global')
  return ['global', 'builtin', 'env', 'tools'].includes(t) ? t : 'global'
})

onMounted(async () => {
  const [globals, builtins, envs, refs] = await Promise.all([
    dataStore.list<GlobalParam>('globalParams'),
    dataStore.list<BuiltinParam>('builtinParams'),
    dataStore.list<EnvGroup>('envGroups'),
    dataStore.list<RefCheckResult>('refCheckResult'),
  ])
  cats.value = [
    { key: 'global', label: '全局参数', path: '/param/global', children: globals.map((g) => g.name) },
    { key: 'builtin', label: '内置时间参数', path: '/param/builtin', children: builtins.map((b) => b.name) },
    { key: 'env', label: '环境参数组', path: '/param/env', children: envs.map((e) => e.name) },
    { key: 'tools', label: '引用检测与预览', path: '/param/tools', children: refs.map((r) => r.file) },
  ]
})

/** 搜索过滤后的树视图（kw 不变时 computed 缓存，模板内不重复过滤） */
const viewCats = computed(() => {
  const k = kw.value.trim().toLowerCase()
  return cats.value.map((c) => ({
    ...c,
    shown: k ? c.children.filter((x) => x.toLowerCase().includes(k)) : c.children,
  }))
})

function toggle(key: string) {
  expanded.value[key] = !expanded.value[key]
}

function pickChild(cat: CatNode, text: string) {
  if (activeTab.value === cat.key) emit('pick', text)
  else router.push(cat.path)
}
</script>

<template>
  <div class="ptree card">
    <input v-model="kw" class="pt-search" placeholder="搜索参数/文件" />
    <div
      v-for="cat in viewCats"
      :key="cat.key"
      class="pt-cat"
      :class="{ active: activeTab === cat.key }"
    >
      <div class="pt-cat-row" @click="router.push(cat.path)">
        <span class="pt-arrow" :class="{ open: expanded[cat.key] }" @click.stop="toggle(cat.key)">▶</span>
        <span class="pt-cat-name">{{ cat.label }}</span>
        <span class="pt-badge">{{ cat.shown.length }}</span>
      </div>
      <template v-if="expanded[cat.key]">
        <div
          v-for="c in cat.shown"
          :key="c"
          class="pt-child"
          :title="c"
          @click="pickChild(cat, c)"
        >{{ c }}</div>
        <div v-if="cat.shown.length === 0" class="pt-none">无匹配</div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.ptree{width:240px;flex:none;padding:10px;font-size:12.5px}
.pt-search{width:100%;box-sizing:border-box;border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 10px;font-size:12px;outline:none;margin-bottom:8px;color:var(--text)}
.pt-search:focus{border-color:var(--primary)}
.pt-cat{margin-bottom:2px}
.pt-cat-row{display:flex;align-items:center;gap:6px;padding:6px;border-radius:var(--radius-sm);cursor:pointer;font-weight:600;color:var(--text);user-select:none}
.pt-cat-row:hover{background:var(--bg)}
.pt-cat.active .pt-cat-row{background:var(--primary-light);color:var(--primary)}
.pt-arrow{font-size:9px;color:var(--text-3);transition:transform .15s;flex:none}
.pt-arrow.open{transform:rotate(90deg)}
.pt-badge{margin-left:auto;background:var(--bg);border-radius:var(--radius);padding:0 7px;font-size:10.5px;color:var(--text-3);font-weight:400}
.pt-cat.active .pt-badge{background:#fff}
.pt-child{padding:4px 6px 4px 24px;font-size:12px;color:var(--text-2);border-radius:var(--radius-sm);cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pt-child:hover{background:var(--bg);color:var(--primary)}
.pt-none{padding:3px 6px 3px 24px;font-size:11px;color:var(--text-3)}
</style>
