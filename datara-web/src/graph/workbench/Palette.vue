<script setup lang="ts">
import { computed, ref } from 'vue'
import type { NodeSchema, ViewProfile } from '../profiles/types'

const props = defineProps<{ profile: ViewProfile }>()

interface PalRow { schema: NodeSchema; disabled: boolean; phase?: string }

const kw = ref('')
const folded = ref<Record<string, boolean>>({})

/* palette 分组兼容两种写法：types: string[]（老）与 items: PaletteItem[]（新，支持灰置 phase） */
const cats = computed(() =>
  props.profile.palette.map((c) => {
    const k = kw.value.trim().toLowerCase()
    const match = (s: NodeSchema) =>
      !k ||
      s.label.toLowerCase().includes(k) ||
      (s.desc ?? '').toLowerCase().includes(k) ||
      s.type.toLowerCase().includes(k)
    const fromItems = (c.items ?? []).map((i) => ({ type: i.type, disabled: !!i.disabled, phase: i.phase }))
    const fromTypes = (c.types ?? []).map((t) => ({ type: t, disabled: false, phase: undefined as string | undefined }))
    const seen = new Set<string>()
    const rows: PalRow[] = []
    for (const it of [...fromItems, ...fromTypes]) {
      if (seen.has(it.type)) continue
      seen.add(it.type)
      const s = props.profile.nodeTypes[it.type]
      if (s && match(s)) rows.push({ schema: s, disabled: it.disabled, phase: it.phase })
    }
    return { name: c.name, rows }
  }).filter((c) => c.rows.length > 0),
)

function onDragStart(e: DragEvent, row: PalRow) {
  if (row.disabled) return
  e.dataTransfer?.setData('datara/node-type', row.schema.type)
  if (e.dataTransfer) e.dataTransfer.effectAllowed = 'copy'
}
</script>

<template>
  <aside class="wb-palette">
    <div class="pal-search">
      <input v-model="kw" placeholder="搜索组件" style="width:100%;border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 9px;font-size:12.5px;outline:none" />
    </div>
    <div class="pal-list">
      <div v-for="cat in cats" :key="cat.name" class="pal-cat" :class="{ fold: folded[cat.name] }">
        <div class="pal-cat-head" @click="folded[cat.name] = !folded[cat.name]">
          <span class="arrow">▼</span>{{ cat.name }}
          <span class="cnt">{{ cat.rows.length }}</span>
        </div>
        <div class="pal-items">
          <div
            v-for="row in cat.rows" :key="row.schema.type"
            class="pal-item" :class="{ disabled: row.disabled }"
            :title="row.disabled ? `${row.schema.desc ?? row.schema.label}（${row.phase ?? '后续增量注册'}）` : row.schema.desc"
            :draggable="!row.disabled"
            @dragstart="onDragStart($event, row)"
          >
            <div class="p-ico" :style="{ background: row.schema.color }">{{ row.schema.icon }}</div>
            <div style="min-width:0">
              <div class="p-name">
                {{ row.schema.label }}
                <span v-if="row.schema.code" class="p-code">{{ row.schema.code }}</span>
              </div>
              <!-- F56c R5：常规项描述走 hover tooltip（title 已挂），仅灰置项保留说明行 -->
              <div v-if="row.disabled" class="p-desc">灰置 · {{ row.phase ?? '后续增量注册' }}</div>
            </div>
          </div>
        </div>
      </div>
      <div v-if="cats.length === 0" style="padding:20px;text-align:center;color:var(--text-3);font-size:12px">无匹配组件</div>
    </div>
  </aside>
</template>
