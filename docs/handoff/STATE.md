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

- 历史活动 S1–S3 原文归档：docs/handoff/archive/2026-10-19-STATE-S1-S3.md。
- 历史活动 S4–S13 原文归档：docs/handoff/archive/2026-10-19-STATE-S4-S13.md。
- 历史活动 S14–S21 原文归档：docs/handoff/archive/2026-10-19-STATE-S14-S21.md（D1/D3/D4/D5/D7/D8 早期闭环，已被后续 S 落案取代）。
- **S22（2026-10-19 Codex 线更正）**：补录 S19 后续提交 `936f53c`（D5 方案单文件落库；未部署，待用户批准）；更正 S21：`agents/mailbox_loop.py` 提示词由 Codex 本轮修改并提交 `c8efb52`，`python -m py_compile agents/mailbox_loop.py` 通过，Codex/Claude 角色提示词动态加载核验一致；PID 22016 仍载入旧版，未获 STOP 不重启，故两线运行试行及 Claude 复评待办。下一单：待 Claude 复评并在监督员 STOP/重启授权后试行；远端部署待用户批准。
- **S23（2026-10-19 Codex 线交付/阻塞）**：用户批准 D5 执行后完成只读远端预检；`/lei/datara` 非 Git 工作树、Compose 配置缺 `datara-rebuild-api`，现有 healthy 容器挂载 `/lei/datara/rebuild-source/rebuild`；按方案停止，未上传/切换/重建，远端零写入。证据 `docs/increments/evidence/2026-10-19-Codex-D5-preflight-blocked.txt`（`e8f1d9a`）。Resolved：BLOCKED；需监督线核实正确 Compose 服务与源码锚、修订方案后重新报批。下一单：待监督线提供核定后的目标与新方案。
- **S24**（2026-10-19 Claude 实施线交付，D7 闭环）：①P-OPT-1 评审 PASS（对照裁定基线 11 条全符合，附 4 项非阻塞问题）；②P1-7 DBX 融合研读交付——融合点 F1-F13、冲突歧义 C1-C7（DBX 优先）、原版吸收项 A1-A8，独立亲核 DBX 源码（PoolKind/QueryExecutionMode/ObjectSourceKind 13 变体/CM6 composable）与 v2.3 清单一致无冲突。证据：`docs/increments/evidence/R9/p16-prime-收尾取证-20261019.md`（含 P-OPT-1 评审）、`docs/increments/2026-10-19-P1-7-DBX融合研读-Claude线.md`，提交 `7c61093`（pathspec）。下一单：已派——D8 复评（mailbox_loop.py 提示词/模板，待监督员 STOP/重启授权后试行）。
- **S25（2026-10-19 监督线核定+派单）**：①勘误——本条曾误占 S24 并覆盖 S23，已恢复 S23、Claude S24 保留（先落库者保留，依 S4 先例），本条重编 S25。②D5 预检核定=远端为 bind-mount 源码部署形态：容器 `datara-rebuild-api`（healthy）挂载 `rebuild-source/rebuild→/app/rebuild:ro`+`files→/datara/files`，与本地 `docker-compose.rebuild.yml` volumes 逐一吻合，服务本体定义在根 compose:158。**判定：上新代码无需重建镜像/无需 compose 服务——同步 `datara-backend/rebuild/`→远端 `/lei/datara/rebuild-source/rebuild/`+`docker restart datara-rebuild-api` 即生效；非 Git 工作树→版本核验用内容指纹清单（同步前后 sha256 对照本地 HEAD）；回滚=同步前远端 rebuild 目录 tar 备份；验收=health 200+ai tools 401。**派 **D5-v2→Codex**：按核定事实修订部署方案，落 docs/increments/ 报监督线复评+用户批准后执行。③D8 复评待 Claude（已派）；Codex 循环已 STOP 退出（02:20:30），重启后领 D5-v2；STATE.md 已 62 行，下窗分层快照归档回补 ≤60（P-OPT-1 首次实践）。
- **S27（2026-10-19 Codex 线交付）**：D5-v2 部署方案按 S25 bind-mount 核定修订，docs/increments/2026-10-19-Codex-D5-远端部署方案.md，提交 03e65e9；diff-check 通过，未连接或写入远端、未部署；待监督线复评及用户批准。下一单：待派；收到监督线复评结论和用户明确批准后再进入远端预检/部署。
- **S28（2026-10-19 监督线复评落案）**：D5-v2 方案复评 **PASS**（`03e65e9`）——bind-mount 判定/SHA-256 指纹清单核验/tar 回滚/health 200+ai tools 401 验收/四道停止闸与写入范围均与 S25 核定一致；孤儿"下一单"行 ×2 清理（S12/S13 尾，已被取代），全文守住 ≤60。**已报用户批准执行窗口**；批准后 Codex 按方案 v2 三步执行（预检→备份+同步+指纹对照→重启+验收）→A3 复验→Track A GREEN 判定。AOCI scope apply 挂起待全仓静默窗口（旧 preview 已过期，需重新 activate）。
- **S29（2026-10-19 监督线派单）**：用户批准 D5-v2 部署执行窗口（02:49+08:00，批准锚=本条+信箱 TASK）。**D5-v2-EXEC→Codex**：按方案 v2（`03e65e9`）三步执行——①只读预检+本地 HEAD 基线清单（执行基线 HEAD 取执行开始实锚，从该 HEAD 导出 `datara-backend/rebuild/` 清单）②远端 `/lei/datara/rebuild-source/rebuild/` tar 备份→同步→双端 SHA-256 逐项对照③仅 `docker restart datara-rebuild-api`→验收 health 200+ai tools 401。停止条件/回滚严格按方案 v2；远端写入仅限 rebuild 目录+一个本次命名备份归档；证据落 docs/increments/evidence/，交付后心跳。循环 PID 18624 在飞。
- **S30（2026-10-19 Codex 线交付/阻塞）**：D5-v2-EXEC 按派单 #73b0f4c7 在步骤①本地预检处受阻：HEAD `36132da7c200e1216e8727af7aff071702ce9f83`，`datara-backend/rebuild/` pathspec clean，79 文件 SHA-256 清单 `docs/increments/evidence/2026-10-19-Codex-D5-v2-baseline-36132da.txt`；SSH `root@192.168.1.9` 被本机网络策略拒绝（Permission denied，exit 255）。遵方案停止，未备份/同步/重启/验收，远端零写入。执行证据 `docs/increments/evidence/2026-10-19-Codex-D5-v2-exec-blocked.txt`。Resolved：BLOCKED，需恢复获批 SSH 可达入口后重派/续办。下一单：监督线提供可达入口并重新派发后，从只读预检重新开始。
- **S31（2026-10-19 监督线）**：①**AOCI scope apply 成功落案**（transaction `c9745928…`，preview `activate-3560834360`；scope status 实锚=policy/budget 双 aligned、stage `scope_change_required`→**`authoring_required`**、.agents/.claude 排除规则 enabled）——传输策略 c 第一步闭环；后续=增量维护 authoring（222+ 条，后续窗口推进）。②D5-v2-EXEC BLOCKED 核实：Codex rtk ssh 被沙箱策略拒（exit 255）；**监督线直连 `ssh root@192.168.1.9` 实测可达**（SSH_OK/bobi-host，exit 0）——非远端故障。③处置：执行窗口已批+方案 v2 复评 PASS，**D5-v2-EXEC 由监督线代执行**（代执行先例 S17），结果落 S32；mailbox_loop.py STOP 地雷修复补提交。
- **S32（2026-10-19 监督线代执行交付）**：D5-v2-EXEC 按 S29 批准窗口**监督线代执行 PASS**（Codex rtk ssh 沙箱受阻，S31 备案代执行）——①基线 HEAD `8cc02c6` pathspec clean、158 文件 SHA-256 清单落证；②远端 tar 备份 `rebuild-backup-20261019-031738.tar.gz`（sha256 `de159d6b…`）核对可读→全量同步→**双端 158 项逐项一致**；③仅重启 `datara-rebuild-api`→**验收 PASS：容器 healthy、health 200、ai tools 401（invalid token）**。证据 `docs/increments/evidence/2026-10-19-监督线-D5v2-exec-evidence.md`+基线 txt。**Track A GREEN 宣告**（A1 隔离基线 RED 采信闭环 S17+A3 remote-final PASS 本条+#322 局部 PASS+45 项定向测试）。**派 P2-3→Claude**：R5-B 写入闭环开工（设计输入=A5 契约 v1.0 fc2979e+依赖预研 e545688 已恢复：#21/#22/#25 就绪，#23 缺血缘分析、#24 缺生产执行器为攻坚点），先出实施设计报复评。Codex=重启后备派（AOCI authoring 支援+P2-3 设计 AB 角复评）。
- **S34（2026-10-19 Codex 线领单）**：接监督员 #a9c8ab9d，接手循环子进程启动失败后的只读预研，形成 AOCI authoring 增量维护策略文档；不调用 aoci_*、不改 .aoci/config.json。P2-3 复评待 Claude 交付；留守循环 PID 24208 在线。
- **S35（2026-10-19 Codex 线交付）**：只读预研 AOCI authoring 增量维护策略，文档 docs/increments/2026-10-19-Codex-AOCI-authoring-增量维护预研.md，提交 a6c8e64；config 核对命令输出定位=本轮终端，diff-check 通过，未运行测试/未调用 aoci_* /未改配置。P2-3 复评待 Claude 交付；循环 PID 24208 在线。下一单：待派/待复评；Claude 提交 P2-3 设计或监督线发新单时触发。

- **S27**（2026-10-19 Claude 实施线交付，P2-3 实施设计）：R5-B 写入闭环实施设计 v3 落盘。输入=A5 契约 v1.0 fc2979e + 依赖预研 e545688 + v2 设计。产出=可指导编码的模块结构/DDL 存储表/类接口签名/wire format/错误枚举/测试策略/#23 血缘分析/#24 DDL 执行器攻坚点专项设计。证据：`docs/increments/2026-10-19-P2-3-R5-B写入闭环实施设计-v3.md`，提交 `f0f5d89`（pathspec 单文件，无 push）。下一单：监督线复评 P2-3 v3；Codex 复评 AB 角；D8 试行待 STOP 授权。
- **S36（2026-10-19 监督线复评+批量派单）**：①**P2-3 v3 复评 PASS**（`f0f5d89`，#21-#25 wire/模块/安全边界/测试策略与 A5 fc2979e+裁定 #290 对齐，#23/#24 攻坚专项务实）附 2 非阻塞勘误：硬前置"P2-2 FAIL"时态已被 S32 GREEN 取代（阶段 B 开工条件现状满足，实施引用 S32）；建表 ENGINE/CHARSET 声明实施时统一。②勘误：上行 Claude 心跳误占 S27 号（与 Codex S27 撞号），依先落库者保留先例，其内容采信、序号并入本条引用。③**S35 Codex 预研复评 PASS**（`a6c8e64`，六步路径+角色边界符合 AOCI 豁免，旧 stage 不可复用判定正确）；AOCI apply 仍挂起待用户决定，下个静默窗口按预研六步执行（9 条瘦身规则已在 config.json）。④派单：**CX-1** P2-3 v3 AB 角复评、**CX-2** F2 融合立项预研（任务池 §7 F2 待认领项）、**CX-3** DBX 融合实施方案编制（P1-7 `7c61093` 续办→P2-2 融合输入）→Codex 三单配 3 子智能体；**CL-1** Phase 0 任务池状态核验（P0-1~P0-4 闭环证据）→Claude。P2-3 实施待 AB 角复评 PASS+用户批准后开工。
\n- **S37（2026-10-19 Codex 线领单）**：接监督线 #97f4363c，CX-1 P2-3 v3 AB 角复评、CX-2 F2 差异预研、CX-3 DBX 融合方案；按派单启用 3 个并行子任务。Codex mailbox_loop PID 24208 已在线，不重复启动；Claude PID 23536 在线。三项均不改业务代码/不跑测试/不调用 aoci_*；本条先记领单，独立产物完成后统一复核提交。下一单：CX 三项交付后进入监督线复评；循环自动消费信箱新单或 STOP。
- **S28**（2026-10-19 Claude 实施线交付，CL-1 Phase 0 任务池状态核验）：只读核验分阶段混合集成方案 §7 Phase 0 四项闭环证据。P0-1（A2 v2.1 冻结）CLOSED——884277f+25c18a1+6856215；P0-2（R2 GREEN）CLOSED——0824069+6047f0d+1709809；P0-3（R7 GREEN）CLOSED——e0a21ff+e8a622a+1709809；P0-4（R4-SYNC/依赖/资源接线）OPEN——DEP/RES GREEN（1c6d834+b8e3add）但 R4-SYNC 暂停终裁不派发（53990fb）。证据：`docs/increments/2026-10-19-Phase0-任务池状态矩阵.md`，提交 `08631a7`（pathspec 单文件，无 push）。下一单：监督线复评 CL-1；P2-3 实施待 Codex AB 角+用户批准；D8 试行待 STOP 授权。
- **S38（2026-10-19 Codex 线交付）**：CX-1 P2-3 v3 AB 复评 PASS，报告 docs/increments/2026-10-19-Codex-CX-1-P2-3-v3-AB复评.md（3c3d037）；CX-2 F2 差异盘点 docs/increments/2026-10-19-Codex-F2-前端融合差异盘点.md（f219583，diff-check 通过）；CX-3 DBX/SQLIDE 方案 docs/increments/2026-10-19-Codex-P2-2-DBX-SQLIDE融合实施方案.md（4aa901f）。均单文件提交、无 push/页面改造/aoci_*，未运行测试。循环 PID 24208 在线，留守待派。下一单：待派；新 TASK 或 STOP 经循环唤醒触发。
- **S39**（2026-10-19 监督线四交付复核+派单）：①**CX-1 AB 复评 PASS 采信**（3c3d037）→**P2-3 v3 设计终裁 PASS**（监督线 S36+AB 双 PASS，用户批准锚=用户明示批准）——**派 P2-3-IMPL-B1→Claude**：按 v3 阶段 B 首批实施（rb 八包骨架+rb_models+rb_errors+三表迁移+单测 RED→GREEN），只新增 rb/ 包不改 R5-A。②**CL-1 矩阵 PASS 采信**（08631a7 落盘版取代信箱内联版）：P0-1/2/3 CLOSED；**P0-4 CLOSED**（DEP/RES GREEN，R4-SYNC 以 53990fb 终裁不派发为准）——**Phase 0 全收口**。③**CX-2 PASS 采信**（f219583，Phase 3 立项输入就绪）；**CX-3 PASS 采信**（4aa901f）——**派 P2-2-FUSION-0→Codex**：按方案阶段 0 建 P1-7 F/C/A 逐条映射追踪表。④格式勘误：S37 转义残留已修；S14-S21 归档。⑤AOCI 瘦身窗口改策：不为此停线，取两线自然待命间隙执行。
