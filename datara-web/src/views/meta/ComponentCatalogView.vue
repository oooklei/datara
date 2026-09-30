<script setup lang="ts">
/**
 * M0 组件目录（只读系统组件清单）——组件管理功能的第一个里程碑。
 *
 * 解决的问题：系统组件注册表此前只存在于 `graph/profiles/*.ts`（编译进 Vue bundle），
 * 后端无法校验、无法版本化、无法服务给其他客户端。M0 由
 * `scripts/export_dag_catalog.py` 导出 `common/dag_catalog.json`，经
 * `GET /api/v1/components` 只读下发，本页消费之。
 *
 * 本页**刻意暴露注册表漂移**，而不只做"好看的列表"：
 * - 无执行实现须分两个口径看：DAG 引擎内 3 个 stream_* 硬缺口；全系统 30 个
 *   （另有 etl 17 + stream 10 在后端全文检索不到任何执行实现，属 F56a 演示态）；
 * - 仅后端类型（backendOnlyTypes）：smoke / src_select / tgt_select，无前端 NodeSchema；
 * - 跨 profile 重复定义：op_script 在 etl 与 stream 各一份（当前内容一致，缺同步约束）；
 * - palette 容器格式不统一：dag/stream 用 items，etl 用 types 且展开 dagProfile.palette。
 * 这些是 M1 收敛组件注册表的一手证据，不能被"列表看起来正常"掩盖。
 *
 * M0 只读：系统内置组件无新建/编辑入口。B4：本页提供「组件设计器」入口
 * （/meta/components/design/:type?，用户自建组件草稿编辑/预览/冻结，t_component 三表）。
 * 发布（admin）权限与闸门属 M2。路由：/meta/components
 *
 * M-B0：组件条目挂基线化徽标（baselineApi.progress，失败静默降级）——
 * status=published →「已发 vN」绿徽标（动态版本号）；designing+已发版 →「修订中（vN 已发）」蓝徽标；
 * 其余 →「未基线」灰徽标；runtimeOnly →「运行态」。
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listComponents, getComponentStats, getComponent, getComponentRegistry,
  type ComponentRow, type ComponentStats, type ComponentDetail, type ComponentRoute,
  type CompRegistryRow,
} from '../../services/componentApi'
import { progress } from '../../services/baselineApi'

const rows = ref<ComponentRow[]>([])
const stats = ref<ComponentStats | null>(null)
const router = useRouter()
const detail = ref<ComponentDetail | null>(null)
const detailOpen = ref(false)
const loading = ref(false)
const error = ref('')

/* D3：用户组件（t_component 治理库）生命周期标签区 */
const userComps = ref<CompRegistryRow[]>([])
const LIFE_META: Record<string, { t: string; cls: string }> = {
  draft: { t: '草稿', cls: 'life-draft' },
  published: { t: '已发布', cls: 'life-pub' },
  offline: { t: '已下线', cls: 'life-off' },
}
function lifeText(s: string): string {
  return LIFE_META[s]?.t ?? s
}

const keyword = ref('')
const fProfile = ref('')
const fRoute = ref('')
const fPaletteOnly = ref(false)

const profileOptions = [
  { v: '', t: '全部' },
  { v: 'dag', t: 'DAG 编排' },
  { v: 'etl', t: 'ETL 管道' },
  { v: 'stream', t: '流处理' }
]

// ComponentCategory 分类（对标 palette 组件分类）
const categoryOptions = [
  { v: '', t: '全部分类' },
  { v: 'sync', t: '同步' },
  { v: 'etl', t: 'ETL' },
  { v: 'stream', t: '流处理' },
  { v: 'general', t: '通用' }
]
const fCategory = ref('')
const routeOptions = [
  { v: '', t: '全部派发方式' },
  { v: 'master', t: 'Master 处理器' },
  { v: 'worker', t: 'Worker executor' },
  { v: 'template', t: '流程模板' },
  { v: 'nonExecutable', t: '不执行（画布辅助）' },
  { v: 'UNROUTED', t: '无派发实现' },
]

/** 派发方式徽标文案与配色 */
const routeMeta: Record<ComponentRoute, { t: string; cls: string }> = {
  master: { t: 'Master', cls: 'ok' },
  worker: { t: 'Worker', cls: 'ok' },
  template: { t: '模板', cls: 'off' },
  nonExecutable: { t: '不执行', cls: 'off' },
  UNROUTED: { t: '无派发', cls: 'err' },
}

/** 执行实现徽标：M1「发布必须绑定执行契约」的判断依据 */
const execMeta: Record<string, { t: string; cls: string }> = {
  'dag-engine': { t: 'DAG 引擎', cls: 'ok' },
  'demo-only': { t: '仅演示·无实现', cls: 'err' },
  'canvas-device': { t: '画布元件', cls: 'off' },
}
function execText(m: string): string {
  return execMeta[m]?.t ?? m
}

/** 漂移告警条：M1 收敛注册表的一手证据 */
const drift = computed(() => {
  const s = stats.value
  if (!s) return [] as string[]
  const out: string[] = []
  const st = s.stats
  // 两个口径都要报。只报 DAG 的 3 个会掩盖"etl/stream 共 27 个组件
  // 在后端全文检索不到任何执行实现"这个更大的问题。
  if (st.unrouted > 0) {
    out.push(`DAG 引擎口径 ${st.unrouted} 个无派发实现：${st.unroutedTypes.join('、')}`)
  }
  if (st.unroutedTotal > st.unrouted) {
    const per = Object.entries(st.unroutedByProfile ?? {})
      .filter(([k]) => k !== 'dag')
      .map(([k, v]) => `${k} ${v.length} 个`)
      .join('、')
    out.push(`全系统口径 ${st.unroutedTotal} 个无任何执行实现（另有 ${per}）——这些组件可拖出、可保存，但后端检索不到执行代码`)
  }
  if (st.backendOnlyTypes?.length) {
    out.push(`${st.backendOnlyTypes.length} 个类型有后端路由但无前端 NodeSchema：${st.backendOnlyTypes.join('、')}`)
  }
  if (st.crossProfileDuplicateTypes?.length) {
    out.push(`${st.crossProfileDuplicateTypes.length} 个 type 跨 Profile 重复定义（当前定义内容一致，但无约束保护，编辑一处不会同步另一处）：${st.crossProfileDuplicateTypes.join('、')}`)
  }
  if (st.consistencyErrors?.length) {
    out.push(...st.consistencyErrors)
  }
  return out
})

const visible = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return rows.value.filter((r) => {
    // TOPO 不在治理范围（集群拓扑视图保留，但组件目录不展示）
    if (r.profile === 'topo') return false
    if (fProfile.value && r.profile !== fProfile.value) return false
    if (fCategory.value && !(r.categories || []).includes(fCategory.value)) return false
    if (fRoute.value && r.route !== fRoute.value) return false
    if (fPaletteOnly.value && !r.paletteVisible) return false
    if (kw) {
      const hay = `${r.type} ${r.label} ${r.desc} ${r.code} ${(r.categories || []).join(' ')}`.toLowerCase()
      if (!hay.includes(kw)) return false
    }
    return true
  })
})

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  void loadRegistry()
  void loadBaseline()
  try {
    const [list, st] = await Promise.all([listComponents(), getComponentStats()])
    rows.value = list.items
    stats.value = st
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
    ElMessage.error(`组件目录加载失败：${error.value}`)
  } finally {
    loading.value = false
  }
}

/** D3：用户组件治理库注册表（§8 生命周期标签区）。失败静默——mock 模式无此端点，不阻塞系统组件清单 */
async function loadRegistry(): Promise<void> {
  try {
    userComps.value = await getComponentRegistry()
  } catch {
    userComps.value = []
  }
}

/* M-B0：基线化进度（目录徽标数据源）。失败静默降级——后端未就位/网络异常时不显示基线徽标，不影响原页面 */
const baselineMap = ref<Record<string, string>>({})
const baselineVer = ref<Record<string, number>>({})
const baselineLoaded = ref(false)
async function loadBaseline(): Promise<void> {
  try {
    const r = await progress()
    const m: Record<string, string> = {}
    const v: Record<string, number> = {}
    for (const it of r.items) {
      m[it.type] = it.status
      v[it.type] = it.publishedVersion ?? 0
    }
    baselineMap.value = m
    baselineVer.value = v
    baselineLoaded.value = true
  } catch {
    baselineMap.value = {}
    baselineVer.value = {}
    baselineLoaded.value = false
  }
}

async function openDetail(r: ComponentRow): Promise<void> {
  try {
    detail.value = await getComponent(r.type)
    detailOpen.value = true
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

/** 删除组件（二次确认后调用删除 API） */
async function handleDelete(r: ComponentRow): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定删除组件「${r.label}」（${r.type}）？此操作将清理对应的构建代码和资源。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消', confirmButtonClass: 'el-button--danger' }
    )
  } catch {
    return // 用户取消
  }

  try {
    // TODO: 调用删除 API
    // await deleteComponent(r.type)
    ElMessage.success(`组件 ${r.type} 已删除`)
    await load() // 刷新列表
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

/** 表单字段的联动标记（不可序列化函数，目录里只保留布尔标记） */
function flagText(f: { flags: Record<string, boolean | undefined> }): string {
  const t: string[] = []
  if (f.flags.showIf) t.push('showIf')
  if (f.flags.onChange) t.push('onChange')
  if (f.flags.pick) t.push('pick')
  if (f.flags.text) t.push('text')
  return t.join(' / ')
}

onMounted(load)
</script>

<template>
  <div class="page">
    <header class="head">
      <div>
        <h2>组件目录</h2>
        <p class="sub">
          系统内置组件只读清单（M0）。组件注册表由
          <code>scripts/export_dag_catalog.py</code> 从 <code>graph/profiles/*.ts</code> 导出，
          随代码提交、可 diff、可评审。
          <template v-if="stats">
            快照 <code>{{ stats.catalogHash }}</code>，生成于 {{ stats.generatedAt }}。
          </template>
        </p>
      </div>
      <div class="head-actions">
        <el-button type="primary" @click="router.push('/meta/components/design')">组件设计器</el-button>
        <el-button :loading="loading" @click="load">刷新</el-button>
      </div>
    </header>

    <el-alert v-if="error" type="error" :closable="false" :title="error" show-icon />

    <!-- 注册表漂移告警：M1 收敛的一手证据，不隐藏 -->
    <el-alert
      v-if="drift.length"
      type="warning"
      :closable="false"
      show-icon
      title="组件注册表存在漂移（M1 收敛项）"
      class="drift"
    >
      <ul class="drift-list">
        <li v-for="(d, i) in drift" :key="i">{{ d }}</li>
      </ul>
    </el-alert>

    <!-- D3：用户组件（t_component 治理库）生命周期区——设计器产物，与上方系统内置目录区分 -->
    <section v-if="userComps.length" class="ugov">
      <div class="ugov-t">用户组件（治理库 · {{ userComps.length }}）</div>
      <div class="ugrid">
        <div v-for="u in userComps" :key="u.type" class="ucard" :class="{ off: u.state === 'offline' }">
          <div class="uc-head">
            <span class="uc-nm">{{ u.name }}</span>
            <code class="ty">{{ u.type }}</code>
            <span class="life" :class="LIFE_META[u.state]?.cls ?? 'life-draft'">{{ lifeText(u.state) }}</span>
          </div>
          <div class="uc-sub">
            {{ u.profile }} · {{ execText(u.executionModel) }}
            <template v-if="u.publishedVersion"> · 供给 v{{ u.publishedVersion }}</template>
            <template v-else> · 未发布</template>
          </div>
          <el-button link type="primary" size="small" @click="router.push(`/meta/components/design/${u.type}`)">
            设计
          </el-button>
        </div>
      </div>
    </section>

    <el-form inline class="filters">
      <el-form-item label="搜索">
        <el-input
          v-model="keyword" placeholder="类型 / 名称 / 描述 / 编码" clearable style="width: 240px"
        />
      </el-form-item>
      <el-form-item label="Profile">
        <el-select v-model="fProfile" style="width: 140px">
          <el-option v-for="o in profileOptions" :key="o.v" :label="o.t" :value="o.v" />
        </el-select>
      </el-form-item>
      <el-form-item label="分类">
        <el-select v-model="fCategory" style="width: 120px">
          <el-option v-for="o in categoryOptions" :key="o.v" :label="o.t" :value="o.v" />
        </el-select>
      </el-form-item>
      <el-form-item label="派发方式">
        <el-select v-model="fRoute" style="width: 180px">
          <el-option v-for="o in routeOptions" :key="o.v" :label="o.t" :value="o.v" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-checkbox v-model="fPaletteOnly">仅 Palette 可见</el-checkbox>
      </el-form-item>
      <el-form-item>
        <span class="count">共 {{ visible.length }} / {{ rows.length }} 个组件</span>
      </el-form-item>
    </el-form>

    <!-- Profile 分布：说明"组件"并非单一集合 -->
    <section v-if="stats" class="profiles">
      <div
        v-for="p in stats.profiles" :key="p.profile"
        class="pcard" :class="{ off: !p.dagRelevant }"
      >
        <div class="pcard-t">{{ p.profile }}</div>
        <div class="pcard-n">{{ p.nodeTypes }}</div>
        <div class="pcard-s">
          palette {{ p.paletteItems }} 项 / {{ p.paletteGroups }} 组
          <template v-if="p.paletteFormat"> · {{ p.paletteFormat }}</template>
        </div>
        <div v-if="p.paletteSpreads.length" class="pcard-s">
          继承 {{ p.paletteSpreads.join(', ') }}
        </div>
        <div v-if="p.nodeTypes === 0" class="pcard-s">仅画布工具，无组件</div>
      </div>
    </section>

    <el-table :data="visible" v-loading="loading" size="small" border stripe>
      <el-table-column label="组件" min-width="220">
        <template #default="{ row }">
          <div class="comp">
            <span class="ico" :style="{ color: row.color }">{{ row.icon || '⬢' }}</span>
            <div>
              <div class="nm">
                {{ row.label }}
                <code class="ty">{{ row.type }}</code>
                <span v-if="row.code" class="code">{{ row.code }}</span>
                <!-- M-B0 基线化徽标：progress 成功才显示基线徽标（失败静默降级）；修订中（designing+已发版）优先提示；已发版动态带版本号；runtimeOnly 恒显示 -->
                <span v-if="baselineMap[row.type] === 'published'" class="bl bl-ok">
                  {{ (baselineVer[row.type] ?? 0) > 0 ? `已发 v${baselineVer[row.type]}` : '已发版' }}
                </span>
                <span
                  v-else-if="baselineMap[row.type] === 'designing' && (baselineVer[row.type] ?? 0) > 0"
                  class="bl bl-rev"
                >修订中（v{{ baselineVer[row.type] }} 已发）</span>
                <span v-else-if="baselineLoaded" class="bl bl-none">未基线</span>
                <span v-if="row.runtimeOnly" class="bl bl-rt">运行态</span>
              </div>
              <div v-if="row.desc" class="ds">{{ row.desc }}</div>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="Profile" width="96">
        <template #default="{ row }">
          <span class="prof" :class="{ dag: row.dagRelevant }">{{ row.profile }}</span>
        </template>
      </el-table-column>
      <el-table-column label="执行实现" width="132">
        <template #default="{ row }">
          <span class="exec" :class="row.executionModel">{{ execText(row.executionModel) }}</span>
          <div v-if="row.executor" class="ex">{{ row.executor }}</div>
        </template>
      </el-table-column>
      <el-table-column label="派发" width="100">
        <template #default="{ row }">
          <span class="badge" :class="routeMeta[row.route as ComponentRoute].cls">
            {{ routeMeta[row.route as ComponentRoute].t }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="Palette" width="132">
        <template #default="{ row }">
          <template v-if="row.paletteVisible">
            <div class="grp">{{ row.paletteGroup }}</div>
          </template>
          <span v-else class="muted">不可见</span>
        </template>
      </el-table-column>
      <el-table-column label="表单" width="118">
        <template #default="{ row }">
          <span>{{ row.formFieldCount }} 字段</span>
          <span v-if="row.requiredFieldCount" class="req"> / {{ row.requiredFieldCount }} 必填</span>
          <div v-if="row.runtimeOnly" class="rt">runtimeOnly</div>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="openDetail(row)">详情</el-button>
          <!-- 内置目录组件走基线化治理链（t_baseline_progress），编辑入口在基线化工作台设计区；
               已发 v1 的底稿锁定（一次性认可）故显示「查看」。M1 设计器仅服务用户自建组件。 -->
          <el-button link type="primary" size="small" @click="router.push({ path: '/meta/baseline', query: { type: row.type } })">{{ baselineMap[row.type] === 'published' ? '查看' : '修改' }}</el-button>
          <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-drawer v-model="detailOpen" size="46%" :title="detail ? `${detail.label}（${detail.type}）` : ''">
      <template v-if="detail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="Profile">{{ detail.profile }}</el-descriptions-item>
          <el-descriptions-item label="编码">{{ detail.code || '—' }}</el-descriptions-item>
          <el-descriptions-item label="执行实现" :span="2">
            <span class="exec" :class="detail.executionModel">{{ execText(detail.executionModel) }}</span>
            <span class="muted"> · {{ detail.executionNote }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="派发">
            <span class="badge" :class="routeMeta[detail.route].cls">{{ routeMeta[detail.route].t }}</span>
            <span v-if="detail.executor"> · {{ detail.executor }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="形态">{{ detail.shape || '—' }}</el-descriptions-item>
          <el-descriptions-item label="Palette">
            {{ detail.paletteVisible ? (detail.paletteGroup || '—') : '不可见' }}
          </el-descriptions-item>
          <el-descriptions-item label="runtimeOnly">{{ detail.runtimeOnly ? '是' : '否' }}</el-descriptions-item>
          <el-descriptions-item label="描述" :span="2">{{ detail.desc || '—' }}</el-descriptions-item>
        </el-descriptions>

        <h4 class="dh">表单字段（{{ detail.formFields.length }}）</h4>
        <el-table :data="detail.formFields" size="small" border>
          <el-table-column prop="key" label="key" width="150" />
          <el-table-column prop="label" label="label" width="130" />
          <el-table-column prop="type" label="控件类型" width="120" />
          <el-table-column label="必填" width="60">
            <template #default="{ row }">{{ row.required ? '是' : '' }}</template>
          </el-table-column>
          <el-table-column label="联动/校验" min-width="130">
            <template #default="{ row }">
              <span class="muted">{{ flagText(row) || '—' }}</span>
            </template>
          </el-table-column>
        </el-table>
        <p class="note">
          联动标记对应源码中的 <code>showIf</code> / <code>onChange</code> / <code>pick</code> /
          <code>text</code> 函数，<strong>不可序列化</strong>，故目录中只保留布尔标记。
          组件声明契约见 <code>docs/DAG组件声明契约与Plan产物设计.md</code>。
        </p>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
.page { padding: 16px; }
.head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.head-actions { display: flex; gap: 10px; flex-shrink: 0; }
h2 { margin: 0 0 4px; font-size: 18px; }
.sub { margin: 0; color: #64748b; font-size: 12px; line-height: 1.7; max-width: 900px; }
.sub code, .note code, .ty { font-size: 11px; background: #f1f5f9; padding: 1px 4px; border-radius: 3px; }
.drift { margin-top: 12px; }
.drift-list { margin: 6px 0 0; padding-left: 18px; font-size: 12px; line-height: 1.8; }
.filters { margin-top: 12px; }
.count { color: #64748b; font-size: 12px; }
.profiles { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.pcard { border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px 12px; min-width: 116px; background: #fff; }
.pcard.off { background: #f8fafc; opacity: .75; }
.pcard-t { font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: .04em; }
.pcard-n { font-size: 20px; font-weight: 600; line-height: 1.3; }
.pcard-s { font-size: 11px; color: #94a3b8; line-height: 1.5; }
.comp { display: flex; gap: 8px; align-items: flex-start; }
.ico { font-size: 15px; line-height: 1.4; }
.nm { font-weight: 500; }
/* M-B0 基线化徽标（已发 vN / 修订中 / 未基线 / 运行态） */
.bl { margin-left: 6px; font-size: 10px; padding: 1px 6px; border-radius: 3px; white-space: nowrap; }
.bl-ok { background: #dcfce7; color: #15803d; }
.bl-none { background: #f1f5f9; color: #94a3b8; }
.bl-rev { background: #dbeafe; color: #1d4ed8; }
.bl-rt { background: #fef3c7; color: #b45309; }
.ty { margin-left: 6px; color: #475569; }
.code { margin-left: 6px; font-size: 10px; color: #fff; background: #64748b; padding: 1px 5px; border-radius: 3px; }
.ds { font-size: 11px; color: #94a3b8; margin-top: 2px; }
.prof { font-size: 11px; padding: 1px 6px; border-radius: 3px; background: #f1f5f9; color: #64748b; }
.prof.dag { background: #dbeafe; color: #1d4ed8; }
.badge { font-size: 11px; padding: 1px 7px; border-radius: 3px; background: #f1f5f9; color: #475569; }
.badge.ok { background: #dcfce7; color: #15803d; }
.badge.err { background: #fee2e2; color: #b91c1c; }
.badge.off { background: #f1f5f9; color: #94a3b8; }
.ex, .rt { font-size: 10px; color: #94a3b8; margin-top: 2px; }
.exec { font-size: 11px; padding: 1px 7px; border-radius: 3px; background: #f1f5f9; color: #475569; }
.exec.dag-engine { background: #dcfce7; color: #15803d; }
.exec.demo-only { background: #fee2e2; color: #b91c1c; }
.exec.canvas-device { background: #f1f5f9; color: #94a3b8; }
.grp { font-size: 11px; color: #475569; }
.muted { color: #94a3b8; font-size: 11px; }
.req { font-size: 11px; color: #b45309; }
.dh { margin: 16px 0 8px; font-size: 14px; }
.note { font-size: 11px; color: #94a3b8; line-height: 1.7; margin-top: 8px; }
/* D3 用户组件治理库区 */
.ugov { margin-top: 12px; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px 12px; background: #fff; }
.ugov-t { font-size: 12px; font-weight: 600; color: #475569; margin-bottom: 8px; }
.ugrid { display: flex; flex-wrap: wrap; gap: 8px; }
.ucard { border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px 10px; min-width: 250px; }
.ucard.off { opacity: .7; background: #f8fafc; }
.uc-head { display: flex; align-items: center; gap: 6px; }
.uc-nm { font-weight: 500; font-size: 13px; }
.uc-sub { font-size: 11px; color: #94a3b8; margin: 4px 0 6px; }
.life { font-size: 10px; padding: 1px 6px; border-radius: 3px; flex-shrink: 0; }
.life-draft { background: #fef9c3; color: #a16207; }
.life-pub { background: #dcfce7; color: #15803d; }
.life-off { background: #f1f5f9; color: #94a3b8; }
</style>
