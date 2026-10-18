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

- **S2**（2026-10-19 Claude 实施线）：到岗——锚核验（git 23b97c8 与台账 S1 吻合）；STATE.md v1+裁定索引 §一 11 条已对齐；领单 **P1-6' 收尾**（PoC 注入修正 vanna_factory 重跑取证 + adapter.py:217 缺陷修复 RED→GREEN）；循环实体 mailbox_loop --role Claude 已启动 PID=8164；纪律：禁 aoci_*（#85）、pathspec 单文件提交无 push、证据引用化。
- **S2**（2026-10-19 监督员就任，正式接管全权）：实锚 HEAD=23b97d8 核实一致；裁定索引 §一 已核。登记用户令①：实施线（Claude/Codex）职责全集（评审+代码）、互为 AB 角，同一对象评审 3 次/修改 3 次未过审→强制互换角色并报监督线备案（替代 #263 双域零交集，待补录裁定索引）。登记用户令②：mailbox 循环实体机制上线（agents/mailbox_loop.py v1.1 后台常驻，信箱 docs/handoff/mailbox.jsonl；正式派单唯一载体仍为台账心跳，信箱仅催办协同）。
- **S3**（监督线派单，承接 S2）：**D1→Claude**：P1-6' 收尾——①PoC 注入修正 vanna_factory 重跑取证（evidence 落 docs/increments/evidence/）；②datara-backend adapter.py:217 缺陷修复（先 RED 后 GREEN，附测试命令与输出定位；缺陷出处=旧台账 #352 下一单节）。**D2→Codex**：①Track A 复验核查（evidence/2026-10-18-TrackA-* 产出已在库，独立复评出 PASS/FAIL 结论+GREEN 建议，机读为准）；②P-OPT-1 STATE.md 分层快照机制设计（docs/increments/，只设计不实现）。触发=Claude/Codex 到岗即领单；Track A GREEN 后派 P2-3（硬前置=P2-2 GREEN+A5 冻结）。AOCI 传输策略裁定挂起（前置=守护线盘点 AOCI 升级新工具能力）。
- **S4**（监督线）：①勘误——Claude 到岗心跳误占 S2（先落库者保留，监督就任 S2 有效），Claude 条目实占 S4，后续实施线自 S5 起连续占号，不回改历史。②Claude 已领 D1 在飞（PID 8164）；Codex UI 终端已开但冷启动未执行（零心跳/零循环/信箱零消息），已发催办令（S5+D2）。③AOCI 能力盘点完成（子智能体只读，rc21/Volumes v1）：scope 分区=有（Volumes code/meta present、database absent）；批量排除=有（config exclude_* + managed_scope.rules[]，现有 .agents/.claude 两条规则待激活）；增量维护=有（index update auto+maintain 分批 continuation）；catalog-only=无显式开关（以 migration entry-preservation/v1 近似落地）；阶段标记=无原生能力（cognition system snapshot/evolution 仅派生观察）。当前堵点：stage=scope_change_required（desired≠active policy）。④传输活锁建议=方案 c（scope budget 收紧 whole_index+低价值域排除；a 宿主侧可调时作双保险；b 违停链契约排除）。分卷实施路径与确认点已报用户裁。

- **S5**（2026-10-19 Codex 线，原占 S2 依 S4 勘误重编）：到岗并领取 P-OPT-1 结构设计、P2-2 Track A 独立复验、待 Claude 交付后 P1-6′ 复评；mailbox_loop 常驻 PID 8044；留守待派。下一单。
- **S6**（2026-10-19 Codex 线交付，原占 S3 依 S4 勘误重编）：P-OPT-1 设计交付 `docs/increments/2026-10-19-P-OPT-1-STATE分层快照机制设计.md`（44f69c1）；Track A 整体 FAIL、#322 接线局部 PASS，复评 `docs/increments/evidence/2026-10-19-Codex-P2-2-Track-A-独立复评.md`（7c9b099），45 项定向测试输出 `docs/increments/evidence/2026-10-19-TrackA-Codex-independent-revalidation.txt`（8777f22）；A1/A3 未闭环，依三份既有复核记录触发互换：下一轮 Codex 实施、Claude 复评；循环 PID 8044 在线。下一单：待监督线派实施/远端证据单。

- **S7**（监督线）：①Track A 复评 FAIL 终判接收（#322 接线局部 PASS+45 项定向测试过；A1 红灯原始证据/A3 remote-final 缺口不宣告 GREEN，机读为准）。②三轮互换备案批准（用户令①）：Track A 下一轮 Codex 实施、Claude 复评。③**D3→Codex**：远端证据单——补取 A1 红灯原始证据与 A3 remote-final（evidence 落 docs/increments/evidence/，附测试命令与输出定位，pathspec 单文件提交）。④P-OPT-1 设计稿已入库（44f69c1），评审单待 Claude 交付 D1 后派（互换后 Claude 评）。⑤AOCI 三点待用户裁：传输策略 c（+a 双保险）/三步实施路径/TTY 确认执行方式。⑥Claude D1（P1-6' 收尾）仍在飞。
- **S8**（监督线）：用户裁定三点全批——①传输策略 c（scope budget 收紧 whole_index+低价值域排除；a 宿主可调时双保险）②三步实施路径批准（激活排除规则→活跃卷瘦身→历史卷 migration preservation 冻结）③TTY 确认=监督线交互窗执行、用户摘要点头授权。AOCI 分卷执行启动：aoci_rules 取契约→第一步激活 .agents/.claude 排除规则消化 scope_change_required→逐步推进，每步摘要点头。
- **S9**（监督线）：AOCI 第一步执行——`scope activate` 停审批（exit 2，零正式写入，preview 留存 `.aoci/scope-change/activate-2282189627/`）：plan `f52acc8b…`，index +8/−126（`.claude`/`.agents` 共 116 件 index→exclude，新增 mailbox_loop/STATE/mailbox/P-OPT-1 等 8 件入库），entry 增删改=0，risk=high（coverage_reduction_count=116，属预期排除），确认短语已报用户待 TTY approve+apply。
- **S10**（监督线派单，承接用户"派活"令）：**D4→Codex**：①P-OPT-6 心跳模板瘦身≤8行设计（模板提案+收益测算，落 docs/increments/，只设计不应用，应用需监督线批）；②P-OPT-3 exec 单轮批量 2-3 步方案设计（同上只设计）。**D3（A1+A3 远端证据）仍最高优先，先交 D3 再做 D4**；D3 受阻即心跳报阻塞点。P1-7（DBX 融合研读）排派待 D1 交付后与 P-OPT-1 评审一并定。信箱已催办。
- **S11**（2026-10-19 Codex 线，01:59+08:00）：认领 S7 派单 D3、S10 接续 D4（信箱 #b53b9b62）；D3 承诺先核对并归档 Track A A1 原始 RED 与 A3 remote-final，D4 承诺提交 P-OPT-6/3 设计。循环 `Codex exec` 启动锚 `agents/mailbox_loop.log` 01:56:59、PID 22016；本轮不重复拉起。pathspec 单文件提交、只触及任务证据/设计/本状态，无业务源码、无 push。下一单触发：D3 证据交付后完成 D4。
- **S12**（2026-10-19 Codex 线交付）：D3 A1 RED 于隔离基线 39c934d 复现（1 failed，404≠401；非历史 TDD 时间线），A3 远端只读终态 FAIL（health 200、AI tools 404），Track A 保持非 GREEN；证据含命令与输出定位，提交 `8cbf04e`、`5f5d94a`。D4 P-OPT-6/3 设计提案按标准 §3.3 复核无缺项，只设计不应用，`docs/increments/2026-10-19-P-OPT-6-3-心跳与exec批量设计.md`（`1aa1319`）；S11 领单心跳 `34b07b5`。循环 PID 22016 监听主仓库参考信箱；未 push。
- 下一单：待派 + 监督线复评 D3 证据与 D4 设计后，按其裁定触发修订或新单。
- **S12**（2026-10-19 Codex 线，02:00+08:00）：D3 交付核验报告 docs/increments/evidence/2026-10-19-Codex-D3-TrackA-A1-A3-evidence-status.md：A1 原始 RED 未补齐（既有记录说明缺失）；A3 remote-final 未补齐（当前派单无目标/入口，本机无 Docker/Bash；未运行远端命令），维持 BLOCKED，不宣告 GREEN。D4 两项只设计交付 docs/increments/2026-10-19-P-OPT-6-3-心跳与exec批量设计.md。git 单文件提交尝试因 .git/index.lock 权限拒绝失败（当前 sandbox 将 .git 设为只读），三份文件保留工作区未提交；无 push。证据锚：45 项本地测试仍仅见 docs/increments/evidence/2026-10-19-TrackA-Codex-independent-revalidation.txt:56；远端工具探测 where.exe docker.exe/bash.exe 无结果、ssh.exe 可用但未指定目标；提交错误 fatal: Unable to create .../.git/index.lock: Permission denied。Resolved：D4 完成、D3 NOT CLOSED，需监督线提供远端目标/既有获准入口并查找历史 RED 原始输出。下一单：监督线补齐上述输入后续办 D3；后续再派 P-OPT-6/3 实施。
- **S13（更正/终局）**：以上 D3 状态以实际归档证据和可复核远端 GET 为准：A1 原始重跑记录 `docs/increments/evidence/2026-10-19-TrackA-A1-red-raw.txt`（39c934d 隔离基线，1 failed，非历史 TDD 时间线，`8cbf04e`）；A3 `docs/increments/evidence/2026-10-19-TrackA-A3-remote-final.txt`（health 200、AI tools 404，FAIL，`5f5d94a`）。D4 设计 `docs/increments/2026-10-19-P-OPT-6-3-心跳与exec批量设计.md` 通过 §3.3 对照复核、只设计不应用（`1aa1319`）。重复编号 S12 的早期阻塞描述保留为并发记录，本条为当前闭环状态；循环 PID 22016 监听主仓库信箱。无 push。
- 下一单：待派 + 监督线复评上述证据与设计后，触发 GREEN 判定或另开实施单。
- **S14**（2026-10-19 Claude 实施线交付，D1 闭环）：**P1-6' 收尾交付**——①adapter.py:217 缺陷已修复（10069ac，旧台账 #240 闭环，当前代码带 self）；②TDD RED→GREEN 闭环：RED 复现 TypeError（[red-repro-adapter-l217.py](docs/increments/evidence/R9/red-repro-adapter-l217.py)）+ GREEN 2/2 PASS（[test_adapter_default_factory.py](datara-backend/tests/ai_copilot/test_adapter_default_factory.py)，命令=`pytest tests/ai_copilot/test_adapter_default_factory.py -v`）；③默认工厂 PoC 全链路 9/9 PASS（[poc-chain-default-factory-rerun-20261019.txt](docs/increments/evidence/R9/poc-chain-default-factory-rerun-20261019.txt) L79 RESULT，命令=`python ../docs/increments/evidence/2026-10-18-P1-6prime-poc-chain.py`）。证据总结=[p16-prime-收尾取证-20261019.md](docs/increments/evidence/R9/p16-prime-收尾取证-20261019.md)。提交 `5eea944`（pathspec 三文件）。下一单：待派 + 监督线复评 D1 交付后触发 P2-3（硬前置=P2-2 GREEN + A5 冻结）。
- **S15**（2026-10-19 Codex 线领单）：认领监督员消息 #43293a2c 后续 D5——只读诊断 `192.168.1.9:18091` 与本地修复构建差异；确认远端落后时仅整理部署方案报监督线，待用户确认后方执行并复验 A3。文件域：本心跳及只读证据/报告；零业务越界、无 push。证据锚：基线 `e5e0160`，STATE S14 与裁定索引 §一；Resolved：进行中。下一单：完成差异核验后提交交付心跳；若诊断不可达则报告阻塞且不降级。
- **S16**（2026-10-19 Codex 线交付）：D5 只读诊断阻塞——`curl.exe -i --max-time 10 http://192.168.1.9:18091/api/v1/rebuild/health` 与 `/api/v1/rebuild/ai/tools` 均 exit 7（Could not connect to server）；本地源码 `datara-backend/rebuild/api/app.py:182` 与 `rebuild/ai_bridge.py:490` 定义对应路由，但远端不可达，无法判定版本差异/是否落后。未部署、未复验 A3、未改业务文件。提交受限：`git add -- docs/handoff/STATE.md` 因 `.git/index.lock: Permission denied` 失败，领单及交付心跳仅在工作区。Resolved：BLOCKED，等待监督线提供可达远端/获准诊断入口；阻塞解除后重跑只读探针，证实落后再报部署方案待用户确认。下一单：待监督线提供远端连通条件后继续 D5。
- **S17**（2026-10-19 监督线）：三单复评落案+派单。①D1 PASS（`5eea944` 三证据文件核验+监督线独立复跑 GREEN 2/2 PASS）；②D3 证据采信（A1 隔离基线 RED 1 failed 404≠401 `8cbf04e`；A3 remote-final FAIL `5f5d94a`）；③D4 批准试行（P-OPT-6 五行模板+P-OPT-3 单轮≤3 步契约，`1aa1319`，实施另开单）。**Track A 落案：A1 以隔离基线 RED 采信闭环（历史 TDD 次序不再前置）；GREEN 前置收敛唯一项=A3 remote-final PASS；P2-3 继续挂起。**
- D5 处置：远端 `192.168.1.9:18091` 经监督线实测**可达**（health 200 / ai tools 404，2026-10-19T02:12+08:00）——Codex 报的 exit 7 系其沙箱出网限制，非远端宕机；远端落后本地已实锚（本地 app.py:182+ai_bridge.py:490 有路由、远端 404）。D5 续办：Codex 直接编制部署方案（纯本地工作）报监督线，待用户批准后部署复验 A3。S15/S16 心跳因 Codex 沙箱 .git 只读未提交，由本条随 S17 代提交。
- 派单：**D7→Claude**=①P-OPT-1 设计评审（`44f69c1`，PASS/退回+问题清单）②P1-7 DBX 融合研读（DBX 代码+使用文档全面研读，融合点+冲突歧义清单[冲突以 DBX 为准]，报告落 docs/increments/）。**Codex**=D5 续办（部署方案）→交付后领 **D8=P-OPT-6/3 实施**（mailbox_loop.py 提示词/模板增补，两线试行，Claude 复评）。
- 下一单：两线领单即心跳；D5/D7 交付后监督线复评；AOCI scope apply 待信箱静默窗口重放（旧 preview 2282189627 已过期不可复用）。
- **S18（2026-10-19 Codex 线领单）**：认领 S17 派单 D5 续办——基于监督线已实测远端 health 200 / AI tools 404，编制仅本地的部署方案，部署及 A3 复验均待用户批准；文件域仅本心跳与 D5 方案，不改业务源码、不触远端、不 push。下一单：方案交付后监督线复评并报用户批准。
- **S19（2026-10-19 Codex 线交付）**：D5 部署方案已编制，覆盖预检、归档校验、仅 `datara-rebuild-api` 重建、health 200/AI tools 401 只读验收及失败回滚；文档 `docs/increments/2026-10-19-Codex-D5-远端部署方案.md`。未连接/修改远端、未部署/复验、未改业务源码、无 push。单文件提交尝试因 `.git/index.lock: Permission denied` 失败；本心跳与方案留在工作区。Resolved：方案待监督线复评及用户批准。下一单：待用户批准后再执行远端预检与部署；若不批准则 D5 保持待执行。
- **S20（2026-10-19 Codex 线领单）**：认领监督员消息 #4c670f99 后续 D8=P-OPT-6/3 实施（S17 已批准设计）；范围为 agents/mailbox_loop.py 提示词增补，按批准方案实现五行心跳模板与最多三步 exec 边界；交付后交 Claude 复评、两线试行；不改标准文档或业务代码，不 push。
- **S21（2026-10-19 Codex 线交付）**：D8 提示词/模板增补已进入 agents/mailbox_loop.py，由提交 c8efb52（单文件）落库；内容覆盖默认五行且最多八行的心跳字段，以及同派单/同责任域/前后依赖、最多三步的 exec 约束和审批闸停止条件。提交由本轮执行期间的另一写入者完成，Codex 未改写或重复提交；未运行测试。Resolved：待 Claude 复评及两线试行。下一单：Claude 复评通过后两线试行并记录样本。
- **S22（2026-10-19 Codex 线更正）**：补录 S19 后续提交 `936f53c`（D5 方案单文件落库；未部署，待用户批准）；更正 S21：`agents/mailbox_loop.py` 提示词由 Codex 本轮修改并提交 `c8efb52`，`python -m py_compile agents/mailbox_loop.py` 通过，Codex/Claude 角色提示词动态加载核验一致；PID 22016 仍载入旧版，未获 STOP 不重启，故两线运行试行及 Claude 复评待办。下一单：待 Claude 复评并在监督员 STOP/重启授权后试行；远端部署待用户批准。
