<script setup lang="ts">
/**
 * InstanceBar（I10 G1/G2/G3/G6/G22）：实例下拉（仅在线 + 类型标签）+ 属性卡
 * + 全局参数/执行历史/主题/快捷键按钮 + env 选择器 + 事务模式切换。
 * 状态全部走 ideStore；抽屉开关由父壳 IdeView 承接。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useIdeStore, ENV_LIST } from '../../../stores/ideStore'

const store = useIdeStore()

const emit = defineEmits<{
  (e: 'open-params'): void
  (e: 'open-history'): void
  (e: 'show-shortcuts'): void
}>()

const metaVisible = ref(false)

const TYPE_LABELS: Record<string, string> = { mysql: 'MySQL8', greatdb: 'GreatDB' }
function typeLabel(t: string): string {
  return TYPE_LABELS[t] ?? t
}

const metaRows = computed(() => {
  const m = store.dsMeta
  return [
    { label: '数据库类型', value: m ? typeLabel(m.type) : '-' },
    { label: '版本', value: m?.version ?? '-' },
    { label: '默认 Schema', value: m?.defaultSchema || '-' },
    { label: '连接超时', value: m ? `${m.timeoutSec}s` : '-' },
    { label: '事务隔离级别', value: m?.isolation ?? '-' },
    { label: '主机', value: m ? `${m.host ?? '-'}:${m.port ?? '-'}` : '-' },
  ]
})

const noOnline = computed(() => store.dsList.length === 0)

/* 实例切换联动：刷新树/上下文/清空补全缓存（树组件 watch store.activeDsId 自行处理） */
watch(() => store.activeDsId, () => {
  store.clearSchemaCache()
})

onMounted(() => {
  if (store.dsList.length === 0) void store.loadDsList()
})

/* 缺陷1 修复：受控组件 @change 回传新值；旧实现读 store.activeDsId 恒为旧值导致切换失效 */
function onDsChange(id: number | null): void {
  if (id !== null && id !== store.activeDsId) void store.selectDs(id)
}
</script>

<template>
  <div class="ibar">
    <span class="ibar-title">数据开发IDE</span>
    <el-select
      :model-value="store.activeDsId"
      class="ds-sel"
      placeholder="选择实例（仅在线）"
      filterable
      @change="onDsChange"
    >
      <el-option v-for="d in store.dsList" :key="d.id" :value="d.id" :label="d.name">
        <span class="ds-opt">
          <span>{{ d.name }}</span>
          <span class="ds-tag" :class="'tag-' + d.type">{{ typeLabel(d.type) }}</span>
        </span>
      </el-option>
    </el-select>

    <!-- 实例属性卡（G2） -->
    <el-popover placement="bottom-start" :width="330" trigger="hover">
      <template #reference>
        <button class="op-btn" :disabled="!store.dsMeta" @click="metaVisible = !metaVisible">属性卡</button>
      </template>
      <div class="meta-card">
        <div class="meta-name">{{ store.dsMeta?.name ?? '实例属性' }}</div>
        <div v-for="r in metaRows" :key="r.label" class="meta-row">
          <span class="meta-k">{{ r.label }}</span>
          <span class="meta-v mono">{{ r.value }}</span>
        </div>
      </div>
    </el-popover>

    <span class="ibar-sep" />
    <span class="ibar-label">环境</span>
    <el-radio-group v-model="store.env" size="small">
      <el-radio-button v-for="e in ENV_LIST" :key="e" :value="e">{{ e }}</el-radio-button>
    </el-radio-group>

    <span class="ibar-label">事务模式</span>
    <el-radio-group v-model="store.mode" size="small">
      <el-radio-button value="auto">自动提交</el-radio-button>
      <el-radio-button value="manual">事务包裹</el-radio-button>
    </el-radio-group>

    <span class="spacer" />
    <button class="op-btn" @click="emit('open-params')">全局参数</button>
    <button class="op-btn" @click="emit('open-history')">执行历史</button>
    <button class="op-btn" @click="store.toggleTheme()">{{ store.theme === 'datara-dark' ? '☀ 浅色' : '🌙 深色' }}</button>
    <button class="op-btn" @click="emit('show-shortcuts')">快捷键</button>
  </div>
  <div v-if="noOnline" class="ibar-warn">
    暂无连通在线的连接型实例（mysql/greatdb）——请先在「数据源管理」注册并完成连通测试。
  </div>
</template>

<style scoped>
.ibar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:8px 12px;background:var(--ide-card);border-bottom:1px solid var(--ide-border)}
.ibar-title{font-size:14px;font-weight:700;color:var(--ide-text)}
.ds-sel{width:210px}
.ds-opt{display:flex;align-items:center;gap:8px;justify-content:space-between;width:100%}
.ds-tag{font-size:10.5px;border-radius:3px;padding:0 5px;line-height:16px;color:#fff}
.tag-mysql{background:#0b7ea6}
.tag-greatdb{background:#7c3aed}
.ibar-label{font-size:12px;color:var(--ide-text-3)}
.ibar-sep{width:1px;height:18px;background:var(--ide-border)}
.spacer{flex:1}
.ibar-warn{background:var(--ide-warn-bg);color:var(--ide-warn);padding:7px 12px;font-size:12px}
.meta-card{font-size:12px}
.meta-name{font-weight:700;margin-bottom:6px}
.meta-row{display:flex;justify-content:space-between;gap:12px;padding:2px 0}
.meta-k{color:var(--ide-text-3);flex-shrink:0}
.meta-v{word-break:break-all;text-align:right}
</style>
