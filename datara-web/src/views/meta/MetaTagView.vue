<script setup lang="ts">
/**
 * M09 标签管理（todo 11 · F56）
 * 标签列表（dataStore.metaTags）+ 打标操作（表详情抽屉内选择标签保存）+ 按标签筛选。
 * 双向同步：保存时同时更新 tag.tables/tag.cnt 与 table.tags（原型 m09-meta.js L659-671）。
 * 标签不写入图文档（metaTags 独立集合，约束 M1）；localStorage 持久化（dataStore.save）。
 */
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { dataStore } from '../../services/mock/dataStore'
import ListFilterPanel from '../../components/ListFilterPanel.vue'
import type { Facet } from '../../components/ListFilterPanel.vue'
import type { MetaTable, MetaTag } from '../../services/types'

const tags = ref<MetaTag[]>([])
const tables = ref<MetaTable[]>([])

async function reload() {
  tags.value = [...((await dataStore.list<MetaTag>('metaTags')) ?? [])]
  tables.value = [...((await dataStore.list<MetaTable>('metaTables')) ?? [])]
}

onMounted(reload)

/* ---- 搜索 / 筛选（左侧 ListFilterPanel） ---- */
const keyword = ref('')
const filters = ref<Record<string, string>>({ cat: '', tagged: '' })

const facets: Facet[] = [
  { key: 'cat', label: '标签分类', options: ['重要性', '用途', '标准', '安全', '质量'].map((c) => ({ v: c, t: c })) },
  { key: 'tagged', label: '打标状态', options: [{ v: 'yes', t: '已打标' }, { v: 'no', t: '未打标' }] },
]

const filteredTags = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return tags.value.filter((t) => {
    if (filters.value.cat && t.cat !== filters.value.cat) return false
    if (filters.value.tagged === 'yes' && t.tables.length === 0) return false
    if (filters.value.tagged === 'no' && t.tables.length > 0) return false
    if (!kw) return true
    return [t.name, t.cat, t.desc].some((s) => s.toLowerCase().includes(kw))
  })
})

/* ---- 新建 / 编辑标签 ---- */
const formVisible = ref(false)
const editing = ref<MetaTag | null>(null)
const form = ref({ name: '', cat: '重要性', color: '#1668dc', desc: '' })

function openCreate() {
  editing.value = null
  form.value = { name: '', cat: '重要性', color: '#1668dc', desc: '' }
  formVisible.value = true
}

function openEdit(t: MetaTag) {
  editing.value = t
  form.value = { name: t.name, cat: t.cat, color: t.color, desc: t.desc }
  formVisible.value = true
}

async function saveForm() {
  const name = form.value.name.trim()
  if (!name) {
    ElMessage.warning('请填写标签名称')
    return
  }
  if (editing.value) {
    Object.assign(editing.value, { name, cat: form.value.cat, color: form.value.color, desc: form.value.desc })
    await dataStore.save('metaTags', editing.value)
    ElMessage.success('标签已保存')
  } else {
    // ID 取现有最大序号 +1：删除标签后再新建不会碰撞
    const nextSeq = tags.value.reduce((m, t) => {
      const n = Number(String(t.id).replace(/^\D+/, ''))
      return Number.isFinite(n) && n > m ? n : m
    }, 0) + 1
    const tag: MetaTag = {
      id: 'TG' + String(nextSeq).padStart(2, '0'),
      name,
      cat: form.value.cat,
      color: form.value.color,
      cnt: 0,
      desc: form.value.desc,
      tables: [],
    }
    tags.value.push(tag)
    await dataStore.save('metaTags', tag)
    ElMessage.success(`标签「${name}」已创建`)
  }
  formVisible.value = false
}

/* ---- 删除标签（同步从所有表移除） ---- */
async function removeTag(t: MetaTag) {
  try {
    await ElMessageBox.confirm(`确定删除标签「${t.name}」？已打标的表将保留，仅移除该标签。`, '删除标签', { type: 'warning' })
  } catch {
    return
  }
  for (const tb of tables.value) {
    if ((tb.tags ?? []).includes(t.name)) {
      tb.tags = (tb.tags ?? []).filter((x) => x !== t.name)
      await dataStore.save('metaTables', tb)
    }
  }
  tags.value = tags.value.filter((x) => x.id !== t.id)
  await dataStore.remove('metaTags', t.id)
  ElMessage.success('标签已删除')
}

/* ---- 打标资产（双向同步） ---- */
const tagDrawerVisible = ref(false)
const tagTarget = ref<MetaTag | null>(null)
const checkedIds = ref<string[]>([])

function openTagTables(t: MetaTag) {
  tagTarget.value = t
  checkedIds.value = [...t.tables]
  tagDrawerVisible.value = true
}

async function saveTagTables() {
  const d = tagTarget.value
  if (!d) return
  const vals = [...checkedIds.value]
  d.tables = vals
  d.cnt = vals.length
  for (const tb of tables.value) {
    const had = (tb.tags ?? []).includes(d.name)
    const want = vals.includes(tb.id)
    if (had !== want) {
      tb.tags = (tb.tags ?? []).filter((x) => x !== d.name)
      if (want) tb.tags.push(d.name)
      await dataStore.save('metaTables', tb)
    }
  }
  await dataStore.save('metaTags', d)
  ElMessage.success(`标签「${d.name}」已关联 ${vals.length} 张表`)
  tagDrawerVisible.value = false
}

/* ---- 按标签筛选 ---- */
const activeTag = ref('')

const filteredTables = computed(() => {
  if (!activeTag.value) return []
  return tables.value.filter((t) => (t.tags ?? []).includes(activeTag.value))
})

function tagStyle(name: string) {
  const t = tags.value.find((x) => x.name === name)
  const c = t?.color ?? '#64748b'
  return { background: c + '22', color: c }
}
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ListFilterPanel
      v-model:keyword="keyword"
      v-model:filters="filters"
      :facets="facets"
      placeholder="搜索标签/描述"
      :result-count="filteredTags.length"
      :total-count="tags.length"
    />
    <div style="flex:1;min-width:0">
    <div class="card" style="padding:16px">
      <div class="tbl-toolbar">
        <span class="sec-head">标签管理</span>
        <span class="pill info">{{ filteredTags.length }} / {{ tags.length }} 个标签</span>
        <span class="spacer" />
        <button class="tb-new" @click="openCreate">+ 新建标签</button>
      </div>

      <table class="tbl">
        <thead>
          <tr>
            <th>标签</th><th>分类</th><th>描述</th><th>已打标表</th><th style="width:190px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="t in filteredTags" :key="t.id">
            <td>
              <span class="tag" :style="{ background: t.color + '22', color: t.color }">{{ t.name }}</span>
            </td>
            <td><span class="pill info">{{ t.cat }}</span></td>
            <td style="color:var(--text-2)">{{ t.desc }}</td>
            <td><a @click="openTagTables(t)"><b>{{ t.tables.length }}</b> 张</a></td>
            <td>
              <button class="op-btn primary" @click="openTagTables(t)">打标资产</button>
              <button class="op-btn" @click="openEdit(t)">编辑</button>
              <button class="op-btn danger" @click="removeTag(t)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="tags.length === 0" class="empty">暂无标签，点击右上角「+ 新建标签」创建</div>

      <div class="sec-title" style="margin-top:20px">按标签筛选</div>
      <div class="tag-chips">
        <button
          v-for="t in tags"
          :key="t.id"
          class="chip"
          :class="{ on: activeTag === t.name }"
          :style="activeTag === t.name
            ? { background: t.color, borderColor: t.color, color: '#fff' }
            : { color: t.color, borderColor: t.color + '66' }"
          @click="activeTag = activeTag === t.name ? '' : t.name"
        >{{ t.name }}</button>
      </div>

      <template v-if="activeTag">
        <div v-if="filteredTables.length" class="filter-result">
          <table class="tbl">
            <thead>
              <tr><th>表名</th><th>主题域</th><th>分层</th><th>标签</th></tr>
            </thead>
            <tbody>
              <tr v-for="t in filteredTables" :key="t.id">
                <td><span class="mono" style="font-size:12px">{{ t.name }}</span></td>
                <td><span class="pill info">{{ t.domain }}</span></td>
                <td>{{ t.layer }}</td>
                <td>
                  <span v-for="tg in t.tags" :key="tg" class="tag" :style="tagStyle(tg)">{{ tg }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="empty">该标签下暂无资产</div>
      </template>
      <div v-else class="hint">点击上方标签筛选资产（对表打标签后此处即时命中）</div>
    </div>

    <!-- 新建 / 编辑标签抽屉 -->
    <el-drawer v-model="formVisible" :title="editing ? '编辑标签 - ' + editing.name : '新建标签'" size="420px">
      <div class="form-grid">
        <label class="f-item">标签名称
          <input v-model="form.name" class="kw" style="width:100%" placeholder="如：核心" />
        </label>
        <label class="f-item">标签分类
          <select v-model="form.cat" class="kw" style="width:100%">
            <option>重要性</option><option>用途</option><option>标准</option><option>安全</option><option>质量</option>
          </select>
        </label>
        <label class="f-item">颜色
          <input v-model="form.color" type="color" style="width:100%;height:32px;border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:2px" />
        </label>
        <label class="f-item">描述
          <textarea v-model="form.desc" class="kw" style="width:100%;resize:vertical" rows="2" placeholder="标签用途说明" />
        </label>
      </div>
      <div style="margin-top:16px;display:flex;gap:8px">
        <button class="tb-new" @click="saveForm">保存</button>
        <button class="op-btn" @click="formVisible = false">取消</button>
      </div>
    </el-drawer>

    <!-- 打标资产抽屉 -->
    <el-drawer v-model="tagDrawerVisible" :title="tagTarget ? '为标签「' + tagTarget.name + '」选择资产' : ''" size="480px">
      <div v-if="tagTarget">
        <label v-for="t in tables" :key="t.id" class="tbl-check">
          <input type="checkbox" :value="t.id" v-model="checkedIds" />
          <span class="mono" style="font-size:12px">{{ t.name }}</span>
          <span style="margin-left:auto;font-size:11px;color:var(--text-3)">{{ t.domain }} · {{ t.layer }}</span>
        </label>
        <div v-if="tables.length === 0" class="empty">暂无元数据表</div>
        <div style="margin-top:16px;display:flex;gap:8px">
          <button class="tb-new" @click="saveTagTables">保存（{{ checkedIds.length }} 张）</button>
          <button class="op-btn" @click="tagDrawerVisible = false">取消</button>
        </div>
      </div>
    </el-drawer>
    </div>
  </div>
</template>

<style scoped>
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;padding:9px 10px;background:var(--bg);color:var(--text-2);font-weight:600;border-bottom:1px solid var(--border)}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--border)}
.tbl tr:hover td{background:var(--primary-light)}
.tag{display:inline-block;border-radius:4px;padding:1px 8px;font-size:11.5px;font-weight:600;margin-right:4px}
.kw{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 10px;font-size:12.5px;outline:none}
.kw:focus{border-color:var(--primary)}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease)}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
.op-btn.primary{color:var(--primary);border-color:rgba(22,104,220,.4);font-weight:600}
.op-btn.danger{color:#e5484d;border-color:rgba(229,72,77,.4)}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
.sec-title{font-weight:700;font-size:13px;margin:14px 0 8px;color:var(--text)}
.hint{font-size:11.5px;color:var(--text-3);padding:10px 0}
.tag-chips{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px}
.chip{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-xl);padding:3px 12px;font-size:12px;cursor:pointer}
.chip.on{font-weight:600}
.filter-result{margin-top:4px}
.form-grid{display:flex;flex-direction:column;gap:12px}
.f-item{display:flex;flex-direction:column;gap:5px;font-size:12.5px;color:var(--text-2)}
.tbl-check{display:flex;gap:8px;align-items:center;padding:7px 10px;border:1px solid var(--border);border-radius:7px;margin-bottom:7px;cursor:pointer}
</style>