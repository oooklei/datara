<script setup lang="ts">
import { computed } from 'vue'
import type { BaselineSpec } from '../../services/baselineSpec'

const props = defineProps<{ spec: BaselineSpec; readonly?: boolean }>()
const emit = defineEmits<{ 'update:spec': [BaselineSpec] }>()

const text = computed({
  get: () => JSON.stringify(props.spec, null, 2),
  set: (v: string) => {
    try {
      emit('update:spec', JSON.parse(v) as BaselineSpec)
    } catch {
      // Keep the last valid JSON while the user is typing an incomplete value.
    }
  },
})

const sections = [
  '输入参数',
  '输出变量',
  '引用变量',
  '约束条件',
  '互斥规则',
  '渲染声明',
  '配置抽屉预览',
  '投放策略',
]
</script>

<template>
  <div class="ese eight-editor" :class="{ ro: readonly }">
    <div class="ese-tabs" aria-label="八段 DSL 编辑区">
      <span v-for="s in sections" :key="s" class="ese-tab">{{ s }}</span>
    </div>
    <textarea v-model="text" :readonly="readonly" spellcheck="false" />
  </div>
</template>

<style scoped>
.eight-editor {
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: #fff;
}
.eight-editor.ro {
  background: #f8fafc;
}
.ese-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 10px;
  border-bottom: 1px solid #e2e8f0;
  background: #f8fafc;
}
.ese-tab {
  font-size: 12px;
  color: #475569;
  background: #fff;
  border: 1px solid #dbe3ef;
  border-radius: 999px;
  padding: 2px 8px;
}
textarea {
  width: 100%;
  min-height: 360px;
  border: 0;
  outline: 0;
  resize: vertical;
  padding: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.6;
  background: transparent;
  color: #334155;
  box-sizing: border-box;
}
</style>
