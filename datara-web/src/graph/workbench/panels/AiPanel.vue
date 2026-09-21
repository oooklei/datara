<script setup lang="ts">
import { computed, ref } from 'vue'
import { useGraphStore } from '../../../stores/graph'

const store = useGraphStore()
const input = ref('')
const msgs = ref<{ role: 'user' | 'ai'; text: string }[]>([
  { role: 'ai', text: '我是画布 AI 助手（mock）。可以让你：分析当前图结构、给出配置建议、解释校验问题。点击「分析当前图」试试。' },
])

const stats = computed(() => {
  const doc = store.doc
  if (!doc) return null
  const byType: Record<string, number> = {}
  doc.nodes.forEach((n) => { byType[n.type] = (byType[n.type] ?? 0) + 1 })
  return { nodes: doc.nodes.length, edges: doc.edges.length, byType }
})

function send() {
  const q = input.value.trim()
  if (!q) return
  msgs.value.push({ role: 'user', text: q })
  input.value = ''
  msgs.value.push({
    role: 'ai',
    text: `（mock 回复）关于「${q}」：建议先运行「校验」确认结构合法，再在右侧属性面板完善关键参数。真实接入 aiService 后此回复由后端生成。`,
  })
}

function analyze() {
  const s = stats.value
  if (!s) return
  const detail = Object.entries(s.byType).map(([t, c]) => `${t}×${c}`).join('、')
  msgs.value.push({
    role: 'ai',
    text: `当前图：${s.nodes} 个节点 / ${s.edges} 条边（${detail}）。建议：1) 所有任务节点配置关键参数；2) 使用「自动布局」规整排布；3) 校验通过后保存生成新版本。`,
  })
}
</script>

<template>
  <div style="display:flex;flex-direction:column;gap:8px">
    <div
      v-for="(m, i) in msgs" :key="i"
      :style="{
        alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
        background: m.role === 'user' ? 'var(--primary-light)' : 'var(--bg)',
        color: 'var(--text)',
        padding: '7px 10px', borderRadius: '8px', maxWidth: '92%', fontSize: '12px', lineHeight: 1.6,
      }"
    >{{ m.text }}</div>
    <div style="display:flex;gap:6px;margin-top:4px">
      <button
        style="border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:5px 10px;font-size:12px;cursor:pointer"
        @click="analyze"
      >分析当前图</button>
    </div>
    <div style="display:flex;gap:6px">
      <input
        v-model="input" placeholder="输入问题…"
        style="flex:1;border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 9px;font-size:12px;outline:none"
        @keydown.enter="send"
      />
      <button
        style="border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:5px 12px;font-size:12px;cursor:pointer"
        @click="send"
      >发送</button>
    </div>
  </div>
</template>
