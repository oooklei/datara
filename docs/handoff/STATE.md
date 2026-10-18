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
- **S1**（2026-10-19 监督线）：就任准备完成——STATE.md v1 落库+主标准台账指针切换+mailbox_loop v1.1+watchdog 删除落库；旧台账冻结；待用户确认就任。
- **S2**（2026-10-19 监督员就任，正式接管全权）：实锚 HEAD=23b97d8 核实一致；裁定索引 §一 已核。登记用户令①：实施线（Claude/Codex）职责全集（评审+代码）、互为 AB 角，同一对象评审 3 次/修改 3 次未过审→强制互换角色并报监督线备案（替代 #263 双域零交集，待补录裁定索引）。登记用户令②：mailbox 循环实体机制上线（agents/mailbox_loop.py v1.1 后台常驻，信箱 docs/handoff/mailbox.jsonl；正式派单唯一载体仍为台账心跳，信箱仅催办协同）。
- **S3**（监督线派单，承接 S2）：**D1→Claude**：P1-6' 收尾——①PoC 注入修正 vanna_factory 重跑取证（evidence 落 docs/increments/evidence/）；②datara-backend adapter.py:217 缺陷修复（先 RED 后 GREEN，附测试命令与输出定位；缺陷出处=旧台账 #352 下一单节）。**D2→Codex**：①Track A 复验核查（evidence/2026-10-18-TrackA-* 产出已在库，独立复评出 PASS/FAIL 结论+GREEN 建议，机读为准）；②P-OPT-1 STATE.md 分层快照机制设计（docs/increments/，只设计不实现）。触发=Claude/Codex 到岗即领单；Track A GREEN 后派 P2-3（硬前置=P2-2 GREEN+A5 冻结）。AOCI 传输策略裁定挂起（前置=守护线盘点 AOCI 升级新工具能力）。
