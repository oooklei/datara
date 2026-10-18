# P2-2-FUSION-1-B：原版 SQLIDE A1–A8 UI 吸收清单

- 日期：2026-10-19；范围：只形成 UI 承接与验收建议，不改页面、代码或 A5。
- 输入：P1-7 §4 A1–A8；FUSION-0 §3；冻结 A5 SQL IDE 契约 v1.0。
- 阶段约束：分阶段混合集成方案 §4 将正式前端重构列为 Phase 3；其启动须等待后端冻结及设计 §10 门禁（API、数据模型、节点、变量、执行状态、统计、时间戳协议冻结，试运行和正式运行验收通过）。平台重建设计 §1.2 仅豁免已批准的三项菜单展示调整，不能据此解冻 SQL IDE 页面。本清单不构成页面实施授权。
- 映射说明：下列文件是当前可定位的候选承接面；凡描述为“拟承接/建议目标”的交互均未声称已实现。具体路由、键位冲突和可用能力须在 Phase 3 立项时核实。DBX 提供交互参照；身份、授权、变量、数据源、审计和运行关联仍由 Datara 定义，任何 driver 能力以真实证据为准。

| 项 | 拟承接点（均为目标映射，非功能已实现声明） | 时机 | Phase 3 验收标准（冻结边界内） |
|---|---|---|---|
| A1 悬浮表/视图生成 SQL | datara-web/src/views/ide/components/ExplorerTree.vue 对象树选择 + SqlEditor.vue 编辑器；在对象上下文提供生成入口。 | Phase 3 的对象树/编辑器切片，后端门禁通过后。 | 对象须用完整 ObjectRef；只向编辑器插入可审阅草稿，绝不自动执行。定义读取服从 A5 §1、#18 的 capability；执行仍走 #9 完整预检和只读门。无能力时明确显示未知/不支持状态，不能伪造成功。 |
| A2 结果 Tab 回显 SQL与单元格复制 | ResultPanel.vue 结果区、HistoryDrawer.vue 历史入口；结果视图关联原 history/statement。 | Phase 3 结果与历史切片。 | 每个结果按 A5 #12/#13 的 history/result 引用回显对应语句；多语句索引不串位。单元格复制只写用户剪贴板，不修改目标库；过期快照按契约反馈，不偷偷重跑 SQL。 |
| A3 Ctrl+Enter / Ctrl+S / Ctrl+Shift+F | IdeView.vue 协调快捷键，SqlEditor.vue 处理编辑器动作；键位作为待核实目标。 | Phase 3 交互与无障碍/冲突验收切片。 | Ctrl+Enter 调用既有执行流程，仍执行 A5 #9 授权、全批预检、只读及顺序执行约束；Ctrl+S 保存为平台脚本并遵守 #16 revision/CAS 与 ACL；Ctrl+Shift+F 仅本地格式化，不新增后端 API、不执行 SQL。输入控件聚焦冲突及平台快捷键须有明确行为。 |
| A4 结果页间漂移提示 | ResultPanel.vue 分页/结果区；提示与结果快照身份绑定。 | Phase 3 分页和结果状态呈现切片。 | 提示能区分“同一不可变结果快照的分页”与“另一次执行/另一 history”；A5 #12 同一快照分页不得被说成结果漂移。不得宣称数据库事务快照隔离；过期或缺失依 A5 expiresAt/域错误显示。 |
| A5 服务端重放分页 | ResultPanel.vue 结果分页，通过正式 service facade（候选 datara-web/src/services/ideApi.ts）接入。 | Phase 3 结果数据切片；需有对应后端能力实证。 | A5 #12 的页请求读取固定 history/resultSet 快照；翻页不得重新执行 SQL或切换快照。尊重 cursor/page 和过期语义；无快照/能力时显示契约错误，不以本地缓存假装服务端证据。 |
| A6 变量分色与分类补全 | SqlEditor.vue 编辑器装饰/补全，变量候选可由 IDE 上下文提供但以 R2 为准。 | Phase 3 编辑器与变量协议切片，待变量协议门通过。 | 语法着色/补全仅辅助输入；作用域、解析和 run snapshot 完全服从 R2 与 A5 §4，不由 UI 推断变量值。不得把解析值写入普通日志、SQL 历史、事件或导出元数据；业务值展示遵循 A5 §1 的 Q11 裁定。 |
| A7 失败即停、警告收集与取消标记 | IdeView.vue 执行状态协调 + ResultPanel.vue 逐语句状态/警告/取消反馈。 | Phase 3 执行生命周期切片，完成 task/SSE/cancel 协议实测后。 | 前端呈现 A5 §4 的终态和逐语句结果；预检失败时首条目标 SQL 尚未执行，多语句按冻结顺序，失败行为遵循 partial_failure；取消只在服务端确认的状态下显示为已取消。连接回收、SSE 重连和终态以服务端证据为准，不复制旧 api/ide.py 语义。 |
| A8 独立数据源中心 | 复用既有候选页面 views/datasource/DataSourceListView.vue、DataSourceDetailView.vue、DataSourceWizard.vue；IDE InstanceBar.vue 仅选择/显示上下文并导航至中心。 | 数据源中心本身按现有授权持续治理；IDE 集成入口随 Phase 3。 | 数据源只在 Datara 中心创建/管理并受项目授权；IDE 消费已批准的 datasourceId（A5 #1–#9），不复制数据源真源、凭据管理或授权判断。切换上下文需明确，拒绝/失效由服务端反馈；不得因 UI 标签宣称某 operation supported。 |

## 验收与范围收口

- 上表每项实现前均须由 Phase 3 立项确认具体页面目标与交互；当前组件路径只证明有候选承接位置，不证明目标交互已经存在。
- Phase 3 任何测试以冻结 A5 v1.0、R2 变量契约、Datara 权限/审计主权边界为判定；DBX UI 只供交互参考。若参考行为与 Datara 冻结契约冲突，保留 Datara 契约语义并将差异记录为显式取舍。
- 不纳入 SQL IDE 页面即时改造、编辑器内核替换、目标库 DML、R5-B DDL 人工闸绕过、DBX 桌面壳/本地文件行为或未经真实运行证据的 capability 升级。
