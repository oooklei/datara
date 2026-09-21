<script setup lang="ts">
/**
 * IdeView（I10 §5.1 壳）：可视化数据开发 IDE 完整版布局根。
 * - 顶部：左侧资源树收缩开关 + InstanceBar（实例/属性卡/env/模式/全局参数/历史/主题/快捷键）
 * - splitpanes 左右分割（左=ExplorerTree 可收缩，右=上下分割 SqlEditor / ResultPanel）
 * - 承接 GlobalParamDrawer / HistoryDrawer / 快捷键帮助弹窗
 * - 主题：ideStore.theme 驱动 .ide-dark / .ide-light 局部 CSS 变量（--ide-*，不影响 IDE 之外页面）
 * 契约与口径见 docs/increments/I10-设计文档.md §5/§6。
 */
import { onMounted, ref } from 'vue'
import { Splitpanes, Pane } from 'splitpanes'
import 'splitpanes/dist/splitpanes.css'
import { useIdeStore } from '../../stores/ideStore'
import InstanceBar from './components/InstanceBar.vue'
import ExplorerTree from './components/ExplorerTree.vue'
import SqlEditor from './components/SqlEditor.vue'
import ResultPanel from './components/ResultPanel.vue'
import GlobalParamDrawer from './components/GlobalParamDrawer.vue'
import HistoryDrawer from './components/HistoryDrawer.vue'

const store = useIdeStore()

const leftCollapsed = ref(false)
const paramsVisible = ref(false)
const historyVisible = ref(false)
const shortcutsVisible = ref(false)

/* 缺陷3 修复：IDE 挂载即预加载全局参数（三分组），未开抽屉时 ${var} 补全/提示也有数据 */
onMounted(() => {
  void store.loadGlobalParams()
})

function toggleLeft(): void {
  leftCollapsed.value = !leftCollapsed.value
}

const SHORTCUTS = [
  { keys: 'Ctrl + Enter', desc: '运行 SQL（选中片段则仅执行片段）' },
  { keys: 'Ctrl + S', desc: '保存脚本（未命名则提示命名）' },
  { keys: 'Ctrl + Shift + F', desc: '格式化 SQL' },
  { keys: '——', desc: '悬浮表/视图可展开 11 项操作菜单（仅生成 SQL，不自动执行）' },
  { keys: '——', desc: '点击结果 Tab 回显原始 SQL；单元格点击复制值' },
]
</script>

<template>
  <div class="ide-root" :class="store.theme === 'datara-light' ? 'ide-light' : 'ide-dark'">
    <!-- 顶部操作条（按钮置顶） -->
    <div class="ide-topline">
      <button
        class="op-btn"
        :title="leftCollapsed ? '展开资源树' : '收起资源树'"
        @click="toggleLeft"
      >{{ leftCollapsed ? '⇥ 资源树' : '⇤ 收起' }}</button>
      <InstanceBar
        @open-params="paramsVisible = true"
        @open-history="historyVisible = true"
        @show-shortcuts="shortcutsVisible = true"
      />
    </div>

    <!-- 主区：左右分割 -->
    <splitpanes class="ide-split ide-main" :push-other-panes="false">
      <pane v-if="!leftCollapsed" :size="24" min-size="10" max-size="45">
        <ExplorerTree />
      </pane>
      <pane>
        <!-- 右区：上下分割 -->
        <splitpanes class="ide-split ide-right" horizontal>
          <pane :size="56" min-size="20">
            <SqlEditor />
          </pane>
          <pane :size="44" min-size="20">
            <ResultPanel />
          </pane>
        </splitpanes>
      </pane>
    </splitpanes>

    <GlobalParamDrawer v-model="paramsVisible" />
    <HistoryDrawer v-model="historyVisible" />

    <!-- 快捷键帮助 -->
    <el-dialog v-model="shortcutsVisible" title="快捷键与操作提示" width="460px" append-to-body>
      <div class="sc-list">
        <div v-for="s in SHORTCUTS" :key="s.keys + s.desc" class="sc-row">
          <kbd v-if="s.keys !== '——'" class="mono">{{ s.keys }}</kbd>
          <span class="sc-desc">{{ s.desc }}</span>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
/* ===== IDE 局部主题变量（深色默认，延续原 IDE 视觉；不影响 IDE 之外页面） ===== */
.ide-root{
  /* 深色（默认） */
  --ide-card:#12161d;
  --ide-bg:#0e1116;
  --ide-border:#242b37;
  --ide-border-strong:#333d4e;
  --ide-text:#e6ebf4;
  --ide-text-2:#b8c2d4;
  --ide-text-3:#7e889d;
  --ide-hover:#1b2330;
  --ide-input:#0e1116;
  --ide-warn:#e8a33d;
  --ide-warn-bg:rgba(232,163,61,.12);

  height:100%;
  min-height:520px;
  display:flex;
  flex-direction:column;
  background:var(--ide-bg);
  color:var(--ide-text);
  overflow:hidden;
}
.ide-root.ide-light{
  --ide-card:#ffffff;
  --ide-bg:#f5f7fa;
  --ide-border:#e7eaf0;
  --ide-border-strong:#d3d9e3;
  --ide-text:#1f2430;
  --ide-text-2:#5b6478;
  --ide-text-3:#8c94a6;
  --ide-hover:#f0f3f8;
  --ide-input:#ffffff;
  --ide-warn:#d97706;
  --ide-warn-bg:#fdf3e0;
}

.ide-topline{display:flex;align-items:flex-start;flex-shrink:0}
.ide-topline > .op-btn{margin:8px 0 0 10px;flex-shrink:0}
.ide-topline > :last-child{flex:1;min-width:0}

.ide-main{flex:1;min-height:0}

/* 分割条（窄条 + 悬停高亮） */
.ide-split > .splitpanes__splitter{background:var(--ide-border);position:relative;z-index:5}
.ide-split.splitpanes--vertical > .splitpanes__splitter{width:5px}
.ide-split.splitpanes--horizontal > .splitpanes__splitter{height:5px}
.ide-split > .splitpanes__splitter:hover,
.ide-split > .splitpanes__splitter.is-dragging{background:var(--primary)}

/* 快捷键弹窗 */
.sc-list{display:flex;flex-direction:column;gap:9px;font-size:12.5px}
.sc-row{display:flex;align-items:center;gap:10px}
.sc-row kbd{border:1px solid var(--ide-border-strong);background:var(--ide-bg);border-radius:4px;padding:2px 8px;font-size:11.5px;color:var(--ide-text);min-width:110px;text-align:center}
.sc-desc{color:var(--ide-text-2)}
</style>
