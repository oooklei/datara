# AOCI 分卷立卷方案

> 状态：**已批准**（2026-10-20 用户裁定：D1–D5 按推荐整体批准；三项附带确认全部同意）｜起草：监督线实体子智能体｜2026-10-20
> 执行主体：质量监督线守护会话（#85 豁免；实施线禁触）。守护会话开窗后按 §7.4 顺序链执行：步骤0 清场 → A1–A7 → F1–F4。

---

## 一、裁定记录

### 1.1 用户 2026-10-20 最新裁定（三卷制，本方案的最高依据）

AOCI 认知索引进行**分卷、从 2026-10-20 开始重新立卷**，实行三卷制：

1. **第 1 卷「纠偏前卷」**：纠偏重构（2026-10-16）之前的全部历史；
2. **第 2 卷「纠偏后端重构卷」**：纠偏后的后端重构时期（约 2026-10-16 ~ 2026-10-19，rb 线重建时期）；
3. **第 3 卷「前端重构集成卷」**：从 2026-10-20 立卷的活跃卷，围绕唯一项目目标 `docs/increments/2026-10-19-纠偏重构前端权威设计.md` 推进。

历史卷（第 1、2 卷）采用 **catalog-only 免修**策略：目录内容冻结，不再进入维护闭环。

### 1.2 在案裁定链衔接（本方案的合法性来源）

| 锚 | 裁定点 | 与本方案的关系 |
|---|---|---|
| #85（2026-10-17） | AOCI 全权授权：监督线唯一可调用 aoci_*；实施线豁免，认知源 = docs/handoff/ 心跳 + docs/increments/ 文档 | 本方案由监督线起草执行，实施线零参与 |
| #111 | 传输 chunk_tokens 4000→24000 等 | 传输参数裁定沿革；现 config 实值 chunk_tokens=8000（见 §5） |
| #197 | 守护三度呈报终裁：(a) 窗扩时否决、(b) cursor 接刀否决、**(c) scope 分卷/排除采纳** | 三卷制是 (c) 选项的阶段维度落定实现 |
| #304/#315 | 语义批次 GREEN 后分窗 ≤50/批；#315 分卷评估重启（#197 (c) 框架）；Attestation partial 禁重试 | 分卷评估即 #315 重启项，本方案为其产出 |
| #330 | gen=0 全量传输 4/4 零停链 + attest 9/10（仅历史单次结果） | 证明传输链路本身可用，失败在体量 |
| STATE.md §二-1 | AOCI 传输策略裁定与分卷裁定**联动**；前置 = 盘点 AOCI 新工具能力、产出实施方案报用户裁 | 本文档即该前置产出 |

### 1.3 活锁教训（分卷必须解决的结构性问题）

旧台账 #349–#351：三窗在同一位置停链，**93k token 单窗结构性无法完成全量传输，Attestation 无法提交**（STATE.md §一「AOCI」行）。当前索引体量：`aoci.code.txt` 413KB、128 个目录节、约 1021 条 Entry（正则统计），governance_aligned=false（semantic_change 436/30、222+ 条待消化）。**分卷方案成立与否的硬标准：V3 活跃卷的单卷传输体量必须实质性低于单窗可完成阈值。**

### 1.4 本方案定位

本文档为**方案草案**：所有决策点（§九）须报用户裁定后方可执行；执行主体为质量监督线守护会话（#85），实施线不参与。

---

## 二、卷册定义表

| 维度 | 第 1 卷「纠偏前卷」 | 第 2 卷「纠偏后端重构卷」 | 第 3 卷「前端重构集成卷」 |
|---|---|---|---|
| 卷 id（建议） | `pre-rectify` | `rectify-backend` | `fe-integration` |
| 卷文件（建议，D5 待裁） | `aoci.v1.txt` | `aoci.v2.txt` | `aoci.v3.txt` |
| 起止时间边界 | 对象形成期 < 2026-10-16 00:00（Asia/Shanghai） | 2026-10-16 00:00 ~ 2026-10-20 00:00（含 10-19 全天） | 2026-10-20 00:00 起（立卷日即活跃首日） |
| 边界判定依据 | 旧台账 `docs/handoff/2026-10-16-并行协作分工.md`（#1–#352）以 10-16 开卷，即纠偏重构日（AGENTS.md「Active handoff」节） | STATE.md v1「2026-10-19 就任准备落库」为监督线新纪元起点；rb 线重建产出在 10-16~10-19 形成（S151–S156 于 10-20 核查的均为「rb 线未提交改动」）；权威设计 v1 四项要求出自 10-19 | 权威设计 v3（文件 meta `updated=2026-10-20`）；STATE.md 快照窗 2026-10-20；用户裁定原文「从今天 2026-10-20 立卷」 |
| 覆盖目录域 | 旧后端主体：`datara-backend/api|common|components|alert|master|worker|logger|ai_copilot` 等；旧前端主体：`datara-web/**`（除 `src/views/rebuild/**`）；基础设施：`infra/`、根目录 docker-compose 旧组、LICENSE/README 等 | `datara-backend/rebuild/**`（除 V3 活跃面，见 R2/R3）；`datara-web/src/views/rebuild/**`（rb 线验证页）；`docker-compose.rebuild.yml` 等 rebuild 配套 | `datara-newweb/**`（权威设计 §2 新前端目录，待创建）；`datara-backend/rebuild` 集成活跃面（app.py 装配、§6 迁移端点、models.py）；`docs/handoff/**`、`docs/agents/**`；根治理配置（AGENTS.md、.mcp.json、aoci*.txt 本体、GLOSSARY.md 等） |
| 覆盖对象类型 | code=file；database=table（若 meta 字典卷之外存在表对象条目，按对象入册时期归卷） | 同左 | 同左 |
| 维护策略 | **catalog-only 冻结免修**：不再 maintain/update_entry，语义随卷冻结 | **catalog-only 冻结免修**：同左 | **全维护闭环**：maintain → update_entry → overview/传输/Attestation 正常运转 |
| 卷身份标识建议 | 根清单 `aoci.txt` 增 Volume 行：`#Volume: id=pre-rectify kind=code path=aoci.v1.txt format=object-fras-v2 depends=meta state=enabled`（state 枚举是否支持 catalog-only/archived 语义 → 见 §5 待验证项） | 同左（id=rectify-backend，path=aoci.v2.txt） | 同左（id=fe-integration，path=aoci.v3.txt） |

**meta 字典卷处置**：现役根清单已声明 `#Volume: id=meta kind=meta path=aoci.meta.txt format=meta-v1`（20 行，Tag 字典 + FRAS 纪律 + S 配额）。meta 卷**保留不动**，三个内容卷均 `depends=meta`。

**不入卷对象**：`managed_scope` 现行 11 条排除规则（config.json：docs/increments、datara-backend/tests、datara-web/tests、datara-web/src/__tests__、docs/组件基线化、docs/archive、prototype、datara-web/deploy、release、.agents、.claude）的对象继续排除，不入任何卷。

---

## 三、归卷判定规则

### 3.1 机械判定流程（按序执行，禁止跳步）

- **R3 路径域先验表（第一优先）**：

| 路径域 | 默认卷 |
|---|---|
| `datara-backend/api|common|components|alert|master|worker|logger|ai_copilot/**` | V1 |
| `datara-web/**`（除下两行） | V1 |
| `datara-web/src/views/rebuild/**` | V2 |
| `datara-backend/rebuild/**` | 默认 V2；命中 R2 活跃修正者改判 V3 |
| `datara-newweb/**` | V3 |
| `docs/handoff/**`、`docs/agents/**`、根目录治理配置（AGENTS.md、.mcp.json、GLOSSARY.md、aoci*.txt、docker-compose 旧组中的活跃治理文件） | V3 |
| `infra/`、LICENSE、README、SECURITY 等静态历史资产 | V1 |
| managed_scope 排除域 | 不入卷 |

- **R2 活跃度修正（第二优先，可覆盖路径先验）**：对象在 V3 期（2026-10-20 起）**仍将实质语义演变** → 判 V3。典型：`datara-backend/rebuild/api/app.py`（权威设计 §6 API 一源的五步迁移落点、§0.3 引其 L306 sql_ide 挂载）。
- **R1 形成期判定（第三优先，兜底）**：按对象本体首次引入仓库的时期：<2026-10-16 → V1；[2026-10-16, 2026-10-20) → V2；≥2026-10-20 → V3。
- **R4 冲突消解**：R3 → R2 → R1 仍不能唯一判定时，**报监督线裁定，禁止猜测**（对齐 AOCI「Entry 语义必须来自证据，不得由规则引擎推断」的总纪律——本规则表仅用于**归卷**（卷籍归属），不用于生成任何 Entry 语义）。
- **R5 卷籍终身 + 跨卷引用**：一次归卷、卷籍终身；`R:` 跨卷引用允许；历史卷（V1/V2）冻结后**不因被引对象演变而回写**。
- **R6 新对象单向**：V3 期一切新建对象只入 V3，禁止回填历史卷。
- **R7 语义撰写时间无关性**：卷籍按**对象时期**判定，不按 Entry 语义文本的撰写时间判定（V1 卷允许存在后期补写的高质量语义文本，见样本 5）。

### 3.2 真实 Entry 归卷判定示例（全部来自 2026-10-20 对 `aoci.code.txt` 的实际抽读，行号为该文件行号）

| # | 对象（真实引用） | 归卷 | 判定理由 |
|---|---|---|---|
| 1 | `datara-backend/api/auth.py[EI8S]`（L37，F：登录/登出/token 持久化/角色权限依赖） | V1 | 旧后端 api 域，纠偏前语义定型；权威设计裁定 2「API 一源走新后端」，旧后端仅冻结参考，V3 期不动 |
| 2 | `datara-backend/rebuild/__init__.py[AZ5T]`（L977，F："Defines the I1 rebuild responsibility and contract…"，S："Keep isolated until freeze"） | V2 | rb 域对象、I1 时代模板语义，10-16~10-19 重建期定型；V3 期预计不再演变（该条同时是「222+ 待消化」低质模板语的典型） |
| 3 | `datara-backend/rebuild/api/app.py`（其 R: 引用遍布 L11/L13/L24 等多节；权威设计 §0.3 引其 L306） | V3 | **R2 活跃修正覆盖路径先验的示例**：路径属 rebuild 域（V2 先验），但 V3 期 API 一源迁移与集成将持续修改该装配文件 → 活跃对象 |
| 4 | `datara-web/src/views/rebuild/validation/sync-form/` 节（L1249；同族 validation 节见 L1222–1252） | V2 | rb 线验证页，重建期成型；用户裁定（权威设计 §0.2 裁定 1）「不要管旧前端」→ 冻结 |
| 5 | `datara-web/package-lock.json[FL4L]`（L245，中文语义高质量条目：npm/pnpm 双锁并存约束） | V1 | **R7 示例**：对象本体为旧前端依赖锁，纠偏前已存在；语义虽系后期补写，卷籍仍按对象形成期判 V1 |
| 6 | `.mcp.json[CC4T]`（L12，F：注册 AOCI MCP 服务命令） | V3 | 根治理配置，活跃管理对象（R3 表第四行） |
| 7 | `docker-compose.yml[CM7M]`（L11，R: 引用 `datara-backend/rebuild/api/app.py`） | V1（边界情形） | **跨期对象**：本体是纠偏前的旧 compose，R 却指向 V2/V3 对象 → 按本体判 V1，R 跨卷引用允许（R5），历史卷不回写 |

### 3.3 边界情形处理约定

1. **跨期对象**（本体旧、引用新，或反之）：按 R3→R2→R1 判本体卷籍；跨卷关系不迁移、不回写。
2. **纠偏后重建又沿用的对象**（如 `rebuild/api/app.py` 始于 I1 期但 rb 期大改、V3 期仍改）：以「V3 期是否仍实质演变」一票定 V3（R2），不按首次创建期判 V1——保证活跃面完整收敛在唯一活跃卷。
3. **10-20 当天的 rb 线收口对象**（S151–S156 验收对象）：本体多在 10-16~10-19 形成但 10-20 达到最终稳定态；凡属 V3 期集成活跃面（app.py、rebuild api 层）→ V3；凡属测试文件 → 已排除不入卷；其余静止对象按 R1 归 V2。
4. **归卷与语义分离**：本节规则只决定「条目放进哪一卷」；条目的 Tag/F/R/A/S 语义一律在正式入册时按当时证据由模型独立撰写（对齐 AGENTS.md AOCI 节「Entry semantics must come from the model's understanding of actual evidence」）。

---

## 四、物理形态方案

### 4.1 现役机制基线（事实，非设想）

仓库根 `aoci.txt`（7 行）**已是多卷根清单**：`#Format-Version: cognition-volumes/v1`，声明两个 Volume（meta → aoci.meta.txt；code → aoci.code.txt，`depends=meta`）。`.aoci/verify_history/20261016T182326Z.txt` 明确记录 **"AOCI Verify: Volumes v1 candidate structure is valid"**——工具已实际校验过多卷候选结构。`.aoci/governance/entries-*.json` 回执的 `paths` 字段绑定单卷文件（如 `["aoci.code.txt"]`），即**写事务天然按卷文件绑定**。

### 4.2 候选对比

| 维度 | A：单 aoci.txt 内分卷章节化 + 卷 Header | B：多文件分卷（aoci.v1/v2/v3.txt）+ 根清单 Volume 声明 | C：B + 历史卷目录卡轻量化（仅路径+Tag+F 摘要，删 R/A/S 全文） |
|---|---|---|---|
| 工具兼容性 | **差**：与现役 cognition-volumes/v1 机制冲突（根清单按 path 指向独立卷文件）；cognition plan/migration 面向卷布局，单文件章节化无对应机器结构 | **好**：与 meta/code 双卷现役模式同构；verify 已验证 Volumes v1 候选结构；cognition plan→migration 提供受治理迁移路径 | 较好（继承 B）；但卷内容裁剪是否被 plan/migration 接受**未证实** |
| 传输体量 | 不减（单文件 413KB 全量仍在） | **实质缩小**：V1+V2（约千条、占 413KB 绝大多数）冻结后不参与活跃传输；V3 初期约 80–120 条 ≈ 8–12k token，单窗可完成 | 进一步缩小历史卷文件体积，但历史卷本就不参与活跃传输，收益仅存档层面 |
| 活锁缓解 | 无效（93k token 问题原样保留） | **有效**：传输对象从全索引变为 V3 单卷；222+ 待消化按 §6.3 出清至 V3 域子集 | 同 B |
| 维护成本 | 高（手工章节化 + 无工具护航） | 中（一次受治理迁移 + 之后 V3 正常闭环） | 高于 B（目录卡裁剪需逐条处理且涉语义删改） |
| 回滚难度 | 高（无 exact recovery 对应） | 低（cognition migration 自带 exact recovery + git 快照双保险） | 中（裁剪动作不可逆性比 B 强） |

### 4.3 推荐

**推荐 B**。核心理由：

1. **同构现役机制**：根清单多卷声明、卷文件事务绑定（governance 回执 paths 字段）、verify 的 Volumes v1 候选校验，三处机器事实都站在 B 一侧；A 是逆着工具走。
2. **直接命中活锁要害**：全量传输从「1021 条 / 413KB / 93k token」缩到「V3 单卷初期约 8–12k token」，单窗（含 Attestation）结构性可完成——这是 #349–#351 三窗停链的唯一根治路径。
3. **222+ 待消化自动出清**（详见 §6.3）：历史域条目随卷冻结免修，待消化集合缩至 V3 域子集。
4. C 作为**可选后续增强**保留：若未来需要压缩存档体积，可在 B 稳定运行后以「整卷替换 + verify 校验」方式实施，不与本次立卷捆绑。

---

## 五、工具能力盘点结果（CLI help 实测，2026-10-20，共 3 次调用）

binary：`D:\aoci\aoci.exe`（来源 `.mcp.json`）。调用：顶层 `--help`、`cognition --help`、`index --help`。

### 5.1 实测支持的能力

| 命令 | 能力 | 对本方案的意义 |
|---|---|---|
| `aoci cognition plan` | "Plan Bootstrap or Legacy migration **without applying changes**" | **卷册布局迁移可先 dry-run 出计划**（A2 步骤），报批后再应用 |
| `aoci cognition migration` | "Migrate an approved Legacy cognition layout **with exact recovery**" | 存量布局 → 三卷布局的受治理迁移通道，自带精确恢复 |
| `aoci cognition bootstrap` | "Apply an approved new-repository **Volume Bootstrap** with recovery" | 新卷（V3）立卷的官方应用通道 |
| `aoci index header/build/entries` | Header 草拟 / 分批起草 Entry（仅草稿区）/ check+diff+原子 Apply | V3 立卷 authoring 的正式工作流 |
| `aoci index inventory/score` | 离线盘点未索引文件；九维质量评分 | V3 候选对象发现与立卷验收 |
| `aoci scope` | 管理 index/observe/exclude 政策 | managed_scope 排除规则的维护入口 |
| `aoci verify / check / status --deep` | 只读校验（可写本地审计数据）；alignment 状态 | 迁移前后留痕与漂移信号 |
| `aoci update-entry / remove-entry` | 与 MCP 同管线的单条写/删 | 兜底修正 |
| `aoci capabilities` | 单一版本化机器能力清单 | **下一步实测入口**（见 5.2） |

### 5.2 help 未证实、需 `capabilities` / `cognition plan` 实测的项

1. **Volume state 枚举**：现役根清单只见 `state=enabled`；是否支持 catalog-only / archived / readonly 等语义未知 → 决定 D4（免修是机器强制还是纪律约束）。
2. **传输按卷 scope**：help 未展示 per-volume 传输参数；MCP `aoci_overview` 是否可指定仅传 V3 卷需实测。
3. **卷文件的自动拆分/合并命令**：help 中无显式 split/merge 子命令；拆分动作大概率由 `cognition migration` 的迁移计划承载。

### 5.3 结论

- **可由工具完成**：布局迁移规划（plan）、迁移应用（migration/bootstrap）、V3 立卷 authoring（index 工作流）、校验留痕（verify/score/status）。
- **只能文件手工操作 + 下次 Overview 重建兜底**：根清单 Volume 行的增补（若 migration 计划未覆盖）；catalog-only 的「免修」纪律执行本身（无显式机器开关时）——以 git 冻结提交 + verify composite_identity 审计替代机器强制。
- 现行 config 关键实值（盘点顺带确认）：`overview_delivery.chunk_tokens=8000`（注意 #111 曾裁定 24000，现值回落，需在 A2 时一并核对）；`cognition_budget.whole_index` target 150k / warning 220k / max 300k token；`automation.mode=auto`；`ledger_enabled=true`。

---

## 六、前端重构集成卷（第 3 卷）立卷初始化清单

### 6.1 新卷 Header 骨架草案（人类可读骨架；机器字段以 `aoci cognition plan` 输出与 `index header` 工作流为准，不手工臆造机器契约）

```
# 卷身份
卷名：前端重构集成卷（fe-integration）
卷文件：aoci.v3.txt（待 D5 裁定）
范围：datara-newweb/**；datara-backend/rebuild 集成活跃面（app.py 装配、API 一源迁移端点、models.py）；
     docs/handoff/**；docs/agents/**；根治理配置（AGENTS.md、.mcp.json、GLOSSARY.md、aoci*.txt 本体）
立卷依据：docs/increments/2026-10-19-纠偏重构前端权威设计.md（v3，2026-10-20，冻结功能清单/
     目录契约/菜单继承/API 一源/集成联通/验收六维设计结论）
对标真源：docs/increments/2026-10-14-datara-platform-rebuild.md（I0~I11，managed_scope 排除不入卷，
     仅以 R: 路径引用）
格式：object-fras-v2；字典依赖：aoci.meta.txt（depends=meta）
维护策略：全维护闭环（V1/V2 为 catalog-only 冻结免修）
```

### 6.2 初始 Entry 候选范围（**对象清单骨架**；每条的 Tag/F/R/A/S 语义待正式入册时按当时证据独立撰写，本方案不预填）

| 组 | 候选对象 | 来源依据 |
|---|---|---|
| 新前端工程 | `datara-newweb/**`（目录创建后由 `index inventory` 发现；首批预计 = 工程骨架 + 菜单框架 + 首批页面） | 权威设计 §2（独立新目录）、§4（菜单框架继承） |
| 后端集成活跃面 | `datara-backend/rebuild/api/app.py`（装配，§0.3 引 L306）；§6 五步迁移规则产出的迁移端点域；`datara-backend/rebuild/models.py`（workflow 六模型，§0.3 引 L32-144） | 权威设计 §6（API 一源）、§0.3 Codex 发现 |
| 契约与文档 | `docs/handoff/STATE.md`；`docs/agents/issue-tracker.md`、`triage-labels.md`、`domain.md`；`AGENTS.md` | AGENTS.md「Agent skills」节；STATE.md 现行权威地位 |
| 治理配置 | `.mcp.json`；`docker-compose.rebuild.yml`；GLOSSARY.md（若存在）；`aoci.txt/aoci.meta.txt/aoci.code.txt` 本体的索引条目 | 现役卷内已有对应条目（如 .mcp.json L12） |

### 6.3 与现有未消化 222+ 条待办的关系处置建议

1. **分流**：按 §3.1 R3 路径域先验表对 222+ 待消化条目逐条贴卷籍标签。
2. **出清**：贴为 V1/V2 的条目（预计占绝大多数——rebuild 域与 datara-web 域条目合计约千条量级）**随历史卷 catalog-only 冻结自动免修**，从 maintain 队列移除；semantic_change 436 中涉及历史域的部分同此出清。
3. **保留**：仅 V3 域子集（app.py 装配层、rebuild api 迁移面、docs/handoff、docs/agents、根配置）继续待消化，立卷后按 #304 分窗 ≤50/批正常消化。
4. **效果**：待消化集合从 222+ 缩至 V3 域子集 + governance_aligned 的对齐目标随之改按 V3 单卷计算——这是分卷对传输活锁与维护积压的**双重根本缓解**。
5. **注意**：出清 ≠ 删除。历史卷条目原样随卷冻结保留（catalog 是冻结的，不是清空的）；V3 对象需要历史背景时经 R: 跨卷引用。

---

## 七、执行步骤清单

### 7.0 前置（顺序依赖的起点）

- **步骤 0（纯文件/监督线代办）**：处置工作区脏态——STATE.md §三披露 `.aoci/*`、`aoci.code.txt` 等未提交修改。先代提交或明确快照，确保迁移以干净 git 基线起步。

### 7.1 第一类：需用户批准的决策点（D1–D5）

| 编号 | 决策点 | 前置 |
|---|---|---|
| D1 | 物理形态选型（推荐 B，见 §4.3） | 本方案 |
| D2 | 三卷边界精确值确认（V2 上界 = 2026-10-20 00:00，Asia/Shanghai；备选：V2 上界 = 立卷动作时刻） | 本方案 §二 |
| D3 | 历史卷是否做最后一次全量快照导出（防 .aoci 运行时状态损坏后无法重建目录卡） | 本方案 §九-3 |
| D4 | catalog-only 的强制机制：纯纪律 + git 冻结 + verify 审计（当前证据下的现实选项），或等待 capabilities 实测出机器开关 | §5.2 实测结果 |
| D5 | 卷文件命名与卷 id（建议 aoci.v1/v2/v3.txt + pre-rectify / rectify-backend / fe-integration） | 本方案 §二 |

### 7.2 第二类：守护会话后续执行的 aoci 操作（A1–A7，严格顺序）

1. **A1** `aoci_rules` 取会话运行时契约（守护会话开窗例行）。
2. **A2** `aoci cognition plan`：生成存量布局 → 三卷布局的迁移计划（dry-run，不改正式索引）；顺带实测 §5.2 三项未证实能力、核对 chunk_tokens 现值。
3. **A3** plan 结果 + 本方案报用户终批（D1–D5 一并裁定）。
4. **A4** `aoci cognition migration`（或 bootstrap，按 plan 指定通道）：应用已批准迁移。
5. **A5** `aoci verify`（Volumes v1 候选结构校验）+ `index score` + `status --deep`：迁移后验收留痕。
6. **A6** V3 立卷 authoring：`index header` → `index inventory` 发现候选 → `index build` 起草 → `index entries` 分窗原子 Apply（≤50/批，#304 纪律）。
7. **A7** 全量传输走 V3 单卷（预期 8–12k token 单窗完成，含 Attestation；partial 禁重试，#315）。

### 7.3 第三类：纯文件操作（F1–F4）

1. **F1** `.aoci/` 全量快照备份（含 413KB baseline.json、governance/ 回执、transactions/ 暂存），迁移前执行。
2. **F2** 若 plan 输出要求人工补齐卷文件片段：严格按 plan 落盘，禁止偏离；完成后立即 verify。
3. **F3** 根清单 `aoci.txt` Volume 行变更（仅当 migration 未覆盖；增三行 Volume 声明，meta 行不动）。
4. **F4** git 提交由监督线代办：卷资产（aoci*.txt、.aoci/*）与业务文件分开提交。

### 7.4 顺序依赖总览

```
步骤0 清场 → D1–D5 报批 → A1 → A2 → A3（终批） → F1 快照 → A4 迁移 → A5 校验
→ F2/F3（按需） → A6 V3 立卷 → A7 V3 单卷全量传输 → F4 提交
```

---

## 八、风险与回滚

| # | 风险 | 缓解 | 回滚 |
|---|---|---|---|
| 1 | **工具对三卷 archive 语义支持不全**（state 枚举、per-卷传输未证实）→ 手工态与工具态漂移 | A2 dry-run 先行实测（§5.2 三项）；漂移以 verify 失败为信号 | cognition migration 的 exact recovery + 迁移前 git 快照（F1/步骤 0）双保险，整卷回退 |
| 2 | **工作区脏态卷入迁移**（.aoci/*、aoci.code.txt 现存未提交修改，STATE.md §三） | 步骤 0 强制清场后才允许 A4 | 自步骤 0 快照/提交恢复 |
| 3 | **catalog-only 卷被误改**（无机器开关时实施线/后续会话误编辑历史卷） | 历史卷单独冻结提交；此后每次监督窗 verify 比对 composite_identity；实施线本就禁触 AOCI 资产（#85） | 自冻结提交恢复该卷文件（git checkout 单文件），并追查误改来源心跳 |
| 4 | **V3 单卷体量仍超限**（新前端大规模铺开后单卷膨胀，重蹈 93k token 覆辙） | 传输按目录域 scope 分批（#197 (c) 排除框架）；设预警线（如 V3 全卷 >30k token 触发评估）；V3 内再分卷机制可复制 | 回退至分卷前卷文件快照，按新边界重切 |
| 5 | **跨卷 R: 语义断链误导**（历史卷冻结后，被引对象演变不再回写，后续会话读到过期关系） | V3 高频跨卷关系在其 S 字段显式声明「历史卷为快照语义，以当前源码为准」；GLOSSARY/STATE 记载卷册语义约定 | 个案报监督线，在 V3 对应条目补 S 约束（属正常维护闭环，无需回滚卷结构） |

---

## 九、待用户裁定清单

> **裁定结果（2026-10-20 用户已裁）**：D1–D5 **按推荐整体批准**（B 形态多文件三卷 / V2 上界 = 2026-10-20 00:00 / 冻结前全量快照存 `.aoci/archive` / catalog-only = 纪律+git 冻结+verify 审计 / 卷文件 aoci.v1/v2/v3.txt + 卷 id pre-rectify / rectify-backend / fe-integration）。附带确认三项**全部同意**（① phase_transition 例行报备；② 222+ 待消化中 V3 域子集随 A6 立卷一并消化；③ chunk_tokens 现值 8000 vs #111 裁定 24000 在 A2 dry-run 时核对纠正）。

1. **D1 物理形态**：是否采纳推荐项 B（多文件三卷 + 根清单 Volume 声明）；C（历史卷目录卡轻量化）是否列为后续可选项。
2. **D2 卷边界确认**：V1 < 2026-10-16 00:00；V2 = 2026-10-16 00:00 ~ 2026-10-20 00:00；V3 = 2026-10-20 00:00 起（Asia/Shanghai）。备选：V2 上界改为立卷动作时刻。
3. **D3 历史卷最后快照**：V1/V2 冻结前是否做一次全量快照导出（建议做，存放位置待定：仓库外 or .aoci/archive）。
4. **D4 catalog-only 强制机制**：接受「纪律 + git 冻结 + verify 审计」的现实方案，还是要求先实测/等待工具提供机器开关。
5. **D5 卷命名**：卷文件名（aoci.v1/v2/v3.txt）与卷 id（pre-rectify / rectify-backend / fe-integration）确认或改名。
6. **附带确认**：① V3 立卷是否同步声明一次 `phase_transition`（AOCI 规则第 4 条，属守护会话例行，仅报备）；② 222+ 待消化中 V3 域子集的清理优先级（建议随 A6 立卷一并消化）；③ chunk_tokens 现值 8000 与 #111 裁定 24000 的回落是否需要在 A2 时纠正。

---

## 附：本方案证据清单（起草时实际读取）

- `AGENTS.md`：AOCI 托管节（aoci:begin/end）+ 豁免 #85 节 + Active handoff 节。
- `docs/handoff/STATE.md`：§一现状快照（AOCI governance_aligned=false、semantic_change 436/30、222+ 待消化、#349–#351 活锁 93k token）；§二-1 传输策略×分卷联动；§三脏项。
- `docs/increments/archive/2026-10-20/多终端多智能体项目管理标准规范-裁定索引.md`：§三 #85/#111/#188/#197/#235/#273/#304/#311/#315/#330 行；§四 AOCI 裁定链补充。
- `docs/increments/archive/2026-10-20/多终端多智能体项目管理标准规范.md`：§4.4 AOCI 职责边界（分窗 ≤50/批、Attestation partial 禁重试、rc16 机读为准）。
- `docs/increments/2026-10-19-纠偏重构前端权威设计.md`（v3）：meta updated=2026-10-20；§0.2 用户四条裁定；§0.3 Codex 三发现；§2 datara-newweb；§6 API 一源。
- `aoci.txt`（根清单 7 行，cognition-volumes/v1）；`aoci.meta.txt`（20 行字典卷）；`aoci.code.txt`（413KB，128 节，抽读 L1–L100、L240–245、L976–980、节标全扫、卷尾 L1222–1285）。
- `.aoci/config.json`（managed_scope 11 规则、cognition_budget、chunk_tokens=8000、refresh_threshold=30）；`.aoci/baseline.json`（413KB 指纹库头部）；`.aoci/governance/entries-*.json` 回执样例（paths 绑定 aoci.code.txt）；`.aoci/verify_history/20261016T182326Z.txt`（Volumes v1 candidate 校验记录）。
- `.mcp.json`（binary=D:\aoci\aoci.exe）；CLI help 三次实测（顶层 / cognition / index）。
