<script setup lang="ts">
/**
 * M12 环境参数组（/param/env）
 * 对齐 prototype/assets/pages/m12-param.js L87-108：
 * 参数组表格（环境标签/说明/参数数/默认数据源/参数预览）+ 查看差异（描述弹层）+ 编辑（说明/数据源/参数）+
 * 切换环境提示按钮。操作按钮置顶（页头工具栏）。
 * 注：envGroups 集合行无 id 字段（dataStore.save 以 id upsert），编辑保存时补写 id=name 使覆盖生效。
 */
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { dataStore } from '../../services/mock/dataStore'
import ParamTree from './ParamTree.vue'
import type { EnvGroup } from '../../services/types'

const groups = ref<EnvGroup[]>([])
const keyword = ref('')

async function reload() {
  // 必须展开为新数组：dataStore.save 原地修改数组，直接赋值不会触发 ref 更新
  groups.value = [...((await dataStore.list<EnvGroup>('envGroups')) ?? [])]
}
onMounted(reload)

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return groups.value
  return groups.value.filter((g) => [g.name, g.desc].some((s) => s.toLowerCase().includes(kw)))
})

function envPill(name: string): string {
  return name === 'prod' ? 'err' : name === 'staging' ? 'warn' : 'info'
}

/* ---- 查看差异 ---- */
const viewVisible = ref(false)
const viewTarget = ref<EnvGroup | null>(null)

function openView(g: EnvGroup) {
  viewTarget.value = g
  viewVisible.value = true
}

/* ---- 编辑（说明/默认数据源/参数预览） ---- */
const editVisible = ref(false)
const editTarget = ref<EnvGroup | null>(null)
const editForm = ref({ desc: '', ds: '', params: '' })

function openEdit(g: EnvGroup) {
  editTarget.value = g
  editForm.value = { desc: g.desc, ds: g.ds, params: g.params }
  editVisible.value = true
}

async function saveGroup() {
  const g = editTarget.value
  if (!g) return
  // envGroups 行无 id（dataStore.save 以 id upsert）：补写 id=name，本次及后续保存才能正确覆盖
  ;(g as EnvGroup & { id: string }).id = g.name
  Object.assign(g, { desc: editForm.value.desc, ds: editForm.value.ds, params: editForm.value.params })
  await dataStore.save('envGroups', g)
  ElMessage.success('参数组已保存')
  editVisible.value = false
}
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ParamTree @pick="(kw) => (keyword = kw)" />
    <div style="flex:1;min-width:0">
    <!-- 页头 + 顶部操作工具栏 -->
    <div class="card page-head">
      <div>
        <div class="ph-title">环境参数组</div>
        <div class="ph-desc">同一套任务跨环境（开发/联调/生产）运行：环境参数组覆盖同名全局参数，切换顶栏环境即生效</div>
      </div>
      <span class="spacer" />
      <button class="op-btn" @click="ElMessage.info('环境切换请使用顶栏 DEV / STAGING / PROD 开关')">切换环境</button>
    </div>

    <!-- 参数组 -->
    <div class="card" style="padding:16px">
      <div class="tbl-toolbar">
        <span class="card-title">参数组</span>
        <span class="pill info">{{ filtered.length }} / {{ groups.length }}</span>
        <span class="spacer" />
        <input v-model="keyword" class="kw" placeholder="搜索环境" />
      </div>
      <table class="tbl">
        <thead>
          <tr>
            <th>环境</th><th>说明</th><th>参数数</th><th>默认数据源</th><th>参数预览</th><th style="width:150px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="g in filtered" :key="g.name">
            <td><span class="pill" :class="envPill(g.name)">{{ g.name.toUpperCase() }}</span></td>
            <td style="color:var(--text-2)">{{ g.desc }}</td>
            <td>{{ g.cnt }}</td>
            <td>{{ g.ds }}</td>
            <td><span class="mono" style="font-size:11px">{{ g.params }}</span></td>
            <td>
              <button class="op-btn primary" @click="openView(g)">查看差异</button>
              <button class="op-btn" @click="openEdit(g)">编辑</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="filtered.length === 0" class="empty">未找到匹配的参数组</div>
    </div>

    <!-- 查看差异 -->
    <el-dialog v-model="viewVisible" :title="viewTarget ? '环境参数组 - ' + viewTarget.name.toUpperCase() : ''" width="520px">
      <div v-if="viewTarget" class="desc-grid">
        <span class="d-k">环境</span><span>{{ viewTarget.desc }}</span>
        <span class="d-k">参数数</span><span>{{ viewTarget.cnt }}</span>
        <span class="d-k">默认数据源</span><span>{{ viewTarget.ds }}</span>
        <span class="d-k">参数</span><span class="mono" style="font-size:11.5px">{{ viewTarget.params }}</span>
      </div>
      <div class="lock-tip">同名参数按「节点参数 &gt; 工作流变量 &gt; 环境组 &gt; 全局」优先级解析。</div>
      <template #footer>
        <button class="op-btn" @click="viewVisible = false">关闭</button>
      </template>
    </el-dialog>

    <!-- 编辑参数组 -->
    <el-dialog v-model="editVisible" :title="editTarget ? '编辑参数组 - ' + editTarget.name.toUpperCase() : ''" width="520px">
      <div class="form-grid">
        <label class="f-item">说明
          <input v-model="editForm.desc" class="kw" style="width:100%" />
        </label>
        <label class="f-item">默认数据源
          <input v-model="editForm.ds" class="kw" style="width:100%" />
        </label>
        <label class="f-item">参数预览
          <textarea v-model="editForm.params" class="kw mono" style="width:100%;resize:vertical;font-size:11.5px" rows="3" />
        </label>
      </div>
      <template #footer>
        <button class="tb-new" @click="saveGroup">保存</button>
        <button class="op-btn" style="margin-left:8px" @click="editVisible = false">取消</button>
      </template>
    </el-dialog>
    </div>
  </div>
</template>

<style scoped>
.page-head{display:flex;align-items:center;gap:12px;padding:14px 16px;margin-bottom:14px}
.ph-title{font-weight:700;font-size:15px}
.ph-desc{font-size:12px;color:var(--text-3);margin-top:2px}
.spacer{flex:1}
.card-title{font-weight:700;font-size:14px}
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;padding:9px 10px;background:var(--bg);color:var(--text-2);font-weight:600;border-bottom:1px solid var(--border)}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--border)}
.tbl tr:hover td{background:var(--primary-light)}
.kw{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 10px;font-size:12.5px;width:190px;outline:none}
.kw:focus{border-color:var(--primary)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
.desc-grid{display:grid;grid-template-columns:80px 1fr;gap:6px 10px;font-size:12.5px;margin-bottom:12px}
.desc-grid .d-k{color:var(--text-3)}
.lock-tip{background:var(--warn-bg);color:var(--warn);border-radius:var(--radius-sm);padding:8px 10px;font-size:11.5px}
.form-grid{display:flex;flex-direction:column;gap:12px}
.f-item{display:flex;flex-direction:column;gap:5px;font-size:12.5px;color:var(--text-2)}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease)}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
</style>
