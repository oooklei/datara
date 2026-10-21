# 9-03 ScheduleDialog 定时调度尾随配置组件 — Trae 实施证据

> 票面（拆票登记 L67 原文）：`ScheduleDialog 尾随配置组件（双视图/cron 即时预览/四字段表单校验/上线/下线）｜组件测试：枚举白名单、maxRunning≥1、预览未通过禁提交、初始 offline 回显｜待增量 7（后置 9-02）｜Trae｜否(9.1)｜校验基线=后端 validate_policies（misfire/concurrency 枚举、priority 钳 1-5、failRetry≥0/≥1）`
> 前置链（L186）：9-02 已 PASS；本票 9-03 后置 9-04/9-05。
> 基线 commit：`6a2f327`（监督线笔34：FE-6+Codex 四组验收收口，s307/s308 登记）

## 1. 交付面（2 新件 + 1 登记）

| 件 | 类型 | 说明 |
|---|---|---|
| `datara-newweb/src/components/ScheduleDialog.vue` | 新建组件 | 手工模态壳（Teleport+v-if mask+@click.self+role="dialog" aria-modal，沿 DetailDrawer 范式；禁 el-dialog——vitest happy-dom 无 ElementPlus 插件不可测） |
| `datara-newweb/src/components/__tests__/scheduleDialog.contract.test.ts` | 新建测试 | 12 用例（验收锚四条全覆盖+钳位/toggle 双向/回填/delete/close） |
| `datara-newweb/src/services/rebuild/CONTRACT_REGISTRY.md` | §3 登记 | 新增「9-03 回归」行；组件票消费已冻结契约 `scheduleCrudApi.ts`（#14），契约面零变更，不新增 §1 行 |

## 2. 组件实现要点

- **双视图**：列表视图（新建定时/六列表格：名称/crontab/状态 pill/优先级/失败重试/操作三键 edit+toggle+delete）↔ 表单视图（12 字段+预览区），`editing/editId` 切换，沿旧蓝本 `datara-web/src/views/dag/ScheduleDialog.vue` 行为语义。
- **cron 即时预览**：crontab input `@change="doPreview"`（VTU setValue 实证 input+change 双触发，行为合法）；POST `/rebuild/crontab-preview` 携 `{projectId, crontab, timezone}`（契约 `previewCrontab`）；`valid===false` → previewErr『crontab 表达式无效，请检查后重试』；预览未通过禁提交（submitForm 复查 previewErr+preview===null 时自动补预览）。
- **四字段表单校验（镜像后端 `rebuild/scheduling/api.py` normalized() 门链顺序）**：
  - crontab 非空 → misfire 白名单 `{FIRE_ONCE,SKIP,FIRE_ALL_LIMITED}` → concurrency 白名单 `{ALLOW,FORBID,QUEUE}` → maxRunningInstances **拒绝语义 UI 阻断不钳位**（`Math.trunc(Number())`+`Number.isFinite`+`<1` 拒，对应后端 int 拒/≥1 拒）→ 钳位三连：`priority = min(5, max(1, trunc(Number(priority) || 3)))`、`failRetryTimes = max(0, trunc(Number(...) || 0))`、`failRetryInterval = max(1, trunc(Number(...) || 60))`——精确镜像后端 Python `or` 语义（`0 or 60 → 60`，falsy 同构，测试实证）。
- **上线/下线**：`toggleState(row)` 按 row.state 调 offlineSchedule/onlineSchedule，成功 `Object.assign(row, updated)` 原位刷新。
- **初始 offline**：新建走 `createSchedule`，成功消息 `定时已创建（初始下线），下次触发：${result.nextFireTimes?.[0] ?? '-'}`（ScheduleMutationResult.nextFireTimes 消费）。
- **响应式契约工厂**：`api = computed(() => createScheduleCrudContract(props.projectId))`；watch `[modelValue, wf, projectId]` immediate，开启时 reload 列表。
- **T55 SKIP 语义阻塞边界（§5A.4/§7.2 八门）**：UI 可开发、契约可接线、不宣告融合——组件不设 SKIP 断言占位，归 9-05。
- **9-04 分工边界**：本票纯组件不带入口；行内「定时」按钮+画布顶栏接线归 9-04（两入口同一对话框单实例复用）。
- data-test 锚全集 24 枚（create-btn/name/crontab/preview-btn/preview-list/preview-err/priority/worker-group/misfire/concurrency/max-running/retry-times/retry-interval/timezone/start-time/end-time/toggle-btn/edit-btn/delete-btn/save-btn/back-btn/state-pill/list-loading/list-empty/close-btn）。

## 3. 测试：12 用例 ↔ 验收锚对照

| # | 用例 | 票面验收锚 |
|---|---|---|
| ① | misfire/concurrency option values 精确断言 `['FIRE_ONCE','SKIP','FIRE_ALL_LIMITED']` / `['ALLOW','FORBID','QUEUE']` | 锚① 枚举白名单 |
| ② | maxRunning=0 → warning『最大并行实例数需为不小于 1 的整数』+create/update not called | 锚② maxRunning≥1 |
| ③a | 空 crontab → warning+不调 create | 锚③ 预览未通过禁提交 |
| ③b | previewCrontab {valid:false} → preview-err 渲染+save 阻断 | 锚③ |
| ③c | 未预览直接 save → 自动补预览 1 次+阻断 | 锚③ |
| ④ | 创建成功 → 消息含『初始下线』+nextFireTimes 时间→回列表 state-pill『已下线』 | 锚④ 初始 offline 回显 |
| ⑤ | create payload 钳位（priority 99→5/retryTimes -5→0/interval -3→1+默认值） | 票面校验基线 |
| ⑥⑦ | toggle online→offlineSchedule(5)/offline→onlineSchedule(6)+pill 翻转 | 上线/下线 |
| ⑧ | openEdit 12 字段回填断言+updateSchedule(11, payload) toMatchObject | 双视图/编辑 |
| ⑨ | delete → confirm+deleteSchedule(21)+reload | 上线/下线配套 |
| ⑩ | close-btn → emitted update:modelValue [false]+closed 挂载不重复拉列表 | 模态壳 |

## 4. 三绿门

| 门 | 结果 |
|---|---|
| `vue-tsc -b` | EXIT=0 零错 |
| `npx vitest run` 全量 | **527 passed / 0 failed（48 测试文件）**（FE-7 基线 515/47 递增 +12，零退化；+12 全为本票测试件） |
| `npm run build` | 通过（947ms） |

## 5. s280② 报验三件套

- 基线 commit：`6a2f327`
- 报验文件清单（4 件）与逐件 SHA256（全量 64 位）：见 outbox/trae/tr-done-29 信体（落笔时点实测）。

## 6. 待验证边界

- 9-04 接线（行内按钮+画布顶栏入口）后置；后端联调/E2E 归 1.9 验证栈（Playwright 归 1.9 侧 E2E 票）；T55 SKIP 断言占位归 9-05。
