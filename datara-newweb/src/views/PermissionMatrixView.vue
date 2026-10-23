<template><main class="perm-page" aria-label="权限矩阵">
  <header class="perm-header">
    <div>
      <h1>权限矩阵</h1>
      <p>四角色 × {{ PERMISSION_ORDER.length }} 权限点只读快照（权威源 rebuild/identity/contracts.py ROLE_PERMISSIONS）。</p>
    </div>
  </header>
  <div class="perm-legend" role="note">
    <span><i class="mark yes">✓</i> 已授权</span>
    <span><i class="mark no">—</i> 未授权（authorize() 默认拒绝）</span>
  </div>
  <table data-perm-matrix>
    <thead>
      <tr>
        <th scope="col" class="perm-col">权限点</th>
        <th v-for="r in ROLE_ORDER" :key="r" scope="col" :data-role-head="r">{{ r }}</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="p in PERMISSION_ORDER" :key="p" :data-perm="p">
        <td class="perm-col" data-perm-code>{{ p }}</td>
        <td
          v-for="r in ROLE_ORDER"
          :key="r"
          :data-role="r"
          :data-granted="roleHasPermission(r, p) ? 'yes' : 'no'"
          class="cell"
        >{{ roleHasPermission(r, p) ? '✓' : '—' }}</td>
      </tr>
    </tbody>
  </table>
</main></template>

<script setup lang="ts">
/**
 * 15.1-C 权限矩阵只读页：纯静态消费冻结常量 rolePermissions.ts，
 * 无网络请求、无写操作（矩阵只读渲染；授权判定以后端 authorize() 为最终裁决）。
 */
import { PERMISSION_ORDER, ROLE_ORDER, roleHasPermission } from '../services/rebuild/rolePermissions'
</script>

<style scoped>
.perm-page{max-width:1080px;margin:auto;padding:32px 24px;color:#172033}
.perm-header{display:flex;align-items:center;justify-content:space-between}
.perm-page h1{margin:0}
.perm-header p{color:#64748b}
.perm-legend{display:flex;gap:18px;margin:14px 0;color:#475569;font-size:13px}
.perm-legend .mark{font-style:normal;margin-right:4px}
.perm-legend .mark.yes{color:#15803d}
.perm-legend .mark.no{color:#94a3b8}
table{width:100%;border-collapse:collapse;background:#fff;font-size:14px}
th,td{padding:9px 11px;border-bottom:1px solid #e2e8f0;text-align:left}
thead th{background:#f1f5f9}
.perm-col{width:280px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px}
td.cell{text-align:center}
td[data-granted="yes"]{color:#15803d}
td[data-granted="no"]{color:#cbd5e1}
</style>
