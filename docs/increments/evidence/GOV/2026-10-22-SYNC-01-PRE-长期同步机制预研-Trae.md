# SYNC-01-PRE 预研报告：datara_meta→rebuild_i0 长期同步机制

- **business_key**: SYNC-01-PRE:prestudy:r1（推导口径，票面未显式给出，如 C 席另有裁定以 C 为准）
- **任务**: s359【三】派单五项预研 + s362【二】【五】【六】三项增补输入
- **性质**: 纯预研不触码（零业务代码改动，全部为源码静态只读稽核）
- **执行**: Trae 实施线 | 2026-10-22T02:31–02:50+08:00 | 租约 2026-10-22T03:05:00+08:00
- **报验**: tr-done-42
- **证据源**: 本报告所有结论均绑定下列源码文件与行号（本机静态稽核，未运行任何测试，无 1.9 远程证据——纯预研票面 DoD 不含远程测试）

## 0. 票面核对结论

| 要素 | 现态 |
|---|---|
| GOAL | datara_meta→rebuild_i0 长期同步机制预研（防环境重建后组件数据再断） |
| ALLOWED_PATHS | 报告落 docs/increments/evidence/GOV/ + outbox 回报（本件） |
| FORBIDDEN_PATHS | 禁触码（纯预研）；push 恒候用户放行 |
| DoD | ①预研报告落 GOV ②报验 tr-done-42 ③全程不触码 |
| 增补输入 | s362【五】C3 业务键 upsert、s362【六】坏行降级、s362【二】ETag 复验口径登记 |
| AOCI | 未加载（SUSPENDED_DURING_ACTIVE_DEVELOPMENT 合规） |

## 1. 现状事实（源码实证）

### 1.1 双库结构性制约（s362【二】根因确认）
- 发布链（`api/baseline.py`、`api/component_design.py`）经 `common.models` 写 **datara_meta** 的 t_component/t_component_version/t_component_log；
- rebuild 读链（`rebuild/component_spec/service.py`）经同一组模型类读 **datara_rebuild_i0**（`rebuild/api/app.py` L363 启动建表 `apply_component_spec_migrations`，L1057 挂载 spec router；session_factory 绑 rebuild 引擎）；
- 两侧**同构不同库、当前无任何自动同步机制**——A1 seed（`scripts/seed_rebuild_component_catalog.py`）是唯一桥，且为一次性人工止血脚本。

### 1.2 A1 seed 脚本现态（[seed_rebuild_component_catalog.py](file:///d:/需求/数据治理工具/Datara/datara-backend/scripts/seed_rebuild_component_catalog.py)）
- 独立幂等脚本，双 URL（`REBUILD_DB_URL` 必填 / `META_DB_URL` 缺省回落 settings.db_url）；
- 读侧条件与读链逐字等价（已 s362 深核实证）：t_component `state='published'`；t_component_version join 条件 `component_id==Component.id AND version==published_version AND state='published'`；t_component_log 按 `component_id in (published ids)` 全量取；
- 幂等：先查后写，t_component 按 `type` uk、t_component_version 按 `uk_comp_type_ver(type,version)`、t_component_log 按 `id` 主键收敛；已存在行 `_copy_row` **整行覆盖（含 id）**；
- 新增行显式携带 meta 侧原 id（保 component_version.component_id 引用与自增不破坏）；
- 单事务 commit + 三表计数复核；不写 rebuild_schema_migration 台账（非迁移，s356 裁定）。

### 1.3 读链现态（[service.py](file:///d:/需求/数据治理工具/Datara/datara-backend/rebuild/component_spec/service.py)）
- `published_document()`：L91-103 select join（同 seed 读侧条件）→ L104 列表推导 `_spec_item()` 逐行渲染 → L105 json.dumps 紧凑 UTF-8 body → L106 `etag = sha256(body)`；
- **ETag 天然随 rebuild_i0 内容变更**（读的是 rebuild 侧 session 绑定的表）——s362【二】修正后口径在现架构下**结构性成立**（详见 §7.3）；
- 坏行传播：L36-40 `_spec_item` 内 `json.loads(spec_json)` 失败抛 `ComponentSpecError` → L104 列表推导中断 → `published_document` 整体抛错 → api.py L45-49 捕获返回 **500 全有全无**——s362【六】表述经源码确认属实。

### 1.4 发布链写入点（变更捕获锚点）
`ComponentLog(...)` 写入共四处，均为「业务变更 + log 同事务 commit」模式：
- `api/baseline.py` L513（redraft 开修订轮）、L568（discard_draft）、L715（freeze_version 一带）；
- `api/component_design.py` L369（publish/offline 链）；
- t_component_log 审计语义（models.py L687 注释）：**只追加，不更新不删除**，action 枚举 create/update_draft/freeze_version/publish/offline/rollback。

### 1.5 rebuild 侧消费面（全景见 §4）
读三表的唯一业务代码 = component_spec service；其余消费全部经 HTTP 端点 `GET /api/v1/rebuild/components/spec`（[api.py](file:///d:/需求/数据治理工具/Datara/datara-backend/rebuild/component_spec/api.py)：token 鉴权 + ETag/304）。

## 2. 预研①：A1 seed 一次性冷启动基线与长期同步增量边界定义

**基线定义**：`seed --apply` 收敛后的三表态 = 长期同步的零点。实测基线（s360/s361 定案）：t_component=18、t_component_version=18、t_component_log=31。

**增量边界定义**（同步机制只须覆盖使「读链可见集合」变化的 meta 侧变更）：
1. **t_component 行变化**：新组件发布（state draft→published）、下线（published→offline）、published_version 推进、name/description 等展示字段更新；
2. **t_component_version 行变化**：published 版本快照新增（version N 发布产生 state='published' 快照行）、已发布版本被 offline；
3. **t_component_log 行追加**：审计留痕（只追加语义，单向后向兼容）；
4. **边界外（明确不覆盖）**：draft/frozen 态版本、t_baseline_progress（基线化进度，meta 侧独有流程表，读链不消费）、meta 侧其他业务表。
5. **判定规则**：凡使 `published_document()` 输出 body 变化的 meta 侧写操作都在边界内；可通过「以读链同条件全量重算」机械判定，无需白名单枚举动作类型（防未来新增写入路径漏登记）。

## 3. 预研②：变更捕获三方案对比

| 维度 | A. t_component_log 增量拉取 | B. 全量比对 upsert | C. 发布事件驱动 |
|---|---|---|---|
| **捕获原理** | 按 log.id 水位拉新增 log 行，反推变更组件 | 定时以读链同条件全量拉 meta 现态，与 rebuild_i0 逐行比对收敛 | publish 链发布后主动投递事件，消费者增量同步 |
| **一致性** | 中高：log 与业务变更同事务（§1.4 实证），不丢；但 log 是审计语义非数据变更语义，redraft 等动作也入流需按 (component_id,version,action) 去重归并；**log 只覆盖现有四处写入点，未来新增写入路径漏写 log 即漏同步**（防御缺口） | **最高：以读链同条件全量重算，与 published_document 输入集合机械对齐，天然自愈任何漂移（含历史坏 seed、人工误改）** | 取决于投递可靠性：需 at-least-once + 幂等消费；跨库无分布式事务，失败重试/顺序性须自建 |
| **时延** | 轮询间隔级（如 60s） | 轮询间隔级（如 60s） | 近实时（事件投递即触） |
| **实现成本** | 低-中：水位拉取简单，但动作归并逻辑、漏写防御、回填水位逻辑叠加后复杂度不低 | **低：本质=seed 读侧逻辑+幂等 upsert 的定时化/可触发化，复用已通过深核的读侧条件；数据量 18/18/31 百行级，全量代价可忽略** | 高：当前无现成事件总线/任务队列，引入新基础设施违背最小实现；publish 链需改写（触码面大，publish 链属已发版治理链路） |
| **失败恢复** | 水位回退重放（log 只追加可重放） | 重入即恢复（幂等） | 需事件重放/死信机制 |
| **回滚友好度** | 中 | **高（重跑收敛）** | 低（事件已消费难撤） |

**预研倾向：B 为主方案**。理由：
1. 数据量百行级，全量比对成本与增量无实质差异，却获得最强一致性（与读链集合机械对齐）；
2. 复用 A1 seed 已验证的读侧条件与幂等 upsert 骨架（s362 深核全采信），实现风险最小；
3. 自愈性：任何漂移（含 seed 历史遗留、人工干预、坏行）在下一轮全量比对中自动收敛；
4. A 可作为**对账监控补充**（log 水位差=「meta 有动作而 rebuild 未收敛」的告警信号），不作正确性依赖；
5. C 不建议当前引入：基础设施成本与收益不成比例；但建议同步器预留「手动触发端点」（POST /internal/sync/component-catalog 之类），未来若引入事件仅需事件处理器调用该端点，接口位不变。

**时延权衡**：轮询 60s 内 ETag 稳定期可接受（rebuild 读链本就容忍最终一致；F3 E2E 断言不依赖秒级新鲜度）。如需降低，未来加「publish 完成后触发一次同步」钩子，仍非正确性依赖（漏触发由轮询兜底）。

## 4. 预研③：rebuild 侧只读消费面全景（组件目录读取链路）

```
datara_rebuild_i0 三表 (t_component/t_component_version/t_component_log)
        │ 唯一直接读取点
        ▼
rebuild/component_spec/service.py published_document()   ← sha256 ETag
        ▼
rebuild/component_spec/api.py  GET /api/v1/rebuild/components/spec
        │  (token 鉴权 [L21-27]；ETag→304 [L50-51]；ComponentSpecError→500 [L45-49])
        ▼
rebuild/api/app.py L1057 挂载（L363 启动时 apply_component_spec_migrations 建表）
        ▼
消费方：datara-newweb 前端 palette/画布（间接）；E2E 断言（L12-02 F3 锚1-3）
另：rebuild/trial/validator.py L220 注释提及 SYNC 节点 component 参数（间接依赖 spec 数据，不直查表）
```

**结论**：消费面单一收口于 component_spec service。同步机制的正确性判据可机械化为：**rebuild_i0 三表与 meta 读链条件集合逐行一致**（t_component_log 历史复制语义除外，按 id 收敛）。

## 5. 预研④：WBS 分解 + 可排产粒度票面

> 以下为预研产出的票面草稿，供 C/P2 排产裁定，非本票交付授权。

### SYNC-01-R1 同步器主体（全量比对 upsert 定时任务）
- **GOAL**: 把 A1 seed 的收敛复制逻辑产品化为可定时/可手动触发的同步器，实现 meta→rebuild_i0 目录三表持续收敛。
- **SCOPE**: ① 新模块 `rebuild/component_catalog_sync/`（或 scripts 升级为模块，措辞候裁）：复用 seed 读侧条件 + 幂等 upsert；② upsert 按业务键收敛 + id 处理策略（见 §7.1）；③ 手动触发内部端点（挂 rebuild/api/app.py，内部 token 保护）；④ 定时调度（app 启动后台任务或宿主 cron，措辞候裁——候选本机静态实现即可，部署形态归 I1）；⑤ 单元测试（1.9 远程执行）。
- **DOD**: 同步器可重复执行幂等收敛；对 1.9 现网数据跑 dry-run+apply 后三表计数/内容哈希与 meta 侧读链条件集合一致；ETag 复验（§7.3）通过；evidence 落档。
- **DEPENDENCIES**: 无触码前置；建议在四件原子单元稳定窗外（不涉 ai_tools/app）。

### SYNC-01-R2 坏行降级（单件隔离+告警）
- **GOAL**: 消除「单坏 spec_json 行→整目录 500 全有全无」脆弱性（s362【六】）。
- **SCOPE**: 同步器写入前逐行校验 `json.loads(spec_json)` 可解析且为 dict；坏行**不写入** rebuild_i0（隔离），记隔离清单（日志结构化字段：component type/version/id/错误摘要）+ 告警；读链 500 行为保持不变（数据质量已由源头把关，读链 500 仅剩 meta 侧刚发布坏 spec 的窗口期，同步器已同时告警）。
- **DOD**: 注入坏行后目录端点仍 200 且 items 不含坏件 + 隔离告警留痕；正常行不受影响。
- **依据**: 预研结论=「源头隔离」优于「读链单件跳过」——读链全有全无是契约安全特性（宁 500 不给半份目录），由同步器保证进库数据全部可渲染后，读链 500 概率趋零且必伴随明确告警。（若 C 裁定读链也要单件跳过，属 service.py 契约变更，需另评估 ETag 语义与前端兼容，本预研不推荐。）

### SYNC-01-R3 对账与漂移监控
- **GOAL**: 双库最终一致的可见性保障。
- **SCOPE**: 定期对账任务：meta 读链条件集合计数+内容哈希 vs rebuild_i0 三表计数+内容哈希；不一致→告警；可选：t_component_log 水位差作为「meta 有动作未收敛」前哨信号（§3 A 方案的降级复用）。
- **DOD**: 人为制造漂移后一个对账周期内告警；对账零漂移期静默。

### SYNC-01-R4 seed 脚本与同步器关系收口
- **GOAL**: 明确冷启动（seed）与长期同步（R1）的分工，防双轨漂移。
- **SCOPE**: seed 保留为冷启动工具（空库快速填充）；R1 同步器为长期唯一常态通道；文档化二者幂等语义等价性（同为业务键 upsert）；候选：seed 后续重构为调用同步器同一路径（措辞候裁，避免过度工程可不合并）。
- **DOD**: 登记件/文档说明二者边界；无代码强制项。

**排产建议**: R1 为核心票先行；R2 可并入 R1 同票交付（同一模块同一测试面，拆票反而割裂）；R3/R4 可并行小票。即最小可排产集 = R1(+R2) + R3 + R4 三票。

## 6. 预研⑤：风险清单

| # | 风险 | 场景 | 缓解 |
|---|---|---|---|
| 1 | **双写一致性窗口** | meta 发布事务 commit 后、同步轮询前，rebuild 读链为旧数据；ETag 不变（正确反映 rebuild_i0 现态） | 最终一致语义接受；对账监控（R3）保障收敛可见性；E2E 若需强新鲜度，测试内触发手动同步端点后断言 |
| 2 | **同步器 crash 中途态** | 全量比对事务中途失败 | 沿 seed 模式单事务 commit（rollback 全撤）；重入幂等无副作用 |
| 3 | **版本漂移：PK/FK 撕裂（C3）** | 见 §7.1 | 业务键 upsert + id 防覆盖策略 |
| 4 | **坏行毒化读链（s362【六】）** | meta 侧发布坏 spec_json → 整目录 500 | R2 源头隔离+告警 |
| 5 | **回滚路径** | 同步把坏数据带入 rebuild_i0 | ①同步器幂等可重跑收敛=软回滚；②冷启动兜底：清空三表重跑 seed 可完全重建（seed 读侧条件即重建权威）；③禁任何 rebuild→meta 反向回写（rebuild 侧只读原则不变） |
| 6 | **log 历史复制增长** | t_component_log 只追加，长期同步全量比对会持续覆盖复制 | log 按 id 收敛幂等，量级可控（审计语义）；若长期膨胀可后续加水位增量优化（非当前必要，避免过度工程） |
| 7 | **调度形态与部署耦合** | 定时任务宿主形态（app 内后台 vs 容器 cron）涉及 1.9 部署面 | R1 票面留部署形态候裁接口；代码层只保证「可被触发的同步函数+手动端点」 |

## 7. 增补输入落地（s362 三项）

### 7.1 s362【五】C3 PK 覆盖风险 → 业务键 upsert 写入策略
**问题实证**：`_copy_row`（seed L57-62）遍历 `source.__dict__` 全列 setattr，**含 id**。已存在行（业务键命中）整行覆盖时会把 meta 侧 id 写进 rebuild 侧行——若该 id 在 rebuild 侧已被**其他业务键**的行占用 → PK 冲突事务失败；且 component_version.component_id 逻辑引用（models.py L663 为注释性引用非物理 FK）可能与被改写的 component.id 失配。

**写入策略设计**（建议 R1 采用）：
1. **upsert 键维持业务键**：t_component=`type`、t_component_version=`(type,version)`、t_component_log=`id`（log 天然主键恒等，无此问题）；
2. **已存在行：全列覆盖但排除 id**——保留 rebuild 侧现有 id，其余列随 meta 收敛（id 只是代理键，业务语义在 type/version）；
3. **新插入行：携带 meta 原 id**，插入前查目标 id 占用——占用则改走自增并**在隔离清单告警**（id 恒等假设已破，人工介入；此时 component_version.component_id 按新 id 映射转换）。因 cold-start 即恒等、常态只有同步器单写方，实际触发概率极低，防御即可；
4. **该策略使「rebuild_i0 目录三表 id 恒等 meta」成为不变式**（异常时显式告警而非静默漂移），引用完整性由不变式保证。

### 7.2 s362【六】坏行降级策略
问题与设计见 §5 SYNC-01-R2（结论：同步器源头隔离+告警，读链契约保持全有全无；不推荐读链单件跳过——属契约变更且削弱「宁 500 不半份」安全特性）。

### 7.3 s362【二】ETag 复验口径登记（候 SYNC-01 落地复验）
- **登记事实**：F3 锚3 收口口径修正为「ETag 随 rebuild_i0 内容变更」（原「随发布变更」因双库无同步机制结构性不可满足）。
- **源码实证（本预研）**：service.py L105-106，ETag=sha256(json(读链渲染结果))，读链 session 绑 rebuild 引擎 → **ETag 已天然随 rebuild_i0 内容变更，修正口径在现架构下结构性成立，无需改码**。
- **SYNC-01 落地后复验清单**（转 R1/R3 验收项）：
  ① 同步前：篡改/推进 meta 侧 → rebuild_i0 未变 → GET /spec ETag 稳定（304 链路不破）；
  ② 同步完成后：rebuild_i0 收敛 → ETag 变更 → 客户端 200 拿新 spec 且 items 反映新目录；
  ③ 空转轮询（meta 无变化）→ ETag 恒定（不产生假失效）。

## 8. 未核实项（诚实标记）

1. **本预研全部为静态稽核，未运行任何代码**——§2 基线计数 18/18/31 引自 s360/s361 已采信的 1.9 远程证据，本机未复跑；
2. api/baseline.py L715 与 api/component_design.py L369 的 action 具体枚举值未逐行展开（写入点存在性与同事务模式已确认，动作明细不影响三方案对比结论）；
3. 宿主 cron / 后台任务在 1.9 容器编排的具体形态未查（属部署面，归 I1 域，R1 票面已留候裁接口）；
4. WBS 票面草稿的模块命名、调度方式、端点路径等实现细节均候 C/P2 裁定后细化；
5. trial/validator.py 对 spec 数据的间接依赖深度未展开（不直查表已确认，语义耦合不影响同步机制设计）。

## 9. 预研结论一句话

**datara_meta→rebuild_i0 长期同步 = 「全量比对 upsert 定时收敛（复用 seed 骨架）+ 源头坏行隔离告警 + 三表对账监控」三件套；最小可排产集 R1(+R2)/R3/R4 三票；id 恒等不变式 + 读链全有全无契约 + ETag 随 rebuild_i0 内容变更口径三项结构性结论均经源码确认。**
