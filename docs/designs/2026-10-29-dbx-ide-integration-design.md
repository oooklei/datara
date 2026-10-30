---
design_type: feature
created_at: 2026-10-29
---

# dbx 集成替代自研数据开发 IDE —— 设计

## Intent Contract

**intent**：将数据开发 IDE 由 datara 自研实现改为直接集成 192.168.1.9:4224 的 dbx 服务；datara 仅承担项目/环境组上下文传递、变量只读注入与数据源双入口同步，自研前端 IDE 视图归档废弃。

**constraints**：

- dbx 镜像**固定版本，禁止升级**；不重编 dbx Rust 二进制，仅对前端 dist 打补丁。
- dbx 数据源与 datara 数据源**双入口双向同步**，需新增同步适配层。
- datara 变量在 IDE 内可**提示查值并显示现值**供用户选择参考；敏感变量**脱敏展示**。
- 原自研前端 IDE 视图归档废弃；后端 `rebuild/sql_ide` 模块保留不动。
- 不改动 dbx 连接数据模型结构，不把 dbx 内非 datara 归属连接导入 datara。

**success_criteria**：

- `/ide` 由 dbx 承载，`SELECT * FROM t WHERE dt = '${global.biz_date}'` 可直接执行成功，无需手填参数。
- IDE 内可查看变量现值（敏感变量脱敏），供用户选择时参考。
- datara 数据源与 dbx 连接双向同步生效，冲突按既定策略收敛。
- dbx 镜像版本固定，部署产物可追溯。
- 1.9 隔离环境 E2E 与前端契约测试全部通过。

**risk_level**：high（关闭 dbx 密码属于鉴权面变更，逐项人工批准）

## Verification Contract

```
verify_steps:
  - run tests: datara-newweb 前端 vue-tsc --noEmit 与 vitest run（含新增 dbx 变量桥契约测试）
  - run tests: datara-backend 数据源同步适配层单元测试与既有 rebuild 回归
  - check: 直连 dbx 与经 datara 反代两条路径访问 IDE 子路径均返回 200
  - check: dbx 前端 dist 已打补丁并 bind mount 生效；镜像 digest 已固定
  - check: 数据源上行（datara → dbx）与下行（dbx → datara）各至少一条用例通过
  - confirm: browser-use E2E 在 192.168.1.9 固定前端入口通过；敏感变量现值脱敏展示
```

## Governance Contract

```
approval_gates:
  - 关闭 dbx 密码（DBX_DISABLE_PASSWORD）—— 鉴权面变更，需人工批准
  - 固定 dbx 镜像 digest —— 需人工批准
  - 数据源双向同步写入 dbx 连接 —— 需人工批准
  - 归档自研前端 IDE 视图及其契约测试 —— 需人工批准
rollback: 还原 compose 环境变量与 /app/static 备份；恢复 nginx /ide/ 反代配置；datara 侧同步适配层可独立停用
ownership: 用户裁定路线与批注；本 agent 负责设计、实施与验证证据
```

## Scope

| 维度 | 内容 |
|---|---|
| In | 新增 `DbxIdeView.vue`（iframe 宿主 + 项目/环境组选择 + 变量桥 + 变量现值面板 + 变量管理抽屉入口） |
| In | 改路由与项目段视图，指向新宿主视图 |
| In | 归档 `src/views/ide/*` 及引用它的 6 个契约测试 |
| In | dbx 前端补丁（外部变量注册表 + 变量桥 composable + 执行前替换） |
| In | nginx 新增 `/ide/` 反代（含 SSE 直通） |
| In | compose 环境变量（关闭密码 + 子路径 + 静态目录挂载） |
| In | 数据源同步适配层（后端轮询/上行 + 前端映射） |
| Out | 不重编 dbx Rust 二进制 |
| Out | 不改动 dbx 连接数据模型结构 |
| Out | 不导入 dbx 内非 datara 归属连接 |
| Out | 不在 dbx 内实现变量编辑（datara 变量只读注入） |
| Out | 不保留自研 IDE 视图的运行入口 |

## Decisions

| # | 决策 | 选择 | 被否替代 |
|---|---|---|---|
| D1 | dbx 接入方式 | 子路径同源托管：dbx 以 `/ide` 为公共基路径运行，datara nginx 反代该子路径 | 独立端口直连（破坏同源与入口统一）；重构 datara 前端（重复造轮子） |
| D2 | 变量打通方式 | datara 变量只读注入 dbx：宿主页 postMessage 下发外部变量注册表，dbx 前端执行前替换 shell 参数，未命中回落原生参数弹窗 | 改写 dbx 变量解析器（侵入式、随版本漂移）；要求用户手填参数（体验回退） |
| D3 | dbx 访问鉴权 | 内网环境关闭 dbx 密码 | 保留密码（需额外会话打通，复杂度高） |
| D4 | 自研 IDE 处置 | 仅归档前端 IDE 视图；后端 `rebuild/sql_ide` 保留 | 全量归档（后端元数据能力仍被其他模块依赖） |
| D5 | 构建位置 | 1.9 原地构建，验证后同步到本机备查 | 本机 Windows 构建后 scp（环境差异风险） |
| E1 | 数据源同步触发 | 上行即时（datara 数据源增删改后即同步 dbx）+ 下行定时轮询（datara 后端间隔拉取 dbx 连接） | 全定时双向（datara 侧改动有延迟）；仅上行单向（dbx 改动无法回灌） |
| E1a | 非 datara 归属连接 | 不导入 datara，避免 dbx 内临时/测试连接污染项目数据源清单 | 全导入（datara 沦为 dbx 连接只读镜像） |
| E1b | 冲突策略 | `updatedAt` 新者胜；dbx 侧连接补 datara 可写时间戳字段承载，缺失时降级为四元组比对且 datara 优先 | datara 恒优先（忽略 dbx 侧合理改动）；首次写入胜（静默丢改动） |
| E2 | 变量现值展示 | IDE 内提示查值并显示现值；敏感变量脱敏展示 | 原样展示（泄露敏感值） |
| E3 | 镜像版本 | 固定 digest，禁止升级 | 跟随 latest（拉新覆盖补丁） |

## Surface

**APIs**：dbx 侧复用既有连接管理接口——列表读取用于下行同步，保存接口用于上行同步（该接口为全量 upsert 语义并携带删除清单，天然适合做双向对齐）。datara 侧新增同步适配层，向上为数据源模块提供变更钩子，向下封装 dbx 连接读写；对齐标识采用「项目 + 数据源」派生的稳定标识，保证两侧可互相识别归属。

**Storage**：datara 侧数据源表结构不变，新增同步状态记录（上次同步时间、对端标识、冲突标记）。dbx 侧连接存储不变，仅通过既有可扩展字段承载 datara 归属标记与时间戳。敏感变量现值不落盘、不入日志、不入静态产物。

**Components**：新增宿主视图承载 iframe，负责项目/环境组上下文选择、变量桥生命周期、变量现值面板与变量管理抽屉入口。dbx 前端新增外部变量注册表、变量桥 composable 与执行前替换三处补丁，均以「未命中即回落原生行为」为原则，不破坏 dbx 原生参数流程。

**Files-touched**：datara-newweb 新增宿主视图，改路由与项目段视图，归档自研 IDE 视图及其 6 个契约测试，新增变量桥契约测试；datara-backend 新增同步适配层与状态记录；dbx 前端新增两文件、改一文件；部署侧改 nginx 反代与 compose 环境变量。

## Risks & Open Questions

- **鉴权面**：关闭 dbx 密码后，任何能访问 4224/反代路径的内网主体均可操作 dbx。需确认 4224 与反代路径的访问边界是否满足内网信任假设；这是本设计 `risk_level: high` 的根因，实施前需人工批准。
- **镜像固定**：需先记录当前运行镜像的 digest，再写入 compose 固定；固定后升级路径需人工介入。
- **同步时序**：上行即时 + 下行轮询为最终一致，存在轮询窗口内的短暂不一致；需确认窗口期可接受。
- **dbx 版本漂移**：前端补丁基于当前 dbx 前端源码；dbx 升级（即使被禁止）或前端结构变动可能导致补丁失效，需在验证中覆盖。
- **变量语义差异**：datara 变量为七级作用域链，dbx 变量为前端 `@set` 展开；注入层只覆盖「外部变量注册表 → shell 参数」这一条路径，其余 dbx 原生变量语法行为不变。
- **归档影响面**：归档自研 IDE 视图会同时移除其 6 个契约测试，需确认这些测试未覆盖仍被依赖的后端能力。
