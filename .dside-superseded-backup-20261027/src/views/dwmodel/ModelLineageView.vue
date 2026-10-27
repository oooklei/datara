<template>
  <main class="lineage-page" aria-label="模型血缘" data-lineage>
    <header class="page-head">
      <div><h1>模型血缘</h1><p>声明血缘与运行血缘合并视图，下游影响分析。</p></div>
    </header>

    <p v-if="error" role="alert" class="error" data-error>{{ error }}</p>
    <p v-if="busy" role="status" data-loading>正在加载…</p>
    <p v-else-if="!modelId" class="empty" data-empty>请先在列表中选择一个模型。</p>

    <template v-else>
      <section class="card" data-lineage-graph>
        <header><h2>血缘图</h2><p class="sources">声明 {{ graph?.sources.declared ?? 0 }} · 运行 {{ graph?.sources.runtime ?? 0 }}</p></header>
        <p v-if="!graph || graph.nodes.length === 0" class="empty" data-lineage-empty>暂无血缘节点</p>
        <svg v-else :viewBox="`0 0 ${canvas.w} ${canvas.h}`" :width="canvas.w" :height="canvas.h" class="canvas" data-lineage-canvas>
          <line
            v-for="edge in graph.edges" :key="`${edge.from}-${edge.to}`"
            :x1="nodePos(edge.from).x" :y1="nodePos(edge.from).y"
            :x2="nodePos(edge.to).x" :y2="nodePos(edge.to).y"
            :stroke="edge.kind === 'runtime' ? 'var(--border-strong)' : 'var(--primary)'" stroke-width="1.5" data-lineage-edge
          />
          <g v-for="node in graph.nodes" :key="node.id" :transform="`translate(${nodePos(node.id).x},${nodePos(node.id).y})`" data-lineage-node>
            <rect :x="-60" :y="-16" width="120" height="32" rx="var(--radius)" :fill="node.kind === 'ext' ? 'var(--sidebar)' : 'var(--card)'" :stroke="node.kind === 'ext' ? 'var(--border-strong)' : 'var(--primary)'" />
            <text text-anchor="middle" dominant-baseline="middle" fill="var(--text)">{{ node.label }}</text>
          </g>
        </svg>
      </section>

      <section class="card" data-impact>
        <header><h2>下游影响</h2></header>
        <p v-if="!impactRows.length" class="empty" data-impact-empty>无下游依赖</p>
        <table v-else data-impact-list>
          <thead><tr><th>模型 ID</th><th>编码</th><th>名称</th><th>路径</th></tr></thead>
          <tbody>
            <tr v-for="row in impactRows" :key="row.modelId" :data-impact-id="row.modelId">
              <td>{{ row.modelId }}</td><td><code>{{ row.code }}</code></td>
              <td>{{ row.name }}</td><td>{{ row.path || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </template>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { modelApi, type ModelLineageGraph, type ModelImpactRow } from '../../services/rebuild/modelApi'

const props = defineProps<{ modelId?: number }>()
const route = useRoute()
const routeModelId = () => {
  const raw = route?.query?.modelId
  const value = Number(Array.isArray(raw) ? raw[0] : raw)
  return Number.isFinite(value) && value > 0 ? value : undefined
}
const modelId = computed(() => props.modelId ?? routeModelId())

const graph = ref<ModelLineageGraph | null>(null)
const impactRows = ref<ModelImpactRow[]>([])
const busy = ref(false)
const error = ref('')
const message = (cause: unknown) => cause instanceof Error ? cause.message : String(cause)

const canvas = { w: 960, h: 320 }
const nodePos = (id: string) => {
  const nodes = graph.value?.nodes ?? []
  const index = nodes.findIndex((node) => node.id === id)
  if (index < 0) return { x: 0, y: 0 }
  const step = canvas.w / Math.max(nodes.length, 1)
  return { x: step * (index + 0.5), y: canvas.h / 2 }
}

async function load() {
  const id = modelId.value
  if (!id) { graph.value = null; impactRows.value = []; return }
  busy.value = true; error.value = ''
  try {
    const [lineage, impact] = await Promise.all([modelApi.lineage(id), modelApi.impact(id)])
    graph.value = lineage
    impactRows.value = impact.list
  } catch (cause) { error.value = message(cause); graph.value = null; impactRows.value = [] }
  finally { busy.value = false }
}

onMounted(load)
</script>

<style scoped>
.lineage-page{max-width:1440px;margin:auto;padding:32px 24px;color:var(--text)}.page-head h1{margin:0}.page-head p{margin:6px 0 0;color:var(--text-2)}.error{color:var(--danger)}.empty{color:var(--text-3)}.card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius-lg);padding:18px;margin-top:18px}.card header{display:flex;align-items:center;justify-content:space-between}.card h2{margin:0}.sources{color:var(--text-2);margin:0}.canvas{margin-top:14px;max-width:100%}table{width:100%;border-collapse:collapse;margin-top:14px}th,td{text-align:left;padding:10px;border-bottom:1px solid var(--border)}th{color:var(--text-2)}
</style>
