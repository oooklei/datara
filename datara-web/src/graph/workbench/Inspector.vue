<script setup lang="ts">
/**
 * Inspector 属性面板（F60 六区块 + F61 页面化入口）。
 * 结构（§8.2）：标题(C编号徽标+页面按钮) → ①输入 ②输出 ③参数 ④条件 ⑤限定约束 ⑥排除（框架级折叠面板）
 * → 业务配置(schema.form) → 关联信息。
 * 六区块已抽为 fields/SixBlocks.vue 共享组件（治理设计 §12.2 禁双实现漂移）——Inspector 与
 * DropConfigDialog 共用同一实现：弹窗期同样呈现六区块，且①输入的值域取自上游②输出注册表。
 * 六区块数据存 node.data.inputs/outputs/params/condition/constraints/exclude；
 * 老节点无字段时显示默认空值（缺省懒初始化：首次编辑才落键），向后兼容既有裁定。
 */
import { computed, onMounted, ref } from 'vue'
import type { GNode } from '../model'
import type { ViewProfile } from '../profiles/types'
import { useGraphStore } from '../../stores/graph'
import { useAuthStore } from '../../stores/auth'
import { useFloatStore } from '../../stores/float'
import FormSections from './fields/FormSections.vue'
import SixBlocks from './fields/SixBlocks.vue'
import { createFieldCtx } from './fields/fieldCtxFactory'

const props = defineProps<{
  node: GNode | null
  profile: ViewProfile
  /** Task 10（§3.3）：选中节点的校验错误 message 列表（optional，向后兼容；非空时顶部红卡展示） */
  nodeErrors?: string[]
}>()

const auth = useAuthStore()
const floatStore = useFloatStore()
/** 系统权限降级（M15）：只读角色锁定编辑 */
const effMode = computed(() => (props.profile.mode === 'edit' && !auth.canEdit ? 'view' : props.profile.mode))
const emit = defineEmits<{ (e: 'delete', id: string): void }>()

const graphStore = useGraphStore()

function markDirty() { graphStore.markDirty() }

/* ================= B3 F0 + F1：FieldCtx 组装收敛到共享工厂（§12.2 禁双实现漂移） =================
   Inspector 传画布选中节点；DropConfigDialog 传未落画布的虚拟节点——同一套候选状态/动态联动/脚本互通 */
const rootEl = ref<HTMLElement | null>(null)
const bundle = createFieldCtx({
  node: computed(() => props.node),
  nodeTypes: props.profile.nodeTypes,
  markDirty,
  rootEl,
})
const { schema, visibleForm, missingLabels, onSet, upd, focusTarget } = bundle
const fieldCtx = bundle.ctx

/* 六区块实例：业务表单 `f:{key}` 变量引用转交其弹窗（保持弹窗唯一实例） */
const six = ref<InstanceType<typeof SixBlocks> | null>(null)
function openVarDialog(target: string) { six.value?.openVarDialog(target) }

/* ================= F61 页面化入口（schema.page → 浮窗挂载，props {node, doc}） ================= */
const page = computed(() => schema.value?.page)
const pageVisible = computed(() =>
  !!page.value && (!page.value!.mode || page.value!.mode === effMode.value))
function openPage() {
  const p = page.value
  if (!p || !props.node || !graphStore.doc) return
  floatStore.open({
    id: `page_${props.node.id}`,
    title: p.title,
    x: 300 + (floatStore.floats.length % 3) * 30,
    y: 80 + (floatStore.floats.length % 3) * 30,
    w: p.w ?? 540,
    h: p.h ?? 400,
    minimized: false,
    comp: p.comp,
    props: { node: props.node, doc: graphStore.doc },
  })
}

/* ================= 六区块状态/数据/表达式/变量弹窗已迁至 fields/SixBlocks.vue ================= */

/* ---------- 以下共享候选状态/动态联动/上游枚举/探测联动已收敛至 fields/fieldCtxFactory.ts ---------- */

/* ---------- upstream-ref 节点输出枚举 ---------- */

/* ---------- C37 探测候选联动 ---------- */
/** 探测依赖的源端库表树拉取收敛到 syncDynamicOptions（见下）：签名 watch 含 dsRows.value.length，
   dsRows 晚就绪（onMounted 多个 await 后赋值）时签名变化重触发补拉，避免首触发 resolveDsId 失败的错误提示粘连 */

/* topic-select：经 dsRef 字段值解析 ds_id → 枚举 topic；失败候选置空 + 行内错误（枚举缓存与访问器在 FieldRenderer） */

/* dir-select：运行时节点（节点名解析 id）→ SFTP 目录懒加载（面包屑导航），选中写回完整路径 */

onMounted(() => { void bundle.loadShared() })

/** 视角语义关联信息（表→已绑规则 / 规则→绑定表等） */
const related = computed(() =>
  props.node && schema.value?.related && graphStore.doc
    ? schema.value.related(props.node, graphStore.doc)
    : [])

/* ---------- 六区块头部摘要已迁至 SixBlocks.vue ---------- */
</script>

<template>
  <aside ref="rootEl" class="wb-inspector">
    <template v-if="node && schema">
      <div class="insp-title">
        <span class="p-ico" :style="{ background: schema.color, width: '22px', height: '22px', borderRadius: '5px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: '11px' }">{{ schema.icon }}</span>
        {{ schema.label }}属性
        <span v-if="schema.code" class="insp-code">{{ schema.code }}</span>
        <span class="insp-spacer" />
        <button v-if="pageVisible" class="pg-btn" title="打开页面化展示（F61）" @click="openPage">页面</button>
        <button v-if="effMode === 'edit'" class="pg-btn pg-del" title="删除该节点" @click="emit('delete', node.id)">删除</button>
      </div>
      <!-- Task 10（§3.3）：校验错误卡片——选中节点在错误模型中有 node 类错误时列出全部 message -->
      <div v-if="nodeErrors?.length" class="insp-errs">
        <div class="insp-errs-cap">校验错误（{{ nodeErrors.length }}）</div>
        <div v-for="(m, i) in nodeErrors" :key="i" class="insp-errs-item">{{ m }}</div>
      </div>
      <div v-if="missingLabels.length" class="insp-miss">必填未配置：{{ missingLabels.join('、') }}</div>
      <div class="insp-form">
        <div class="field">
          <label>节点名称</label>
          <input :value="String(node.data.name ?? '')" :disabled="effMode === 'view'" @change="upd('name', $event)" />
        </div>

        <!-- F60 六区块（①输入 ②输出 ③参数 ④条件 ⑤限定约束 ⑥排除）：框架级标准，与业务表单正交 -->
        <SixBlocks
          ref="six"
          :node="node"
          :ctx="fieldCtx"
          :readonly="effMode === 'view'"
          :mark-dirty="markDirty"
        />

        <!-- 业务配置（schema.form 经 FormSections 分组 → FieldRenderer 按 FieldKind 9 基元渲染；showIf 条件展示联动） -->
        <FormSections
          :form="visibleForm" :data="node.data" :mode="effMode" :node-id="node.id"
          :ctx="fieldCtx" :profile="profile"
          @set="onSet" @dirty="markDirty" @open-var-dialog="openVarDialog" @focus-target="focusTarget"
        />
        <!-- 视角语义关联信息（schema.related 注入） -->
        <div v-if="related.length" class="field" style="margin-top:12px">
          <label>关联信息</label>
          <div class="rel-list">
            <div v-for="(it, i) in related" :key="i" class="rel-item">
              <span v-if="it.color" class="rel-dot" :style="{ background: it.color }" />
              <span>{{ it.text }}</span>
            </div>
          </div>
        </div>
        <div style="font-size:10.5px;color:var(--text-3);margin-top:14px">
          ID: <span class="mono">{{ node.id }}</span> · 类型: <span class="mono">{{ node.type }}</span>
        </div>
      </div>
    </template>
    <div v-else class="insp-empty">
      <div class="ia-art" aria-hidden="true">
        <span class="ia-node"></span>
        <span class="ia-line"></span>
        <span class="ia-node ia-b"></span>
      </div>
      <div class="ia-title">未选中节点</div>
      <div class="ia-sub">点击画布中的节点，在此查看 / 编辑属性</div>
      <div v-if="effMode === 'edit'" class="ia-hint">从左侧组件库拖入节点，开始编排任务流</div>
      <div class="ia-keys">
        <span><kbd>Del</kbd> 删除</span>
        <span><kbd>Ctrl+F</kbd> 搜索</span>
        <span><kbd>Ctrl+Z</kbd> 撤销</span>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.pg-del{border-color:var(--danger);color:var(--danger)}
.pg-del:hover{border-color:var(--danger);color:#fff;background:var(--danger)}
/* C 编号徽标 + 页面按钮（F61） */
.insp-code{font-size:9.5px;font-weight:700;color:var(--primary);background:var(--primary-light);border-radius:4px;padding:1px 5px;margin-left:4px}
/* W1 必填完整性：缺失提示条 + 必填红星 */
.insp-miss{margin:0 12px;padding:5px 9px;background:rgba(217,119,6,.08);border:1px solid rgba(217,119,6,.35);border-radius:var(--radius-sm);font-size:11px;color:#b45309}
/* Task 10（§3.3）：顶部校验错误卡片（红色系，与画布 st-error 同源配色） */
.insp-errs{margin:0 12px 8px;padding:6px 9px;background:rgba(220,38,38,.07);border:1px solid rgba(220,38,38,.4);border-radius:var(--radius-sm)}
.insp-errs-cap{font-size:11px;font-weight:700;color:#dc2626;margin-bottom:3px}
.insp-errs-item{font-size:11.5px;color:#b91c1c;line-height:1.5}
.req-star{color:var(--danger);margin-left:2px;font-weight:700}
.insp-spacer{flex:1}
.pg-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:2px 8px;font-size:11px;cursor:pointer;color:var(--text-2)}
.pg-btn:hover{border-color:var(--primary);color:var(--primary);background:var(--primary-light)}
/* 六区块样式（.blk* / .up-* / .ref-* / .expr-row / .var-* / .bool-row）已迁至 fields/SixBlocks.vue */
.rel-list{display:flex;flex-direction:column;gap:4px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px 9px;max-height:180px;overflow:auto}
.rel-item{display:flex;align-items:flex-start;gap:6px;font-size:11.5px;line-height:1.5;color:var(--text-2);word-break:break-all}
.rel-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;margin-top:4px}
</style>
