# G-28 governance 28 路由漂移对齐（Claude 证据件）

- 日期：2026-10-21
- 票号：G-28
- 执行线：Claude（s275 线别权威表 + s276【四】本窗独有裁定：governance-28 与 api.py 在飞同线避冲突）
- 立票依据：s270 四裁②（S260 心跳归档原文：R3 禁裸称采纳入规则 + governance 28 路由漂移单开对齐票；用户 AskUserQuestion 全批，裁定信 s270-ruling-batch-20261021 落箱）
- 派令：s294「G-28 governance 28 路由漂移对齐成号开工」
- 技术口径权威出处：docs/increments/evidence/PRE/2026-10-21-R3契约双义与治理域对照预研-Codex.md（下称 R3 预研，§2 路由账实对照）
- 实测基线：git HEAD ea1ee3c（=origin/main，ahead=0）
- 目标文件实态：datara-backend/rebuild/governance/api.py 工作区 SHA256 = 0fe40586f7dccd01b86eb442f137feee5326ac27a8f2315f867241b0291a9b95

## 一、漂移定义（禁裸称 R3，本票属 R3-GOV 域）

R3 双义规则（R3 预研 §1，四裁②采纳入规则）：R3-GOV = Datara 自研 metadata/lineage 治理域；R3-SYNC = SYNC 新域契约收口门禁。禁裸称 R3。本票属 R3-GOV 域路由账实对齐。

漂移点：权威设计 §6.3 L853 governance 行端点数快照记 23（表头快照基线 2026-10-20，HEAD bd3250d），与 api.py 实测 28 条不符，差额 +5。

## 二、实测方法与双证对平

1. 装饰器实测：对 api.py（router prefix = `/api/v1/rebuild/governance`，api.py L184）Grep `@router\.` 命中 28 行（迁移面 12 + 产品面 16）。
2. 矩阵对照：R3 预研附表 docs/increments/evidence/PRE/2026-10-21-R3治理域契约对照.csv（SHA256 = 1e4bbda33fc7571627617a04f788faec17aead12767cd31aed5a12a62c5f9c49）28 数据行，与装饰器实测逐条一致（28/28）。
3. 设计快照原文：权威设计 §6.3 L853 修订前原文 `| 2 | governance | /api/v1/.../governance | 23 | 已实现 |`。

## 三、三层差额构成钉死（本票核心结论）

| 层 | 装饰器数 | 构成 | 证据 |
|---|---|---|---|
| bd3250d（快照声明基线） | 24 | 迁移 9 + 产品 15 | `git show bd3250d:datara-backend/rebuild/governance/api.py` Grep `@router\.` 实测 24 行 |
| ea1ee3c（当前 HEAD，已提交） | 27 | = 24 + cd43668 新增 3（standards/check、i21/import、i22/import） | `git show HEAD` 装饰器计数 27；`git log -S` 三条均命中 cd43668 |
| 工作区（当前实态） | 28 | = 27 + 未提交 1（POST /projects/{project_id}/quality-rules/{rule_id}/run，diff +67/-0 行） | `git status --porcelain` = M；`git diff --stat HEAD` = +67/-0 |

结论分解：

1. 快照 23 系手填误差：bd3250d git 对象实测 24 条，快照编制时少记 1。
2. bd3250d 之后已提交新增 3 条：standards/check（STANDARD_READ，migration-validation）、legacy/i21/import、legacy/i22/import，引入 commit = cd43668（feat(rebuild-backend): AI 八工具接线(ai_tools+ai_bridge)+执行/流/治理/指标/变量域扩展+alembic 迁移+legacy_bridge 适配+fv 与域测试扩充（T47r/T48r/T55r/C21r/s129 交付代提交））。
3. 工作区在飞未提交 1 条：POST /projects/{project_id}/quality-rules/{rule_id}/run（处理函数 run_quality_rule，api.py L1768-1769），git status=M、diff +67/-0；`git log -S 'run_quality_rule'` 零命中与该端点未提交互为印证。
4. i23/identity-preview 非 bd3250d 后新增：bd3250d 已含（L490，路径 /legacy/i23/identity-preview，无 project_id 段），引入 commit = a6b1de6（feat(rebuild): add I23 identity preview control loop）。

## 四、28 条路由全表（迁移 12 + 产品 16）

来源：R3 预研附表 CSV（SHA 见上），与 api.py 装饰器实测逐条一致。

| 分类 | 方法 | 路径 | 处理函数 | 权限现状 | 判定 |
|---|---|---|---|---|---|
| 迁移 | POST | /projects/{project_id}/legacy/i18/dry-run | legacy_i18_dry_run | EDIT_DEFINITION | migration-only |
| 迁移 | POST | /projects/{project_id}/legacy/i18/import | legacy_i18_import | EDIT_DEFINITION | migration-only |
| 迁移 | POST | /projects/{project_id}/legacy/i19/mapping-preview | legacy_i19_mapping_preview | EDIT_DEFINITION | migration-only |
| 迁移 | POST | /projects/{project_id}/legacy/i19/import | legacy_i19_import | EDIT_DEFINITION | migration-only |
| 迁移 | POST | /projects/{project_id}/legacy/i20/mapping-preview | legacy_i20_mapping_preview | EDIT_DEFINITION | migration-only |
| 迁移 | POST | /projects/{project_id}/legacy/i20/import | legacy_i20_import | EDIT_DEFINITION | migration-only |
| 迁移 | POST | /projects/{project_id}/legacy/i21/mapping-preview | legacy_i21_mapping_preview | EDIT_DEFINITION | migration-only |
| 迁移 | POST | /projects/{project_id}/legacy/i21/import | legacy_i21_import | EDIT_DEFINITION | migration-only |
| 迁移 | POST | /projects/{project_id}/legacy/i22/mapping-preview | legacy_i22_mapping_preview | EDIT_DEFINITION | migration-only |
| 迁移 | POST | /projects/{project_id}/legacy/i22/import | legacy_i22_import | EDIT_DEFINITION | migration-only |
| 迁移 | POST | /legacy/i23/identity-preview | legacy_i23_identity_preview | EDIT_DEFINITION | migration-only |
| 迁移 | POST | /projects/{project_id}/standards/check | standards_check | STANDARD_READ | migration-validation |
| 产品 | POST | /projects/{project_id}/assets | create_asset | EDIT_DEFINITION | 已实现 |
| 产品 | GET | /projects/{project_id}/assets | list_assets | VIEW_ALL | 已实现 |
| 产品 | GET | /assets/{asset_id} | get_asset | VIEW_ALL | 已实现 |
| 产品 | POST | /projects/{project_id}/tags | create_tag | EDIT_DEFINITION | 缺列表更新删除 |
| 产品 | PUT | /assets/{asset_id}/tags | assign_asset_tags | EDIT_DEFINITION | 已实现 |
| 产品 | POST | /projects/{project_id}/lineage | create_lineage | EDIT_DEFINITION | 缺删除 |
| 产品 | GET | /assets/{asset_id}/lineage | get_lineage | VIEW_ALL | 已实现 |
| 产品 | POST | /projects/{project_id}/quality-rules | create_quality_rule | EDIT_DEFINITION | 权限待细化 |
| 产品 | GET | /projects/{project_id}/quality-rules | list_quality_rules | VIEW_ALL | 权限待细化 |
| 产品 | GET | /projects/{project_id}/quality-runs | list_quality_runs | VIEW_ALL | 权限待细化 |
| 产品 | POST | /projects/{project_id}/quality-rules/{rule_id}/run | run_quality_rule | EDIT_DEFINITION | 权限待细化 |
| 产品 | POST | /projects/{project_id}/standards | create_standard | EDIT_DEFINITION | 权限待细化 |
| 产品 | GET | /projects/{project_id}/standards | list_standards | VIEW_ALL | 权限待细化 |
| 产品 | POST | /projects/{project_id}/metrics | create_metric | EDIT_DEFINITION | 缺更新删除 |
| 产品 | GET | /projects/{project_id}/metrics | list_metrics | VIEW_ALL | 已实现 |
| 产品 | GET | /projects/{project_id}/audit | list_audit | VIEW_ALL | 已实现 |

## 五、对齐动作

1. 权威设计 §6.3 L853 governance 行修订：端点数 23 → 28；状态列加注「已实现（G-28 对齐 2026-10-21，ea1ee3c 已提交 27+在飞 1）」。修订前文件 SHA256 = 300a73c3c04d0ac5ad28ff465ce785263bb1541e40dcb2cedff3aa2427e5d006；修订后 = 2845591975a66f12859bb1dda40b19c02c193cf32ec8b10c443614778efbd968。
2. 行内独立锚定沿用该表既有风格（同 L858 workflow 行注记带 SHA 先例）；表头与 L867 底注 bd3250d 总基线不动，其余 13 行不动，最小修订。
3. 手填总数机制化替代（R3 预研 §3.4 建议采纳入账）：以自动生成路由清单替代手填总数 + 设计状态列标注基线 SHA——本票已按行内注记带基线 SHA 落地；自动清单生成属后续正式票范围。

## 六、范围界定（不在本票内，候后续正式票）

1. R3 预研 §3.2 四项待正式票裁定：权限粒度未用足（Permission 已定义 QUALITY_READ/WRITE/RUN + STANDARD_READ/WRITE/APPROVE，实现仍 EDIT_DEFINITION/VIEW_ALL；standards/check 是少数用 STANDARD_READ 的端点）、产品 CRUD 面不完整（资产无更新/删除、标签无列表/更新/删除、血缘无删除等）、迁移工具面与产品面混装同一路由模块（建议 OpenAPI 分 tag + 前端契约注册标 migration-only）、端点数快照漂移机制。
2. R3 预研 §5 拆票序列：R3-GOV-01 契约冻结 → 02 迁移面隔离 → 03 前端契约层 → 04 页面消费 + 命名治理。
3. 前端消费边界（R3 预研 §4）：CONTRACT_REGISTRY.md 无 governance 契约模块、routes.ts 仅注册 /login 与 /（13 治理路径未注册）、metricsApi 指向 /rebuild/metrics 不视为 governance 适配层、/sec/audit 标 future/inc15-post——均不在本票动。

## 七、在飞边界声明

POST quality-rules/{rule_id}/run 端点 67 行为工作区在飞未提交代码（实测 git status=M + diff +67/-0）。本票只做账实对平（快照行修订），不动 api.py 一行；对齐快照按实态 28 记账（与立票口径 governance 28、R3 预研实测口径 28 三者一致），在飞 1 条已行内注记声明，待其在飞线 commit 后账面自动闭合。

## 八、验收锚点（复验命令）

1. 工作区装饰器计数（28）：Grep `@router\.` datara-backend/rebuild/governance/api.py。
2. 已提交计数（27）：`git show HEAD:datara-backend/rebuild/governance/api.py | Select-String '@router\.' | Measure-Object`。
3. 快照基线计数（24）：`git show bd3250d:datara-backend/rebuild/governance/api.py | Select-String '@router\.' | Measure-Object`。
4. 新增 3 条溯源：`git log --oneline -S 'standards/check' -- datara-backend/rebuild/governance/api.py`（命中 cd43668；i21/i22 import 同理）。
5. 在飞实态：`git status --porcelain -- datara-backend/rebuild/governance/api.py`（M）；`git diff --stat HEAD -- datara-backend/rebuild/governance/api.py`（+67/-0）。
6. 文件 SHA256：api.py 工作区 0fe40586…；CSV 1e4bbda3…；权威设计修订后 28455919…。

## 九、报验

cl-done 信 s299 落箱（mailbox.jsonl），验收方按第八节锚点复验；G-28 待验收。
