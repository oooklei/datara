<template>
  <main class="ide-page" aria-label="数据开发IDE">
    <header class="ide-head">
      <div>
        <h1>数据开发 IDE</h1>
        <p>对象树（数据源 · 库 · Schema · 表/视图/例程 · 字段/索引）→ 编写 SQL（含变量引用）→ 执行 → 结果网格 → 历史。</p>
      </div>
      <div class="ide-actions">
        <button type="button" data-variable-manage :disabled="projectId === null" @click="variableManagementOpen = true">变量管理</button>
        <button type="button" data-execute :disabled="!canExecute" @click="runSql">
          {{ executing ? '执行中…' : '执行' }}
        </button>
        <button type="button" data-cancel :disabled="!executing || cancelBusy" @click="cancelRun">{{ cancelBusy ? '取消中…' : '取消' }}</button>
      </div>
    </header>

    <!-- 错误横幅独立于内容态：加载失败不丢上下文，执行失败保留编辑器 -->
    <p v-if="error" role="alert" data-error>{{ error }}</p>
    <p v-if="contractError" role="alert" data-contract-error>{{ contractError }}</p>
    <p v-if="status" role="status" data-status>{{ status }}</p>
    <p v-if="projectId === null" data-no-project>请先选择项目</p>

    <Splitpanes v-else class="ide-split" data-ide-workspace @resized="onIdeResize('workspace', $event)">
      <Pane :size="ideSplit.workspace[0]">
      <aside class="ide-left" data-object-panel>
        <section>
          <h2>对象树</h2>
          <label class="ide-search">搜索对象
            <input v-model.trim="keyword" data-search-input placeholder="表 / 视图 / 例程名"
                   @keyup.enter="runSearch" />
          </label>
          <button type="button" data-search :disabled="keyword === '' || datasourceId === null" @click="runSearch">搜索</button>
          <p v-if="treeCapability" class="ide-cap" data-capability>能力分级：{{ treeCapability }}</p>
          <p v-if="treeConstraints.length" class="ide-muted">{{ treeConstraints.join('；') }}</p>
        </section>

        <!-- S9 树根节点化（用户裁定 2026-10-28）：无数据源选择器；根节点 = 当前用户
             有权限访问的全部数据源；点击根节点切换执行上下文；展开时后端逐级鉴权，
             403 节点提示"无权限访问该数据源"且不可展开；默认展开第一个根节点。 -->
        <p v-if="tree.length === 0" class="ide-muted" data-tree-empty>暂无有权限数据源</p>
        <ul v-else class="ide-tree" data-object-tree>
          <li v-for="item in visibleNodes" :key="item.node.meta.key">
            <button type="button"
                    :data-tree-node="item.node.meta.key"
                    :data-node-kind="item.node.meta.kind"
                    :class="{ active: item.node.meta.key === activeNodeKey, denied: item.node.denied }"
                    :style="{ paddingLeft: `${item.depth * 14 + 8}px` }"
                    @click="onNodeClick(item.node)"
                    @mouseenter="onTreeNodeEnter(item.node, $event)"
                    @mouseleave="scheduleMenuHide">
              <span class="ide-tree-arrow">{{ item.node.meta.expandable ? (item.node.expanded ? '▾' : '▸') : '' }}</span>
              <span class="ide-tree-label">{{ item.node.meta.label }}<small v-if="kindLabel(item.node.meta.kind)">{{ kindLabel(item.node.meta.kind) }}</small></span>
              <span v-if="item.node.loading" class="ide-muted">加载中…</span>
              <span v-else-if="item.node.denied" class="ide-denied" data-node-denied>{{ item.node.deniedText }}</span>
            </button>
          </li>
        </ul>

        <p v-if="searched.length" class="ide-search-result" data-search-result>
          <button v-for="s in searched" :key="`${s.local ? 'l' : 'r'}.${s.kind}.${s.name}`" type="button"
                  :data-search-hit="s.name" :disabled="s.kind !== 'table' && s.kind !== 'view'"
                  @click="fillFromSearch(s)">
            {{ s.name }}<small>{{ s.kind }}</small><small v-if="s.local" class="ide-loaded">已加载</small>
          </button>
        </p>
      </aside>
      </Pane>

      <Pane :size="ideSplit.workspace[1]">
      <section class="ide-right">
        <Splitpanes horizontal class="ide-editor-split" @resized="onIdeResize('editor', $event)">
        <Pane :size="ideSplit.editor[0]">
        <div class="ide-editor-pane">
        <!-- S2 多 Tab 脚本会话（对标审计-03 G16）：未命名 Tab 存 sessionStorage（上限 5），
             命名 Tab 绑定后端 scripts API；关闭当前 Tab 切邻位；同 scriptId 复用。 -->
        <div class="ide-script-tabs" data-script-tabs>
          <span v-for="t in scriptTabs" :key="t.id" class="ide-script-tab" :class="{ active: t.id === activeScriptTabId }">
            <button type="button" :data-script-tab="t.id" :title="t.name" @click="activateScriptTab(t.id)">
              {{ t.name }}<small v-if="t.scriptId === null">未保存</small>
            </button>
            <button type="button" class="ide-tab-close" :data-tab-close="t.id" aria-label="关闭脚本页" @click.stop="closeScriptTab(t.id)">×</button>
          </span>
          <button type="button" data-script-tab-new @click="newScriptTab">＋ 新建</button>
        </div>
        <div class="ide-editor-head">
          <span class="ide-editor-title">SQL</span>
          <button type="button" data-sample-query title="填充示例查询（不自动执行）" @click="fillSampleQuery">示例查询</button>
          <button type="button" data-lint :disabled="sqlText.trim() === '' || datasourceId === null" @click="runLint">语法检查</button>
          <button type="button" data-format :disabled="sqlText.trim() === ''" @click="formatCurrentSql">格式化</button>
          <button type="button" data-var-check :disabled="varCheckBusy || projectId === null || sqlText.trim() === ''" @click="checkVariableReferences">
            {{ varCheckBusy ? '变量校验中…' : '变量校验' }}
          </button>
          <button type="button" data-var-complete :disabled="projectId === null" @click="toggleVarSuggestions">插入变量</button>
          <button type="button" data-save-script :disabled="sqlText.trim() === ''" @click="saveScript">存为脚本</button>
          <button type="button" data-export :disabled="lastResultSetId === null || exportBusy" @click="exportCurrent">{{ exportBusy ? '导出中…' : '导出结果' }}</button>
          <button type="button" data-lineage :disabled="projectId === null" @click="openLineage">查看血缘</button>
        </div>
        <SqlCodeEditor
          ref="sqlEditorEl"
          v-model="sqlText"
          placeholder="SELECT … -- 支持变量引用"
          :variables="editorVariables"
          :relation-names="relationNames"
          :lint-provider="editorLintProvider"
          :hover-provider="editorHoverProvider"
        />

        <p v-if="diagnostics.length" class="ide-diag" data-diagnostics>
          <span v-for="(d, i) in diagnostics" :key="i" :class="['pill', d.severity]">
            L{{ d.line }}:{{ d.col }} {{ d.severity }} {{ d.code }} — {{ d.message }}
          </span>
        </p>
        <p v-if="varCheckError" class="ide-err" data-var-check-error>变量校验失败：{{ varCheckError }}</p>
        <p v-else-if="varCheckResult" class="ide-diag" data-var-check-result>
          <span :class="['pill', varCheckResult.status]">
            {{ varCheckResult.status === 'valid' ? '变量校验通过' : '变量校验未通过' }}
          </span>
          <span v-for="(d, i) in varCheckResult.diagnostics" :key="i" :class="['pill', varCheckResult.status]">
            {{ d.code }} {{ d.label }} — {{ d.message }}
          </span>
        </p>

        <section v-if="varRefs.length || varErrors.length" class="ide-vars" data-vars>
          <h3>变量引用</h3>
          <p v-for="v in varRefs" :key="`${v.scope}.${v.name}`" class="ide-var">
            <code>${{ `${v.scope}.${v.name}` }}</code>
            <span v-if="varValues[`${v.scope}.${v.name}`] !== undefined">
              → {{ varValues[`${v.scope}.${v.name}`] ?? '（不可解析）' }}
            </span>
          </p>
          <p v-for="e in varErrors" :key="e" class="ide-err" data-var-error>{{ e }}</p>
          <p v-if="varTimes.length" class="ide-muted">时间表达式：{{ varTimes.join('，') }}</p>
        </section>

        <section v-if="varSuggestionsOpen" class="ide-var-suggestions" data-var-suggestions>
          <h3>插入变量引用</h3>
          <p v-if="varSuggestions.length === 0" class="ide-muted">当前项目暂无可用变量</p>
          <ul v-else>
            <li v-for="s in varSuggestions" :key="`${s.scope}.${s.name}`">
              <button type="button" data-var-suggestion @click="insertVariableRef(s)">
                <code>${{ `${s.scope}.${s.name}` }}</code><small>{{ s.valueType }}</small>
              </button>
            </li>
          </ul>
        </section>
        </div>
        </Pane>

        <Pane :size="ideSplit.editor[1]">
        <div class="ide-results-pane" :data-result-column-count="resultColumns.length">
        <!-- S3 按语句独立结果 Tab（对标审计-03 G17）：结果 #N / DML #N / 错误；
             title=原始 SQL，seq 每次运行重置，点击 Tab 回显该语句 SQL。 -->
        <div v-if="resultTabs.length" class="ide-result-tabs" data-result-tabs>
          <button v-for="t in resultTabs" :key="t.key" type="button"
                  :data-result-tab="t.key" :title="t.sql"
                  :class="{ active: t.key === activeResultTabKey }"
                  @click="activateResultTab(t)">{{ t.title }}</button>
        </div>
        <section v-if="activeResultTab" class="ide-result" data-result-grid>
          <header class="ide-result-head">
            <span v-if="activeResultTab.kind === 'dml'" data-result-affected>受影响行数：{{ activeResultTab.affected ?? 0 }} · {{ activeResultTab.elapsedMs }}ms</span>
            <template v-else>
              <span class="ide-muted" data-result-meta>共 {{ resultRowsTotal }} 行 · 已取 {{ resultRows.length }} 行</span>
              <span class="ide-result-nav">
                <button type="button" :disabled="resultPage <= 1" @click="changePage(resultPage - 1)">上一页</button>
                <span data-result-page>第 {{ resultPage }} 页</span>
                <button type="button" :disabled="!resultHasMore" @click="changePage(resultPage + 1)">下一页</button>
                <select v-model.number="resultPageSize" data-page-size aria-label="每页行数" @change="onPageSizeChange">
                  <option v-for="size in RESULT_PAGE_SIZES" :key="size" :value="size">{{ size }} 行/页</option>
                </select>
              </span>
            </template>
            <button v-if="activeResultTab.kind === 'dml'" type="button" data-result-echo @click="echoTabSql(activeResultTab)">回显 SQL</button>
            <button type="button" data-export-csv :disabled="activeResultTab.kind !== 'query'" @click="exportCsv">导出 CSV</button>
          </header>
          <!-- G19 七操作符筛选：仅内存首屏，绝不触发后端 -->
          <div v-if="activeResultTab.kind === 'query'" class="ide-result-filter" data-result-filter>
            <select v-model="filterColumn" data-filter-column aria-label="筛选列">
              <option v-for="c in activeResultTab.columns" :key="c" :value="c">{{ c }}</option>
            </select>
            <select v-model="filterOp" data-filter-op aria-label="筛选操作符">
              <option value="">不筛选</option>
              <option v-for="op in FILTER_OPS" :key="op" :value="op">{{ op }}</option>
            </select>
            <input v-model="filterValue" data-filter-value
                   :disabled="filterOp === '' || filterOp === '为空' || filterOp === '非空'"
                   placeholder="筛选值（仅已取回的内存行）" />
            <button type="button" data-filter-clear @click="clearResultFilter">清除筛选</button>
            <span v-if="filterOp !== ''" class="ide-muted" data-filter-meta>内存筛选命中 {{ filteredMemoryRows.length }} 行</span>
          </div>
          <ResultGrid v-if="activeResultTab.kind === 'query'" :columns="resultColumns" :rows="resultRows" @copied="onCellCopied" />
          <p v-else-if="activeResultTab.kind === 'error'" class="ide-err" data-result-error>{{ activeResultTab.message || '执行出错' }}</p>
          <section class="ide-result-logs" data-result-logs>
            <h3>逐语句日志</h3>
            <p v-if="resultLogs.length === 0" class="ide-muted">暂无日志</p>
            <ul v-else class="ide-log-list">
              <li v-for="(log, i) in resultLogs" :key="i" data-result-log-item>
                <code>#{{ (log.stmtIndex ?? -1) + 1 }} {{ log.type ?? '-' }}/{{ log.kind ?? '-' }}</code>
                <span v-if="log.affected !== undefined">受影响 {{ log.affected }}</span>
                <span v-if="log.elapsedMs !== undefined">{{ log.elapsedMs }}ms</span>
                <span v-if="log.error" class="ide-err">{{ log.error }}</span>
              </li>
            </ul>
          </section>
        </section>
        <div v-else class="ide-result-empty">执行 SQL 后在此查看分页结果</div>
        </div>
        </Pane>
        </Splitpanes>
      </section>
      </Pane>
    </Splitpanes>

    <aside v-if="historyOpen" class="ide-history" data-history data-history-drawer>
      <header>
        <h2>执行历史</h2>
        <span class="ide-history-actions">
          <button type="button" data-history-refresh @click="loadHistory">刷新</button>
          <button type="button" data-history-toggle @click="historyOpen = false">收起</button>
        </span>
      </header>
      <div class="ide-history-filter">
        <input v-model="historyKeywordInput" data-history-keyword placeholder="关键字过滤（回车应用）" @keydown.enter="applyHistoryFilter">
      </div>
      <p v-if="historyPaged.length === 0" class="ide-muted">暂无历史</p>
      <ul v-else>
        <li v-for="(h, i) in historyPaged" :key="h.historyId">
          <button type="button" class="ide-history-item" data-history-view @click="toggleHistoryDetail(h)">
            <span class="ide-history-meta">
              <b class="ide-history-status" :class="historyStatusClass(h.status)" data-history-status>{{ h.status }}</b>
              <small>#{{ (historyPage - 1) * HISTORY_PAGE_SIZE + i + 1 }}</small>
              <small>{{ h.db ?? '默认库' }}</small>
              <small>{{ h.stmtCount }} 语句 · {{ h.elapsedMs }}ms</small>
              <small>{{ formatHistoryTime(h.createdAt) }}</small>
            </span>
            <code>{{ h.sqlText.slice(0, 60) }}</code>
          </button>
          <span class="ide-history-ops">
            <button type="button" data-history-edit @click="restoreHistory(h)">编辑</button>
            <button type="button" data-history-rerun :disabled="h.datasourceId !== datasourceId" @click="rerunHistory(h)">再执行</button>
            <button type="button" class="ide-history-del" data-history-del @click="removeHistory(h)">删除</button>
          </span>
          <div v-if="historyExpandedId === h.historyId" class="ide-history-detail" data-history-detail>
            <ol class="ide-history-stmts">
              <li v-for="d in execStmtDetails[String(h.historyId)] ?? []" :key="d.stmtIndex" data-history-stmt>
                <b>{{ d.kind === 'query' ? '查询' : d.kind === 'exec' ? '执行' : '错误' }} #{{ d.stmtIndex + 1 }}</b>
                <small v-if="d.kind === 'query'">{{ d.rowsTotal ?? 0 }} 行 · {{ d.elapsedMs }}ms</small>
                <small v-else-if="d.kind === 'exec' && d.affected !== null">affected {{ d.affected }} · {{ d.elapsedMs }}ms</small>
                <small v-else>{{ d.status }}{{ d.error ? ` · ${d.error}` : '' }}</small>
                <code>{{ d.sql.slice(0, 80) }}</code>
              </li>
            </ol>
            <p v-if="(execVarSnapshots[String(h.historyId)] ?? []).length > 0" class="ide-history-vars" data-history-vars>
              变量快照：{{ (execVarSnapshots[String(h.historyId)] ?? []).join('；') }}
            </p>
          </div>
        </li>
      </ul>
      <div v-if="historyTotalPages > 1" class="ide-history-pager">
        <button type="button" :disabled="historyPage <= 1" @click="historyPage -= 1">上一页</button>
        <span>{{ historyPage }} / {{ historyTotalPages }}</span>
        <button type="button" :disabled="historyPage >= historyTotalPages" @click="historyPage += 1">下一页</button>
      </div>
    </aside>
    <button v-else type="button" class="ide-history-open" data-history-toggle @click="openHistory">执行历史</button>

    <aside v-if="scriptsOpen" class="ide-history" data-scripts>
      <header>
        <h2>SQL 资产</h2>
        <button type="button" data-scripts-toggle @click="scriptsOpen = false">收起</button>
      </header>
      <p v-if="scripts.length === 0" class="ide-muted">暂无已保存脚本</p>
      <ul v-else>
        <li v-for="script in scripts" :key="script.id">
          <button type="button" class="ide-history-item" data-script-open @click="restoreScript(script)">
            <b>{{ script.name }}</b>
            <code>{{ script.sqlText.slice(0, 60) }}</code>
            <small>版本 {{ script.revision }}</small>
          </button>
          <button type="button" class="ide-history-del" data-script-delete @click="removeScript(script)">删除</button>
        </li>
      </ul>
    </aside>
    <button v-else type="button" class="ide-scripts-open" data-scripts-toggle @click="openScripts">SQL 资产</button>
    <!-- G10 表/视图悬浮菜单：hover 触发、teleport body、fixed 定位、260ms 延迟隐藏；
         预制 SQL 语义 = 仅填充编辑器，绝不自动执行（底部固定提示）。 -->
    <Teleport to="body">
      <div v-if="hoverMenuNode" class="ide-hover-menu" data-hover-menu
           :style="{ left: `${hoverMenuPos.x}px`, top: `${hoverMenuPos.y}px` }"
           @mouseenter="cancelMenuHide" @mouseleave="scheduleMenuHide">
        <button v-for="item in hoverMenuItems" :key="item.key" type="button"
                :data-menu-item="item.key" @click="item.run()">{{ item.label }}</button>
        <p class="ide-menu-foot">预制 SQL 仅填充编辑器，不自动执行</p>
      </div>
    </Teleport>

    <!-- §6.2 创建列（440px）：纯前端生成 ALTER，仅填充不执行 -->
    <div v-if="addColumnOpen" class="ide-dialog-mask" data-add-column-dialog @click.self="addColumnOpen = false">
      <section ref="addColumnRef" class="ide-dialog ide-dialog-form" role="dialog" aria-label="创建列" :style="addColumnDragStyle">
        <header ref="addColumnHdRef" class="ide-dialog-head" @pointerdown="onAddColumnDragStart">
          <h3>创建列 · {{ relationLabel }}</h3>
          <button type="button" @click="addColumnOpen = false">×</button>
        </header>
        <div class="ide-dialog-body ide-form-grid">
          <label>目标表<input :value="relationLabel" readonly data-target-table /></label>
          <label>字段名<input v-model.trim="addColumnForm.name" data-column-name placeholder="字段名" /></label>
          <label>类型
            <select v-model="addColumnForm.type" data-column-type>
              <option v-for="t in COLUMN_TYPES" :key="t" :value="t">{{ t }}</option>
            </select>
          </label>
          <label>长度
            <input v-model.trim="addColumnForm.length" data-column-length
                   :disabled="!lengthEnabled" placeholder="如 64" />
          </label>
          <label>默认值<input v-model="addColumnForm.defaultValue" data-column-default placeholder="可空" /></label>
          <label class="ide-form-check"><input type="checkbox" v-model="addColumnForm.nullable" data-column-nullable /> 允许 NULL</label>
        </div>
        <footer class="ide-dialog-foot">
          <button type="button" data-generate-column @click="generateAddColumn">生成 SQL</button>
        </footer>
      </section>
    </div>

    <!-- §6.3 创建索引（440px）：纯前端生成 CREATE INDEX，仅填充不执行 -->
    <div v-if="addIndexOpen" class="ide-dialog-mask" data-add-index-dialog @click.self="addIndexOpen = false">
      <section ref="addIndexRef" class="ide-dialog ide-dialog-form" role="dialog" aria-label="创建索引" :style="addIndexDragStyle">
        <header ref="addIndexHdRef" class="ide-dialog-head" @pointerdown="onAddIndexDragStart">
          <h3>创建索引 · {{ relationLabel }}</h3>
          <button type="button" @click="addIndexOpen = false">×</button>
        </header>
        <div class="ide-dialog-body ide-form-grid">
          <label>索引名<input v-model.trim="addIndexForm.name" data-index-name placeholder="idx_表名" /></label>
          <label>字段（逗号分隔）<input v-model.trim="addIndexForm.columns" data-index-columns placeholder="col1,col2" /></label>
          <label class="ide-form-check"><input type="checkbox" v-model="addIndexForm.unique" data-index-unique /> 唯一索引</label>
        </div>
        <footer class="ide-dialog-foot">
          <button type="button" data-generate-index @click="generateAddIndex">生成 SQL</button>
        </footer>
      </section>
    </div>

    <TableDataDialog v-model:open="editDataOpen" :api="api" :datasource-id="datasourceId"
                     :schema="dialogSchema" :table="dialogTable" @applied="onDialogNotice" />
    <CsvImportDialog v-model:open="csvImportOpen" :api="api" :datasource-id="datasourceId"
                     :schema="dialogSchema" :table="dialogTable" @imported="onDialogNotice" />

    <GlobalParamDrawer
      v-model="variableManagementOpen"
      :project-id="projectId ?? undefined"
    />
  </main>
</template>

<script setup lang="ts">
/**
 * 数据开发 IDE（`/ide`）。
 *
 * 契约面：`sqlIdeApi`（createSqlIdeContract，23 方法）——
 *   对象树 listDatabases/Schemas/Relations/Columns/Routines/Indexes/searchObjects、
 *   lintSql、executeSql + openEventStream(SSE) + fetchResultPage 分页、
 *   listHistory/deleteHistory、listScripts/saveScript、exportResult/getExportDownloadUrl。
 * 数据源列表复用 `datasourceApi`（createDatasourceContract.listDatasources）。
 * 唯一后端事实源为 rebuild-api(8001)；项目数据由 URL 中的 projectId 隔离。
 * 项目上下文：`/ide` 为全局模式路由（AppShell 项目模式仅覆盖 `/p/` 前缀），
 *   故项目段从 `route.params.projectId` 或 `route.query.projectId` 承接。
 * S9 树根节点化（用户裁定 2026-10-28）：对象树为单棵懒加载树，根节点 =
 *   当前用户有权限访问的全部数据源（listDatasources 项目域即权限过滤面）；
 *   点击根节点切换执行上下文；展开时后端逐级鉴权（sql_ide 路由 + datasource
 *   rb 授权），403 节点提示"无权限访问该数据源"且不可展开；默认展开第一个根。
 * 范式：CodeMirror 6 编辑器 + splitpanes 持久化工作区，业务操作仍只调用真实后端契约。
 */
import { computed, getCurrentInstance, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Pane, Splitpanes, type SplitpanesResizedPayload } from 'splitpanes'
import { format } from 'sql-formatter'
import { useDraggable } from '../../composables/useDraggable'
import GlobalParamDrawer from '../../components/VariableManagementDialog.vue'
import SqlCodeEditor from './SqlCodeEditor.vue'
import ResultGrid from './ResultGrid.vue'
import TableDataDialog from './TableDataDialog.vue'
import CsvImportDialog from './CsvImportDialog.vue'
import 'splitpanes/dist/splitpanes.css'
import {
  createSqlIdeContract,
  type DefinitionObjectKind,
  type HistoryEntry,
  type ScriptEntry,
  type SqlDiagnostic,
  type SqlDoneEvent,
  type SqlLogEvent,
  type SqlResultEvent,
  type SqlIdeContract,
} from '../../services/rebuild/sqlIdeApi'
import {
  createDatasourceContract,
  type DatasourceContract,
  type DatasourceRecord,
} from '../../services/rebuild/datasourceApi'
import {
  createVariableContract,
  parseVariableReferences,
  type VariableCompletionItem,
  type VariableContract,
} from '../../services/rebuild/variableApi'
import {
  checkVariableReferenceField,
  defineVariableReferenceField,
  type VariableReferenceCheckViewModel,
} from '../../services/rebuild/variableReferenceField'
import { listProjects, type ProjectSummary } from '../../services/rebuild/projectApi'

const props = defineProps<{ projectId?: number }>()
const route = useRoute()
const router = useRouter()

const IDE_SPLIT_KEY = 'datara.ide.split.v1'
function initialIdeSplit(): { workspace: [number, number]; editor: [number, number] } {
  try {
    const value = JSON.parse(localStorage.getItem(IDE_SPLIT_KEY) ?? '{}') as { workspace?: number[]; editor?: number[] }
    return {
      workspace: value.workspace?.length === 2 ? [value.workspace[0], value.workspace[1]] : [25, 75],
      editor: value.editor?.length === 2 ? [value.editor[0], value.editor[1]] : [58, 42],
    }
  } catch {
    return { workspace: [25, 75], editor: [58, 42] }
  }
}
const ideSplit = ref(initialIdeSplit())

function onIdeResize(area: 'workspace' | 'editor', payload: SplitpanesResizedPayload) {
  if (!Array.isArray(payload.panes) || payload.panes.length !== 2) return
  ideSplit.value = { ...ideSplit.value, [area]: [payload.panes[0].size, payload.panes[1].size] }
  localStorage.setItem(IDE_SPLIT_KEY, JSON.stringify(ideSplit.value))
}

const projects = ref<ProjectSummary[]>([])
const variableManagementOpen = ref(false)
const selected = ref('')

/* ---------- S9 对象树：根节点 = 有权限数据源，懒加载逐级展开 ---------- */

type TreeKind =
  | 'source' | 'database' | 'schema'
  | 'table' | 'view' | 'function' | 'procedure' | 'trigger'
  | 'column' | 'index'

interface TreeMeta {
  key: string
  kind: TreeKind
  label: string
  dsId: number
  db: string | null
  schema: string | null
  name: string
  expandable: boolean
}

interface TreeNode {
  meta: TreeMeta
  expanded: boolean
  loading: boolean
  denied: boolean
  deniedText: string
  children: TreeNode[]
}

type NodeInit = { kind: TreeKind; label: string; dsId: number; db?: string | null; schema?: string | null; name?: string; expandable: boolean }

function nodeKey(m: Omit<TreeMeta, 'key'>): string {
  switch (m.kind) {
    case 'source': return `source:${m.dsId}`
    case 'database': return `db:${m.dsId}:${m.label}`
    case 'schema': return `schema:${m.dsId}:${m.db}:${m.label}`
    case 'table': case 'view': return `rel:${m.dsId}:${m.db}:${m.schema}:${m.kind}:${m.label}`
    case 'function': case 'procedure': case 'trigger': return `rtn:${m.dsId}:${m.db}:${m.schema}:${m.kind}:${m.label}`
    case 'column': return `col:${m.dsId}:${m.db}:${m.schema}:${m.name}:${m.label}`
    default: return `idx:${m.dsId}:${m.db}:${m.schema}:${m.name}:${m.label}`
  }
}

function makeNode(init: NodeInit): TreeNode {
  const m = {
    kind: init.kind,
    label: init.label,
    dsId: init.dsId,
    db: init.db ?? null,
    schema: init.schema ?? null,
    name: init.name ?? init.label,
    expandable: init.expandable,
  }
  return { meta: { ...m, key: nodeKey(m) }, expanded: false, loading: false, denied: false, deniedText: '', children: [] }
}

const tree = ref<TreeNode[]>([])
const activeNodeKey = ref('')
const activeDatabase = ref('')
const activeSchema = ref('')
const activeRelation = ref('')

const visibleNodes = computed(() => {
  const out: Array<{ node: TreeNode; depth: number }> = []
  const walk = (nodes: TreeNode[], depth: number): void => {
    for (const node of nodes) {
      out.push({ node, depth })
      if (node.expanded && node.children.length > 0) walk(node.children, depth + 1)
    }
  }
  walk(tree.value, 0)
  return out
})

const KIND_LABEL: Partial<Record<TreeKind, string>> = {
  table: '表', view: '视图', function: '函数', procedure: '存储过程', trigger: '触发器', column: '字段', index: '索引',
}
const kindLabel = (k: TreeKind): string => KIND_LABEL[k] ?? ''

const searched = ref<Array<{ kind: string; name: string; parent: string | null; local: boolean }>>([])
const keyword = ref('')

const treeCapability = ref('')
const treeConstraints = ref<string[]>([])

/* ---------- S2 多 Tab 脚本会话（对标审计-03 G16）：未命名 Tab 存 sessionStorage（上限 5） ----------
 * sqlText 以 computed 代理当前活动 Tab，runSql/saveScript/格式化/变量预览等既有消费方零改动；
 * 命名 Tab 绑定后端 scripts API（scriptId+revision），Ctrl+S 命名更新、未命名转命名。 */
interface ScriptTab {
  id: string
  name: string
  sqlText: string
  scriptId: number | null
  revision: number | null
}

const UNNAMED_SCRIPTS_KEY = 'datara.ide.unnamedScripts'
const UNNAMED_SCRIPT_LIMIT = 5
let scriptTabSeq = 0
let unnamedSeq = 1
const nextScriptTabId = (): string => `script-tab-${++scriptTabSeq}`

function makeScriptTab(name: string, sql = ''): ScriptTab {
  return { id: nextScriptTabId(), name, sqlText: sql, scriptId: null, revision: null }
}

function maxUnnamedSeq(tabs: ScriptTab[]): number {
  return tabs.reduce((max, t) => {
    const m = /^未命名SQL #(\d+)$/.exec(t.name)
    return m ? Math.max(max, Number(m[1])) : max
  }, 0)
}

function loadUnnamedTabs(): { tabs: ScriptTab[]; nextSeq: number } {
  try {
    const raw = sessionStorage.getItem(UNNAMED_SCRIPTS_KEY)
    if (!raw) return { tabs: [], nextSeq: 1 }
    const saved = JSON.parse(raw) as Array<{ name?: string; sqlText?: string }>
    const tabs = (Array.isArray(saved) ? saved : [])
      .slice(-UNNAMED_SCRIPT_LIMIT)
      .map((s) => makeScriptTab(s.name ?? '未命名SQL', s.sqlText ?? ''))
    return { tabs, nextSeq: maxUnnamedSeq(tabs) + 1 }
  } catch {
    return { tabs: [], nextSeq: 1 }
  }
}

const scriptTabs = ref<ScriptTab[]>([makeScriptTab('未命名SQL #1')])
const activeScriptTabId = ref(scriptTabs.value[0].id)
const activeScriptTab = computed<ScriptTab | null>(
  () => scriptTabs.value.find((t) => t.id === activeScriptTabId.value) ?? scriptTabs.value[0] ?? null,
)

const sqlText = computed<string>({
  get: () => activeScriptTab.value?.sqlText ?? '',
  set: (value) => {
    const tab = activeScriptTab.value
    if (!tab) return
    tab.sqlText = value
    if (tab.scriptId === null) persistUnnamedTabs()
  },
})

function persistUnnamedTabs(): void {
  const unnamed = scriptTabs.value
    .filter((t) => t.scriptId === null)
    .map((t) => ({ name: t.name, sqlText: t.sqlText }))
  try {
    sessionStorage.setItem(UNNAMED_SCRIPTS_KEY, JSON.stringify(unnamed))
  } catch {
    /* 存储不可用时静默：Tab 会话仅是会话级便利 */
  }
}

function activateScriptTab(id: string): void {
  if (scriptTabs.value.some((t) => t.id === id)) activeScriptTabId.value = id
}

function newScriptTab(): void {
  if (scriptTabs.value.filter((t) => t.scriptId === null).length >= UNNAMED_SCRIPT_LIMIT) {
    status.value = `最多保留 ${UNNAMED_SCRIPT_LIMIT} 个未命名脚本，请保存或关闭后再新建`
    return
  }
  const tab = makeScriptTab(`未命名SQL #${unnamedSeq}`)
  unnamedSeq += 1
  scriptTabs.value = [...scriptTabs.value, tab]
  activeScriptTabId.value = tab.id
  persistUnnamedTabs()
}

function closeScriptTab(id: string): void {
  const index = scriptTabs.value.findIndex((t) => t.id === id)
  if (index < 0) return
  const nextTabs = scriptTabs.value.filter((t) => t.id !== id)
  if (nextTabs.length === 0) {
    unnamedSeq = 1
    const fresh = makeScriptTab('未命名SQL #1')
    scriptTabs.value = [fresh]
    activeScriptTabId.value = fresh.id
    persistUnnamedTabs()
    return
  }
  scriptTabs.value = nextTabs
  if (activeScriptTabId.value === id) {
    // 关闭当前 Tab 后切邻位：优先同位次（右侧），否则左侧
    activeScriptTabId.value = nextTabs[Math.min(index, nextTabs.length - 1)].id
  }
  persistUnnamedTabs()
}

const executing = ref(false)
const currentTaskId = ref('')
const currentEventStream = ref<EventSource | null>(null)
const cancelBusy = ref(false)
const exportBusy = ref(false)
const diagnostics = ref<SqlDiagnostic[]>([])
const contractError = ref('')
const error = ref('')
const status = ref('')

/* ---------- S3 按语句独立结果 Tab + S4 内存筛选/双分页（对标审计-03 G17-G20） ----------
 * ResultTab：query=结果网格；dml=受影响行数卡片；error=错误信息；seq 每次运行重置；
 * stmtSqlCache 缓存 sql.split(';') 语句序（§5.2 执行流）。
 * 双分页：内存页优先（SSE 首批切片）；越内存且落历史 → fetchResultPage 自内存末端续取；
 * 未落历史提示 warning。7 操作符筛选仅作用于 memoryRows，绝不触发后端。 */
interface ResultTab {
  key: string
  kind: 'query' | 'dml' | 'error'
  title: string
  sql: string
  stmtIndex: number
  resultSetId: string | null
  historyId: string | number | null
  columns: string[]
  rows: unknown[][]          // 当前展示缓冲（内存切片或重放页）
  memoryRows: unknown[][]    // SSE/同步首取批次（内存优先分页与筛选的数据面）
  rowsTotal: number
  elapsedMs: number
  affected: number | null
  message: string
  page: number
}

const RESULT_PAGE_SIZES = [100, 200, 500, 1000]
const FILTER_OPS = ['包含', '等于', '不等于', '为空', '非空', '大于', '小于'] as const

const resultTabs = ref<ResultTab[]>([])
const activeResultTabKey = ref('')
const resultLogs = ref<SqlLogEvent[]>([])
let querySeq = 0
let dmlSeq = 0
let errorSeq = 0
let stmtSqlCache: string[] = []

const activeResultTab = computed<ResultTab | null>(
  () => resultTabs.value.find((t) => t.key === activeResultTabKey.value) ?? resultTabs.value[0] ?? null,
)
const lastHistoryId = computed<string | number | null>(() => activeResultTab.value?.historyId ?? null)
const lastResultSetId = computed<string | null>(() => activeResultTab.value?.resultSetId ?? null)
const resultColumns = computed<string[]>(() => activeResultTab.value?.columns ?? [])
const resultPage = computed(() => activeResultTab.value?.page ?? 1)
const resultPageSize = ref(200)

const filterColumn = ref('')
const filterOp = ref('')
const filterValue = ref('')

function matchResultFilter(cell: unknown, op: string, needle: string): boolean {
  const text = cell === null || cell === undefined ? '' : typeof cell === 'object' ? JSON.stringify(cell) : String(cell)
  switch (op) {
    case '包含': return text.includes(needle)
    case '等于': return text === needle || (needle !== '' && text !== '' && Number(text) === Number(needle))
    case '不等于': return !(text === needle || (needle !== '' && text !== '' && Number(text) === Number(needle)))
    case '为空': return text === ''
    case '非空': return text !== ''
    case '大于': return Number.isFinite(Number(text)) && Number.isFinite(Number(needle)) && Number(text) > Number(needle)
    case '小于': return Number.isFinite(Number(text)) && Number.isFinite(Number(needle)) && Number(text) < Number(needle)
    default: return true
  }
}

const filteredMemoryRows = computed<unknown[][]>(() => {
  const tab = activeResultTab.value
  if (!tab || filterOp.value === '') return []
  const index = tab.columns.indexOf(filterColumn.value || (tab.columns[0] ?? ''))
  if (index < 0) return tab.memoryRows
  return tab.memoryRows.filter((row) => matchResultFilter(row[index], filterOp.value, filterValue.value))
})

const resultRows = computed<unknown[][]>(() => {
  const tab = activeResultTab.value
  if (!tab) return []
  if (filterOp.value !== '') {
    const start = (tab.page - 1) * resultPageSize.value
    return filteredMemoryRows.value.slice(start, start + resultPageSize.value)
  }
  return tab.rows
})

const resultRowsTotal = computed(() => {
  const tab = activeResultTab.value
  if (!tab) return 0
  if (filterOp.value !== '') return filteredMemoryRows.value.length
  return tab.rowsTotal
})

const resultHasMore = computed(() => {
  const tab = activeResultTab.value
  if (!tab) return false
  const size = resultPageSize.value
  if (filterOp.value !== '') return tab.page * size < filteredMemoryRows.value.length
  const memLen = tab.memoryRows.length
  if (tab.page * size <= memLen) return tab.page * size < tab.rowsTotal
  const shownEnd = (tab.page - 1) * size + tab.rows.length
  return Math.max(shownEnd, memLen) < tab.rowsTotal
})

function clearResultFilter(): void {
  filterOp.value = ''
  filterValue.value = ''
  const tab = activeResultTab.value
  if (tab) tab.page = 1
}

function onCellCopied(text: string): void {
  status.value = `已复制单元格：${text.slice(0, 60)}`
}

const varRefs = ref<Array<{ scope: string; name: string }>>([])
const varErrors = ref<string[]>([])
const varTimes = ref<string[]>([])
const varValues = ref<Record<string, string | null>>({})

/** §5B 变量三要求（校验按钮/现时值/补全）：本编辑器作为输入位显式登记（L5-04 契约的首个 UI 消费方）。 */
const sqlReferenceField = defineVariableReferenceField({
  surfaceId: 'ide.sql-editor',
  fieldPath: 'sql',
  label: 'SQL 编辑器',
  inputKind: 'sql',
  allowScopedReference: true,
  allowTimeExpression: true,
})
const sqlEditorEl = ref<{ insertText: (text: string) => void; focus: () => void } | null>(null)
const varCheckBusy = ref(false)
const varCheckResult = ref<VariableReferenceCheckViewModel | null>(null)
const varCheckError = ref('')
const varSuggestionsOpen = ref(false)
const varSuggestions = ref<VariableCompletionItem[]>([])

const history = ref<HistoryEntry[]>([])
const historyOpen = ref(false)

/* ---------- S8 历史抽屉（§6.7 核心子集）：关键字过滤/20 条分页/状态徽标/四操作/逐语句详情 ----------
 * 逐语句详情双源：本会话执行时捕获 SSE 日志（内存），重载条目回退 fetchResultPage(stmtIndex) 重放；
 * 变量快照 = 执行时把编辑器引用的 ${scope.name}（含现时解析值）随 historyId 存档（S7 快照回显落点）。 */
interface StatementDetail {
  stmtIndex: number
  sql: string
  kind: 'query' | 'exec' | 'error'
  status: string
  affected: number | null
  rowsTotal: number | null
  elapsedMs: number
  error: string
}
const HISTORY_PAGE_SIZE = 20
const historyKeyword = ref('')
const historyKeywordInput = ref('')
const historyPage = ref(1)
const historyExpandedId = ref<string | number | null>(null)
const execStmtDetails = ref<Record<string, StatementDetail[]>>({})
const execVarSnapshots = ref<Record<string, string[]>>({})
let pendingStmtDetails: StatementDetail[] = []
let pendingVarSnapshot: string[] = []

function recordStmtDetail(detail: StatementDetail): void {
  const at = pendingStmtDetails.findIndex((d) => d.stmtIndex === detail.stmtIndex)
  if (at >= 0) pendingStmtDetails[at] = { ...pendingStmtDetails[at], ...detail }
  else pendingStmtDetails.push(detail)
}
const scripts = ref<ScriptEntry[]>([])
const scriptsOpen = ref(false)

const message = (e: unknown): string => (e instanceof Error ? e.message : String(e))

/** 403 鉴权失败判定：SqlIdeApiError.code === 403（sql_ide PERMISSION_DENIED 包络）；ContractApiError.httpStatus === 403。 */
function isPermissionError(e: unknown): boolean {
  const code = (e as { code?: unknown } | null)?.code
  const httpStatus = (e as { httpStatus?: unknown } | null)?.httpStatus
  return code === 403 || httpStatus === 403
}

const dsApi = computed<DatasourceContract>(() =>
  projectId.value === null ? ({} as DatasourceContract) : createDatasourceContract(projectId.value),
)
const api = computed<SqlIdeContract>(() =>
  projectId.value === null ? ({} as SqlIdeContract) : createSqlIdeContract(projectId.value),
)
const varApi = computed<VariableContract>(() => createVariableContract())

/** 项目上下文：项目段注入优先，其次 route 参数/query，最后选择器。
 * ProjectSegmentView 以 prop 挂载本页；若只读取 route，会在 /p/:id/ide
 * 下退化成「请选择项目」并且不会加载数据源。 */
const routeProjectId = computed<number | null>(() => {
  const raw = route.params.projectId ?? route.query.projectId
  const value = Array.isArray(raw) ? raw[0] : raw
  const n = Number(value)
  return value !== undefined && value !== '' && Number.isInteger(n) && n > 0 ? n : null
})
const projectId = computed<number | null>(() => {
  if (Number.isInteger(props.projectId) && props.projectId! > 0) return props.projectId!
  const fromRoute = routeProjectId.value
  if (fromRoute !== null) return fromRoute
  const n = Number(selected.value)
  return selected.value !== '' && Number.isInteger(n) && n > 0 ? n : null
})
/** 执行上下文：点击根节点（source:*）切换；默认展开第一个根节点时即建立。 */
const datasourceId = ref<number | null>(null)
const canExecute = computed(() => datasourceId.value !== null && sqlText.value.trim() !== '' && !executing.value)

async function loadProjects(): Promise<void> {
  try {
    projects.value = (await listProjects()).list
  } catch (e) {
    error.value = message(e)
  }
}

/** S9：根节点 = 当前用户有权限访问的全部数据源；默认展开第一个根节点。 */
async function loadTree(): Promise<void> {
  tree.value = []
  treeCapability.value = ''
  treeConstraints.value = []
  datasourceId.value = null
  activeNodeKey.value = ''
  activeDatabase.value = ''
  activeSchema.value = ''
  activeRelation.value = ''
  if (projectId.value === null) return
  try {
    const items = (await dsApi.value.listDatasources()).items
    tree.value = items.map((d: DatasourceRecord) => makeNode({ kind: 'source', label: d.name, dsId: d.id, expandable: true }))
    if (tree.value.length > 0) {
      const first = tree.value[0]
      activateDatasource(first)
      await expandNode(first)
    }
  } catch (e) {
    error.value = message(e)
  }
}

function activateDatasource(node: TreeNode): void {
  if (datasourceId.value !== node.meta.dsId) {
    datasourceId.value = node.meta.dsId
    treeCapability.value = ''
    treeConstraints.value = []
    activeDatabase.value = ''
    activeSchema.value = ''
    activeRelation.value = ''
  }
  activeNodeKey.value = node.meta.key
}

function syncActiveContext(node: TreeNode): void {
  activeNodeKey.value = node.meta.key
  if (node.meta.kind === 'database') {
    activeDatabase.value = node.meta.name
  } else if (node.meta.kind === 'schema') {
    activeDatabase.value = node.meta.db ?? ''
    activeSchema.value = node.meta.name
  } else if (node.meta.kind === 'table' || node.meta.kind === 'view') {
    activeDatabase.value = node.meta.db ?? ''
    activeSchema.value = node.meta.schema ?? ''
    activeRelation.value = node.meta.name
  }
}

async function onNodeClick(node: TreeNode): Promise<void> {
  if (node.denied || node.loading) return
  if (!node.meta.expandable) {
    activeNodeKey.value = node.meta.key
    if (node.meta.kind === 'function' || node.meta.kind === 'procedure' || node.meta.kind === 'trigger') {
      await showDefinition(node)
    }
    return
  }
  if (node.meta.kind === 'source') activateDatasource(node)
  else syncActiveContext(node)
  if (node.expanded) {
    node.expanded = false
    return
  }
  await expandNode(node)
}

async function expandNode(node: TreeNode): Promise<void> {
  if (node.loading || node.denied || node.expanded) return
  node.loading = true
  try {
    node.children = await loadChildren(node)
    node.expanded = true
  } catch (e) {
    if (isPermissionError(e)) {
      node.denied = true
      node.deniedText = node.meta.kind === 'source' ? '无权限访问该数据源' : '无权限访问'
    } else {
      error.value = message(e)
    }
  } finally {
    node.loading = false
  }
}

async function loadChildren(node: TreeNode): Promise<TreeNode[]> {
  const m = node.meta
  if (m.kind === 'source') {
    const page = await api.value.listDatabases(m.dsId)
    if (m.dsId === datasourceId.value) {
      treeCapability.value = page.capability
      treeConstraints.value = page.constraints
    }
    return page.items.map((d) => makeNode({ kind: 'database', label: d.name, dsId: m.dsId, db: d.name, expandable: true }))
  }
  if (m.kind === 'database') {
    const page = await api.value.listSchemas(m.dsId, m.name)
    return page.items.map((s) => makeNode({ kind: 'schema', label: s.name, dsId: m.dsId, db: m.db, expandable: true }))
  }
  if (m.kind === 'schema') {
    const db = m.db ?? ''
    const [tables, views, funcs, procs, triggers] = await Promise.all([
      api.value.listRelations(m.dsId, db, m.name, 'table'),
      api.value.listRelations(m.dsId, db, m.name, 'view'),
      api.value.listRoutines(m.dsId, db, m.name, 'function'),
      api.value.listRoutines(m.dsId, db, m.name, 'procedure'),
      api.value.listRoutines(m.dsId, db, m.name, 'trigger'),
    ])
    return [
      ...[...tables.items, ...views.items].map((r) => makeNode({ kind: r.kind, label: r.name, dsId: m.dsId, db, schema: m.name, expandable: true })),
      ...[...funcs.items, ...procs.items, ...triggers.items].map((r) => makeNode({ kind: r.kind, label: r.name, dsId: m.dsId, db, schema: m.name, expandable: false })),
    ]
  }
  // table / view → 字段 + 索引（叶子）
  const [cols, idx] = await Promise.all([
    api.value.listColumns(m.dsId, m.db ?? '', m.name, m.schema ?? ''),
    api.value.listIndexes(m.dsId, m.db ?? '', m.name, m.schema ?? ''),
  ])
  return [
    ...cols.items.map((c) => makeNode({ kind: 'column', label: c.name, dsId: m.dsId, db: m.db, schema: m.schema, name: m.name, expandable: false })),
    ...idx.items.map((i) => makeNode({ kind: 'index', label: i.name, dsId: m.dsId, db: m.db, schema: m.schema, name: m.name, expandable: false })),
  ]
}

async function showDefinition(node: TreeNode): Promise<void> {
  try {
    const def = await api.value.getDefinition({
      datasourceId: node.meta.dsId,
      database: node.meta.db ?? '',
      objectKind: node.meta.kind as DefinitionObjectKind,
      objectRef: { schema: node.meta.schema ?? '', name: node.meta.name },
    })
    sqlText.value = def.definition
    status.value = `已载入定义：${node.meta.name}（${def.capability}）`
  } catch (e) {
    error.value = message(e)
  }
}

async function runSearch(): Promise<void> {
  if (datasourceId.value === null || keyword.value === '') return
  try {
    // S5 搜索合并（对标审计-03 §2.1）：后端 searchObjects（树未加载也能查）
    // + 本地已加载树节点匹配（标「已加载」），各限 50 条，本地在前。
    const page = await api.value.searchObjects(datasourceId.value, keyword.value)
    const backend = page.items
      .slice(0, 50)
      .map((o) => ({ kind: o.kind, name: o.name, parent: o.parent, local: false }))
    const needle = keyword.value.toLowerCase()
    const local: typeof backend = []
    const walk = (nodes: TreeNode[]): void => {
      for (const node of nodes) {
        const k = node.meta.kind
        if ((k === 'table' || k === 'view' || k === 'function' || k === 'procedure' || k === 'trigger')
          && node.meta.label.toLowerCase().includes(needle)) {
          local.push({ kind: k, name: node.meta.label, parent: node.meta.schema, local: true })
          if (local.length >= 50) return
        }
        if (node.expanded) walk(node.children)
      }
    }
    walk(tree.value)
    searched.value = [...local, ...backend]
  } catch (e) {
    error.value = message(e)
  }
}

/** 搜索命中行点击：仅填充 `SELECT * FROM parent.name LIMIT 100;`，不自动执行 */
function fillFromSearch(item: { kind: string; name: string; parent: string | null }): void {
  if (item.kind !== 'table' && item.kind !== 'view') return
  const parent = item.parent ?? ''
  fillEditor(parent ? `SELECT * FROM ${parent}.${item.name} LIMIT 100;` : `SELECT * FROM ${item.name} LIMIT 100;`)
}

/** G11 空态引导：一键填充示例查询（仅填充不执行）。 */
function fillSampleQuery(): void {
  fillEditor('SELECT 1 AS ok;')
}

async function runLint(): Promise<void> {
  if (datasourceId.value === null) return
  diagnostics.value = []
  try {
    diagnostics.value = await api.value.lintSql(datasourceId.value, sqlText.value)
  } catch (e) {
    error.value = message(e)
  }
}

function appendQueryTab(input: {
  stmtIndex: number
  resultSetId: string | null
  columns: string[]
  rows: unknown[][]
  memoryRows: unknown[][]
  rowsTotal: number
  elapsedMs: number
}): ResultTab {
  querySeq += 1
  const tab: ResultTab = {
    key: `q-${querySeq}`,
    kind: 'query',
    title: `结果 #${querySeq}`,
    sql: stmtSqlCache[input.stmtIndex] ?? sqlText.value,
    stmtIndex: input.stmtIndex,
    resultSetId: input.resultSetId,
    historyId: null,
    columns: input.columns,
    rows: input.rows,
    memoryRows: input.memoryRows,
    rowsTotal: input.rowsTotal,
    elapsedMs: input.elapsedMs,
    affected: null,
    message: '',
    page: 1,
  }
  resultTabs.value = [...resultTabs.value, tab]
  activeResultTabKey.value = tab.key
  return tab
}

function appendDmlTab(input: { stmtIndex: number; affected: number; elapsedMs: number; sql: string }): ResultTab {
  dmlSeq += 1
  const tab: ResultTab = {
    key: `d-${dmlSeq}`,
    kind: 'dml',
    title: `DML #${dmlSeq}`,
    sql: input.sql,
    stmtIndex: input.stmtIndex,
    resultSetId: null,
    historyId: null,
    columns: [],
    rows: [],
    memoryRows: [],
    rowsTotal: 0,
    elapsedMs: input.elapsedMs,
    affected: input.affected,
    message: '',
    page: 1,
  }
  resultTabs.value = [...resultTabs.value, tab]
  activeResultTabKey.value = tab.key
  return tab
}

function appendErrorTab(input: { stmtIndex: number; message: string; sql: string }): ResultTab {
  errorSeq += 1
  const tab: ResultTab = {
    key: `e-${errorSeq}`,
    kind: 'error',
    title: '错误',
    sql: input.sql,
    stmtIndex: input.stmtIndex,
    resultSetId: null,
    historyId: null,
    columns: [],
    rows: [],
    memoryRows: [],
    rowsTotal: 0,
    elapsedMs: 0,
    affected: null,
    message: input.message,
    page: 1,
  }
  resultTabs.value = [...resultTabs.value, tab]
  activeResultTabKey.value = tab.key
  return tab
}

function bindHistoryToTabs(historyId: string | number | null): void {
  for (const tab of resultTabs.value) tab.historyId = historyId
}

/** 点击结果 Tab：激活并回显该语句 SQL（对标审计-03 G17）。 */
function activateResultTab(tab: ResultTab): void {
  activeResultTabKey.value = tab.key
  if (tab.sql) sqlText.value = tab.sql
}

function echoTabSql(tab: ResultTab): void {
  if (tab.sql) sqlText.value = tab.sql
}

function clearResult(): void {
  resultTabs.value = []
  activeResultTabKey.value = ''
  resultLogs.value = []
  querySeq = 0
  dmlSeq = 0
  errorSeq = 0
  stmtSqlCache = sqlText.value.split(';').map((s) => s.trim())
  filterOp.value = ''
  filterValue.value = ''
}

/** G01 终态兜底：SSE 无心跳事件，断线期间用 status 端点轮询收敛，避免 executing 永久悬挂。 */
const TERMINAL_EXECUTION_STATUSES = new Set(['succeeded', 'failed', 'partial_failure', 'canceled', 'timed_out'])
const EXECUTION_POLL_MS = 2000
const EXECUTION_POLL_MAX_FAILURES = 5
const EXECUTION_LONG_WAIT_MS = 60000
let statusPollTimer: ReturnType<typeof setInterval> | null = null
let statusPollFailures = 0
let longWaitTimer: ReturnType<typeof setTimeout> | null = null

function stopStatusPolling(): void {
  if (statusPollTimer !== null) {
    clearInterval(statusPollTimer)
    statusPollTimer = null
  }
  statusPollFailures = 0
}

function clearLongWaitTimer(): void {
  if (longWaitTimer !== null) {
    clearTimeout(longWaitTimer)
    longWaitTimer = null
  }
}

function settleExecution(terminalStatus: string | null): void {
  stopStatusPolling()
  clearLongWaitTimer()
  currentEventStream.value?.close()
  currentEventStream.value = null
  executing.value = false
  if (terminalStatus === 'succeeded') {
    status.value = '执行完成（状态查询确认）；结果集请见执行历史'
  } else if (terminalStatus === 'canceled') {
    status.value = '执行已取消'
  } else if (terminalStatus !== null) {
    contractError.value = '执行失败'
  } else {
    contractError.value = '执行状态查询连续失败，已停止等待；结果可在执行历史中确认'
  }
  if (datasourceId.value !== null) void loadHistory()
}

function startStatusPolling(taskId: string): void {
  if (statusPollTimer !== null) return
  statusPollFailures = 0
  statusPollTimer = setInterval(() => {
    void (async () => {
      try {
        const result = await api.value.getExecutionStatus(taskId)
        if (!executing.value || currentTaskId.value !== taskId) {
          stopStatusPolling()
          return
        }
        statusPollFailures = 0
        if (TERMINAL_EXECUTION_STATUSES.has(result.status)) settleExecution(result.status)
      } catch {
        statusPollFailures += 1
        if (statusPollFailures >= EXECUTION_POLL_MAX_FAILURES) settleExecution(null)
      }
    })()
  }, EXECUTION_POLL_MS)
}

async function runSql(): Promise<void> {
  if (!canExecute.value) return
  executing.value = true
  contractError.value = ''
  error.value = ''
  status.value = ''
  diagnostics.value = []
  clearResult()
  // S8/S7：清空逐语句捕获缓冲，并固化变量快照（引用清单 + 现时解析值，若可得）
  pendingStmtDetails = []
  pendingVarSnapshot = varRefs.value.map((r) => {
    const key = `${r.scope}.${r.name}`
    const value = varValues.value[key]
    return value === undefined ? `\${${key}}` : `\${${key}} = ${String(value)}`
  })
  currentTaskId.value = `ide-${Date.now()}`
  try {
    const execution = await api.value.executeSql({
      datasourceId: datasourceId.value as number,
      db: activeDatabase.value || null,
      sql: sqlText.value,
      mode: 'auto',
      sessionId: currentTaskId.value,
      clientRequestId: `req-${Date.now()}`,
    })
    const { taskId } = execution
    currentTaskId.value = taskId
    if (execution.historyId !== undefined && execution.resultSetId) {
      const result = await api.value.fetchResultPage(execution.historyId, execution.resultSetId, 0, Math.min(resultPageSize.value, 500))
      appendQueryTab({
        stmtIndex: result.stmtIndex ?? 0,
        resultSetId: result.resultSetId,
        columns: result.columns,
        rows: result.rows,
        memoryRows: result.rows,
        rowsTotal: result.rowsTotal,
        elapsedMs: 0,
      })
      bindHistoryToTabs(execution.historyId)
    } else if (execution.columns?.length) {
      const rows = execution.rows ?? []
      appendQueryTab({
        stmtIndex: 0,
        resultSetId: execution.resultSetId ?? null,
        columns: execution.columns,
        rows,
        memoryRows: rows,
        rowsTotal: execution.totalRows ?? execution.rowCount ?? rows.length,
        elapsedMs: 0,
      })
      if (execution.historyId !== undefined && execution.historyId !== null) bindHistoryToTabs(execution.historyId)
    }
    openStream(taskId)
  } catch (e) {
    contractError.value = message(e)
    executing.value = false
  }
}

function openStream(taskId: string): void {
  currentEventStream.value?.close()
  stopStatusPolling()
  clearLongWaitTimer()
  const es = api.value.openEventStream(taskId)
  currentEventStream.value = es
  es.addEventListener('open', () => {
    if (status.value.startsWith('事件流连接中断')) status.value = ''
    stopStatusPolling()
  })
  es.addEventListener('result', (ev: MessageEvent) => {
    const data = JSON.parse(ev.data) as SqlResultEvent
    recordStmtDetail({
      stmtIndex: data.stmtIndex,
      sql: stmtSqlCache[data.stmtIndex] ?? '',
      kind: 'query',
      status: 'succeeded',
      affected: null,
      rowsTotal: data.rowsTotal,
      elapsedMs: data.elapsedMs,
      error: '',
    })
    appendQueryTab({
      stmtIndex: data.stmtIndex,
      resultSetId: data.resultSetId,
      columns: data.columns,
      rows: data.rows,
      memoryRows: data.rows,
      rowsTotal: data.rowsTotal,
      elapsedMs: data.elapsedMs,
    })
  })
  es.addEventListener('log', (ev: MessageEvent) => {
    // S3 逐语句日志：DML（affected）/错误语句各自成 Tab，其余进日志面板
    const data = JSON.parse(ev.data) as SqlLogEvent
    resultLogs.value = [...resultLogs.value, data]
    const stmtSql = stmtSqlCache[data.stmtIndex ?? -1] ?? sqlText.value
    if (data.type === 'error') {
      recordStmtDetail({ stmtIndex: data.stmtIndex ?? -1, sql: data.sql ?? stmtSql, kind: 'error', status: 'failed', affected: null, rowsTotal: null, elapsedMs: data.elapsedMs ?? 0, error: data.error ?? '执行出错' })
      appendErrorTab({ stmtIndex: data.stmtIndex ?? -1, message: data.error ?? '执行出错', sql: data.sql ?? stmtSql })
    } else if (data.kind === 'exec' && typeof data.affected === 'number') {
      recordStmtDetail({ stmtIndex: data.stmtIndex ?? -1, sql: data.sql ?? stmtSql, kind: 'exec', status: 'succeeded', affected: data.affected, rowsTotal: null, elapsedMs: data.elapsedMs ?? 0, error: '' })
      appendDmlTab({ stmtIndex: data.stmtIndex ?? -1, affected: data.affected, elapsedMs: data.elapsedMs ?? 0, sql: data.sql ?? stmtSql })
    }
  })
  es.addEventListener('done', async (ev: MessageEvent) => {
    es.close()
    stopStatusPolling()
    clearLongWaitTimer()
    if (currentEventStream.value === es) currentEventStream.value = null
    executing.value = false
    const wire = JSON.parse(ev.data) as SqlDoneEvent & {
      history_id?: string | number | null
      result_set_id?: string
      elapsed_ms?: number
      stmt_count?: number
    }
    const data: SqlDoneEvent = {
      ...wire,
      historyId: wire.historyId ?? wire.history_id ?? null,
      elapsedMs: wire.elapsedMs ?? wire.elapsed_ms ?? 0,
      stmtCount: wire.stmtCount ?? wire.stmt_count ?? wire.resultSets?.length ?? resultTabs.value.filter((t) => t.kind === 'query').length,
    }
    bindHistoryToTabs(data.historyId)
    // S8：落历史后固化本会话逐语句捕获与变量快照；执行 done 增量刷新回到第 1 页（§6.7）
    if (data.historyId !== null) {
      execStmtDetails.value = { ...execStmtDetails.value, [String(data.historyId)]: pendingStmtDetails }
      if (pendingVarSnapshot.length > 0) {
        execVarSnapshots.value = { ...execVarSnapshots.value, [String(data.historyId)]: pendingVarSnapshot }
      }
    }
    historyPage.value = 1
    const fallbackResultSetId = wire.result_set_id ?? data.resultSets?.[0]?.resultSetId ?? null
    if (resultTabs.value.every((t) => t.kind !== 'query') && data.historyId !== null && fallbackResultSetId) {
      try {
        const result = await api.value.fetchResultPage(data.historyId, fallbackResultSetId, 0, Math.min(resultPageSize.value, 500))
        appendQueryTab({
          stmtIndex: result.stmtIndex ?? 0,
          resultSetId: result.resultSetId,
          columns: result.columns,
          rows: result.rows,
          memoryRows: result.rows,
          rowsTotal: result.rowsTotal,
          elapsedMs: 0,
        })
      } catch (e) {
        error.value = message(e)
      }
    }
    if (data.status === 'succeeded') {
      status.value = `执行成功：${data.stmtCount} 语句 · ${data.elapsedMs}ms`
    } else if (data.status === 'canceled') {
      status.value = '执行已取消'
    } else {
      contractError.value = '执行失败'
    }
    if (datasourceId.value !== null) void loadHistory()
  })
  es.addEventListener('error', () => {
    // The authenticated SSE adapter owns Last-Event-ID replay and retries.
    // Keep this run cancellable until a terminal `done` event arrives; while
    // the stream is down, poll the status endpoint as a heartbeat fallback.
    status.value = '事件流连接中断，正在恢复…'
    startStatusPolling(taskId)
  })
  longWaitTimer = setTimeout(() => {
    if (executing.value) status.value = '执行时间较长，可点击取消；执行完成后结果将保留在执行历史'
  }, EXECUTION_LONG_WAIT_MS)
}

async function cancelRun(): Promise<void> {
  const taskId = currentTaskId.value
  if (!taskId || cancelBusy.value) return
  cancelBusy.value = true
  error.value = ''
  try {
    const result = await api.value.cancelExecution(taskId)
    if (!result.canceled) {
      status.value = '取消请求未被接受，任务仍在运行'
      return
    }
    currentEventStream.value?.close()
    currentEventStream.value = null
    stopStatusPolling()
    clearLongWaitTimer()
    executing.value = false
    currentTaskId.value = ''
    status.value = '执行已取消'
  } catch (e) {
    error.value = message(e)
  } finally {
    cancelBusy.value = false
  }
}

/** 双分页（G18）：内存页优先切片；越内存且落历史 → fetchResultPage 自内存末端按页续取；
 * 未落历史提示 warning；筛选激活时纯内存切片绝不触发后端。 */
async function changePage(page: number): Promise<void> {
  const tab = activeResultTab.value
  if (!tab) return
  const size = resultPageSize.value
  if (filterOp.value !== '') {
    const maxPage = Math.max(1, Math.ceil(filteredMemoryRows.value.length / size))
    tab.page = Math.min(Math.max(1, page), maxPage)
    return
  }
  const target = Math.max(1, page)
  const memLen = tab.memoryRows.length
  const memPages = Math.max(1, Math.ceil(memLen / size))
  if (target <= memPages) {
    tab.rows = tab.memoryRows.slice((target - 1) * size, target * size)
    tab.page = target
    return
  }
  if (tab.historyId === null || tab.resultSetId === null) {
    status.value = '当前结果未落历史，仅可浏览已取回的行'
    return
  }
  const replayLimit = Math.min(size, 500)
  const offset = memLen + (target - memPages - 1) * replayLimit
  try {
    const result = await api.value.fetchResultPage(tab.historyId, tab.resultSetId, offset, replayLimit)
    tab.rows = result.rows
    tab.columns = result.columns
    tab.rowsTotal = result.rowsTotal
    tab.page = target
  } catch (e) {
    error.value = message(e)
  }
}

function onPageSizeChange(): void {
  const tab = activeResultTab.value
  if (tab) tab.page = 1
}

/** S4 前端 CSV 导出（带 UTF-8 BOM）：导出当前 Tab 内存行（含筛选命中），不动后端契约。 */
async function exportCsv(): Promise<void> {
  const tab = activeResultTab.value
  if (!tab || tab.kind !== 'query' || exportBusy.value) return
  exportBusy.value = true
  try {
    const rows = filterOp.value !== '' ? filteredMemoryRows.value : tab.memoryRows
    const escape = (value: unknown): string => {
      const s = value === null || value === undefined ? '' : typeof value === 'object' ? JSON.stringify(value) : String(value)
      return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
    }
    const lines = [tab.columns.map(escape).join(','), ...rows.map((row) => row.map(escape).join(','))]
    const blob = new Blob(['\uFEFF' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `result-${tab.historyId ?? 'draft'}-${tab.resultSetId ?? 'local'}.csv`
    anchor.click()
    URL.revokeObjectURL(url)
    status.value = `已导出 ${rows.length} 行（CSV·UTF-8 BOM）`
  } finally {
    exportBusy.value = false
  }
}

const historyFiltered = computed(() => {
  const keyword = historyKeyword.value.trim().toLowerCase()
  if (keyword === '') return history.value
  return history.value.filter((h) =>
    h.sqlText.toLowerCase().includes(keyword) ||
    (h.db ?? '').toLowerCase().includes(keyword) ||
    h.status.toLowerCase().includes(keyword))
})
const historyTotalPages = computed(() => Math.max(1, Math.ceil(historyFiltered.value.length / HISTORY_PAGE_SIZE)))
const historyPaged = computed(() => historyFiltered.value.slice((historyPage.value - 1) * HISTORY_PAGE_SIZE, historyPage.value * HISTORY_PAGE_SIZE))

function historyStatusClass(status: string): string {
  if (status === 'succeeded') return 'is-ok'
  if (status === 'canceled' || status === 'timed_out') return 'is-warn'
  return 'is-fail'
}

function formatHistoryTime(value: string): string {
  return value.replace('T', ' ').slice(0, 19)
}

function applyHistoryFilter(): void {
  historyKeyword.value = historyKeywordInput.value
  historyPage.value = 1
}

async function loadHistory(): Promise<void> {
  if (datasourceId.value === null) return
  try {
    history.value = await api.value.listHistory(datasourceId.value)
    historyPage.value = Math.min(historyPage.value, historyTotalPages.value)
  } catch (e) {
    error.value = message(e)
  }
}

async function openHistory(): Promise<void> {
  scriptsOpen.value = false
  historyOpen.value = true
  await loadHistory()
}

/** 查看：就地展开逐语句详情；内存无捕获时按语句序 fetchResultPage(stmtIndex) 重放探测。 */
async function toggleHistoryDetail(h: HistoryEntry): Promise<void> {
  const key = String(h.historyId)
  if (historyExpandedId.value === h.historyId) {
    historyExpandedId.value = null
    return
  }
  historyExpandedId.value = h.historyId
  if (execStmtDetails.value[key]) return
  const statements = h.sqlText.split(';').map((s) => s.trim()).filter((s) => s !== '')
  const details: StatementDetail[] = []
  for (let i = 0; i < statements.length; i++) {
    try {
      const page = await api.value.fetchResultPage(h.historyId, null, 0, 1, i)
      details.push({ stmtIndex: i, sql: statements[i], kind: 'query', status: 'succeeded', affected: null, rowsTotal: page.rowsTotal, elapsedMs: 0, error: '' })
    } catch {
      details.push({ stmtIndex: i, sql: statements[i], kind: 'exec', status: h.status, affected: null, rowsTotal: null, elapsedMs: 0, error: '' })
    }
  }
  execStmtDetails.value = { ...execStmtDetails.value, [key]: details }
}

function restoreHistory(h: HistoryEntry): void {
  sqlText.value = h.sqlText
  status.value = '已载入历史 SQL 到编辑器（未执行）'
}

/** 再执行：仅当前数据源的历史可再执行（跨源先提示切换），confirm 后按当前模式重跑。 */
async function rerunHistory(h: HistoryEntry): Promise<void> {
  if (h.datasourceId !== datasourceId.value) {
    status.value = '该历史属于其他数据源，请先切换数据源'
    return
  }
  if (!confirm('按当前模式再次执行该历史 SQL？')) return
  sqlText.value = h.sqlText
  await runSql()
}

async function removeHistory(h: HistoryEntry): Promise<void> {
  if (!confirm('确认删除该条执行历史？')) return
  try {
    await api.value.deleteHistory(h.historyId)
    if (historyExpandedId.value === h.historyId) historyExpandedId.value = null
    await loadHistory()
    historyPage.value = Math.min(historyPage.value, historyTotalPages.value)
    status.value = '历史已删除'
  } catch (e) {
    error.value = message(e)
  }
}

/** S2 存脚本：命名 Tab → id+revision 更新；未命名 Tab → 新建后绑定转命名。 */
async function saveScript(): Promise<void> {
  const tab = activeScriptTab.value
  if (!tab || tab.sqlText.trim() === '') return
  try {
    if (tab.scriptId !== null) {
      const saved = await api.value.saveScript({ id: tab.scriptId, name: tab.name, sqlText: tab.sqlText, revision: tab.revision ?? undefined })
      tab.name = saved.name
      tab.scriptId = saved.id
      tab.revision = saved.revision
      status.value = `脚本已更新：${saved.name}`
    } else {
      const saved = await api.value.saveScript({ name: `脚本-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}`, sqlText: tab.sqlText })
      tab.name = saved.name
      tab.scriptId = saved.id
      tab.revision = saved.revision
      status.value = `脚本已保存：${saved.name}`
      persistUnnamedTabs()
    }
    if (scriptsOpen.value) await loadScripts()
  } catch (e) {
    error.value = message(e)
  }
}

async function loadScripts(): Promise<void> {
  try {
    scripts.value = await api.value.listScripts()
  } catch (e) {
    error.value = message(e)
  }
}

async function openScripts(): Promise<void> {
  historyOpen.value = false
  scriptsOpen.value = true
  await loadScripts()
}

/** S2 打开命名脚本：同 scriptId 复用既有 Tab（刷新内容+revision），否则新开命名 Tab。 */
function restoreScript(script: ScriptEntry): void {
  const existing = scriptTabs.value.find((t) => t.scriptId === script.id)
  if (existing) {
    existing.name = script.name
    existing.sqlText = script.sqlText
    existing.revision = script.revision
    activeScriptTabId.value = existing.id
    return
  }
  const tab = makeScriptTab(script.name, script.sqlText)
  tab.scriptId = script.id
  tab.revision = script.revision
  scriptTabs.value = [...scriptTabs.value, tab]
  activeScriptTabId.value = tab.id
}

async function removeScript(script: ScriptEntry): Promise<void> {
  try {
    await api.value.deleteScript(script.id, script.revision)
    await loadScripts()
  } catch (e) {
    error.value = message(e)
  }
}

async function exportCurrent(): Promise<void> {
  if (lastHistoryId.value === null || lastResultSetId.value === null || exportBusy.value) return
  exportBusy.value = true
  error.value = ''
  try {
    const result = await api.value.exportResult({ historyId: lastHistoryId.value, resultSetId: lastResultSetId.value, format: 'csv' })
    if (result.status === 'failed') throw new Error(`导出失败：${result.exportId}`)
    if (result.status === 'ready' || result.status === 'completed') {
      const downloadUrl = result.downloadUrl || api.value.getExportDownloadUrl(result.exportId)
      globalThis.open(downloadUrl, '_blank', 'noopener,noreferrer')
      status.value = `导出下载已打开：${result.exportId}`
    } else {
      status.value = `导出任务已创建：${result.exportId}，正在生成`
    }
  } catch (e) {
    error.value = message(e)
  } finally {
    exportBusy.value = false
  }
}

function formatCurrentSql(): void {
  try {
    sqlText.value = format(sqlText.value, { language: 'sql', keywordCase: 'upper' })
    status.value = 'SQL 格式化完成'
  } catch (e) {
    error.value = `SQL 格式化失败：${message(e)}`
  }
}

function openLineage(): void {
  if (projectId.value === null) return
  void router.push({ path: `/p/${projectId.value}/meta/lineage`, query: activeRelation.value ? { object: activeRelation.value } : {} })
}

/** 变量引用：本地语法归类 + 服务端现时解析预览（best-effort）。 */
function refreshVarPreview(): void {
  const parsed = parseVariableReferences(sqlText.value)
  varRefs.value = parsed.refs
  varErrors.value = parsed.syntaxErrors
  varTimes.value = parsed.timeExpressions
  varValues.value = {}
  if (projectId.value === null) return
  for (const ref of parsed.refs) {
    const expression = `\${${ref.scope}.${ref.name}}`
    varApi.value
      .previewResolution(expression, { projectId: projectId.value })
      .then((preview) => {
        varValues.value = { ...varValues.value, [`${ref.scope}.${ref.name}`]: preview.resolvedValue }
      })
      .catch(() => {
        varValues.value = { ...varValues.value, [`${ref.scope}.${ref.name}`]: null }
      })
  }
}

// Keep the variable reference panel in sync with edits made in the SQL editor.
// Without this watcher the initial empty editor was parsed once on mount and
// newly typed `${scope.name}` references remained invisible until a remount.
watch(sqlText, refreshVarPreview)

/** §5B 三要求·校验：显式按钮触发服务端 checkReference，诊断码+消息原样透出（§5B 显式触发语义）。 */
async function checkVariableReferences(): Promise<void> {
  if (projectId.value === null || sqlText.value.trim() === '') return
  varCheckBusy.value = true
  varCheckError.value = ''
  try {
    varCheckResult.value = await checkVariableReferenceField(
      sqlReferenceField,
      sqlText.value,
      { projectId: projectId.value },
      varApi.value,
    )
  } catch (e) {
    varCheckResult.value = null
    varCheckError.value = message(e)
  } finally {
    varCheckBusy.value = false
  }
}

/** §5B 三要求·补全：拉取当前项目可用变量清单，点选后按光标位置插入引用 token。 */
async function toggleVarSuggestions(): Promise<void> {
  varSuggestionsOpen.value = !varSuggestionsOpen.value
  if (!varSuggestionsOpen.value || projectId.value === null) return
  try {
    varSuggestions.value = await varApi.value.completeVariables('', { projectId: projectId.value })
  } catch (e) {
    error.value = message(e)
  }
}

function insertVariableRef(item: VariableCompletionItem): void {
  const token = `\${${item.scope}.${item.name}}`
  if (sqlEditorEl.value) sqlEditorEl.value.insertText(token)
  else sqlText.value = `${sqlText.value}${token}`
}

/* ---------- B4-b S1/S7：编辑器能力面数据源（补全/分色/lint 防抖/hover provider 注入） ----------
 * 变量清单驱动编辑器内 ${scope.name} 补全/分色/未定义警告（S7 六点联动的编辑器侧）；
 * lint/hover 以 provider 注入编辑器组件，后端契约仍唯一出自 sqlIdeApi/variableApi。 */
const editorVariables = ref<VariableCompletionItem[]>([])

async function loadEditorVariables(): Promise<void> {
  if (projectId.value === null) {
    editorVariables.value = []
    return
  }
  try {
    editorVariables.value = await varApi.value.completeVariables('', { projectId: projectId.value })
  } catch {
    editorVariables.value = []
  }
}

watch(projectId, () => void loadEditorVariables())

/** S1 关系补全清单：对象树已加载的关系节点（表/视图）名。 */
const relationNames = computed<string[]>(() => {
  const names = new Set<string>()
  const walk = (nodes: TreeNode[]): void => {
    for (const node of nodes) {
      if (node.meta.kind === 'table' || node.meta.kind === 'view') names.add(node.meta.label)
      if (node.children.length > 0) walk(node.children)
    }
  }
  walk(tree.value)
  return [...names]
})

const editorLintProvider = async (
  sql: string,
): Promise<Array<{ line: number; col: number; severity: 'error' | 'warning' | 'info'; message: string }>> => {
  if (datasourceId.value === null) return []
  try {
    return await api.value.lintSql(datasourceId.value, sql)
  } catch {
    return []
  }
}

const editorHoverProvider = async (expression: string): Promise<string | null> => {
  if (projectId.value === null) return null
  try {
    const preview = await varApi.value.previewResolution(expression, { projectId: projectId.value })
    return preview.resolvedValue
  } catch {
    return null
  }
}

/* ---------- §7.1.5 快捷键三件套：Ctrl+Enter 执行 / Ctrl+S 存脚本 / Ctrl+Shift+F 格式化 ----------
 * 权威键位出自旧版对标审计-03（L129/L153）：Ctrl+Enter runSql、Ctrl+S saveScript、Ctrl+Shift+F fmtSql。
 * window keydown 幂等挂载 + 实例活性守卫（后台/已卸载实例不响应）；
 * Ctrl 组合键不产生字符输入，故仅 Ctrl+Shift+F 对纯输入控件（INPUT/TEXTAREA/SELECT）退避，
 * CodeMirror 的 contentEditable 不在退避之列；Ctrl+S 始终 preventDefault 阻止浏览器保存。 */
const kaInstance = getCurrentInstance()

function onIdeKeydown(event: KeyboardEvent): void {
  const rootEl = kaInstance?.subTree?.el
  if (rootEl && !(rootEl as Node).isConnected) return
  const ctrl = event.ctrlKey || event.metaKey
  if (ctrl && !event.shiftKey && !event.altKey && event.key === 'Enter') {
    if (!canExecute.value) return
    event.preventDefault()
    void runSql()
    return
  }
  if (ctrl && !event.shiftKey && !event.altKey && (event.key === 's' || event.key === 'S')) {
    event.preventDefault()
    if (sqlText.value.trim() !== '') void saveScript()
    return
  }
  if (ctrl && event.shiftKey && (event.key === 'F' || event.key === 'f')) {
    const target = event.target as HTMLElement | null
    if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT')) return
    if (sqlText.value.trim() === '') return
    event.preventDefault()
    formatCurrentSql()
  }
}

/* ---------- G10 表/视图悬浮菜单（B4-d S5/S6，对标审计-03 §2.1/§6.2-6.5） ---------- */

const COLUMN_TYPES = ['INT', 'BIGINT', 'TINYINT', 'VARCHAR', 'CHAR', 'TEXT', 'DECIMAL', 'DATE', 'DATETIME', 'BOOLEAN'] as const
const MENU_HIDE_DELAY_MS = 260

interface MenuTarget { schema: string; table: string; label: string }

const hoverMenuNode = ref<TreeNode | null>(null)
const hoverMenuPos = ref({ x: 0, y: 0 })
let menuHideTimer: ReturnType<typeof setTimeout> | undefined

const editDataOpen = ref(false)
const csvImportOpen = ref(false)
const addColumnOpen = ref(false)
const addIndexOpen = ref(false)
const dialogSchema = ref('')
const dialogTable = ref('')
const dialogLabel = ref('')

const addColumnForm = ref({ name: '', type: 'VARCHAR', length: '', defaultValue: '', nullable: true })
const addIndexForm = ref({ name: '', columns: '', unique: false })

/* G14 §2.2：弹窗默认可拖动 + 视口钳制 + 位置记忆（把手=ide-dialog-head） */
const addColumnRef = ref<HTMLElement | null>(null)
const addColumnHdRef = ref<HTMLElement | null>(null)
const { dragStyle: addColumnDragStyle, onHandlePointerdown: onAddColumnDragStart } = useDraggable(addColumnRef, addColumnHdRef, { storageKey: 'ide.add-column' })
const addIndexRef = ref<HTMLElement | null>(null)
const addIndexHdRef = ref<HTMLElement | null>(null)
const { dragStyle: addIndexDragStyle, onHandlePointerdown: onAddIndexDragStart } = useDraggable(addIndexRef, addIndexHdRef, { storageKey: 'ide.add-index' })

const lengthEnabled = computed(() => ['VARCHAR', 'CHAR', 'DECIMAL'].includes(addColumnForm.value.type))
const relationLabel = computed(() => dialogLabel.value)

function onTreeNodeEnter(node: TreeNode, event: MouseEvent): void {
  if (node.meta.kind !== 'table' && node.meta.kind !== 'view') return
  cancelMenuHide()
  hoverMenuNode.value = node
  const x = Math.min(event.clientX + 8, window.innerWidth - 200)
  const y = Math.min(event.clientY + 8, window.innerHeight - 340)
  hoverMenuPos.value = { x: Math.max(8, x), y: Math.max(8, y) }
}

function scheduleMenuHide(): void {
  clearTimeout(menuHideTimer)
  menuHideTimer = setTimeout(() => { hoverMenuNode.value = null }, MENU_HIDE_DELAY_MS)
}

function cancelMenuHide(): void {
  clearTimeout(menuHideTimer)
}

function closeMenu(): void {
  clearTimeout(menuHideTimer)
  hoverMenuNode.value = null
}

function menuTarget(node: TreeNode): MenuTarget | null {
  const m = node.meta
  if (!m.schema) return null
  return { schema: m.schema, table: m.label, label: `${m.schema}.${m.label}` }
}

/** 所有菜单动作统一的填充语义：仅覆写编辑器内容，绝不自动执行 */
function fillEditor(sql: string): void {
  sqlText.value = sql
  closeMenu()
  status.value = '已填充 SQL（未执行）'
}

interface HoverMenuItem { key: string; label: string; run: () => void }

const hoverMenuItems = computed<HoverMenuItem[]>(() => {
  const node = hoverMenuNode.value
  if (!node) return []
  const target = menuTarget(node)
  if (!target) return []
  const openDialog = (kind: 'edit' | 'csv' | 'column' | 'index'): void => {
    dialogSchema.value = target.schema
    dialogTable.value = target.table
    dialogLabel.value = target.label
    if (kind === 'edit') editDataOpen.value = true
    else if (kind === 'csv') csvImportOpen.value = true
    else if (kind === 'column') { resetColumnForm(); addColumnOpen.value = true }
    else { resetIndexForm(); addIndexOpen.value = true }
    closeMenu()
  }
  const items: HoverMenuItem[] = [
    { key: 'select', label: '查询数据（可限定行数）', run: () => void promptSelectRows(node, target) },
    { key: 'edit', label: '编辑数据', run: () => openDialog('edit') },
    { key: 'ddl', label: '结构（DDL）', run: () => void fillDdl(node, target) },
    { key: 'count', label: '行数统计', run: () => fillEditor(`SELECT COUNT(*) AS cnt FROM ${target.schema}.${target.table};`) },
    { key: 'add-column', label: '创建列', run: () => openDialog('column') },
    { key: 'add-index', label: '创建索引', run: () => openDialog('index') },
    { key: 'csv', label: '导入数据（CSV）', run: () => openDialog('csv') },
  ]
  // DROP/TRUNCATE 仅对表开放（视图无截断语义）；无条件项同样先过稽核，
  // 差异只在 confirm 文案是否附稽核明细（对标审计-03 #8-#11）。
  if (node.meta.kind === 'table') {
    const auditAndFill = (op: 'drop' | 'truncate', withDetail: boolean): void => {
      void runDestructive(node, target, op, withDetail)
    }
    items.push(
      { key: 'drop', label: '删除表（无条件）', run: () => auditAndFill('drop', false) },
      { key: 'drop-audit', label: '删除表（稽核校验）', run: () => auditAndFill('drop', true) },
      { key: 'truncate', label: '截断表（无条件）', run: () => auditAndFill('truncate', false) },
      { key: 'truncate-audit', label: '截断表（稽核校验）', run: () => auditAndFill('truncate', true) },
    )
  }
  return items
})

async function promptSelectRows(node: TreeNode, target: MenuTarget): Promise<void> {
  const input = prompt(`查询 ${target.label}（行数上限）`, '100')
  if (input === null) return
  const rows = input.trim()
  if (!/^\d+$/.test(rows)) {
    closeMenu()
    error.value = '行数上限须为非负整数'
    return
  }
  fillEditor(`SELECT * FROM ${target.schema}.${target.table} LIMIT ${rows};`)
}

async function fillDdl(node: TreeNode, target: MenuTarget): Promise<void> {
  try {
    const def = await api.value.getDefinition({
      datasourceId: node.meta.dsId,
      database: node.meta.db ?? '',
      objectKind: node.meta.kind as DefinitionObjectKind,
      objectRef: { schema: target.schema, name: target.table },
    })
    fillEditor(`-- ${target.label} 结构\n${def.definition};`)
  } catch (e) {
    closeMenu()
    error.value = message(e)
  }
}

/** S6 稽核交互：audit pass → confirm → 仅填充；block → 硬阻断 alert */
async function runDestructive(node: TreeNode, target: MenuTarget, op: 'drop' | 'truncate', withDetail: boolean): Promise<void> {
  closeMenu()
  try {
    const audit = await api.value.auditTable({
      datasourceId: node.meta.dsId, schema: target.schema, table: target.table, op,
    })
    if (audit.status === 'block') {
      alert(`稽核未通过，已硬阻断：\n${audit.findings.map((f) => `${f.code}: ${f.message}`).join('\n')}`)
      return
    }
    const detail = withDetail
      ? `\n稽核明细：\n${audit.findings.map((f) => `- [${f.severity}] ${f.code}: ${f.message}`).join('\n')}\n`
      : ''
    const rowCount = audit.rowCount === null ? '' : `（约 ${audit.rowCount} 行）`
    const statement = op === 'drop'
      ? `DROP TABLE ${target.schema}.${target.table};`
      : `TRUNCATE TABLE ${target.schema}.${target.table};`
    if (confirm(`${op === 'drop' ? '删除' : '截断'} ${target.label}${rowCount}${detail}\n确认后仅填充 SQL，不自动执行。`)) {
      fillEditor(statement)
    }
  } catch (e) {
    error.value = message(e)
  }
}

function resetColumnForm(): void {
  addColumnForm.value = { name: '', type: 'VARCHAR', length: '', defaultValue: '', nullable: true }
}

function resetIndexForm(): void {
  addIndexForm.value = { name: '', columns: '', unique: false }
}

/** §6.2 生成 ALTER TABLE ADD COLUMN（仅填充，不执行） */
function generateAddColumn(): void {
  const name = addColumnForm.value.name
  if (!name) { error.value = '字段名不能为空'; return }
  const t = addColumnForm.value.type
  const length = addColumnForm.value.length.trim()
  const typed = (t === 'VARCHAR' || t === 'CHAR' || t === 'DECIMAL') && length !== '' ? `${t}(${length})` : t
  const nullable = addColumnForm.value.nullable ? '' : ' NOT NULL'
  const def = addColumnForm.value.defaultValue.trim()
  const defaultPart = def !== '' ? ` DEFAULT ${def}` : ''
  fillEditor(`ALTER TABLE ${dialogSchema.value}.${dialogTable.value} ADD COLUMN ${name} ${typed}${nullable}${defaultPart};`)
  addColumnOpen.value = false
}

/** §6.3 生成 CREATE [UNIQUE] INDEX（仅填充，不执行） */
function generateAddIndex(): void {
  const name = addIndexForm.value.name || `idx_${dialogTable.value}`
  const columns = addIndexForm.value.columns.split(',').map((c) => c.trim()).filter(Boolean)
  if (columns.length === 0) { error.value = '索引字段不能为空'; return }
  const unique = addIndexForm.value.unique ? 'UNIQUE ' : ''
  fillEditor(`CREATE ${unique}INDEX ${name} ON ${dialogSchema.value}.${dialogTable.value} (${columns.join(', ')});`)
  addIndexOpen.value = false
}

function onDialogNotice(text: string): void {
  status.value = text
}

function bindIdeShortcuts(): void {
  window.removeEventListener('keydown', onIdeKeydown)
  window.addEventListener('keydown', onIdeKeydown)
}

function unbindIdeShortcuts(): void {
  window.removeEventListener('keydown', onIdeKeydown)
}

onMounted(async () => {
  // S2：恢复会话内未命名脚本 Tab（上限 5，对标审计-03 G16）
  const restored = loadUnnamedTabs()
  if (restored.tabs.length > 0) {
    scriptTabs.value = restored.tabs
    activeScriptTabId.value = restored.tabs[0].id
    unnamedSeq = restored.nextSeq
  } else {
    unnamedSeq = 2
  }
  if (projectId.value !== null) selected.value = String(projectId.value)
  await loadProjects()
  await loadTree()
  void loadEditorVariables()
  refreshVarPreview()
  if (datasourceId.value !== null) await loadHistory()
  bindIdeShortcuts()
})
onUnmounted(() => {
  unbindIdeShortcuts()
  currentEventStream.value?.close()
  stopStatusPolling()
  clearLongWaitTimer()
  clearTimeout(menuHideTimer)
})
</script>

<style scoped>
/* FE-MERGE-B5: visual values come from the shared r6 token foundation. */
.ide-page{max-width:1400px;margin:auto;padding:32px 24px;color:var(--text)}
.ide-head{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.ide-head h1{margin:0}
.ide-head p{margin:4px 0 0;color:var(--text-2);flex-basis:100%;font-size:13px}
.ide-actions{display:flex;align-items:center;gap:10px;margin-left:auto;flex-wrap:wrap}
.ide-split{height:calc(100vh - 190px);min-height:520px;margin-top:16px;border:1px solid var(--border);border-radius:var(--radius);background:var(--card);overflow:hidden}
.ide-split :deep(.splitpanes__splitter){position:relative;background:var(--border);min-width:5px;min-height:5px}.ide-split :deep(.splitpanes__splitter:hover){background:var(--primary)}
.ide-left,.ide-right{height:100%;min-width:0;box-sizing:border-box;background:var(--card)}
.ide-left{padding:16px;overflow:auto}.ide-right{overflow:hidden}.ide-editor-split{height:100%}
.ide-editor-pane{height:100%;box-sizing:border-box;padding:12px;overflow:auto;display:flex;flex-direction:column}.ide-editor-pane .sql-code-editor{flex:1;min-height:220px}
.ide-results-pane{height:100%;box-sizing:border-box;padding:12px;overflow:hidden;display:flex;flex-direction:column;gap:8px}
/* S2 脚本 Tab */
.ide-script-tabs{display:flex;align-items:center;gap:4px;flex-wrap:wrap;margin-bottom:8px}
.ide-script-tab{display:inline-flex;align-items:center;border:1px solid var(--border);border-radius:var(--radius-sm);overflow:hidden}
.ide-script-tab.active{border-color:var(--primary);background:var(--primary-light)}
.ide-script-tab button{border:none;background:transparent;padding:4px 8px}
.ide-tab-close{color:var(--text-3);padding:4px 6px!important}
.ide-tab-close:hover{color:var(--danger)}
.ide-script-tabs small{margin-left:4px;color:var(--text-3);font-size:11px}
/* S3 结果 Tab */
.ide-result-tabs{display:flex;gap:4px;flex-wrap:wrap}
.ide-result-tabs button{border:1px solid var(--border);background:var(--card);border-radius:var(--radius-sm);padding:4px 10px}
.ide-result-tabs button.active{border-color:var(--primary);background:var(--primary-light)}
/* S4 筛选与日志 */
.ide-result-filter{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.ide-result-filter input{min-width:140px}
.ide-result-logs{border-top:1px solid var(--border);padding-top:6px;max-height:160px;overflow:auto}
.ide-result-logs h3{margin:0 0 4px;font-size:13px}
.ide-log-list{list-style:none;margin:0;padding:0;display:grid;gap:2px;font-size:12px}
.ide-log-list li{display:flex;gap:10px;flex-wrap:wrap}
.ide-result{flex:1;min-height:0;display:flex;flex-direction:column;gap:8px}
.ide-left h2{margin:0 0 8px;font-size:15px}
.ide-left h3{margin:16px 0 8px;font-size:13px;color:var(--text)}
.ide-search{display:flex;flex-direction:column;gap:4px;font-size:12px;color:var(--text-2)}
.ide-search input{padding:6px 8px}
.ide-cap{font-size:12px;color:var(--primary);margin:8px 0 0}
.ide-muted{color:var(--text-2);font-size:12px;margin:6px 0 0}
.ide-tree{list-style:none;padding:0;margin:0;display:grid;gap:2px;align-content:start}
.ide-tree button{width:100%;text-align:left;border:1px solid var(--border);background:var(--card);border-radius:var(--radius-sm);padding:6px 9px;cursor:pointer;display:flex;align-items:center;gap:8px}
.ide-tree button.active{border-color:var(--primary);background:var(--primary-light)}
.ide-tree button.denied{color:var(--text-3);cursor:not-allowed}
.ide-tree-arrow{flex:none;width:12px;display:inline-block}
.ide-tree-label{display:flex;align-items:center;gap:6px;min-width:0;flex:1}
.ide-tree-label small{color:var(--text-2)}
.ide-denied{flex:none;color:var(--warn);font-size:11px}
.ide-search-result{display:flex;flex-wrap:wrap;gap:6px}
.ide-search-result span{border:1px solid var(--border);border-radius:var(--radius-sm);padding:4px 8px;display:flex;flex-direction:column}
.ide-search-result small{color:var(--text-2)}
.ide-editor-head{display:flex;align-items:center;gap:10px;margin-bottom:8px}
.ide-editor-title{font-weight:600}
.ide-diag{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 0}
.pill{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;background:var(--bg-deep);color:var(--text-2)}
.pill.error,.pill.invalid{background:var(--danger-bg);color:var(--danger)}
.pill.warning{background:var(--warn-bg);color:var(--warn)}
.pill.info,.pill.valid{background:var(--info-bg);color:var(--info)}
.ide-vars{margin-top:12px;border-top:1px solid var(--border);padding-top:8px}
.ide-vars h3{margin:0 0 6px;font-size:13px}
.ide-var{display:flex;gap:8px;margin:4px 0;font-size:12px}
.ide-err{color:var(--danger);font-size:12px;margin:4px 0}
.ide-var-suggestions{margin-top:12px;border-top:1px solid var(--border);padding-top:8px}
.ide-var-suggestions h3{margin:0 0 6px;font-size:13px}
.ide-var-suggestions ul{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:6px}
.ide-var-suggestions li button{display:flex;align-items:center;gap:6px;border:1px solid var(--border);background:var(--card);border-radius:var(--radius-sm);padding:5px 9px}
.ide-var-suggestions small{color:var(--text-2)}
.ide-result-empty{display:grid;place-items:center;height:100%;color:var(--text-3);font-size:13px}
.ide-result-head{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.ide-result-nav{display:flex;align-items:center;gap:8px;margin-left:auto}
.ide-history{border:1px solid var(--border);border-radius:var(--radius);padding:16px;background:var(--card);margin-top:16px}
[data-history-drawer]{position:fixed;z-index:80;top:58px;right:0;bottom:0;width:min(420px,92vw);margin:0;border-radius:var(--radius) 0 0 var(--radius);box-shadow:var(--shadow-lg);overflow:auto}
.ide-history header{display:flex;align-items:center;justify-content:space-between}
.ide-history h2{margin:0;font-size:15px}
.ide-history-actions{display:flex;gap:6px}
.ide-history-filter{margin-top:8px}
.ide-history-filter input{width:100%;box-sizing:border-box;border:1px solid var(--border);border-radius:var(--radius-sm);padding:6px 9px;background:var(--card);color:var(--text)}
.ide-history ul{list-style:none;padding:0;margin:8px 0 0;display:grid;gap:6px}
.ide-history li{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.ide-history-item{flex:1;display:flex;flex-direction:column;gap:2px;text-align:left;border:1px solid var(--border);background:var(--card);border-radius:var(--radius-sm);padding:6px 9px;cursor:pointer}
.ide-history-meta{display:flex;flex-wrap:wrap;gap:2px 10px;align-items:baseline}
.ide-history-status{font-size:12px;padding:1px 6px;border-radius:var(--radius-sm);border:1px solid var(--border)}
.ide-history-status.is-ok{color:var(--success);border-color:var(--success)}
.ide-history-status.is-warn{color:var(--warn);border-color:var(--warn)}
.ide-history-status.is-fail{color:var(--danger);border-color:var(--danger)}
.ide-history-ops{display:flex;gap:4px;flex:none}
.ide-history-detail{flex-basis:100%;margin-top:4px;border:1px dashed var(--border);border-radius:var(--radius-sm);padding:8px;background:var(--card)}
.ide-history-stmts{margin:0;padding-left:18px;display:grid;gap:4px}
.ide-history-stmts code{display:block;color:var(--text-2)}
.ide-history-vars{margin:8px 0 0;color:var(--text-2);font-size:12px}
.ide-history-pager{display:flex;align-items:center;gap:10px;margin-top:10px}
.ide-history-del{flex:none}
.ide-history-open,.ide-scripts-open{margin-top:16px}
.mono,code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}
@media(max-width:900px){.ide-split{height:auto;min-height:0;overflow:visible}.ide-split:deep(>.splitpanes__pane){width:100%!important}.ide-split{display:block}.ide-left{max-height:320px}.ide-right{height:720px}}

/* B4-d：G10 悬浮菜单 + §6.2/§6.3 表单弹窗 */
.ide-hover-menu{position:fixed;z-index:70;display:flex;flex-direction:column;min-width:200px;background:var(--card);border:1px solid var(--border);border-radius:var(--radius);box-shadow:0 8px 24px rgba(0,0,0,.18);padding:4px}
.ide-hover-menu button{border:none;background:transparent;color:var(--text);text-align:left;padding:7px 12px;font-size:13px;cursor:pointer;border-radius:4px}
.ide-hover-menu button:hover{background:var(--primary);color:var(--card)}
.ide-menu-foot{margin:4px 8px 2px;padding-top:6px;border-top:1px solid var(--border);color:var(--text-2);font-size:11px;white-space:nowrap}
.ide-search-result{display:flex;flex-wrap:wrap;gap:6px}
.ide-search-result button{border:1px solid var(--border);background:transparent;color:var(--text);border-radius:4px;padding:2px 8px;font-size:12px;cursor:pointer}
.ide-search-result button:disabled{cursor:default;opacity:.55}
.ide-search-result .ide-loaded{color:var(--success);margin-left:4px}
.ide-dialog-mask{position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:60;display:flex;align-items:flex-start;justify-content:center}
.ide-dialog-form{background:var(--card);color:var(--text);border:1px solid var(--border);border-radius:var(--radius);margin-top:12vh;width:440px;max-width:92vw}
.ide-dialog-form .ide-dialog-head{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;border-bottom:1px solid var(--border);cursor:grab;user-select:none}
.ide-dialog-form .ide-dialog-head:active{cursor:grabbing}
.ide-dialog-form .ide-dialog-head h3{margin:0;font-size:15px}
.ide-dialog-form .ide-dialog-head button{border:none;background:transparent;color:var(--text-2);font-size:18px;cursor:pointer}
.ide-form-grid{display:flex;flex-direction:column;gap:10px;padding:14px 16px}
.ide-form-grid label{display:flex;flex-direction:column;gap:4px;font-size:12px;color:var(--text-2)}
.ide-form-grid input,.ide-form-grid select{border:1px solid var(--border);background:var(--card);color:var(--text);border-radius:4px;padding:6px 8px;font-size:13px}
.ide-form-grid input[readonly]{color:var(--text-2)}
.ide-form-check{flex-direction:row!important;align-items:center;gap:6px!important}
.ide-dialog-form .ide-dialog-foot{display:flex;justify-content:flex-end;gap:10px;padding:12px 16px;border-top:1px solid var(--border)}
</style>
