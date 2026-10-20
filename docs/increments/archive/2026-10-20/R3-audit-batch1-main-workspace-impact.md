# R3 稽核批次 1（D: 权威工作区补做）开始前影响分析

> 状态：PASS（本地源码、远端单服务退役、Playwright 控件闭环已完成）；本文件针对 `D:\需求\数据治理工具\Datara` 当前内容取证，不把 C: worktree 中的 PASS 记录当作本目录已完成。
> 时间：2026-10-14 Asia/Shanghai；本机只做静态/逻辑检查，运行资源仅在 `192.168.1.9`。

## 1. 上一批次与触发原因

R3-S7 治理验证页已完成控件/UI/DB/时间戳/API 日志闭环，但整体 R3 仍 PARTIAL。质量审核指出旧质量 API 清理在 D: 主目录未落地。C: `worktree/2d99` 有独立提交 `b092c80`，但它并非 D: `main` 的祖先，本批以 D: 工作区为准。批次 1 后续已完成本地源码移除、独立提交、远端仅 datara-api 退役与同页 Playwright 验收；本批 PASS 不表示整体 R3 完成。

## 2. 影响范围与安全边界

- 本批源码变更范围为 `datara-backend/api/qc.py`、其唯一执行器 `datara-backend/common/qc_engine.py`，以及运行副本 `api/main.py` 的 `qc` import/include 两处；本地已提交 `1cb03f8`，远端差异经备份文件 `diff` 验证恰好只有上述两行路由移除。
- `common/models.py` 内 `QcRule/QcTask/QcRun/QcException/QcReport/QcAlarmPolicy` 六类 ORM 保留；不删除数据库表、行、迁移、远端旧资产或质量前端页面/路由。
- `api/std.py` / `std_engine.py`、`Std*` ORM 与 `std` 路由不属于本批；标准模块提前进入旧 Backend 的原因与范围在第 4 节说明，不借此放大正式前端功能范围。
- 远端只读核验（2026-10-14 19:37 +08:00，并复核到 21:20）：`datara-api` running/healthy，旧 API health=UP，OpenAPI 中 QC 路由 18 条；`datara-rebuild-api` running/healthy，治理路由 11 条，近 10 分钟错误标记均为 0。六张 `t_qc_*` 表均存在且行数均为 0。查询参数虽为 `--since=168h`，实际保留窗口只有约 8.5 小时（API 日志首行为 2026-10-14 12:48 +08:00），该窗口 API 与 Web access log 均未命中 QC 路由；不可表述为完整 7 日无调用。
- `datara-api` 的 8000 端口绑定 `0.0.0.0`，Uvicorn 启动命令未禁用 access log；因此已检索到的窗口具备请求日志，但不能覆盖更早历史或窗口外调用。
- 全仓库直接搜索未发现业务代码调用 `/api/v1/qc/*`；QC 前端 `/qc/*` 路由仍保留并标记为 demo，页面主要经 `dataStore` 工作。同仓库扫描和当前日志窗口均未发现消费者，但仍不能证明窗口外/内网外部调用方完全不存在。
- D: committed `api/main.py` 原本没有 `qc` 注册；本地源码保留该基线，远端旧源有注册时只移除两处注册并删除两份已备份的 QC 实现文件。新镜像基于 `/lei/datara` 运行源构建，只重建 `datara-api`；其余共用镜像服务、Web、Master/Worker、重建治理 API、DB 与中间件均未重启。
- R3 重建治理 API `rebuild/governance/*` 独立提供质量规则定义及真实运行历史查询，本批不删除、不改写该实现。

## 3. 前置引用盘点

实施前需完成只读 `rg` 引用扫描：除 `api/qc.py` 内对 `common.qc_engine.rule_sql` 的引用，以及相应无效 router 两行外，不得有生产代码依赖；测试若直接绑定废弃路由，则标注为旧 API 覆盖并移除/改由重建治理 API 覆盖。扫描必须确认 Qc ORM 定义仍完整存在。发现真实生产调用或页面必须依赖旧路由时暂停本批并更新设计/计划，不以强删绕过。

## 4. 标准模块提前实现原因与裁定边界

标准模块提前实现是为承接既有 I22 标准资产、已批准的 `/std/*` 路由退出 demo 标记及现场演示/功能实测，不代表新 Backend 冻结门禁被绕过。D-1=B 豁免仅限 `App.vue` 菜单分组和 `routes.ts` 路由展示元信息；标准页面的功能、API、表单和交互仍属于旧系统资产承接工作，不作为新 Backend 的运行时依赖，也不解冻其他正式前端改造。证据以项目内 2026-10-13 现场演示/功能实测报告及 I18-I19 实现核验为依据；本批不改这些页面。

## 5. 步骤与验收

1. `git show HEAD:datara-backend/api/main.py` 与现工作树差异核验，精确确认待撤销的 `qc` 两行；只读扫描 API、worker、测试和重建模块的 import。
2. 静态确认六类 Qc ORM 存在且映射表名不变；记录基线文件与差异。
3. 本地删除两份旧源文件、撤销 `api/main.py` 的旧 QC 注册；不改 std/ORM/数据库。已完成本地源码变更，但须与远端退役状态分开验收。
4. 本机 `pytest tests -q`、Ruff 对本批相关源、`compileall`、import 扫描和 `git diff --check`。
5. 192.168.1.9 只读核验旧 `datara-api`、旧 QC 路由、表行数和重建治理 API；若发现旧路由仍挂载或调用方不明，保持不部署并提交裁定。
6. 更新台账及证据；本地源码与测试已独立提交 `1cb03f8`，随后完成远端单服务更新、路由归零和浏览器控件级验收。

## 6. 停止条件

部署前核实：仓库无调用方、QC 表为空、实际约 8.5 小时留存窗口无命中、变更只影响 `datara-api`，且已保存旧源码与镜像回滚点。按用户已下发的源码移除工作单及继续执行指令，可回滚地退役了旧路由；全过程无 DROP、无远端表/行删除，保留 `Qc*` ORM/表/数据、重建治理 API 与 QC 前端 demo 页面。部署后 API health=UP、OpenAPI QC routes=0，原标准和工作流路由仍在，其他容器健康，目标 18091 页面控件级 Playwright 21/21、browser errors=0，详见 `evidence/R3/batch1-postdeploy-20261014.txt`。

## 7. 完成记录

- 本地 commit：`1cb03f8 fix(qc): remove unmounted legacy quality engine`；全 Backend `pytest tests -q` 583 passed，相关 Ruff/compileall/git diff 检查通过。
- 远端：旧镜像保留标签 `datara-backend:pre-qc-retirement-1cb03f8`（旧 ID `7ee19bc…`）；新镜像 ID `43e5f556…`。API 启动健康，QC OpenAPI 路由 0，标准路由 24，实例/调度路由存在；重建治理 API 11 路由 healthy；所有核验容器健康、近 10 分钟错误标记 0。六张 QC 表均保留且各 0 行。
- UI：browser-use 两次无法绑定现有 tab（Tab not found），按约切换 Playwright 到同一 `http://192.168.1.9:18091/rebuild-validation-r3.html`。首轮 20 个业务断言通过但 console 将预期 QC 404 误报；收窄监听到该请求窗口后复跑，Run `R3V-20261014132741-7af32d` 21/21 PASS、errors=0。精确响应及截图在 R3 evidence 目录。
- 远端容器请求日志出现 2 条 `/api/v1/qc/rules`，逐条确认均为上述浏览器退役探针，状态 404，不是业务消费；部署前历史覆盖仅约 8.5 小时，非七天。旧日志及更早外部流量无法追溯，保留旧镜像可按需快速回滚。
