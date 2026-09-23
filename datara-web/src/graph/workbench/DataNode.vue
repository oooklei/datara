<script setup lang="ts">
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'
import type { GNode } from '../model'
import type { NodeSchema } from '../profiles/types'
import { requiredMissing } from '../profiles/formLinkage'
import { NODE_ART, NODE_ART_FALLBACK } from './arts'
import { useRunStore } from '../../stores/run'

const props = defineProps<{
  id: string
  gnode: GNode
  schema: NodeSchema
  selected?: boolean
}>()

const run = useRunStore()
const status = computed<string>(() => run.nodeStatus[props.id] ?? 'idle')
const stClass = computed(() => (status.value === 'idle' ? '' : `st-${status.value}`))
const sub = computed(() => (props.schema.summary ? props.schema.summary(props.gnode.data) : ''))
const health = computed(() => String(props.gnode.data.health ?? ''))
/** I3：实例详情 DAG 的 attempt 徽标（>1 时展示，注入自 _attempt） */
const attempt = computed(() => Number(props.gnode.data._attempt ?? 0))
const healthColor = computed(() =>
  health.value === 'fail' ? 'var(--danger)' : health.value === 'warn' ? 'var(--warn)' : 'var(--success)')
const blind = computed(() => props.gnode.data.blind === true)
/** 动态分支端点（条件分支/Switch 等）：每分支独立输出 Handle */
const ports = computed(() => props.schema.ports?.(props.gnode.data) ?? [])
/** W1 必填完整性：required 字段在当前分型下为空 → 画布「未配置」角标（title 列缺失项，与校验面板/保存闸门共用判定） */
const missing = computed(() => requiredMissing(props.schema, props.gnode.data))
/** 设备形态：拓扑视角专用（主机/交换机/服务器/中间件 logo 图标卡片） */
const isDevice = computed(() => props.schema.shape === 'device')
const art = computed(() => NODE_ART[props.schema.type] ?? NODE_ART_FALLBACK)
</script>

<template>
  <!-- 设备形态：图标卡片（图标在上 SVG currentColor，名称/组件地址在下） -->
  <div v-if="isDevice" class="gnode gnode-device" :class="[stClass, { selected, blind }]">
    <Handle type="target" :position="Position.Left" />
    <div class="dev-art-wrap" :style="{ borderColor: schema.color, color: schema.color }">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" class="dev-art" v-html="art" />
    </div>
    <div class="dev-name" :title="String(gnode.data.name ?? '')">{{ gnode.data.name }}</div>
    <div class="dev-sub" :title="sub">{{ sub }}</div>
    <div v-if="health" class="dev-health" :style="{ background: healthColor }" :title="'健康状态: ' + health" />
    <div class="n-status" />
    <span v-if="attempt > 1" class="n-attempt">#{{ attempt }}</span>
    <Handle type="source" :position="Position.Right" />
  </div>

  <!-- 分支节点：头部 + 每分支一行（右侧独立端点，Handle 锚定行内） -->
  <div v-else-if="ports.length" class="gnode gnode-branch" :class="[stClass, { selected, blind }]">
    <Handle type="target" :position="Position.Left" />
    <div class="nb-head">
      <div class="n-ico" :style="{ background: schema.color }">{{ schema.icon }}</div>
      <div style="min-width:0;flex:1">
        <div class="n-name" :title="String(gnode.data.name ?? '')">{{ gnode.data.name }}</div>
        <div class="n-sub" :title="sub">{{ sub }}</div>
      </div>
      <div v-if="health" class="n-health" :style="{ background: healthColor }" :title="'健康状态: ' + health" />
      <div class="n-status" />
      <span v-if="attempt > 1" class="n-attempt">#{{ attempt }}</span>
      <span v-if="missing.length" class="n-miss" :title="'未配置：' + missing.join('、')">!</span>
    </div>
    <div v-for="p in ports" :key="p.id" class="nb-row">
      <span class="nb-label" :title="p.label">{{ p.label }}</span>
      <Handle type="source" :id="p.id" :position="Position.Right" />
    </div>
  </div>

  <!-- 普通节点：单输入单输出 -->
  <div v-else class="gnode" :class="[stClass, { selected, blind }]">
    <Handle type="target" :position="Position.Left" />
    <div class="n-ico" :style="{ background: schema.color }">{{ schema.icon }}</div>
    <div style="min-width:0;flex:1">
      <div class="n-name" :title="String(gnode.data.name ?? '')">{{ gnode.data.name }}</div>
      <div class="n-sub" :title="sub">{{ sub }}</div>
    </div>
    <div
      v-if="health" class="n-health"
      :style="{ background: healthColor }"
      :title="'健康状态: ' + health"
    />
    <div class="n-status" />
    <span v-if="attempt > 1" class="n-attempt">#{{ attempt }}</span>
    <span v-if="missing.length" class="n-miss" :title="'未配置：' + missing.join('、')">!</span>
    <Handle type="source" :position="Position.Right" />
  </div>
</template>

<style scoped>
/* 设备形态：图标卡片（覆盖 theme.css 固定宽度/高度与横向布局） */
.gnode-device{width:152px;height:auto;min-height:0;flex-direction:column;align-items:center;justify-content:center;gap:3px;padding:10px 8px 9px;text-align:center}
.dev-art-wrap{position:relative;width:52px;height:52px;display:flex;align-items:center;justify-content:center;background:#fff;border:1.6px solid;border-radius:11px;box-shadow:0 1px 4px rgba(15,23,42,.08)}
.dev-art{width:36px;height:36px;display:block}
.dev-name{font-size:12.5px;font-weight:600;color:var(--text-1);line-height:1.35;max-width:138px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dev-sub{font-size:10.5px;color:var(--text-3);line-height:1.3;max-width:138px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-family:var(--mono,monospace)}
.dev-health{position:absolute;top:6px;right:6px;width:10px;height:10px;border-radius:50%;border:2px solid #fff;box-shadow:0 0 0 1px rgba(0,0,0,.06)}

/* 分支节点纵向布局：头部 + 分支行（覆盖 theme.css 固定高度） */
.gnode-branch{height:auto;min-height:var(--node-h);flex-direction:column;align-items:stretch;gap:5px;padding:8px 10px}
.nb-head{display:flex;align-items:center;gap:9px;min-height:30px}
.nb-row{position:relative;display:flex;align-items:center;justify-content:flex-end;min-height:22px;padding:2px 16px 2px 8px;background:rgba(217,119,6,.07);border:1px dashed rgba(217,119,6,.35);border-radius:var(--radius-sm)}
.nb-label{font-size:11px;color:#b45309;line-height:1.3;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:calc(var(--node-w) - 44px)}
.gnode .n-health{width:10px;height:10px;border-radius:50%;flex-shrink:0}
/* W1 必填未配置角标（右上角悬浮，与 n-health 行内圆点不冲突；hover title 列缺失项） */
.gnode .n-miss{position:absolute;top:-7px;right:-7px;z-index:2;width:15px;height:15px;border-radius:50%;background:var(--warn,#d97706);color:#fff;font-size:10px;font-weight:700;line-height:15px;text-align:center;border:2px solid #fff;box-shadow:0 1px 3px rgba(15,23,42,.25);cursor:help;pointer-events:auto}
</style>
