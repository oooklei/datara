<template><dl class="snap-meta" data-snapshot-meta>
  <div class="meta-row"><dt>sourceVersion</dt><dd><code data-source-version>{{ snapshot.sourceVersion }}</code></dd></div>
  <div class="meta-row"><dt>capability</dt><dd>
    <code data-capability>{{ snapshot.capability }}</code>
    <span :data-write-allowed="writable ? 'yes' : 'no'">{{ writable ? '写链放行' : '写链拒写（fail-closed）' }}</span>
  </dd></div>
  <div v-if="snapshot.constraints.length > 0" class="meta-row"><dt>constraints</dt><dd>
    <ul data-constraint-list><li v-for="c in snapshot.constraints" :key="c" data-constraint>{{ c }}</li></ul>
  </dd></div>
</dl></template>

<script setup lang="ts">
/**
 * 16.1 波3 定义快照元信息（两轨共用）：sourceVersion（快照绑定链锚）+
 * capability 分级闸呈现（supported/conditional 放行，unsupported/unknown 及
 * 一切未知值 fail-closed 拒写）+ constraints 限制格逐条呈现。
 */
import { computed } from 'vue'
import type { DdlDefinitionSnapshot } from '../../../services/rebuild/sqlIdeDdlApi'

const props = defineProps<{ snapshot: DdlDefinitionSnapshot }>()

const writable = computed(() => props.snapshot.capability === 'supported' || props.snapshot.capability === 'conditional')
</script>

<style scoped>
.snap-meta{margin:0 0 12px;padding:10px 12px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;font-size:13px}
.meta-row{display:flex;gap:10px;align-items:baseline;padding:3px 0}
.meta-row dt{min-width:110px;color:#64748b}
.meta-row dd{margin:0;color:#172033}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px;background:#eef2f7;padding:1px 5px;border-radius:3px}
[data-write-allowed]{margin-left:8px;font-size:12px}
[data-write-allowed="yes"]{color:#15803d}
[data-write-allowed="no"]{color:#b91c1c}
[data-constraint-list]{margin:0;padding-left:16px}
[data-constraint]{color:#92400e}
</style>
