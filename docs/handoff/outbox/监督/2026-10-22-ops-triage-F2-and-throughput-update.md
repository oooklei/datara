# Ops 分类 F-2 + 吞吐跟踪更新

- 截至: 水位 `v3-0029-integration-patrol-v3-0024`（15:05，epoch 3 / RUNNING）
- 触发: v3-0026 将新发现 F-2 路由 Ops 分类（"Ops triage -> Decision/user ruling"）；v3-0028 登记工具链 advisory 转 Ops 备查

## 1. F-2 分类（dead code 迁移挂载缺位）

**事实（引自 v3-0026，Ops 不复检实施细节）**
- `apply_runtime_node_migrations` + `RUNTIME_NODE_MIGRATIONS` 全仓无调用点；修订 `i17_0002_runtime_node_registry` 从未登记进 `rebuild_schema_migration`
- `apply_execution_migrations` 同样未挂载；app.py git diff 为空 = **既有状态，非 v2→v3 合并回归**
- `v0001_` 文件名 vs `i17_0002_` 内部修订号不匹配，纯表面问题
- 运行时无恙（表经 app.py lifespan create_all + B6 seed 建立）；实施线未越界自修（app.py 不在 01 pathspec 内——纪律正确）

**Ops 分类**
- **深度**: D1–D2（已接受架构内、可逆、局部/跨文件实现选择）——归 Decision 自主裁定，**无需上呈用户**
- **对 01 验收链影响**: 零运行时影响 + 既有状态 + 非回归 → **不阻塞 01 的 ENV_VERIFIED/PASS**；01 验收应按票面标准执行（1.9 pytest GREEN、节点 A/B 证据链、F-1 注释修正）
- **Ops 推荐处置**: **选项 D2（独立票）**——并入下一批立项（建议票面：迁移挂载对账或死模块删除二选一 + i17/v0001 命名对齐 + INC17 证据措辞同步），优先级 P3/MAINTENANCE
  - 理由: ① app.py 在 01 pathspec 外，链中自修破坏 pathspec 纪律；② 若选挂载（D1）触及 app.py lifespan/迁移链语义，需独立 1.9 测试周期；③ 删除死模块（D3）同样需证据措辞同步——无论方向都是小票，不急于本批
- **后续**: Decision 确认方向（挂载 vs 删除）后 Task 立票；本批不动

## 2. 工具链 advisory 备查（W-1，非 EXCEPTION）

- v3-0028 登记: trae 终端 RunCommand 通道环境级故障（Toolhost routing），经 integrated_code_mode Exec→Shell 通路完成并留痕；Flow 主会话同刻复现
- Ops 处置: 登记 watch item **W-1**；无越权写入/路径冲突/循环依赖，不构成 EXCEPTION。若该故障后续阻断任一线证据产出（workaround 失效），立即升级 EXCEPTION
- 提示: 与 v3-0009/v3-0010 计划任务平台下限同类，属环境能力边界，继续观察

## 3. 吞吐实况更新（相对上轮提速分析）

**已落地（用户上轮 B-3/B-4 下令后 Flow 执行）**
- B-1/B-4 等效完成: 05 已派 trae（v3-0024）且已 EVIDENCE_READY（v3-0028）
- 01 亦达 EVIDENCE_READY（v3-0026，静态检查全绿、F-1/D03/D04 三项配套登记）
- 连带收口: 04 验收 PASS 补录（v3-0021）；EXC-v4-01 选项 A 已执行核销（v3-0023）；R-1 lifecycle 字段已对齐；push 预授权已登记到 06

**新瓶颈（双线空闲 + 库存清零）**
- claude、trae 两线均已释放，IMPLEMENTATION ready=0，**无票可派**——库存见底预警兑现
- 1.9 租约成关键路径守门人: RT-IMPL-V4-01-A-GROUP（01 全量 pytest）候 Integration 回执（LEASE_GRANTED/DEFERRED）；03 e2e 亦需租约——单环境两单，错峰排程（A-1）现由建议转必做
- 02 仍形式 BLOCKED（标准计划: 01 PASS 后回填）；02a 解耦呈递件（15:08 写入）待 Flow 心跳接纳

**当前提速排序（更新版）**
1. **02a 立即派 claude**——用户已批解耦、claude 已空闲，Task 重构 02 票面 + Flow 派单即可；若等不及心跳可再点名"02a 派 claude"
2. **Task 下一批立项即刻发布**（质量五项/项目管理前端/API/API-Key/T55/流表 + F-2 独立票）——防 02a 之后二次空转
3. **Integration 租约回执提速 + 错峰**: 建议 03 e2e（量小）先行回执执行、01 pytest 后接，或按到达序，但回执延迟即关键路径延迟
4. **codex 上线（B-2）** 仍待用户下令——有库存后才有第三线意义

## 边界声明

Ops 仅分类与建议；F-2 方向归 Decision、立票归 Task、派单/接纳归 Flow、租约归 Integration。未写共享状态。
