# 血缘遗留项收尾实施计划（2026-10-01）

Spec：docs/superpowers/specs/2026-10-01-lineage-followup.md（已批准）
执行方式：子代理驱动（implementer → spec 审查 → 质量审查 → 修复回环）；三路并行分派（后端/前端/评估，文件面无交叠）；完成后两级审查，全绿收口单 commit。

## Task 1：详情抽屉「最近采集」（后端部分）

- 文件：`datara-backend/api/lineage.py`；测试 `datara-backend/tests/test_lineage_graph.py`
- 要点：
  - node_acc 聚合结构加 `"last": None`；table 级循环（L351-363）随边行 r.create_time、field 级循环（L302-323）随父边 e.create_time 累积 max（注意 None 安全比较）
  - nodes 输出（L424-429）加 `"lastCollected": fmt_dt(node_acc[fq]["last"])`（fmt_dt 已导入，None→null）
  - 口径 = 该节点全部聚合行（design+runtime）create_time 的 max（与 /stats lastTime 一致）；不新增查询
- 测试：造数时显式传 create_time（datetime 对象），断言 max 序列化值 'YYYY-MM-DD HH:mm:ss'；无 create_time 的节点 lastCollected 为 None
- 验收：pytest 回归全绿

## Task 2：详情抽屉「最近采集」（前端部分）

- 文件：`datara-web/src/services/lineageApi.ts`（node 类型 + lastCollected?: string | null）、`datara-web/src/services/mock/lineageUtils.ts`（buildLineageGraphDoc 透传 node.data.lastCollected，GNode data 类型最小扩展）、`datara-web/src/graph/profiles/lineage.ts`（lineageRelated 存在时追加 `最近采集 {值}`，缺失不加）
- 明确不动：`Inspector.vue`（M 状态他线文件；related 区数据驱动渲染 {text,color?}，已确认零改动成立）
- 测试：lastCollected 存在 → related 含「最近采集」；缺失 → 不含；node.data 透传断言
- 验收：vitest + vue-tsc 全绿

## Task 3：deriveImpact 预建邻接 Map

- 文件：`datara-web/src/services/mock/lineageUtils.ts`（deriveImpact）
- 要点：一次遍历预建 adjOut/adjIn: Map<string,string[]> + visited Set，O(V+E)；ImpactSubgraph 输出语义与现状逐字段一致（现有测试锚定，不改对外契约）
- 验收：现有 deriveImpact 相关测试全绿；全量 vitest 回归

## Task 4：后端常量化

- 文件：`datara-backend/common/lineage_extract.py`（定义 SRC_TYPE_DESIGN/SRC_TYPE_RUNTIME/FILE_NAME_PREFIX 并替换内部字面量 L156/L162 及 "file:" 使用处）、`datara-backend/api/lineage.py`（导入并替换 src_type=="design" 三处 L445/L488/L512 与 _bare/_split_fq 的 "file:"）
- 明确不动：common/db.py 迁移默认值、Query pattern 字面量、测试断言字面量、worker/
- 验收：pytest 回归全绿

## Task 5：rebuild 部分写库失败路径测试补齐

- 文件：`datara-backend/tests/test_wf_design_lineage.py`
- 用例：
  - rebuild_design_lineage 中途抛错（如 monkeypatch db.flush 单次抛异常）→ 异常向上抛；db.rollback() 后旧 design 行完整保留、无半写 edge/field 行（delete-then-reinsert 同事务回滚语义）
  - redesign_wf_lineage 吞异常路径 → 不向调用方抛、rollback 后旧行保留
- 验收：pytest 回归全绿

## Task 6：field 挂靠仅首边评估（只读）

- 读：api/lineage.py（edge_by_pair.setdefault L493-499、/fields、/trace、graph field 级）、worker/lineage.py（runtime 字段挂靠路径）、common/models.py
- 产出：按 spec §5 四维度结论，Edit 回写 spec「> 评估结论」占位处；不改任何代码

## Task 7：收口

- 两级审查（spec 审查 + 质量审查）→ 修复回环 → 全量回归（pytest + vitest + vue-tsc）
- commit（只 add 本任务组文件：api/lineage.py、common/lineage_extract.py、tests/test_lineage_graph.py、tests/test_wf_design_lineage.py、lineageApi.ts、lineageUtils.ts、lineage.ts、相关测试文件、spec/plan 文档）
- 文档回写：本计划状态、spec 状态行与 §5 结论、2026-09-30-lineage-design.md §6.3 遗留表勾销
- 1.9 部署复验：lineage.py/lineage_extract.py docker cp + py_compile + 五后端重启 + graph 探针验 lastCollected；前端 dist 构建部署 + 抽屉抽查
