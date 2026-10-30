# 合并收口与七项核查待办（2026-10-30）

> 范围：codex 真源合并收口 + 用户新增 7 项任务核查。权威序：用户最新裁定 > `docs/designs/2026-10-29-dbx-unified-target-design.md`（唯一实施权威）> `docs/agents/协作规程.md` > 其余文档。

## 一、合并收口现状（结论）

- **main = 唯一真源**，共 6 个提交落库：`afe301d6`（codex 代码落地）/ `33359052`（权威归档）/ `71ea54e5`（设计四件）/ `08442aad`（i19-i20 收口并入）/ `6ae557f3`（DAG 目录修复并入）/ `aec73ba8`（登录撤销 bug 修复）。
- 22 个 `codex/*` 分支全保留；`backup/pre-consolidation-20261030` 指向合并前基线 `561000d7`。
- 13 个分支已全量并入（branch_only=0）；9 个判定被 main 超越或目标退役未并入，其中 `codex/correction-plan` 为唯一实质争议项（177 个独有文件，见待办 #2）。
- 合并验证：前端 `vue-tsc -b` ✅、`npm run build` ✅；后端 `compileall` ✅、`create_app` 导入 ✅、治理聚焦 42 passed ✅。
- **合并引入的登录撤销回归已定位并修复**（`aec73ba8`）：`app.py` 登录时无条件撤销上一 cookie 的 token，跨账号切换会连带注销他人会话，导致测试夹具与真实账号切换连锁失败；修复为校验 token 归属后才撤销。修复后 `test_r4_resources_edit_api.py + test_r8a_run_sql_port.py` **43/43 通过**。
- 全量 `tests/rebuild`：1398 passed / 8 skipped / 188 failed；其中 ≥39 个经基线 worktree（`561000d7`）比对确认**为基线固有失败、与合并无回归关系**（明细见待办 #3）。

## 二、七项核查结果

| # | 任务 | 判定 | 已完成 | 未完成 |
|---|---|---|---|---|
| 1 | zhangsan 未授权空白页核查 | ⚠️ 部分 | 前端账号切换竞态修复（`21e70ba5`+`1835fe4` 恢复误删）+ 契约测试 2/2；WSL E2E 退出码 0：dev 无监控入口、匿名 IDE API 401、切回 admin 恢复、token 不入持久存储、页面异常 0；设计对齐证据 `app.py:1248-1265` 项目按用户过滤、`routes.ts:63` `monitor:read` 门槛 | ① DBX 1.9 直连 `4224/ide/api/connection/list` 无授权仍读到 13 项连接，owner 绕过未封闭；② zhangsan 本人凭据未实测（E2E 仅用现有 dev/admin）；③ 1.9 已部署版本是否含账号切换修复未核查 |
| 2 | 变量/资源/治理全面验证 | ⚠️ 部分 | 源码/契约级证据矩阵完成（`docs/handoff/outbox/codex/2026-10-30-non-dolphin-acceptance-audit.md`，§10.7 十五项边界逐项判定）；变量 API 五处契约覆盖；脚本/路由守卫前端契约 21/21；登录 bug 修复后资源编辑+脚本试运行 43/43 | B2 SSH 真实试运行 E2E、治理十页逐项业务场景运行、每日影响分析真实采集、敏感值/运行时投影 E2E、DBX owner 网关运行边界均未取得运行证据 |
| 3 | 清除验证数据 | ⚠️ 部分 | 清理界限冻结（`docs/research/2026-10-30-ecommerce-governance-simulation.md` §4：仅专用命名空间、先列清单核对引用）；WSL E2E 未产生业务数据 | 治理对象（标签/规则/标准/指标/报告/告警）缺删除 API，项目删除不保证治理 FK 级联；仅有变量具备可清理导入（`infra/fixtures/business/import_ecommerce_sim_variables.py`） |
| 4 | 电商仿真体系数据构建 | ⚠️ 部分 | 业务依据文档（8 环节闭环 + 模块×场景×验收表 + 统一口径正反样本，全部一手外部引用）；独立命名空间生成器 `ecommerce_core_simulation.py` + `ECOM_SIM_20261030.json`（3/3 测试）；导入脚本（7/7 测试）；API 契约审计表 | 样本尚未导入 DBX/Datara；现 infra 数据不足以检验跨日/分仓/部分履约/部分退款/复购（research §2 缺口清单待补）；「所有选项非空」与合成回执两项已上报待裁定（research §5） |
| 5 | 全网调研与功能分析 | ⚠️ 部分 | 一手调研完成并嵌入文档（Google/Stripe/Shopify/GS1/dbt/OpenLineage/NIST/Atlas）；12 条会议条目×电商场景×当前承载方式映射矩阵 + 四类归类规则（原样/变通/降级/超预期/未覆盖） | 12 条映射行状态词全部待运行验证回填（规则明确：不凭菜单或数据非空推断）；现有 25 万订单/20 万支付/1.5 万退款的复用核对未做 |
| 6 | 仿真核心功能注解文档 | ⚠️ 部分 | `core-annotation-simulation-map.md`（注解五条逐条追溯 + 六条后端重构落实 + 逻辑差异处理）；`customer-requirements-consolidated.md` 四材料去重 11 条 | 注解表「当前核对/优先级」列的运行级证据回填；质量规则行级执行 vs 结构校验 0 行的判定未出 |
| 7 | 实现与诠释规则遵守 | ✅ 规则落地 | 不硬编码未实现功能 → 状态填写规则；AI 助手由 dbx AI 承载、不恢复自研 AI/不新增 OpenMetadata/DataHub/Vanna；三份会议文档已完成数字化归并（matrix + consolidated） | 四类归类的实际判定依赖任务 4/5 的仿真运行（动态约束，非独立工作项） |

## 三、最终待办列表

### A. 合并与测试收口（合并线）

1. **correction-plan 178 独有文件裁定**（🚫 用户裁决）：`codex/correction-plan` 约 25k 行旧并行实现（execution/coordinator/dispatcher、sync、workflows、dependency 旧架构 + 60+ 测试 + 调试脚本），目标模块已被权威设计 §三/§七 P4 裁定退役并由 main 新架构（orchestration/dbx/sshnode）替代。按「与权威设计冲突→暂停候批」上报两选一：维持不并入 / 指定子集并入。
2. **测试基线债修复（≈39 例固有失败，三组）**：
   - a) auth gate 语义边界类（`403==401`/`200==401`/`404==401`，涉及 workflow_domain/trial_snapshot/schedule/runtime_node/datasource/dependency/sync/resources/r2_variables/execution 等）：按设计 §四 路由契约统一期望后修测试或路由；
   - b) trial runner 2 例（`FAILED==SUCCEEDED`，`test_trial_e2e.py`、`test_trial_runner_extensions.py`）；
   - c) sql_ide 路由矩阵 3 例（`28==24` 计数、`sqlIdeApi.ts` 已删导致 FileNotFoundError，`test_sql_ide_route_coverage_matrix.py`）：对齐设计 §三 后删除或改写该测试文件。
   验收：`tests/rebuild` 全量 0 failed（环境噪音除外）。
3. **前端/文档对标残留**（合并前置已解除，可开工）：旧后端 datara-web 归档、前端删除残留清理、模板中心 tab 删除、告警与 SLA 适配、`/task-group` 路由死链、§9.5 变量投影、§四 路由命名核实（此前对标清单 A-G 组 19 条名目）。

### B. zhangsan 权限链路收口（核查任务 1/2 遗留）

4. **DBX 1.9 直连鉴权封口**：`4224/ide/api/connection/list` 无授权仍返回 13 项连接；owner 门禁按设计 §四 落到 DBX 运行边界，验收以匿名/无授权返回 401+空集为准。
5. **zhangsan 本人凭据 E2E**：未授权全页面受限空态 → 授权/共享后仅指定资源可见 → 撤销共享立即失效 → 切回 admin 全量恢复；在 WSL `18121` 用 Playwright 复测。
6. **1.9 部署版本核查**：确认 `18091` 已部署镜像含账号切换修复（`21e70ba5`/`1835fe4`）与登录撤销修复（`aec73ba8`），不含则重建镜像。

### C. 仿真落地（核查任务 2-7 遗留）

7. **治理清理契约补齐**：标签/规则/标准/指标/报告/告警补删除 API + 项目删除治理 FK 级联（否则任务 3 的清理无法闭环）；验收以「专用命名空间一键清理后零残留」为准。
8. **仿真样本导入执行**：WSL 隔离环境先只读盘点 project 33 已授权连接与治理对象 → 专用命名空间导入 `ECOM_SIM_20261030.json` 与变量样本 → 逐模块运行对账。
9. **矩阵逐项运行与状态回填**：按 `customer-meeting-simulation-matrix.md` 12 行逐项运行，回填四类归类（原样/变通/降级/超预期），证据对齐权威 §10.7 十五项。
10. **质量规则行级执行判定**：现运行器仅结构校验 0 行；依目标设计质量执行要求裁定是否补行级执行，判定后回填注解映射表。
11. **电商业务事实补齐**：按 research §2 清单补 SKU/规格、库存地点状态、浏览/加购事件、支付尝试历史、履约轨迹、退货行、活动数据（带 `fixture_namespace`，复用 25 万订单基线优先）。
12. **B2 SSH 真实试运行 E2E**：授权 SSH 节点上跑 SQL/Python/Shell 三类脚本试运行，stdout/来源/共享逐项核验（`rebuild/resources/api.py:352-383` 运行时证据）。

### D. 裁定与文档定稿（核查任务 4/6 遗留）

13. **仿真特殊项裁定**（🚫 用户裁决）：① GTIN/物流承运商/支付回执用明示合成标注（不冒称真实回执）是否认可；② 无真实资源场景呈现说明性空态+补配入口，不伪造可运行资源——超出此边界需用户裁定。
14. **注解矩阵运行证据回填 + 「本次不实施」清单固化**：任务 9 完成后回填 `core-annotation-simulation-map.md` 全表，冻结「旧注解提及但本次不实施」边界，形成最终版交差材料。

## 四、执行顺序建议

A1 裁定（阻塞项）→ B4-6（权限链路，验证环境前提）→ C7-8（契约+导入，仿真前提）→ C9-12（逐项运行）→ D13-14（定稿）；A2/A3 与 B/C 并行推进。
