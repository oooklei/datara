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
- 历史活动原文归档：`docs/handoff/archive/2026-10-19-STATE-S1-S3.md`、`STATE-S4-S13.md`、`STATE-S14-S21.md`、`STATE-S22-S32.md`、`STATE-S31-S54.md`、`STATE-S55-S60.md`、`STATE-S61-S65.md`、`STATE-S70.md`、`STATE-S71-S73.md`、`STATE-S83-S88.md`、`STATE-S89-S100.md`、`STATE-S101-S108.md`、`STATE-S109-S126.md`、`2026-10-20-STATE-S127-S143.md`。

S144 | 监督员 | 2026-10-20 Asia/Shanghai | Codex token 消耗根因调查闭环 | ①用户令查「Codex 执行派单提示词 token 消耗异常、新开会话也很快耗尽」：读 `.codex/state_5.sqlite`（1021 线程）+ rollout jsonl 逐条解析 + config.toml 取证，脚本 `agents/check_codex_tokens*.py` 4 个（未跟踪，待裁定处置）。②**根因五项**：a) input 占 99.6%——S135 会话 4 线程 153 轮 input 约 1670 万 tokens（缓存命中 95-98% 但**缓存命中仍计配额**），单轮最高 16.8万；b) 每线程固定起步约 4 万 tokens（12 插件全开 additional_tools 85.7KB≈2.4万 + developer 人设 1.8万 chars + AGENTS.md 16.4KB），**新开会话只清历史不清固定开销**；c) 一单自动 spawn 多 subagent（S135 拆 1 主+3 子各付起步价，本仓 spawn_edges 510 条）；d) aoci MCP 对 Codex 零义务（裁定 #85）纯注入浪费；e) 单条工具输出最大 42k chars 常驻每轮重发。佐证：10-19 单日 157 线程 4.4 亿 tokens。③**建议 5 项待用户裁定**：删 aoci MCP / 关闲插件 / 派单提示词禁 spawn subagent / 派单附精确验收命令减探索轮 / reasoning effort 降 medium。

S145 | 监督员 | 2026-10-20 Asia/Shanghai | S142/S143 验收 PASS+代提交 | ①**S142（T55-RV）**：复跑回归 13 passed 与 A 复核一致，diff 域零越界（schedule.py +5/-3、test_schedule_policies.py +84/-0）→代提交 `1f0e365`（含修复计划 §5 两处失效 -k 表达式修正：`queue_skip_advances_after_capacity_is_released`、`skip_policy_skips_a_single_overdue_occurrence`）；②**S143（T69+T67）**：六类节点 e2e 7/7 GREEN、dry_run_api 8/8 绿、I69 证据 3 文件在位→代提交 `c267917`（5 files +919/-10）；③两笔均未 push；④S127–S143 已归档 archive/2026-10-20-STATE-S127-S143.md；⑤在飞池：Codex=0、Claude=0（s127 六单随 S131 撤销，T55-RV/T69/T67 已闭环），下一单待用户裁定 token 优化方向后滚动派单；⑥S143 上报的 11 个预先存在失败（i19/i20/i23 系列）待派单核查。
