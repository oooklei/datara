<script setup lang="ts">
/**
 * M15 数据安全 · 脱敏规则（列级权限）
 * 敏感字段类型 → 策略（掩码/替换/哈希）；规则开关即时生效于 sample 预览；
 * 敏感数据发现：正则 + 字段名 + 数据采样（统计条）。
 */
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { dataStore } from '../../services/mock/dataStore'
import { useAuthStore } from '../../stores/auth'
import type { MaskRule, MetaTable } from '../../services/types'

const auth = useAuthStore()
const rules = ref<MaskRule[]>([])
const tables = ref<MetaTable[]>([])

async function reload() {
  rules.value = [...((await dataStore.list<MaskRule>('maskRules')) ?? [])]
  tables.value = (await dataStore.list<MetaTable>('metaTables')) ?? []
}
onMounted(reload)

async function toggle(r: MaskRule) {
  if (!auth.canEdit) { ElMessage.warning('当前角色只读，无法修改脱敏规则'); return }
  r.enabled = !r.enabled
  await dataStore.save('maskRules', r)
  ElMessage.success(`规则「${r.type}」已${r.enabled ? '启用' : '停用'}`)
}

/* 敏感发现统计：按 sample 字段形态扫描（正则 + 字段名 + 采样） */
const found = computed(() => {
  const rows: { field: string; table: string; type: string; samples: number }[] = []
  for (const t of tables.value) {
    const seen = new Set<string>()
    for (const r of t.sample ?? []) {
      for (const [k, v] of Object.entries(r)) {
        let type: string | null = null
        if (/phone|mobile/i.test(k) || /^1\d{10}$/.test(String(v))) type = '手机号'
        else if (/idcard|cert/i.test(k) || /^\d{17}[\dXx]$/.test(String(v))) type = '身份证号'
        else if (/bank|card/i.test(k)) type = '银行卡号'
        else if (/user_name$|realname/i.test(k)) type = '姓名'
        if (type && !seen.has(k)) {
          seen.add(k)
          rows.push({ field: k, table: t.name, type, samples: (t.sample ?? []).length })
        }
      }
    }
  }
  return rows
})
</script>

<template>
  <div class="page">
    <div class="card" style="padding:16px">
      <div class="tbl-toolbar">
        <span class="sec-head">脱敏规则</span>
        <span class="pill info">{{ rules.filter(r => r.enabled).length }} / {{ rules.length }} 启用</span>
        <span class="spacer" />
        <span style="color:var(--text-3);font-size:12px">策略：掩码 / 替换 / 哈希（SM4）</span>
      </div>
      <table class="tbl">
        <thead><tr><th>编号</th><th>敏感类型</th><th>策略</th><th>生效范围</th><th>状态</th><th style="width:90px">操作</th></tr></thead>
        <tbody>
          <tr v-for="r in rules" :key="r.id">
            <td class="mono" style="font-size:11.5px">{{ r.id }}</td>
            <td><b>{{ r.type }}</b><span class="mono" style="margin-left:6px;color:var(--text-3);font-size:11px">{{ r.field }}</span></td>
            <td style="color:var(--text-2)">{{ r.strategy }}</td>
            <td>{{ r.scope }}</td>
            <td><span class="pill" :class="r.enabled ? 'ok' : 'off'">{{ r.enabled ? '启用' : '停用' }}</span></td>
            <td><button class="op-btn" @click="toggle(r)">{{ r.enabled ? '停用' : '启用' }}</button></td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card" style="padding:16px">
      <div class="tbl-toolbar">
        <span class="sec-head">敏感数据发现</span>
        <span class="pill warn">扫描 {{ tables.length }} 张表 · 命中 {{ found.length }} 个敏感字段</span>
        <span class="spacer" />
        <span style="color:var(--text-3);font-size:12px">方式：正则规则 + 字段名匹配 + 数据采样</span>
      </div>
      <table class="tbl">
        <thead><tr><th>敏感字段</th><th>类型</th><th>所在表</th><th>采样行数</th><th>建议</th></tr></thead>
        <tbody>
          <tr v-for="f in found" :key="f.table + f.field">
            <td class="mono" style="font-size:12px">{{ f.field }}</td>
            <td><span class="pill warn">{{ f.type }}</span></td>
            <td class="mono" style="font-size:12px">{{ f.table }}</td>
            <td style="color:var(--text-3)">{{ f.samples }}</td>
            <td style="color:var(--text-2)">建议配置脱敏策略并纳入「{{ f.type }}」规则管理</td>
          </tr>
          <tr v-if="!found.length"><td colspan="5" class="empty">未发现敏感字段</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
/* ---- 区块标题（渐变竖条，与全站统一） ---- */
.sec-head{display:flex;align-items:center;gap:8px;font-weight:700;font-size:14px}
.sec-head::before{content:'';width:3px;height:14px;border-radius:2px;background:linear-gradient(180deg,var(--primary),var(--purple))}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;color:var(--text-2)}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.empty{text-align:center;color:var(--text-3);padding:18px}
</style>
