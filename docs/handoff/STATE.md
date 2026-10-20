# STATE — 监督线现状基线（新纪元唯一权威起点）

> **版本**：v1（2026-10-19 就任准备落库）
> **性质**：冷启动首读文件。旧台账 `2026-10-16-并行协作分工.md`（#1–#352，含双序列与 #317 撞号污染）**冻结为历史考古区，只读不写**；本文件起用新序号 S#。
> **维护纪律**：每监督窗由监督线更新快照+活动区追加一条；全文 ≤60 行硬上限。

## 一、现状快照（2026-10-19）
- **当前值班**：**C 角**（任务性值班，2026-10-20 用户令「处理监督线所有积压任务」直达本角，按 §1.1 用户指令路由接管；B 角按 §1.1 转待命；A 角 AOCI 待命中；入口=`docs/handoff/监管员启动提示词.md`）
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
- 历史活动原文归档：`docs/handoff/archive/2026-10-19-STATE-S1-S3.md`、`STATE-S4-S13.md`、`STATE-S14-S21.md`、`STATE-S22-S32.md`、`STATE-S31-S54.md`、`STATE-S55-S60.md`、`STATE-S61-S65.md`、`STATE-S70.md`、`STATE-S71-S73.md`、`STATE-S83-S88.md`、`STATE-S89-S100.md`、`STATE-S101-S108.md`、`STATE-S109-S126.md`、`2026-10-20-STATE-S127-S143.md`、`2026-10-20-STATE-S144-S150.md`、`2026-10-20-STATE-S151-S156.md`、`2026-10-20-STATE-S157-S165.md`、`2026-10-20-STATE-S166-S171.md`、`2026-10-20-STATE-S172-S177.md`、`2026-10-20-STATE-S178-S182.md`、`2026-10-20-STATE-S183-S189.md`。

S190 | 监督员A(AOCI守护) | 2026-10-20 20:40 Asia/Shanghai（机器时钟实锚） | D3 收口完成（用户 TTY 三连 apply 成功）+D4 启动 | ①用户本地执行 activate→approve→apply 成功，新 Baseline 5e2cf8e7…；中途两次防错拒均属设计行为（approve 未完成即 apply→human_tty_digest_confirmation_not_confirmed；approve 与 apply 隔约 3h 期间三线落盘漂移→managed_scope_replay_mismatch），重走三连+紧接 apply 消解。②收口实锚：scope show desired==active aligned=true（策略 785d…双向一致）、exclude 2054→2058（handoff 考古卷入排）、verify 候选结构有效；E scale 381/916 已知项并入 D4 后 maintain cognition_optimization=e_scale_mismatch 批次顺带修正。③STATE 滚动归档 S183–S189→archive/2026-10-20-STATE-S183-S189.md（本文件 33 行）。下一单：D4 清理提交——git rm 138 删+剩余 8 件移档（SEED_WF_HANDOFF+实测包×2→archive、B2 2 件→increments/archive、ui_*.png×3→evidence、datara-web/deploy nginx.conf+Dockerfile 先移出再删整目录）+业务/AOCI 两笔分开提交+verify 留痕+tag v0.1-pre-wbs；前置已核：dist/ 未入库销项

S192 | 监督员A(AOCI守护) | 2026-10-20 | D4 清理提交收口（A 角，晚于 B 角 S191，避撞改号） | ①A 组 138 清零：git 追踪 137 件删除（agents 11+deploy i8/i9 45+debug 探针 11+tools 播种 20+i13 冒烟 2+Dockerfile.r2-12-d+public 验证页 11+web deploy 36）+未追踪 mailbox_loop.log 磁盘删除；引用面核查无活跃引用，deploy/ 与 datara-web/deploy/ 空目录撤除。②移档 8 件+基建 2 件：SEED_WF_HANDOFF+实测包×2→docs/archive/2026-10-20/（实测包 27KB 一并入库）、B2×2→increments/archive/2026-10-20/、ui 截图×3→increments/evidence/、nginx.conf+Dockerfile→datara-web/ 根保留（无 compose/infra 引用）。③业务/AOCI 两笔分开提交+tag v0.1-pre-wbs；MANIFEST 批次三、D1 清单、STATE S166–S189 归档件随业务笔入库。④后续：aoci_maintain 批次（orphan 清退+E scale 381 cognition_optimization 顺带修）→ D5 文档权威化 → D6 传输量重估。

S191 | 监督员B(经用户直令代行) | 2026-10-20 23:30 Asia/Shanghai | 用户重申「预研所有 WBS 生产库存」——在飞盘点+活性核查+催办 | ①**零新交付实况**：15 张预研（s188-* 三封）派单后约 30 分钟全部在途（方案型深度预研正常需时）；INC17 仅 B7（已验收毕）；0.7 修订候 Claude。②**活性核查**（信箱 74 行）：Codex 活跃（22:50 B7 交付，回执 s189-cd-b7-accept 已达）；Claude 线最后回报 20:30（约 3h）、Trae 线最后心跳 20:32（约 3h）——两线在飞最重（Claude=0.7 修订+A6 对照登记+预研×5；Trae=B3+B6 对照登记+预研×5），已落催办信 s190-cl-nudge/s190-tr-nudge（含下一心跳编号 S191 起编提醒防撞号）。③**库存生产闭环就绪**：预研交付到达即走 审定（六节完整性+实锚+拆票粒度+开放问题单列四查）→⛏ 拆票→入库存池。④知悉 A 角 S190：D3 收口完成（用户 TTY apply 成功，Baseline 5e2cf8e7…），A 角转 D4 清理提交。未 git 提交未推送。
下一单：三线交付到达→验收/审定→to-tickets 拆票入库存；Claude 0.7 修订回报→审定→Codex 开工确认
