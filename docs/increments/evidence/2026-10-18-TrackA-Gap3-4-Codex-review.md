# Track A Gap3 / Gap4 独立复核回执

- 日期：2026-10-18
- 依据：标准 v4 §3 A1–A7（`docs/increments/2026-10-17-核心业务功能实现规范与验收标准.md:93-103`）；监督线 #265/#276/#278；交付提交 `cffa01d`, `942dc41`, `6d9acd6` 及其父提交 `42a39b1`。
- 方法：主智能体源码/提交/应用启动核验 + 3 个只读子智能体独立复核（Gap3、Gap4、A5）。未改业务代码。

## 总结

**Track A Gap3：部分实现，未达到生产验收 PASS。Gap4：FAIL，生产工厂/runtime 装配未交付。Track A GREEN 不可宣告；A5 仍是冻结候选，Claude 会签尚未落库。**

测试命令 `rtk proxy python -m pytest tests/sql_ide/ -v`（工作目录 `datara-backend/`）实际结果为 **76 passed in 2.51s**。完整原始 stdout 与追加的 schema/runtime 启动检查输出：`docs/increments/evidence/2026-10-18-TrackA-Codex-pytest.txt`。测试全绿只证明现有测试断言通过，不等于生产装配已接通。

| 门禁/能力 | Gap3 | Gap4 | 结论 |
|---|---|---|---|
| 实现事实 | `DbBackedAuditWriter` 可通过 `session_factory` 对 ORM 记录执行 start/end 写入；使用 SQL digest，不存 SQL 明文。 | `create_app` 暴露 `session_factory` 与 `datasource_engines`，测试可手动从这两项构造 port/writer；应用没有实际创建/挂载二者。 | Gap3 有限实现；Gap4 未实现生产装配。 |
| A1 TDD 红绿 | `cffa01d` 实现提交（02:20:01）先于 `942dc41` 测试提交（02:20:23）；未提供实现前红灯时间戳及输出。不能证明红绿顺序。 | `6d9acd6` 仅新增测试，无对应生产接线；测试对象没有实现“app 装配并接入 SQL runtime”。 | FAIL（证据不足/没有被测生产接线）。 |
| A2 独立评审 | 本次独立复核确认 writer API 存在，但完整生产持久化/审计范围未闭环。 | 本次独立复核 FAIL。 | 未取得独立 PASS，不能判 GREEN。 |
| A3 JSON+PNG / remote-final | 本次保留了文本 stdout；无 evidence JSON+PNG 成对、pair/digest 和 remote-final 定位。 | 同左。 | FAIL；文本输出不替代标准要求的成对远端证据。 |
| A4 O7 诚实 | #274 应将其准确称作“SQL 执行审计起止写入 slice”，而非完整审计域已完成。 | #274 的“生产工厂装配”表述超出测试事实；应改为“基础服务可供工厂消费，runtime 装配待完成”。 | 必须保持缺口显式登记。 |
| A5 复刻完备性 | 单个审计 writer 基础设施 slice 不单独判 DBX 功能覆盖；但 R5-A 整体仍受 A5 冻结约束。 | 同左。 | A5 冻结仍为前置。 |
| A6 冻结纪律 | 本批无契约改动。 | 本批无契约改动。 | 本次 N/A；不构成 A5 冻结。 |
| A7 红线 | 当前记录 `sql_digest` 而非 SQL 明文；此点通过。 | fail-closed 配置测试通过，但没有 SQL runtime 路由可验证完整只读执行链。 | 仅局部通过，不代表运行时安全链验收。 |

## Gap3 具体缺口

1. **生产表不可用（P1）**：`rebuild/api/app.py` lifespan 的 `Base.metadata.create_all(..., tables=[...])` 明确列出启动建表表集，但未包含 `SqlIdeAuditRecord`；仓库未检出该表 migration。独立启动检查在 `create_app` lifespan 后得到 `audit_table_exists_after_lifespan=False`。因此 writer 虽能构造，生产 DB 中没有受保障的 schema 建表路径，实际 insert 会失败。
2. **测试非数据库集成测试**：`test_audit_writer.py` 以 `MagicMock` session 验证调用；未覆盖真实 ORM insert/update、schema migration、commit 失败/rollback、并发状态、终态不可逆等。76 项套件通过不消除此缺口。
3. **审计模型只是执行摘要**：设计草案 §5 `SqlIdeAudit` 最低字段含 `action/timestamp/outcome/correlation_id/redacted_detail`，并要求区分执行、导出、历史删除和脚本管理，审计独立于历史清理；当前模型为 audit_id/project/user/datasource/sql_digest/task/status/stmt_count/elapsed/error/时间字段。可以把此提交限定为执行审计 slice，但必须注明未完成项与后续接线/迁移。
4. **A3 证据缺口**：#272/#274 只报测试命令/摘要，没有原始 stdout 定位。本次复跑并保存 stdout，补足了文本输出定位；仍缺 v4 A3 要求的 JSON+PNG 配对与 remote-final 证明。

## Gap4 具体缺口

1. `6d9acd6` 是测试文件提交，没有生产实现文件变更。`tests/sql_ide/test_factory.py:52-64` 只断言 `app.state` 有基础字段或 app 存在；`99-116` 则在测试中手动调用 `build_execution_port()` / `build_audit_writer()`，没有证明 `create_app` 创建并保存生产端口，也没有证明运行 handler/router 使用它们。
2. `rebuild/api/app.py:21-48,79-93,165-170` 无 SQL IDE 生产 port/writer 装配；应用只有 session/data-source registry。`rebuild/run_sql.py:1-10` 仍声明默认 `create_app` 保持 run_sql disabled，SQL runtime 尚未挂入。
3. 独立 lifespan 检查得到 `sql_runtime_routes=[]`。所以工厂基础设施可用不等于 runtime DI 完成；Gap4 当前 FAIL（P1）。需实现 create_app 的 production port + audit writer 装配及受控 run_sql 注入，再增加端到端 app/router 测试与缺配置 fail-closed 测试。

## A5 冻结衔接

handoff #278（`482a03c`）指派 Claude 会签，明确“会签回执落库即判 A5 冻结生效”；这条派单不是会签回执。候选文件仍标“待 Claude 实施线会签与监督线收口”。故 **A5 目前未冻结**，即使会签稍后落库，Gap4 的独立实施验收 FAIL 仍未通过；不得仅凭 A5 生效就解除 Track A GREEN 双闸。当前无需改写契约候选，待 Claude 会签后按指定判据确认冻结，再对 Gap3/4 缺口复验。

## A1–A7 总判

- **A1 FAIL**：缺红灯时间戳和先红后绿原始证据；Gap4 没有生产接线实现。
- **A2 FAIL**：本次独立结论不是 PASS。
- **A3 FAIL**：虽保存 pytest 文本输出，但缺 JSON+PNG 配对及 remote-final。
- **A4 FAIL/需更正交付表述**：Gap3 是有限 slice；Gap4 生产装配尚无实现。
- **A5 PENDING**：R5-A 冻结候选待 Claude 会签；整体 DBX 来源覆盖不能由这一 slice 代替。
- **A6 N/A（本批未修改契约）**。
- **A7 局部 PASS**：审计不记录 SQL 明文；完整 runtime 只读安全链尚未接入/验收。

本回执和原始输出均为单文件 pathspec 提交；未 push、未调用 AOCI 工具。
