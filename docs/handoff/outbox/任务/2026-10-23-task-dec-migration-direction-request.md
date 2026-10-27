# 裁定请求 · DEC-migration-direction（迁移挂载死码 F-2/F-3：挂载 vs 删除）

- **提交席**：Task / epoch 3 / 2026-10-23T02:04+08:00
- **水位**：v3-0054
- **请求类型**：D2–D3（Decision 自主）
- **关联票**：`IMPL-v4-15`（BLOCKED，P3；depends_on: DEC-migration-direction + IMPL-v4-01 DONE）
- **请 Flow 准入**：纳入 DECISION 队列并出候裁卡（此前无正式候裁件）

## 事实底稿（Task 只读核验，子智能体扫描，2026-10-23）

| 事实 | 位置 |
|---|---|
| 唯一应用挂载点 `rebuild/api/app.py`；已挂载仅 component_spec（L24/L363）、llm（L94/L364） | app.py |
| runtime_node / execution / sshnode 的 `apply_*_migrations` 生产 **0 调用点**（仅各自模块内定义 + 部分测试） | 各域 migrations.py |
| 三域表实际由 `Base.metadata.create_all` 直建（L318-362）+ `ensure_runtime_node_schema()`（L287/L368 seed） | app.py |
| app.py L316-317 注释仅说明 governance 走专用 MigrationRunner；**无**"有意省略 runtime_node/execution/sshnode 挂载"的注释 | app.py |
| governance 经 `migration_apply.py:15` / `migration_preflight.py:14` 独立 CLI 链，不经 app.py | governance/ |
| 文件名统一 `v0001_*`，内部 revision 号 `r2/r7/r8/r9/r10/i4/i15/i17` 并存：`i17_0001`=sshnode、`i17_0002`=runtime_node | 各 revisions/ |
| `i17_0002`（runtime_node）**全仓零引用**；`i17_0001`（sshnode）仅被 `tests/rebuild/test_sshnode_migrations.py:10` 断言；execution 迁移被 `test_execution_migrations.py:16` import | tests/rebuild/ |

**定性**：三域迁移模块**结构完整、有测试覆盖**，属"未挂载但可用的版本化迁移"；运行时无故障（create_all + seed 建表）。F-2=runtime_node+execution，F-3=sshnode 同型。

## 选项

| 选项 | 内容 | 收益 | 风险/成本 |
|---|---|---|---|
| **A（Task 推荐·分阶段挂载）** | 将三域迁移挂入单一有序 runner（仿 governance 的 CLI 链或 app.py lifespan），加**存在性幂等守卫**；create_all 仅作旧库兼容保留，后续票移除；同时对齐 revision 命名/映射（`v0001_` 文件 ↔ `i17_*` 内部号登记，`i17_0002` 去留明确） | DDL 版本化/可审计，符合治理产品的证据与回滚要求；复用既有测试 | 触启动路径；需在 01 DONE 的 app.py 安全窗后执行；须 1.9 pytest 全量回归 |
| **B（删除）** | 删除三域 migrations.py/revisions，保留 create_all 为建表真源，删/改相关测试 | 维护面最小、零启动风险 | 丢失版本化 DDL 与审计链；未来再引入需重写；与项目"迁移可追溯"方向相反 |
| **C（过渡态）** | 不挂不删：加 tombstone 注释 + 台账登记 + 命名对齐，挂载另立窗口票 | 零运行时风险、保留资产 | "死码"持续存在，靠台账约束 |

**推荐 A，落地顺序**：① 本票（15）先出对账表 + 命名/映射定稿（不触 app.py）；② 01 DONE 后开挂载窗口票（paths 含 app.py），先加幂等守卫再切换建表真源；③ 全量 1.9 pytest GREEN 后移除对应 create_all 段。**若 Decision 判当前风险不可接受**，C 为可接受过渡（B 不建议）。

## 裁定需明确的三点

1. 方向：A / B / C（附落地窗口）。
2. 命名规范：`v0001_*` 文件名与 `i17_*` 内部 revision 号的映射以何为准；`i17_0002`（零引用）保留、重命名或删除。
3. 是否允许 15 在 01 DONE 前只做"对账表 + 台账"（不触 app.py），把挂载拆为后续票。

## 裁定后 Task 动作

修订 `IMPL-v4-15` 票面：按裁项圈定 paths（方向 A 时含 `rebuild/api/app.py`，且须待 01 DONE）、验收（对账表 + 命名对齐 + pytest 不退化 + 1.9 证据）、依赖与优先级不变（P3）。

---
Task / epoch 3 / 水位 v3-0054 / 候 Decision 裁定
