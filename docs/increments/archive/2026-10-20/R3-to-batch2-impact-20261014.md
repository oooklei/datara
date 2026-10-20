# R3 收尾 → 批次 2 影响分析与执行细化

日期：2026-10-14 Asia/Shanghai  
权威工作区：`D:\需求\数据治理工具\Datara`  
前序完成提交：`1cb03f8`（QC 旧 router/engine 源码移除）、`876e459`（远端/控件级验证证据与台账）

## 1. 前序影响核对

- QC 源码退役只改变旧 `datara-api` 的路由注册和私有实现；新治理 API、`Qc*` ORM/表、六张旧 QC 表及 QC demo 页面均保留。远端 `datara-api` health UP、QC routes=0、标准 routes=24；`datara-rebuild-api` 的 11 条治理 API 健康。批次 1 的精确范围与回滚信息见 `R3-audit-batch1-main-workspace-impact.md` 和 `evidence/R3/batch1-postdeploy-20261014.txt`。
- 该变更不会改变新 Backend 的 identity/project/datasource、DAG/SYNC、scheduler、SQL IDE 或五域治理契约；QC 运行历史必须由新治理 API 写入，旧 `/api/v1/qc/*` 不可再作为依赖。
- R3 整体仍非 PASS：I18-I23 的表/API/菜单/消费者映射、数据迁移对账、历史治理资产承接尚未完成。此项进入 R2-01/R3 后续治理审计，不因旧路由退役而视为关闭。
- R0-R11 编号及 D-1 菜单豁免不变；正式前端业务功能继续冻结；任何新增页面仍须按参考系统真实表单与操作流程验证，并只调用新 Backend。
- 远端运行资源保持 192.168.1.9；本机只运行源码、测试、文档及逻辑检查。当前环境已健康，后续如某项有功能变化，须为该功能部署单独验证页并按 R2-14 完成 UI/API/日志/资源闭环；纯文档项不触碰运行服务。

## 2. 本批范围及风险

批次 2 按已评审计划处理 R2-01—R2-15 的设计、契约、实现覆盖和证据缺口。先修订权威设计/计划并标注状态，随后逐项核查实际源码、测试与远端事实；文档中有模型定义不等于实现完成。不得在同一提交混入 I18-I23 业务功能、SYNC 执行器、datasource 实现或用户提供的 XLS/XLSX/DOCX 文件。

重点影响：

1. R2-01 治理真源与旧 I18-I23 处置将影响 R3/R5/R6/R11；只能先建立事实映射，未核实的资产不得标记迁移或废弃。
2. R2-02/03/05/08/09/10 会影响后续调度、权限、变量、流任务、AI 和冻结门禁；同一契约要写入 API/schema、测试及验收页，不重复造概念模型。
3. R2-11/12 是 R4-SYNC 的强前置；在 endpoint/mapping/checkpoint 与 datasource 契约冻结前，不应启动 SYNC 业务实现。
4. R2-04/07/15 的 SQL IDE 写路径与结果集会影响 R10-A/B，需拆开设计和执行。不得为了“补齐文档”提前执行 DDL 或开放生产写权限。
5. R2-13 使用已运行的 1.9 MySQL schema；只读核验和可回滚的专用 schema 初始化可以进行，不在本机启动替代服务，也不修改共享旧 schema。

## 3. 批次 2 执行步骤与门禁

1. 文档同源修订：设计说明 R2-01—R2-15 的边界、真源和验收；计划增加逐项状态、依赖、文件范围和停止条件；台账记录本次用户指令及前序影响。
2. 逐项证据核对：每项标为 `design-only / code-present / locally-tested / remotely-verified / UI-closed` 中的最高实证层级；没有证据不升级状态。QC 退役只给其自身 R3 子项闭环。
3. 建立 R2-01 I18-I23 遗留资产清单：从旧 migrations/models/APIs、I18-I23 文档、远端 schema 只读核实每项的表/接口/菜单/消费者/行数；先生成映射和差异报告，不写旧资产。
4. 执行新 Backend 静态稽核与本机测试：`rebuild/` 旧模块依赖扫描、AI 工具 schema/权限断言、Python 定向/全量测试、ruff 与 compileall；Vue 类型检查使用现有依赖，不安装或改动环境以伪造结果。
5. 有功能变化才部署 192.168.1.9：新验证页复现对应参考产品的控件流程，统一验证 key 在受控 runner 内交换短期 token，页面不展示登录/凭据；browser-use 失败按 R2-14 切 Playwright 同页；同步采集 API、数据库、服务日志、容器健康和截图证据。
6. 每个可独立验收的修复单独提交；提交前核对 staged diff 仅含该修复与对应证据。只在全部 15 项证据满足后，才将批次 2 标记 PASS。

## 4. 本轮执行记录

- 已完成本影响分析；当前具体推进 R2-01 的五域模型与真源展开、R2-10 实测数字刷新。此项只完成设计更新，不能据此声称 15 项修复完成。
- 本机核验：QC runner pytest `4 passed / 0.12s`、auth permission tests `13 passed / 0.13s`、`ruff check rebuild tests/rebuild api/auth.py tests/test_component_models.py` PASS、`node --check` PASS、`git diff --check` PASS；后端全量测试最近值 `584 passed / 60.91s`；控件闭环见批次 1 证据。
- 已知保留风险：浏览器桥本轮不能绑定既有 tab，采用 Playwright 同页完成 21/21。部署前请求日志仅有约 8.5 小时保留窗口，不足以证明完整 7 天没有旧 QC 调用；回滚镜像保留。
- 批次 2 状态：`IN_PROGRESS`。未提交或部署新的业务功能；未改变验证容器。
