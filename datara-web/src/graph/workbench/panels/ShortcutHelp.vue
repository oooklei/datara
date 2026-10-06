<script setup lang="ts">
/**
 * ShortcutHelp 快捷键帮助浮窗（工作台优化 Task 11，方案 §3.5）。
 * 纯展示组件：静态罗列工作台全部快捷键，由宿主 `?` 键 / openFloat('shortcut-help') 打开。
 * 样式走工作台明暗共用的 CSS 变量（同 ErrorPanel 等面板写法），不引入多余依赖。
 */

/** 快捷键行（键位 + 说明），按「通用 / 编辑」两组呈现 */
const groups = [
  {
    cap: '通用',
    items: [
      { keys: 'Ctrl + F', desc: '搜索节点' },
      { keys: '?', desc: '快捷键帮助' },
    ],
  },
  {
    cap: '编辑',
    items: [
      { keys: 'Ctrl + Z / Ctrl + Y', desc: '撤销 / 重做' },
      { keys: 'Ctrl + A', desc: '全选节点' },
      { keys: 'Ctrl + C', desc: '复制选中节点与内部连线（跨组件连线不复制）' },
      { keys: 'Ctrl + V', desc: '粘贴（整体偏移 24px）' },
      { keys: 'Ctrl + D', desc: '原位复制（偏移 0）' },
      { keys: 'Del / Backspace', desc: '删除选中节点 / 连线' },
      { keys: '方向键', desc: '微移选中节点 1px（Shift = 10px 网格步长）' },
      { keys: 'F2', desc: '重命名选中节点（恰好选中一个时）' },
    ],
  },
]
</script>

<template>
  <div class="sh-help">
    <section v-for="g in groups" :key="g.cap" class="sh-sec">
      <div class="sh-cap">{{ g.cap }}</div>
      <div v-for="it in g.items" :key="it.keys" class="sh-row">
        <span class="sh-keys">{{ it.keys }}</span>
        <span class="sh-desc">{{ it.desc }}</span>
      </div>
    </section>
  </div>
</template>

<style scoped>
.sh-help{padding:14px 16px;font-size:12.5px;color:var(--text-1,#1e293b)}
.sh-sec+.sh-sec{margin-top:14px}
.sh-cap{font-size:11px;font-weight:700;color:var(--text-3,#94a3b8);letter-spacing:.08em;margin-bottom:6px}
.sh-row{display:flex;align-items:center;gap:10px;padding:4px 6px;border-radius:var(--radius-sm,6px)}
.sh-row:hover{background:var(--bg,#f5f7fa)}
.sh-keys{flex:none;min-width:150px;font-family:var(--mono,monospace);font-size:11px;color:var(--primary,#2563eb);background:var(--primary-light,rgba(37,99,235,.08));border:1px solid var(--border-strong,#cbd5e1);border-radius:4px;padding:1px 7px;text-align:center}
.sh-desc{color:var(--text-2,#475569)}
</style>
