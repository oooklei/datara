<script setup lang="ts">
/**
 * 业务表单分组渲染器（Inspector 属性面板与拖入配置弹窗**共用同一实现**）。
 *
 * 治理设计 §12.2「禁双实现漂移」：此前两处宿主各自 `v-for` 平铺渲染 `visibleForm`，
 * 标签、必填红星、FieldRenderer 接线完全重复——任何呈现改动都必须同步改两处。
 * 本组件把「分组标题 + 字段行」收敛为唯一实现，两处宿主只提供 `form`（已按 showIf 过滤）。
 *
 * 分组规则见 `profiles/formSections.ts`（相邻同组合并；无 group 的字段平铺成段）。
 * 未声明分组的组件走 `fs-plain` 平铺路径，呈现与改造前逐字一致。
 */
import { computed, ref } from 'vue'
import FieldRenderer from './FieldRenderer.vue'
import { formSections } from '../../profiles/formSections'
import type { FieldSchema, ViewProfile } from '../../profiles/types'
import type { FieldCtx } from './fieldCtx'

const props = defineProps<{
  /** 已按 showIf 过滤的可见表单（务必传 visibleForm，勿传 schema.form 原数组） */
  form: FieldSchema[]
  /** 目标节点 data（FieldRenderer 的读写对象） */
  data: Record<string, unknown>
  /** edit / view */
  mode: 'edit' | 'view'
  nodeId: string
  ctx: FieldCtx
  /** 宿主 profile（FieldRenderer 需要 nodeTypes 语境） */
  profile: ViewProfile
}>()

const emit = defineEmits<{
  /** 透传 FieldRenderer 的 set(f, ev)：由宿主接 onSet（负责 upd + onChange + number 转型） */
  (e: 'set', f: FieldSchema, ev: Event): void
  (e: 'dirty'): void
  (e: 'open-var-dialog', target: string): void
  (e: 'focus-target', key: string): void
}>()

/** 分组切分（纯函数，宿主已过滤 showIf → 组内全隐藏的分组自然不出现） */
const sections = computed(() => formSections(props.form))

/** 是否存在任一分组标题（全平铺时不出标题层，视觉与改造前一致） */
const grouped = computed(() => sections.value.some((s) => !!s.key))

/** 弹窗/面板内的分组折叠态（Set 换新引用以触发响应式；默认全展开） */
const collapsed = ref<Set<string>>(new Set())
function toggle(key: string) {
  const next = new Set(collapsed.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  collapsed.value = next
}
</script>

<template>
  <div class="fs" :class="{ 'fs-grouped': grouped }">
    <section v-for="s in sections" :key="s.key || '__plain'" class="fs-sec">
      <header v-if="s.key" class="fs-head" @click="toggle(s.key)">
        <span class="fs-arrow" :class="{ open: !collapsed.has(s.key) }">▸</span>
        <span class="fs-title">{{ s.title }}</span>
        <span v-if="s.hint" class="fs-hint">{{ s.hint }}</span>
      </header>

      <div v-show="!s.key || !collapsed.has(s.key)" class="fs-body">
        <div v-for="f in s.fields" :key="f.key" class="field">
          <label v-if="f.type !== 'hint'">
            {{ f.label }}<span v-if="f.required" class="req-star" title="必填">*</span>
          </label>
          <FieldRenderer
            :field="f" :data="data" :mode="mode" :node-id="nodeId" :ctx="ctx"
            @set="(f, ev) => emit('set', f, ev)"
            @dirty="emit('dirty')"
            @open-var-dialog="(t) => emit('open-var-dialog', t)"
            @focus-target="(t) => emit('focus-target', t)"
          />
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.fs-grouped { display: flex; flex-direction: column; gap: 10px; }
.fs-sec { min-width: 0; }
.fs-head {
  display: flex; align-items: center; gap: 6px; cursor: pointer; user-select: none;
  padding: 5px 8px; margin-bottom: 6px;
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: var(--bg); font-size: 12px; font-weight: 600; color: var(--text);
}
.fs-head:hover { border-color: var(--primary); color: var(--primary); }
.fs-arrow { font-size: 10px; color: var(--text-3); transition: transform .15s; flex: none; }
.fs-arrow.open { transform: rotate(90deg); }
.fs-title { flex: none; }
.fs-hint {
  font-weight: 400; font-size: 11px; color: var(--text-3);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.fs-body { display: flex; flex-direction: column; gap: 8px; padding-left: 2px; }
</style>
