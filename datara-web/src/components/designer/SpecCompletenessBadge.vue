<script setup lang="ts">
/**
 * Task 6（方案§2.1/§2.6）：声明完整度徽标（消费 specCompleteness 的 CompletenessResult）。
 * - 完整态：绿色「8/8」（8 要素齐备；4 组缺项与 8 要素非一一对应，完整态文案取 8/8）；
 * - 缺项态：黄色 + 缺项 chips（按组渲染），点击 chip emit('goto', groupId)——
 *   由父组件监听切到对应页签（数据单向：本组件不持状态、不直接切 tab）。
 * canDrop 只看身份∧表现（方案§2.1），徽标仅做完成度提示，不承担闸门职责。
 */
import { computed } from 'vue'
import type { CompletenessGroupId, CompletenessResult } from './specCompleteness'

const props = defineProps<{ result: CompletenessResult }>()
const emit = defineEmits<{ (e: 'goto', id: CompletenessGroupId): void }>()

const GROUP_TEXT: Record<CompletenessGroupId, string> = {
  identity: '身份', contract: '契约', visual: '表现', extension: '扩展',
}
const MISSING_TEXT: Record<string, string> = {
  type: 'type 标识', summary: 'summary 简介', 'fields.required': '必填字段', outputs: '输出定义', icon: 'icon 图标',
}

/** 缺项 chips（组序 × 组内缺项序；chip 附组名提示，点击直达对应页签） */
const chips = computed(() =>
  props.result.groups.flatMap((g) =>
    g.missing.map((m) => ({ id: g.id, key: m, text: MISSING_TEXT[m] ?? m, title: `${GROUP_TEXT[g.id]}组缺项：${MISSING_TEXT[m] ?? m}` }))),
)
const complete = computed(() => props.result.missing.length === 0)
</script>

<template>
  <div class="scb" :class="complete ? 'is-ok' : 'is-warn'">
    <template v-if="complete">
      <span class="scb-dot" />
      <span class="scb-ok" data-testid="scb-ok">8/8 声明完整</span>
    </template>
    <template v-else>
      <span class="scb-dot" />
      <span class="scb-miss" data-testid="scb-miss">
        缺 {{ result.missing.length }} 项
        <template v-if="!result.canDrop"> · 不满足拖入落库门槛</template>
      </span>
      <button
        v-for="c in chips" :key="c.key" type="button" class="scb-chip"
        :data-testid="`scb-chip-${c.key}`" :title="`${c.title}，点击直达`" @click="emit('goto', c.id)"
      >{{ c.text }}</button>
    </template>
  </div>
</template>

<style scoped>
.scb {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  padding: 6px 10px;
  border-radius: var(--radius-sm, 6px);
  font-size: 12px;
  border: 1px solid var(--border);
  background: var(--card);
}
.scb.is-ok {
  color: #15803d;
  background: #dcfce7;
  border-color: #bbf7d0;
}
.scb.is-warn {
  color: #a16207;
  background: #fef9c3;
  border-color: #fde68a;
}
.scb-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex: none;
}
.is-ok .scb-dot { background: #16a34a; }
.is-warn .scb-dot { background: #d97706; }
.scb-ok { font-weight: 600; }
.scb-miss { font-weight: 500; }
.scb-chip {
  border: 1px solid #f59e0b;
  background: #fffbeb;
  color: #b45309;
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 10px;
  cursor: pointer;
  transition: background var(--dur-fast, 0.15s) var(--ease, ease);
}
.scb-chip:hover {
  background: #fde68a;
}
</style>
