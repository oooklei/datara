<script setup lang="ts">
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'
import type { GNode } from '../model'
import type { NodeSchema } from '../profiles/types'
import { renderSummary, requiredMissing } from '../profiles/formLinkage'
import { NODE_ART, NODE_ART_FALLBACK } from './arts'
import { memoPorts } from './portsMemo' // Task 12（§3.6）：动态端口结果 memo（收益与边界见 portsOf 处注释）
import { useRunStore } from '../../stores/run'
import { useComponentStore } from '../../stores/componentStore' // Task 15（§4.3/§4.4）：spec 缓存源

const props = defineProps<{
  id: string
  gnode: GNode
  schema: NodeSchema
  selected?: boolean
  /** Task 10（§3.3）：校验错误红描边（st-error）——独立于运行时 st-* 状态类，不占用 status 语义 */
  hasError?: boolean
  /** Task 10（§3.3）：一键定位高亮（error-focus，宿主 2s 后移除） */
  focus?: boolean
}>()

const run = useRunStore()
const status = computed<string>(() => run.nodeStatus[props.id] ?? 'idle')
const stClass = computed(() => (status.value === 'idle' ? '' : `st-${status.value}`))
/** 副标题（M-B2 迁移收口）：render.summaryRules 分型模板 → render.summary 常量 → 旧 schema.summary（字符串/函数）回退链 */
const sub = computed(() => renderSummary(props.schema, props.gnode.data))
const health = computed(() => String(props.gnode.data.health ?? ''))
/** I3：实例详情 DAG 的 attempt 徽标（>1 时展示，注入自 _attempt） */
const attempt = computed(() => Number(props.gnode.data._attempt ?? 0))
const healthColor = computed(() =>
  health.value === 'fail' ? 'var(--danger)' : health.value === 'warn' ? 'var(--warn)' : 'var(--success)')
const blind = computed(() => props.gnode.data.blind === true)
/** 动态分支端点（条件分支/Switch 等）：每分支独立输出 Handle；
 * 端点合一：静态具名输出口（schema.outputs，如 endpoint_select 的 sourceRef/targetRef）归一走同一渲染路径 */
/* Task 12（§3.6）ports memo：memo 实例随 schema 引用重建（schema 双源切换后不残留陈旧缓存），
 * 同 schema 下按 schema type + data JSON 摘要命中。真实收益：profile 源下 data 引用换新但
 * 深相等时命中，避免 Inspector 编辑等场景重复构建端口数组；拖拽帧不经过此路径（position
 * 变更不触发该 computed）。缓存随组件实例创建/卸载回收，无全局泄漏 */
const portsOf = computed(() => {
  const s = props.schema
  return s.ports ? memoPorts((_sid, data) => s.ports!(data)) : null
})
const ports = computed(() => portsOf.value?.(props.schema.type, props.gnode.data) ?? props.schema.outputs ?? [])
/** W1 必填完整性：required 字段在当前分型下为空 → 画布「未配置」角标（title 列缺失项，与校验面板/保存闸门共用判定） */
const missing = computed(() => requiredMissing(props.schema, props.gnode.data))
/** D3 版本角标：componentRef.version（存量未回填/未注入文档无 ref 则不显示） */
const refVersion = computed(() => {
  const ref = props.gnode.data.componentRef as { version?: unknown } | undefined
  const v = ref?.version
  return typeof v === 'number' && Number.isInteger(v) && v > 0 ? v : 0
})
/** Task 15（§4.3/§4.4）引用角标实时刷新：spec 源已发布版本号高于引用版本 → 黄色角标。
 *  比对基准是 spec 骨架下发的 publishedVersion（发布版本号），非 specVersion（声明格式版本字符串）。
 *  服务降级/未加载/旧骨架（缺 publishedVersion）一律不亮黄标，避免脏缓存误导。
 *  component:published 广播 → componentStore.invalidate 重建 specMap → 本 computed 随引用
 *  自动重算，无需画布重挂载（§4.4 失效闭环）。 */
const compStore = useComponentStore()
const publishedVersion = computed(() => {
  if (!compStore.loaded || compStore.degraded) return 0
  const pv = compStore.getSpec(props.schema.type)?.publishedVersion
  return typeof pv === 'number' && Number.isInteger(pv) && pv > 0 ? pv : 0
})
const refBehind = computed(() => publishedVersion.value > refVersion.value)
/** pin 档钉住标记（后端写 ref.pinned=true）：角标 title 提示，不改配色（钉住属版本决策展示） */
const refPinned = computed(
  () => (props.gnode.data.componentRef as { pinned?: unknown } | undefined)?.pinned === true)
const refTitle = computed(() => {
  const base = `组件版本 v${refVersion.value}（componentRef）`
  if (!refBehind.value) return refPinned.value ? `${base}，已钉住` : base
  const behind = `，有新版本 v${publishedVersion.value} 可用${refPinned.value ? '（已钉住）' : ''}`
  return base + behind
})
/** Task 5 血缘来源体系：sources 仅 design（无运行佐证）→「未验」角标（注入自 unverified） */
const unverified = computed(() => props.gnode.data.unverified === true)
/** Task 7 血缘临时表标记：tmpFlag=true（注入自 tmp）→ 虚线边框（对齐 dep_design 虚线语义） */
const tmpNode = computed(() => props.gnode.data.tmp === true)
/** 设备形态：拓扑视角专用（主机/交换机/服务器/中间件 logo 图标卡片） */
const isDevice = computed(() => props.schema.shape === 'device')
const art = computed(() => NODE_ART[props.schema.type] ?? NODE_ART_FALLBACK)
</script>

<template>
  <!-- 设备形态：图标卡片（图标在上 SVG currentColor，名称/组件地址在下） -->
  <div v-if="isDevice" class="gnode gnode-device" :class="[stClass, { selected, blind, 'st-error': hasError, 'error-focus': focus }]">
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
  <div v-else-if="ports.length" class="gnode gnode-branch" :class="[stClass, { selected, blind, 'st-error': hasError, 'error-focus': focus }]">
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
      <span v-if="refVersion" class="n-ref" :class="{ 'n-ref-behind': refBehind }" :title="refTitle">v{{ refVersion }}</span>
    </div>
    <div v-for="p in ports" :key="p.id" class="nb-row">
      <span class="nb-label" :title="p.label">{{ p.label }}</span>
      <Handle type="source" :id="p.id" :position="Position.Right" />
    </div>
  </div>

  <!-- 普通节点：单输入单输出 -->
  <div v-else class="gnode" :class="[stClass, { selected, blind, tmp: tmpNode, 'st-error': hasError, 'error-focus': focus }]">
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
    <span v-if="refVersion" class="n-ref" :class="{ 'n-ref-behind': refBehind }" :title="refTitle">v{{ refVersion }}</span>
    <span v-if="unverified" class="n-unv" title="未验证：仅设计态血缘，暂无运行实例佐证">未验</span>
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
/* D3 版本角标（左下角悬浮，避开左上 n-attempt / 右上 n-miss；复用 n-attempt 视觉语言） */
.gnode .n-ref{position:absolute;bottom:-8px;left:-8px;z-index:2;background:var(--primary,#2563eb);color:#fff;font-size:9.5px;font-weight:700;border-radius:999px;padding:1px 5px;border:2px solid #fff;box-shadow:0 1px 3px rgba(15,23,42,.25);pointer-events:auto}
/* Task 15（§4.3）：spec 源发布版本高于引用版本 → 黄色角标（有新版本可用；琥珀对齐 n-unv） */
.gnode .n-ref.n-ref-behind{background:var(--warn,#d97706)}
/* Task 5 血缘「未验证」角标（右下角悬浮，避开左下 n-ref / 右上 n-miss；琥珀色对齐 dep_design 边） */
.gnode .n-unv{position:absolute;bottom:-8px;right:-8px;z-index:2;background:#d97706;color:#fff;font-size:9.5px;font-weight:700;border-radius:999px;padding:1px 5px;border:2px solid #fff;box-shadow:0 1px 3px rgba(15,23,42,.25);pointer-events:auto;cursor:help}
/* Task 7 血缘临时表：虚线边框（对齐 dep_design 虚线语义；0,2,0 特异性覆盖 theme.css .gnode 实线边框） */
.gnode.tmp{border-style:dashed}
/* Task 10（§3.3）：校验错误红描边（!important 压过 theme.css .gnode / .st-fail 同特异性边框） */
.gnode.st-error{border-color:#dc2626!important;box-shadow:0 0 0 1.5px rgba(220,38,38,.28)}
/* Task 10：一键定位高亮——outline + 右上角感叹角标（脉冲 2s，宿主 setTimeout 移除类） */
.gnode.error-focus{outline:2.5px solid #dc2626;outline-offset:3px}
.gnode.error-focus::after{content:'!';position:absolute;top:-9px;right:-9px;z-index:4;width:17px;height:17px;border-radius:50%;background:#dc2626;color:#fff;font-size:11px;font-weight:700;line-height:17px;text-align:center;border:2px solid #fff;box-shadow:0 1px 4px rgba(15,23,42,.3);animation:ef-pulse .9s ease-in-out infinite;pointer-events:none}
@keyframes ef-pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.18)}}

</style>
