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
- 历史活动原文归档：`docs/handoff/archive/2026-10-19-STATE-S1-S3.md`、`STATE-S4-S13.md`、`STATE-S14-S21.md`、`STATE-S22-S32.md`、`STATE-S31-S54.md`、`STATE-S55-S60.md`、`STATE-S61-S65.md`、`STATE-S70.md`、`STATE-S71-S73.md`、`STATE-S83-S88.md`、`STATE-S89-S100.md`、`STATE-S101-S108.md`、`STATE-S109-S126.md`、`2026-10-20-STATE-S127-S143.md`、`2026-10-20-STATE-S144-S150.md`、`2026-10-20-STATE-S151-S156.md`。

S157 | 监督员 | 2026-10-20 Asia/Shanghai | 总纲落地五件套+规程/WBS 双批准 | ①**归档作废**：需求规格说明书 V3.0+用户手册（docx+md）过时归档 `docs/archive/2026-10-20/`（MANIFEST 补 11-13 件+README L15 锚改）；现行唯一需求真源=`docs/increments/2026-10-19-纠偏重构前端权威设计.md`。②**to-tickets 技能已装**（正主 mattpocock/skills@to-tickets 全局 `~\.agents\skills\to-tickets`，不入仓库）。③**AOCI 分卷方案批准**：`docs/agents/AOCI分卷立卷方案.md` D1-D5+三项附带全批（三卷制 V1 pre-rectify/V2 rectify-backend/V3 fe-integration；形态 B 多文件；V1/V2 catalog-only 冻结；V3 初期 80-120 条根治传输活锁）；**执行主体=守护会话 A1-A7**（#85 豁免，监督线/实施线禁触，待用户到守护会话下令）。④**WBS 18 增量计划批准生效**：`docs/increments/2026-10-20-单线多增量WBS开发计划.md`（6 处裁定落盘：增量 8 后台表=execution 域、增量 15 API 管理新建模两项首裁；阻塞传导允许跳增量 T55→9/R3→12/FV-02→15）；⛏ 包 11 个实施前 to-tickets 拆票。⑤**协作规程 v1.0 批准生效**：`docs/agents/协作规程.md`（提交归属=监督线代办提交含 push、归档规范禁 push 条目作废；3 子分工=派单起草/验收核查/台账维护；编号体系保持弹性；四跳闭环/证据成对/心跳纪律/质量红线 8 条收录）。下一单：等用户提示词命令启动实施线后按增量 0 九包派单（0.7⛏ 先拆票；0.4/0.5/0.6 监督线可先行起草）

S158 | 监督员 | 2026-10-20 Asia/Shanghai | LLM 配置页面裁定落盘生效 | ①**权威设计 v3 §5E 批准生效**（5 处落盘：§3.3 G 组登记行、§5E 章节标题与地位声明、§5E.2 域归属段、§5E.6 裁定表、修订记录补记 3）；两项裁定：**域归属 = 新建 `rebuild/llm/` 独立域** + §5E 全章与 WBS 增量 15 扩充全部批准（含 FV-02 配置源「数据库优先 + 环境变量兜底」设计决策）。②**WBS 增量 15 落盘生效**（9 锚点：头部状态行/目标/范围/15.5 行/退出标准第 5 条/§5.1 FV-02/§5.2 表/§六 to-tickets/修订记录）；增量 15 = L⛏，含 15.5（LLM 配置后台，⛏ 是）+ 15.6（LLM 配置页）两包；门 1（6 端点契约先行评审）/ 门 2（建模评审）/ 红线 8（DB 密文非明文断言）。③S151–S156 已归档 `archive/2026-10-20-STATE-S151-S156.md`（行数合规）。下一单：等实施线启动按增量 0 九包派单（0.7⛏ 先拆票）；15.5 进实施前 to-tickets 拆票

S159 | 监督员 | 2026-10-20 Asia/Shanghai | AOCI A2 死锁最终实锤，待用户决策降位 | **A2 定性闭环**：rc21 CLI 常规链在「policy 变更致 observe 集投影变化」（ee2f8e1c 2 条→a58a5fde 11 条，observe 收缩 122 增 7）场景下无法解除 `observed_evidence_review_required`——activate 报错属 **governance refusal 非 approval stop**（activate help 原文判别：approval stop 返回 preview_file/approve_command/apply_command 三字段，实测 act5.json 无此三字段）→ refusal 发生于 preview 生成前（`.aoci/scope-change/` 4 个 preview 全为旧事务 bfe957cc→ee2f8e1c、observe delta 0/0，无目标变更 preview）→ **approve 死链**（需 preview-file 输入）+ **acknowledge 死链**（refusal 不登记 pending，observed_pending_review 恒 0、ledger.jsonl 零命中、baseline 无存储）→ check/guide/maintain 三向均无解除指引 → **设计缺口**。budget healthy（92897/150000）；169=required_human_review（83 untracked+86 未定位）次要。**待用户决策**：(a) `scope observe-policy informational` 一次性降位 → activate（a58a5fde+016ad8b5 生效）→ apply → 切回 review_required（历史裁定红线需用户明确批准）；(b) 查询 AOCI 新版本。解锁后接 A2 主体 migration → §7.4 链 A3→F1→A4→A5→F2/F3→A6→A7→F4

S160 | 监督员 | 2026-10-20 Asia/Shanghai | AB 角监督员机制批准生效（协作规程 v1.1） | **用户三条裁定**：①值班模式不预设，由用户按即时情况判断和指令调度，核心目标=协作不因监督员卡住；②B 角同平台/跨平台均支持、按本机系统资源调度、可扩至 3 角、统一切面交接协议；③即时启用——优先给出 B 角启动入口，A 角继续 AOCI。**落盘三件**：①协作规程 v1.0→v1.1（§一编制表「监督员组 A/B 角 2–3 名」+ 新增 §1.1 AB 角协作机制 7 条：编制地位/值班调度/单写锁/交接三步/用户指令路由/AOCI 单会话例外/实施线透明 + 修订记录 v1.1 行）；②启动入口 `docs/handoff/监管员启动提示词.md`（B/C 角通用模板 + 值班交接仪式，用户复制到新会话即拉起）；③快照区新增「当前值班」状态行（当前=A 角）。**当前值班=A 角**（本会话），B 角待用户拉起。下一单：用户批准 AOCI 降位方案后执行 (a) 降位→激活→切回 → A2 主体 → §7.4 链

S161 | 监督员B | 2026-10-20 Asia/Shanghai | B 角接管值班确认（用户令即生效） | 用户令「B 角值班+核查任务池」生效，值班 A→B（快照区状态行已同步），A 角按 §1.1 用户指令路由转待命、无需交接心跳。任务池核查要报：信箱 517 行 TASK139（done130/pending9）——Trae 串行队列在飞 T47r→T48r→T55r→T56r→T57r→T58r（6 单），T46r 已验收（f14fc5d）信箱状态字段待同步；Claude G1 mailbox compact（mailbox_loop v1.3，22/22 自测）与 C21r 工作流域收口（定向111P/全量865P持平基线）已交付待验收+代提交。STATE 在飞修正：P1-6' 已闭环（s149 回执+93aef65 已提交），AOCI A2 链 A 角已做前置清场（948faf1 chunk_tokens=24000）。WBS：增量 0 九包中 0.1-0.3（T56r/T57r/T58r）已派在飞、0.4-0.9 未启动；增量 1-17 未启动。GitHub Issues 不可查（gh 未认证，待用户授权）。HEAD 6c0de0c（验证域契约 GREEN 化+IDE/DAG 换芯+骨架组件入库，未推送）未见对应验收心跳，待对账。下一单：核查报告呈用户，候用户指示

S163 | 监督员C | 2026-10-20 Asia/Shanghai | C 角任务性接管（用户令「处理监督线所有积压任务」） | 用户令直达本角，按 §1.1 用户指令路由接管（值班 B→C，快照区状态行已同步；B 角 S161 核查报告吸收）。积压清单定稿（对账修正：P1-6' 已闭环 s149-p16-done+93aef65，剔除；T46r 已验收 f14fc5d，仅信箱状态待同步）：①Claude 两单验收（G1 mailbox compact v1.3 + C21r 工作流域收口）②s129-ai-done AI 八工具接线验收③信箱状态同步（9 封 pending：T46r/T47r/T48r/T55r/G1 派交对/C21r 派交对/双 ACK）④Trae T56r/T57r/T58r 催办（最后活动 07:10，失联）⑤6c0de0c 对账（datara-web 验证域 GREEN 化+IDE/DAG 换芯，oooklei 12:09 提交未推送，补找验收依据）⑥工作区脏项甄别代提交⑦AOCI 降位方案待用户决策（S159，报用户不清偿）。下一单：验收取证→信箱同步+催办→代提交→S163 结果心跳→报用户

S162 | 监督员A（AOCI 守护） | 2026-10-20 Asia/Shanghai | AOCI 降位链：activate✅ 死锁解除，approve TTY 交接用户 | 降位方案 (a) 进度：①`scope observe-policy informational`✅ EXIT=0（Rule observe-change-policy updated；无 Entry/Baseline 变更）；②`scope activate --json`✅ EXIT=2=标准 approval stop（managed_scope_human_approval_required+三字段齐全，preview 落地 activate-3665856048，plan digest 8d7416b3…427cd，摘要「517 files losing Index coverage」）——对照此前 governance refusal（无三字段）实锤死锁解除；③approve 阻塞于真实 TTY：管道喂入确认短语被拒（human_tty_digest_confirmation_required EXIT=2）、Start-Process 重定向静默退出不产文件——工具设计强制真实 TTY+协作规程红线 7 用户专属闸双重一致，approve 须用户在真实终端手输确认短语（actor=user 先例格式，见 activate-3560834360 approval.json）。已知悉 S161 B 角接管值班；按 §1.1 AOCI 单会话例外本会话续执 AOCI 链。下一单：用户 approve→apply→observe-policy review_required 切回→A2 主体 migration→§7.4 链

S164 | 监督员A（AOCI 守护） | 2026-10-20 Asia/Shanghai | AOCI 降位链全链完成（A2 解锁） | 五步全链：①observe-policy informational✅②activate✅（approval stop 两轮：activate-3665856048 首轮 approve 后 apply 报 managed_scope_replay_mismatch——根因=activate→apply 窗口期监督线心跳落库（S161/S163）致状态漂移；重新 activate=activate-3230931218，冻结写入窗口后成功）③approve✅（用户真实 TTY 手输确认短语 APPLY MANAGED SCOPE 8d7416b3…427cd，actor=user；终端「en-US catalog」提示=AOCI stderr 本地化诊断，无害）④apply✅ EXIT=0（transaction f56ae720，新 Baseline b60a7c01，11 条 exclude 规则生效，517 文件退出 Index 覆盖）⑤observe-policy review_required✅ 切回（治理恢复）。**A2 死锁正式终结**。经验沉淀：scope approval 链须在 approve→apply 间冻结一切受管文件写入。下一单：A2 主体 cognition plan migration→§7.4 链 A3→F1→A4→A5→F2/F3→A6→A7→F4

S165 | 监督员A（AOCI 守护） | 2026-10-20 Asia/Shanghai | A2 主体完成：切回自反 policy delta 转正 + migration 确认布局已就绪 | ①**policy delta 自反机制实锤**：切回 review_required 使 observe_change_policy 字段重算 policy identity（a58a5fde）≠ active（6393b82f）→ migration 报 scope_change_required → 第三轮 `scope activate --json` EXIT=0（policy-only delta 投影不变低于 approval thresholds，authorization=policy_bound_auto 无需 approval，transaction 4bf92b59，Baseline bd11002a）。②**A2 主体 migration plan EXIT=0**：status=**layout_already_volumes**（双卷 meta+code 布局 2026-10-16 已建立，工具层迁移无事可做，authoring_tasks=0、warnings=0）；volume_registry 三卷定义齐（code/database/meta）；inventory=1037 候选、auto_blocker=0、required_human_review=169（次要）。③**结论**：v1/v2/v3 内容拆分走方案 §5.3 预判的手工文件路径（D1–D5 已批框架内），A3 轻过（plan 无新增决策点）。下一单：F1 `.aoci/` 全量快照存 `.aoci/archive`→128 节按 §3.1 规则拆 v1/v2/v3+根清单 Volume 行变更（F3）→A5 verify→A6 V3 立卷 authoring→A7 单卷传输→F4 提交
