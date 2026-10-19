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
- 历史活动原文归档：`docs/handoff/archive/2026-10-19-STATE-S1-S3.md`、`STATE-S4-S13.md`、`STATE-S14-S21.md`、`STATE-S22-S32.md`、`STATE-S31-S54.md`、`STATE-S55-S60.md`、`STATE-S61-S65.md`、`STATE-S70.md`、`STATE-S71-S73.md`、`STATE-S83-S88.md`、`STATE-S89-S100.md`、`STATE-S101-S108.md`、`STATE-S109-S126.md`、`2026-10-20-STATE-S127-S143.md`、`2026-10-20-STATE-S144-S150.md`。

S151 | Trae线 | 2026-10-20 04:39 Asia/Shanghai | preexist-11-failures-i19-i20-i23 | 完成
交付：datara-backend/tests/rebuild/ 下 i19_preview_api（_client 改 i21 直发 DEVELOPER token 模式）、i20_preview_api（同）、i23_mapping（角色数据迁移新枚举 dev/analyst→developer/operator）3 个测试文件 + rebuild/api/app.py current_user capability 白名单收口（仅 validation:bootstrap 放行，恢复 endpoint-only 契约且兼容 bootstrap）；提交由监督线代办
证据：docs/increments/evidence/2026-10-20-Trae-preexist-11-failures-i19-i20-i23.md（根因三分类：A/B=用例预期过时、C=用例预期过时、D=实现缺陷；git 取证定案 11 失败=rb 线工作区回归非 HEAD 预存）；定向 pytest 4 文件→18 passed；全量 pytest tests/rebuild -q → 865 passed, 1 skipped, 0 failed（854P/11F→865P/0F 达成）
阻塞：无
下一单：待监督线验收派单

S152 | Trae线 | 2026-10-20 04:56 Asia/Shanghai | T46r-sync+p0-4-r4-sync | 完成（核查型交付，零代码改动）
交付：核查报告 docs/increments/evidence/SYNC/2026-10-20-T46r-sync收口与R4接线核查.md；T46r 全任务点（D1 sync_executor 接入共享执行层/D2 统计8项/D3 血缘回写/D7 产出核查/SYNC-01 02 03 05 06/09 + R4-SYNC 契约解禁 + syncComponentApi 接线）已被工作区产出（rb 线未提交改动）覆盖，无需补码；SYNC-04/07/08 待后续（环境依赖/worker 超文件域）
证据：定向 4 文件 pytest→21 passed；前端 vitest sync-form→2 文件 5 passed；全量 pytest tests/rebuild -q→865 passed, 1 skipped, 0 failed（与 S151 基线一致不新增失败）；逐项核查对照表见证据文件 §二
阻塞：无（SYNC-04/07/08 记待后续，非本单阻塞）
下一单：待监督线验收派单（信箱余 T47r-stream、T48r-exec）

S153 | 监督员 | 2026-10-20 Asia/Shanghai | 四单验收 PASS+全量派单落地 | ①**验收四单全 PASS 并标 done**（连 s129-sqlide-done 重复回报共 10 条）：S151=11 失败修复（i19/i20/i23 三测试文件+app.py capability 白名单收口，定向 18 passed，全量 854P/11F→865P/1s/0F）；P1-6'=缺陷修复单+默认工厂重跑证据+脚本 Role.DEVELOPER 兼容；P-OPT-1=盘点文档收尾；T46r=核查型零代码改动（监督线复跑定向 pytest 21 passed+vitest 2 文件 5 passed，与回报一致；SYNC-04/07/08 记待后续非阻塞）。②**dispatch_s152.py+mailbox_tools.py 落地**（信箱 514 行）派 6 单：Claude×2（G1 mailbox compact：done 占比>50% 或 >500 行滚动归档+--compact-threshold；C21r 工作流域 WF-10~29 修订版，前置 898ea68）+Trae×4（T55r 运行时 P0=RT-01~04+RT-06 fencing、T56r RBAC P0=EXECUTE_SQL+metrics 6 端点+rb 域 4 端点、T57r DEP P0=CANCELLED 终态族、T58r GOV P0=GOV-01/02，串行排 T48r 后）。③**不派项**：FE 全部（用户裁定继续暂缓）、RT-05/RBAC-08（S109 裁定暂缓）、五域 P1/P2 待 P0 批次后续派；s129-ai-done 未验收不动。④S144–S150 已归档 archive/2026-10-20-STATE-S144-S150.md。⑤代提交五组（S151/P1-6'/P-OPT-1/T46r-SYNC 域/基础设施含 WBS 派单真源文档）并 push；本条+信箱快照+脚本+归档卷随本窗提交。
