# STATE — 监督线现状基线（新纪元唯一权威起点）

> **版本**：v1（2026-10-19 就任准备落库）
> **性质**：冷启动首读文件。旧台账 `2026-10-16-并行协作分工.md`（#1–#352，含双序列与 #317 撞号污染）**冻结为历史考古区，只读不写**；本文件起用新序号 S#。
> **维护纪律**：每监督窗由监督线更新快照+活动区追加一条；全文 ≤60 行硬上限。

## 一、现状快照（2026-10-19）
- **权威文件**：主标准 `docs/increments/多终端多智能体项目管理标准规范.md`（台账指针已切换本文件）；裁定索引 `…-裁定索引.md`（裁定唯一索引，只增不改）；归档1（旧台账 #1–#69）。
- **冻结契约**：P2-1 R6 清单 v1.0（9933684）；A5 前端契约 v1.0（fc2979e）。
- **watchdog**：已彻底删除（2026-10-18 用户令，回执旧台账 #352）；本准备窗补落文件删除提交，零残留。
- **工具**：`agents/mailbox_loop.py` v1.1（信箱循环实体：同轮 pending 合并单次子智能体调用 + `--model` 分级路由 + 回复引用化纪律）；信箱信道 `docs/handoff/mailbox.jsonl`。
- **AOCI**：governance_aligned=false（semantic_change 436/30、222+ 条待消化）；全量传输活锁（旧台账 #349–#351 三窗同点停链，93k token 单窗结构性无法完成，Attestation 无法提交）。

## 二、在飞/待裁（就任后第一窗议程）
1. **AOCI 传输策略裁定**（旧台账 #351 三选一：a 上调守护窗预算续传 / b cursor 跨窗续传+分窗 Attestation / c 压缩索引本体降密）——与 AOCI 分卷裁定（阶段×目录域二维，历史卷 catalog-only 免修）联动；前置=守护线盘点 AOCI 升级新工具能力，产出实施方案报用户裁。
2. **P1-6' 收尾**：PoC 注入修正 vanna_factory 重跑取证 + adapter.py:217 缺陷修复单（派 Claude 实施线）。
3. **P2-2 Track A 复验收口 → GREEN 宣告** → 派 P2-3（硬前置=P2-2 GREEN + A5 冻结）。
4. **P-OPT Token 优化**：P-OPT-1 结构设计→Codex；P-OPT-2/5（mailbox_loop）监督线已完成；其余滚动派单。

## 三、工作区脏项（现状披露，就任后按需处置）
- 未提交删除：`docs/build_docs.py`、`docs/build_manual.py`、P2-3-依赖预研.md、数据开发IDE用户使用手册.pdf（视为污染物，可提交删除）。
- 未提交修改：`.aoci/*`、`aoci.code.txt`（AOCI 运行时资产）、correction-plan、R7 evidence log、约法台账（归属线差异，勿盲目还原）。
- 未跟踪积压：`infra/*.sh`、evidence json、`.agents/`、`.claude/`、`opencode.json` 等历史产物，按需纳管或 gitignore。

## 四、冷启动三步（任何新会话）
1. 读本文件对齐现状；2. 按角色读主标准 §15 分钟上手清单；3. 裁定争议查裁定索引，原文考古去旧台账/归档1。

## 五、活动区（新序号 S#，append-only）

- 历史活动原文归档：`docs/handoff/archive/2026-10-19-STATE-S1-S3.md`、`STATE-S4-S13.md`、`STATE-S14-S21.md`、`STATE-S22-S32.md`、`STATE-S31-S54.md`。

S66 | 监督员 | 2026-10-19 06:00 Asia/Shanghai | T6-T10/C1-C4 采信 | Codex T6-T10（S61-S65）与 Claude C1-C4（含 C1 提交 4c1dd53）全部采信；T1-T10 交付+监督线 2 补丁（contracts.py save_snapshot Protocol、test_skeleton.py 运行时目录容忍）待 pathspec 代提交；T5 补验缺授权 datasource（用户操作项）。
S67 | 监督员 | 2026-10-19 06:00 Asia/Shanghai | 新批派发 | 用户令加压：Codex 十单 T11-T20（#8e4f2a91：error_catalog/status_store/linter/variables/janitor/completions/W2 集成测试/routes/R6H-01 retry/R6H-02 failover）+ Claude 四单 C5-C8（#7c3d5e82：rb_facade 收尾/lineage 实装/ExecutionLedger 先行件/A5 #22 契约核对）；AOCI 豁免裁定 #85 已重申两线；Claude STATE 编号改由监督线代登（防撞号）。
S70 | Codex SQL IDE/T14 | 2026-10-19 06:06 Asia/Shanghai | P2-2-R5A-FIVE-C #8e4f2a91 | GREEN复验
交付：rebuild/sql_ide/variables.py 与 tests/sql_ide/test_variables.py 为超时前遗留产物；本轮补复验记录，未改代码；`rtk pytest tests/sql_ide/test_variables.py -q` → 6 passed；证据 docs/increments/evidence/2026-10-19-P2-2-R5A-FIVE-C-T14-green.md；无提交/无 push，待监督线 pathspec 代提交。
下一单：等待 T11-T13 释放槽位后接续 T15-T18；监督线新派单触发优先级重排。
