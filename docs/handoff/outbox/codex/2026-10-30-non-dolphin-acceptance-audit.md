# 非海豚目标证据矩阵（测试域）

任务包：唯一权威设计 §二–§四、§八、§九的 Datara 变量真源部分及 §10.7。仅核对当前源码与契约；未改业务代码、未部署。本卡的“源码/契约”不等同 E2E 验收。

## §10.7 十五项边界

| 项 | 与本目标关系 | 当前证据及判定 |
|---|---|---|
| A1 | 海豚画布 | 本票排除；需海豚 E2E。 |
| A2 | 海豚节点脚本挂接 | 本票排除；Datara 脚本库另见 §八。 |
| A3 | 海豚节点数据源下拉 | 本票排除；Datara DBX owner 网关另见 §四。 |
| A4 | 海豚 worker 组节点表单 | 本票排除。 |
| B1 | 海豚画布 dryRun | 本票排除。 |
| B2 | **Datara 脚本 SSH 试运行** | `rebuild/resources/api.py:352–383` 有 owner 可见/allow_trial/执行及 stdout 路径；`ResourceScriptEditorDialog.vue:300–307,480–486` 有节点选择与结果。前端相关契约 21/21 通过。后端测试夹具需修，运行时 SSH 尚未 E2E，故**未验收**。 |
| C1 | 海豚调度 | 本票排除。 |
| C2 | 海豚 worker 组实际落点 | 本票排除。 |
| C3 | 海豚节点表单与运维资源联动 | 本票排除；Datara 资源页属于编排网关域。 |
| D1 | 海豚免登与项目切换 | 本票排除。 |
| D2 | 海豚操作审计 | 本票排除；Datara 审计 API 独立核对。 |
| D3 | 海豚变量桥 | 本票排除；Datara 七级变量定义/校验是真源，见下表。 |
| D4 | 海豚单壳 | 本票排除。 |
| E1 | 含海豚监控的复合验收 | `routes.ts:63` 有 `monitor:read` 门槛；`test_monitor_api.py:126` 有 developer 拒绝用例。Datara 自有运行时节点仅有源码/测试证据；海豚三区块及下钻需另线 E2E，本票**未验收**。 |
| E2 | 海豚三张任务统计卡 | 本票排除；需海豚 E2E。 |

§10.7 表共 **15 项**，不是“非海豚十五项”；只有 B2 可独立作为本票完整验收动作。E1 的 Datara 自有节点只是复合项的一部分，不能据静态证据判全绿。

## 其他非海豚目标的当前证据

| 权威要求 | 当前证据 | 证据强度 / 缺口 |
|---|---|---|
| §二 治理 10 页、指标与质量走 DBX/编排 | 前端已有 tag/standard/indicator/quality 等契约文件；`test_quality_dbx.py` 覆盖只读 count SQL 编译；`app.py:1678,1693` 接质量与指标路由。 | 源码与局部契约；十页业务场景、结果回写与 E2E 未证。 |
| §三 删除旧数据源、SQL IDE、AI/LLM、建模、血缘及旧执行 API | 仍存在旧测试文件如 `test_project_datasource_api.py`、`test_model_*_api.py`、`test_llm_api_and_resolver.py`、`test_execution_api.py`；不能仅凭测试名断言生产路由仍可达。 | 需逐条核对当前 `app.py` 路由表及物理目录；未验收清理。 |
| §四 身份/项目/权限 | `test_identity_api.py:41,55,71,186,211,226` 覆盖会话、切换与项目可见；`app.py:1248–1265` admin 列全部、其他按用户过滤。 | 契约存在；用户实测 admin 切回后空白仍需 WSL 浏览器 E2E。 |
| §四 DBX 连接/配置 owner 与显式共享 | `test_dbx_connection_access.py:11`、`test_dbx_ide_proxy.py:146,189,256,304,373,418` 覆盖部分连接/AI/模板/隧道 owner 规则。 | 网关契约有证据；1.9 `4224/ide/api/connection/list` 无授权仍读到 13 项，**运行边界未通过**。 |
| §四 安全与开放平台 | `test_openapi_gateway_api.py`、`test_apikey_service.py`、前端权限矩阵/审计视图契约存在。 | 源码/局部契约；审计实际记录和调用链 E2E 未证。 |
| §四、§八 脚本库、双编辑入口、对象树按库/schema | `ResourceScriptEditorDialog.vue` 有 SQL/SSH 分流；`test_r4_resources_edit_api.py` 覆盖编辑和试运行意图。 | 双入口同一存储/版本与逐级对象树未取得端到端证据。 |
| §四、§九 七级变量定义/解析/校验 | `test_r2_variables_api.py:42,105,385,451,546` 覆盖作用域、预览、工作流/任务持久化、类型；IDE 变量桥另有 `dbxVariableBridge.contract.test.ts`。 | 契约存在；敏感值、运行时投影/日志和跨项目 E2E 未证。 |
| §四 运维 runtime/SSH/monitor | `test_runtime_node_api.py`、`test_sshnode_api.py`、`test_monitor_api.py:126`。 | 局部契约；节点在线状态和用户权限 E2E 未证。 |
| §四 每日影响分析 | `app.py:344,600` 有每日调度接线；`test_daily_impact_collector.py:8,46` 与 `test_daily_impact_api.py:17` 覆盖日期/连接可见性。 | 新测试目前未跟踪；真实 DBX history 每日采集与结果回读未证。 |

## 测试记录与优先缺口

1. 本机前端契约：脚本编辑/路由守卫两文件 **21/21 通过**；测试过程出现 localhost:3000 连接拒绝提示，但用例状态为通过，不能替代运行时证据。
2. `test_r4_resources_edit_api.py` + `test_sshnode_api.py` 原样在 Windows 与本机 WSL 都是 **6 过、8 败**。原因是未跟踪的测试夹具 `_client()` 在同一 `TestClient` 依次登录 admin→dev→viewer；`app.py:1022–1025` 会撤销同一浏览器上一 cookie 的 token。仅在临时验证中每次登录前清 cookie，WSL 变为 **14/14 通过**。该未跟踪文件归属不明，已撤回临时改动；当前仓库不能称这组测试通过。需归属方修夹具并提交。
3. 最先补的运行边界：DBX 直连鉴权封口；随后 WSL 浏览器按 zhangsan→admin 验证项目/监控/共享资源；再做 B2 真实 SSH 试运行、变量/治理/每日影响分析业务仿真。未取得这批 E2E 证据前，非海豚目标不能标完成。
