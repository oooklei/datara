<script setup lang="ts">
/**
 * Task 23（§2.4/§8.2）保存 409 三方逐项 diff 对话框。
 * 「我的（本地）/ 远端（他端会话）/ 基准（上次保存）」三列逐项对比；每项可选采纳我的或远端
 * （默认遵循 threeWayDiff.adopt：单侧改动→采纳改动侧，双侧改动→采纳远端）；
 * 确认按 mergeThreeWay 合并出待保存 spec，emit('resolve', merged) 交父组件保存——
 * 对话框自身不落库（父组件取最新 draftRev 保存；期间远端再变而再遇 409 时由父组件重进冲突流程重开本框）。
 */
import { computed, ref, watch } from 'vue'
import { threeWayDiffItems, mergeThreeWay, type DiffSide, type ThreeWayItem } from './threeWayDiff'

const props = defineProps<{
  modelValue: boolean
  mine: Record<string, unknown> | null
  remote: Record<string, unknown> | null
  base: Record<string, unknown> | null
  /** 父组件保存中（确认按钮 loading，防重复提交） */
  saving?: boolean
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'resolve', merged: Record<string, unknown>): void
}>()

const items = computed<ThreeWayItem[]>(() => threeWayDiffItems(props.mine, props.remote, props.base))

/** 逐项采纳结果：打开或 diff 输入变化时按默认重置（防止再次 409 重开时残留上轮 decisions） */
const decisions = ref<Record<string, DiffSide>>({})
watch(
  () => [props.modelValue, props.mine, props.remote, props.base] as const,
  ([open]) => {
    if (!open) return
    const next: Record<string, DiffSide> = {}
    for (const it of threeWayDiffItems(props.mine, props.remote, props.base)) next[it.path] = it.adopt
    decisions.value = next
  },
  { immediate: true },
)

const bothChangedCount = computed(() => items.value.filter((it) => it.mineChanged && it.remoteChanged).length)

/** undefined → '(无)'；其余单行 JSON（长内容换行 + 单元格内滚动） */
function fmt(v: unknown): string {
  if (v === undefined) return '(无)'
  try { return JSON.stringify(v) ?? String(v) } catch { return String(v) }
}

function setAdopt(path: string, side: DiffSide): void {
  decisions.value = { ...decisions.value, [path]: side }
}

function onConfirm(): void {
  emit('resolve', mergeThreeWay(props.mine, items.value, decisions.value))
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="保存冲突 · 三方逐项对比"
    width="920px"
    append-to-body
    :close-on-click-modal="false"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="cfd-tip">
      草稿已被其他会话修改，请逐项选择采纳方向，确认后按合并结果保存。
      默认：仅一侧改动 → 采纳改动侧；两侧均改 → 采纳远端。也可改用「以本地内容覆盖远端 / 放弃本地并载入远端」。
      <span v-if="bothChangedCount" class="cfd-both">双方均改：{{ bothChangedCount }} 项</span>
    </div>
    <div class="cfd-head">
      <span>条目</span>
      <span>我的（本地）</span>
      <span>远端（他端会话）</span>
      <span>基准（上次保存）</span>
      <span class="cfd-adopt-col">采纳</span>
    </div>
    <div class="cfd-body">
      <div
        v-for="(it, i) in items" :key="it.path" class="cfd-row"
        :class="{ 'is-both': it.mineChanged && it.remoteChanged }"
      >
        <span class="cfd-path" :title="it.path">{{ it.path }}</span>
        <pre class="cfd-val" :class="{ 'is-changed': it.mineChanged }">{{ fmt(it.mine) }}</pre>
        <pre class="cfd-val" :class="{ 'is-changed': it.remoteChanged }">{{ fmt(it.remote) }}</pre>
        <pre class="cfd-val is-base">{{ fmt(it.base) }}</pre>
        <span class="cfd-adopt-col">
          <label class="cfd-opt"><input type="radio" :name="`cfd-${i}`" :checked="decisions[it.path] === 'mine'" @change="setAdopt(it.path, 'mine')" />我的</label>
          <label class="cfd-opt"><input type="radio" :name="`cfd-${i}`" :checked="decisions[it.path] === 'remote'" @change="setAdopt(it.path, 'remote')" />远端</label>
        </span>
      </div>
      <div v-if="!items.length" class="cfd-empty">当前对比粒度下无逐项差异，确认将直接保存本地内容。</div>
    </div>
    <template #footer>
      <el-button size="small" @click="emit('update:modelValue', false)">取消</el-button>
      <el-button size="small" type="primary" :loading="saving" data-testid="cfd-confirm" @click="onConfirm">合并并保存</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.cfd-tip{font-size:12px;color:var(--text-2);line-height:1.7;margin-bottom:10px}
.cfd-both{display:inline-block;margin-left:8px;padding:1px 8px;border-radius:10px;font-size:11px;color:#b45309;background:rgba(217,119,6,.1);border:1px solid rgba(217,119,6,.35)}
.cfd-head,.cfd-row{display:grid;grid-template-columns:120px 1fr 1fr 1fr 96px;gap:8px;align-items:start}
.cfd-head{font-size:11px;font-weight:700;color:var(--text-2);padding:0 2px 6px;border-bottom:1px solid var(--border)}
.cfd-body{max-height:420px;overflow:auto;display:flex;flex-direction:column;gap:8px}
.cfd-row{padding:4px 2px;border-bottom:1px dashed var(--border)}
.cfd-row.is-both{background:rgba(220,38,38,.04);border-radius:var(--radius-sm)}
.cfd-path{font-size:11px;font-weight:600;color:var(--text-2);word-break:break-all;padding-top:5px}
.cfd-val{margin:0;font-size:10.5px;line-height:1.5;font-family:ui-monospace,Menlo,Consolas,monospace;white-space:pre-wrap;word-break:break-all;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);padding:4px 6px;max-height:96px;overflow:auto;color:var(--text-2)}
.cfd-val.is-changed{color:var(--text-2);font-weight:600;border-color:var(--border-strong)}
.cfd-val.is-base{color:var(--text-3)}
.cfd-adopt-col{display:flex;flex-direction:column;gap:4px;padding-top:4px}
.cfd-opt{display:flex;align-items:center;gap:4px;font-size:11px;color:var(--text-2);cursor:pointer;white-space:nowrap}
.cfd-empty{padding:18px 0;text-align:center;font-size:12px;color:var(--text-3)}
</style>
