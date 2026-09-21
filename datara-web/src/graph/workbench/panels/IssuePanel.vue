<script setup lang="ts">
import type { Issue } from '../../../graph/model'

defineProps<{ issues: Issue[] }>()
</script>

<template>
  <div>
    <div v-if="issues.length === 0" style="padding:16px;text-align:center;color:var(--success)">
      ✓ 校验通过，未发现问题
    </div>
    <div v-for="(it, i) in issues" :key="i" class="issue-item" :class="it.level" style="margin-bottom:6px">
      <span class="lv">{{ it.level === 'error' ? '错误' : '警告' }}</span>
      <span>{{ it.msg }}</span>
    </div>
    <div v-if="issues.length" style="margin-top:8px;font-size:11px;color:var(--text-3)">
      共 {{ issues.filter((x) => x.level === 'error').length }} 错误 · {{ issues.filter((x) => x.level === 'warn').length }} 警告
    </div>
  </div>
</template>
