<script setup lang="ts">
/**
 * M10 命名规范（/std/naming）
 * 对齐 prototype/assets/pages/m10-standard.js L418-467：
 * 左侧规范列表（namingRules：适用范围/正则/示例/状态），右侧命名校验工具（选类型 + 输入名称在线正则校验）；
 * 行操作：校验示例（回填右侧工具并立即校验）/ 编辑（抽屉）。
 */
import { ref, computed, onMounted } from 'vue'
import ListFilterPanel from '../../components/ListFilterPanel.vue'
import type { Facet } from '../../components/ListFilterPanel.vue'
import { ElMessage } from 'element-plus'
import { dataStore, ST } from '../../services/mock/dataStore'
import type { NamingRule } from '../../services/types'

const rows = ref<NamingRule[]>([])
const keyword = ref('')
const filters = ref<Record<string, string>>({ scope: '', status: '' })

/* ---- 左侧筛选面板 facets（选项按页内数据派生） ---- */
const facets = computed<Facet[]>(() => [
  {
    key: 'scope',
    label: '适用范围',
    options: [...new Set(rows.value.map((r) => r.scope))].map((s) => ({ v: s, t: s })),
  },
  {
    key: 'status',
    label: '状态',
    options: [...new Set(rows.value.map((r) => r.status))].map((s) => ({ v: s, t: stLabel(s) })),
  },
])

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return rows.value.filter((r) => {
    if (filters.value.scope && r.scope !== filters.value.scope) return false
    if (filters.value.status && r.status !== filters.value.status) return false
    if (!kw) return true
    return [r.id, r.scope, r.desc].some((s) => s.toLowerCase().includes(kw))
  })
})

async function reload() {
  // 展开为新数组触发响应式更新（save 原地修改数组，list 返回同一引用）
  rows.value = [...((await dataStore.list<NamingRule>('namingRules')) ?? [])]
}

onMounted(reload)

/* ---- ST 徽标 ---- */
function stCls(s: string): string {
  return ST[s]?.cls ?? 'st-gray'
}
function stLabel(s: string): string {
  return ST[s]?.label ?? s
}

/* ---- 命名校验工具（对齐原型 A.nrRun：按适用范围硬编码正则） ---- */
const scopeOptions = ['表命名-Ods', '表命名-Dwd', '表命名-Dws', '表命名-Ads', '字段命名', '任务命名']
const checkScope = ref('表命名-Ods')
const checkName = ref('')
const checkResult = ref<{ ok: boolean; text: string; pattern: string; eg: string } | null>(null)

const SCOPE_REGEX: Record<string, RegExp> = {
  '表命名-Ods': /^ods_[a-z0-9]+_[a-z0-9_]+$/,
  '表命名-Dwd': /^dwd_[a-z0-9]+_[a-z0-9_]+$/,
  '表命名-Dws': /^dws_[a-z0-9]+_[a-z0-9_]+$/,
  '表命名-Ads': /^ads_[a-z0-9]+_[a-z0-9_]+$/,
  '字段命名': /^[a-z][a-z0-9_]*$/,
  '任务命名': /^(etl|sync)_[a-z0-9_]+$/,
}

function runCheck() {
  const name = checkName.value.trim()
  if (!name) {
    ElMessage.warning('请输入待校验名称')
    return
  }
  const rule = rows.value.find((r) => r.scope === checkScope.value)
  const re = SCOPE_REGEX[checkScope.value]
  if (!rule || !re) {
    checkResult.value = { ok: false, text: '未找到适用规范', pattern: '-', eg: '-' }
    return
  }
  const ok = re.test(name)
  checkResult.value = { ok, text: ok ? '符合规范' : '不符合规范', pattern: rule.pattern, eg: rule.eg }
}

/* ---- 校验示例：回填工具并立即校验 ---- */
function testRule(r: NamingRule) {
  if (SCOPE_REGEX[r.scope]) checkScope.value = r.scope
  checkName.value = r.eg
  runCheck()
}

/* ---- 编辑（抽屉） ---- */
const formVisible = ref(false)
const editing = ref<NamingRule | null>(null)
const form = ref({ scope: '', pattern: '', eg: '', desc: '' })

function openEdit(r: NamingRule) {
  editing.value = r
  form.value = { scope: r.scope, pattern: r.pattern, eg: r.eg, desc: r.desc }
  formVisible.value = true
}

async function saveForm() {
  if (!editing.value) return
  if (!form.value.scope.trim()) {
    ElMessage.warning('请填写适用范围')
    return
  }
  Object.assign(editing.value, {
    scope: form.value.scope.trim(),
    pattern: form.value.pattern,
    eg: form.value.eg,
    desc: form.value.desc,
  })
  await dataStore.save('namingRules', editing.value)
  formVisible.value = false
  ElMessage.success('命名规范已保存')
}
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ListFilterPanel
      v-model:keyword="keyword"
      v-model:filters="filters"
      :facets="facets"
      placeholder="搜索规范"
      :result-count="filtered.length"
      :total-count="rows.length"
    />
    <div style="flex:1;min-width:0">
    <div class="nr-grid">
      <!-- 左：规范列表 -->
      <div class="card" style="padding:16px">
        <div class="tbl-toolbar">
          <span class="sec-head">规范列表</span>
          <span class="pill info">{{ filtered.length }} / {{ rows.length }}</span>
          <span class="spacer" />
        </div>

        <table class="tbl">
          <thead>
            <tr>
              <th>适用范围</th><th>正则 / 规则</th><th>示例</th><th>状态</th><th style="width:130px">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in filtered" :key="r.id">
              <td><b>{{ r.scope }}</b></td>
              <td><span class="mono" style="font-size:11.5px">{{ r.pattern }}</span></td>
              <td><span class="mono" style="font-size:11.5px;color:var(--success)">{{ r.eg }}</span></td>
              <td>
                <span class="st" :class="stCls(r.status)"><span class="dot" />{{ stLabel(r.status) }}</span>
              </td>
              <td>
                <button class="op-btn primary" @click="testRule(r)">校验示例</button>
                <button class="op-btn" @click="openEdit(r)">编辑</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="filtered.length === 0" class="empty">未找到匹配的命名规范</div>
      </div>

      <!-- 右：命名校验工具 -->
      <div class="card" style="padding:16px">
        <div class="tbl-toolbar">
          <span class="sec-head">命名校验工具</span>
        </div>
        <div class="form-grid">
          <label class="f-item">校验类型
            <select v-model="checkScope">
              <option v-for="s in scopeOptions" :key="s" :value="s">{{ s }}</option>
            </select>
          </label>
          <label class="f-item">待校验名称
            <input v-model="checkName" placeholder="如：dwd_order_pay_detail" />
          </label>
        </div>
        <div style="margin-top:12px">
          <button class="tb-new" @click="runCheck">校验</button>
        </div>
        <div v-if="checkResult" class="check-line" :class="checkResult.ok ? 'ok' : 'err'">
          <span>{{ checkResult.ok ? '✓' : '✗' }}</span>
          <div>
            <b>{{ checkResult.text }}</b>
            <span class="mono" style="font-size:11.5px"> · {{ checkResult.pattern }}</span>
            <div v-if="!checkResult.ok" style="font-size:11px;color:var(--text-3);margin-top:3px">
              参考示例：{{ checkResult.eg }}
            </div>
          </div>
        </div>
        <div v-else class="hint">建模保存与任务发布时将按上述规范自动拦截不规范命名（NR-01~06）。</div>
      </div>
    </div>

    <!-- 编辑抽屉 -->
    <el-drawer v-model="formVisible" :title="editing ? '编辑命名规范 - ' + editing.scope : ''" size="420px">
      <div class="form-grid">
        <label class="f-item">适用范围
          <input v-model="form.scope" />
        </label>
        <label class="f-item">正则 / 规则
          <textarea v-model="form.pattern" rows="2" class="mono" style="resize:vertical" />
        </label>
        <label class="f-item">示例
          <input v-model="form.eg" />
        </label>
        <label class="f-item">说明
          <textarea v-model="form.desc" rows="2" style="resize:vertical" />
        </label>
      </div>
      <div style="margin-top:16px;display:flex;gap:8px">
        <button class="tb-new" @click="saveForm">保存</button>
        <button class="op-btn" @click="formVisible = false">取消</button>
      </div>
    </el-drawer>
    </div>
  </div>
</template>

<style scoped>
.nr-grid{display:grid;grid-template-columns:1.5fr 1fr;gap:16px;align-items:start}
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;padding:9px 10px;background:var(--bg);color:var(--text-2);font-weight:600;border-bottom:1px solid var(--border)}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--border)}
.tbl tr:hover td{background:var(--primary-light)}
.kw{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 10px;font-size:12.5px;width:190px;outline:none;transition:all var(--dur-fast) var(--ease)}
.kw:focus{border-color:var(--primary)}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease)}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2);transition:all var(--dur-fast) var(--ease)}
.op-btn.primary{color:var(--primary);border-color:rgba(22,104,220,.4);font-weight:600}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
.form-grid{display:flex;flex-direction:column;gap:12px}
.f-item{display:flex;flex-direction:column;gap:5px;font-size:12.5px;color:var(--text-2)}
.f-item input,.f-item select,.f-item textarea{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 10px;font-size:12.5px;outline:none;font-family:inherit;background:#fff;color:var(--text);transition:all var(--dur-fast) var(--ease)}
.f-item input:focus,.f-item select:focus,.f-item textarea:focus{border-color:var(--primary)}
.check-line{display:flex;gap:8px;align-items:flex-start;margin-top:12px;border-radius:var(--radius);padding:9px 11px;font-size:12.5px;transition:all var(--dur-fast) var(--ease)}
.check-line.ok{background:var(--success-bg);color:var(--success)}
.check-line.err{background:var(--danger-bg);color:var(--danger)}
.hint{font-size:11.5px;color:var(--text-3);margin-top:12px;line-height:1.6}
</style>
