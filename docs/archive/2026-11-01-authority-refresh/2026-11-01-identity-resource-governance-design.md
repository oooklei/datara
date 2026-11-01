---
design_type: initiative
created_at: 2026-11-01
updated_at: 2026-11-01
status: draft-for-review
scope: 平台用户管理 / 项目成员管理 / 资源隔离（数据源连接）/ 用户与成员间资源分享授权
---

# 身份、成员与资源授权治理（调研 + 优化方案）

## 1. 问题（Problem）

Datara 现有身份与授权体系是在「单团队、单租户、少量用户」假设下长出来的最小实现：平台角色是 4 个硬编码枚举，项目成员表复用同一套平台权限矩阵，资源隔离只做到「项目」一层，分享是「按用户名的布尔可见性」。随着用户数与项目数增长，这套模型出现三类系统性问题：

1. **界面语义与后端行为不一致**：前端提示「owner/ADMIN 可管理」，后端成员接口只放行 admin，项目 owner 操作必然 403；成员列表只返回数字 user_id，无法辨识是谁。
2. **资源边界不闭合**：数据源连接存在两条并行链路（`rebuild_project_datasource` 与 dbx 连接），归属模型不同；admin 对 dbx 连接可跨项目穿透。
3. **授权不可治理**：分享只有「可见/不可见」两态，无权限等级、无有效期、无审计、无级联回收；四套 ownership/share 实现各写各的表。

**已确认的设计前提**（2026-11-01 用户裁定，作为本方案约束）：

- **平台级权限优先于项目级权限**。项目角色只能做项目内降权/裁剪，不能提权；需要写权必须提升平台级角色。
- **角色与成员配置统一由 admin 行使**；**资源分享是资源 owner 的固有权利**——owner 可把自有资源分享给任何人（不限于 admin），但分享只授予访问资格，被授予者的有效权限 = min(分享上限, 平台角色 ∩ 项目角色上限)，默认 view。分享不做审批流，提供功能页面即可（模型见 §7.4）。

## 2. 愿景（Vision）

在**不放宽平台级权限优先规则**的前提下，建立**单一授权判定入口 + 统一资源 ACL + 可审计的共享生命周期**：把平台角色（能进入哪些功能域）与项目角色（在本项目内被裁剪到什么程度）的语义明确分层，把「资源归属 + 显式共享」收敛为一张通用 ACL 表，并让每一次授权决策可追溯。

## 3. 非目标（Non-goals）

- **本期不引入多租户/组织层**（影响分析见 §14，本期仅登记备忘）。
- **本期不加密数据源连接密码**（用户裁定，见 `docs/research/2026-11-01-datasource-credential-encryption-memo.md`）。
- 本期不做授权申请/审批流（用户裁定：提供配置页面即可）。
- 本期不引入外部 IdP / SSO / LDAP（预留接口，不实现）。
- 本期不做行级/列级数据权限（数据脱敏走 `rebuild/sec` 线，另立设计）。
- 本期不重构 dbx 自身的单用户数据库模型（dbx 仍是配置真身，Datara 继续在旁路维护归属元数据）。
- 不引入通用策略引擎（OPA/Cedar）作为运行时依赖；先在应用内实现策略层，保留可替换接口。

## 4. 干系人（Stakeholders）

| 角色 | 关注点 |
|---|---|
| 平台管理员（admin） | 用户生命周期、最后管理员保护、全部授权配置、越权排查 |
| 项目 owner | 项目内资源可见性；可分享自有资源（分享只授访问资格） |
| 数据开发/运维 | 能否看到并使用被授权的数据源，且不越界 |
| 安全/合规 | 授权审计、离职回收 |
| 平台研发 | 授权逻辑是否单点、可测试、可扩展 |

---

## 5. 现状调研（Evidence-based）

### 5.1 平台用户管理

**数据模型**（`rebuild/identity/models.py`）：`rebuild_user` 仅有 `id / username(unique) / password_hash / role(单值) / status(enabled|disabled) / created_at / updated_at`。无显示名、邮箱、部门、`last_login_at`、`password_changed_at`。

**角色与权限**（`rebuild/identity/contracts.py`）：`Role` 四值 `admin / developer / operator / viewer`；`Permission` 33 个权限点；`ROLE_PERMISSIONS` 为**代码内硬编码常量**，运行时不可配置、不可扩展、不可新增自定义角色。`authorize(role, permission)` 未知角色/权限一律拒绝（fail-closed，正确）。

**密码**（`rebuild/identity/passwords.py`）：PBKDF2-HMAC-SHA256，240,000 轮，16 字节随机盐。算法选型合理。缺失：无弱口令/复杂度校验（创建用户仅校验非空）、无首次登录强制改密、无密码过期、无登录失败锁定与限流、无 MFA。

**会话**（`TokenService` + `rebuild_active_token`）：无状态 HMAC-SHA256 token，payload 含 `jti/user_id/username/role/iat/exp`，可选 `capability`；撤销靠数据库 `token_digest` 主键表。TTL 固定 86400 秒，无滑动续期、无并发会话上限、无 refresh token。停用/改密/改角色时在同一事务内 `revoke_user`（正确实践）。

**最后管理员保护**：`update_user_status` 与 `update_user_role` 均调用 `count_enabled_admins_excluding`，停用或降级唯一 admin 时返回 409（正确）。

**审计**（`rebuild/sec/middleware.py`）：`SecAuditMiddleware` 按请求记录 `user_name / action(由 method 推导) / target(URL path) / result(由状态码推导)`。粒度只到路径级——**不含业务对象 ID、不含变更前后值**，因此「谁把 zhangsan 从 developer 降成 viewer」在审计里只有一条 `PATCH /api/v1/rebuild/users/9/role`。

**API Key**（`rebuild/apikey/models.py`）：`key_hash + key_prefix`（只存摘要，正确）、`scopes_json(permissions/projectIds)`、`expires_at / last_used_at / revoked_at`。缺陷：`created_by` 存的是**用户名字符串而非 user_id 外键**，用户名变更或删除后归属断链。

### 5.2 项目成员管理

**数据模型**：`rebuild_project.owner_id` + `rebuild_project_member(project_id, user_id, role)`。**成员表没有 `(project_id, user_id)` 唯一约束**，仅靠应用层先查重，并发下可产生重复成员行。

**成员角色复用平台 Role 枚举**（developer/operator/viewer），即项目角色没有独立语义，直接借用平台权限点全集。

**判定函数 `project_permission_error`**（`rebuild/api/app.py`）的实际顺序：

1. admin → 直通；
2. 全局角色不具该权限 → 403；
3. 是项目 owner → 直通；
4. 是成员且成员角色具该权限 → 通过，否则 403。

这是 **AND 关系**：平台角色权限是硬门槛。**按用户 2026-11-01 裁定，此语义为期望行为，本方案不改判定顺序**。项目角色的正确定位因此是「项目内降权/裁剪」：管理员可以把某平台 developer 在指定项目裁剪为 viewer，但不能反向提权。

**成员接口授权**：`add_member / list_members / remove_member / update_member` 全部要求 `Permission.MANAGE_USER`，而 `MANAGE_USER` **只有 admin 拥有**。按用户裁定「权限配置统一由 admin 行使」，**此行为保留**；需要修的是前端提示与页面渲染与之一致。

**成员列表信息不足**：接口只返回 `user_id + role`，无用户名、状态、加入时间，前端只能渲染数字 ID（截图中成员列为 1 / 7 / 8）。

**其他缺口**：无「项目角色目录」接口（只有平台 `/users/roles`）；删除用户时不清成员关系与分享记录；项目删除时清成员但不清 dbx 归属。

### 5.3 资源隔离（数据源连接）

存在**两条并行链路**：

| 维度 | `rebuild_project_datasource` | dbx 连接 |
|---|---|---|
| 归属 | 仅 `project_id`，**无 owner** | `dbx_connection_ownership(connection_id PK, project_id, owner_id)` |
| 配置真身 | Datara 库 | dbx 单用户库 |
| 访问控制 | `project_permission_error(DATASOURCE_READ / EDIT_DEFINITION)` | owner/share + `visible_ids` |
| 粒度 | 项目内全员共享 | 按用户可见 |
| 凭据 | `password` 明文 `String(512)` | dbx 侧持有 |

**凭据存储**：本期按用户裁定**不做修改**，另立项目备忘（见 §3 与 `docs/research/2026-11-01-datasource-credential-encryption-memo.md`）。仅记录事实：同仓库 LLM 供应商 key 已使用 AES-256-GCM 信封加密（`rebuild/llm/crypto.py`），数据源密码未加密，两处标准不一致。

**隔离边界**：只到「项目」一层，没有组织/租户概念；admin 全局穿透。`require_connection` 对 admin 走 fallback——直接比对 dbx 全量连接列表，因此 **admin 可以访问任意项目的 dbx 连接**，项目边界对 admin 不成立。按裁定 admin 统一行使权限配置，此穿透**保留但需补审计**。

**对象级分享 kind 取值**：`ai-config / ai-conversation / prompt-template / tunnel-profile / saved-sql / sql-folder`。

### 5.4 分享授权

**连接级分享**：`POST /connections/{id}/share`，入参 `username` 或 `user_id`，写 `dbx_connection_share(connection_id, user_id)`，唯一约束齐全。只有 owner 或 admin 可分享；`unshare` 只有 owner 可撤销。

**现状能力边界**：
- 只有「可见」一种效果（等价 `DATASOURCE_READ`），**无 view/use/manage 等级**；
- **无有效期**、**无审计**、**无分享理由/备注**；
- **不能分享给项目或角色**，只能逐个用户；
- 删用户不级联清理 `dbx_connection_share` / `dbx_object_share`；
- 无「我分享给谁/谁分享给我」聚合视图。

**实现碎片化**：同一套「claim + share + visible_ids」模式被重复实现四份，表结构互不相同：`rebuild/dbx/access.py`（连接与对象）、`rebuild/orchestration/governance.py`（编排资源）、`rebuild/sshnode/governance.py`（SSH 节点）、`rebuild/resources/api.py`（IDE 脚本可见性）。

**与裁定的关系**：分享主体是**资源 owner 与 admin**（不是 admin 专属）；owner 可分享给任何人。分享只授予访问资格——被授予者的有效权限 = min(分享上限, 平台角色 ∩ 项目角色上限)，默认 view，因此分享不构成提权路径。模型见 §7.4。

---

## 6. 差距分析（对标最佳实践）

| 能力 | 业界基线 | Datara 现状 | 差距 |
|---|---|---|---|
| 角色模型 | RBAC 角色目录可配置 | 4 角色硬编码 | 中 |
| 项目角色 | 项目内降权/裁剪维度，语义明确 | 借用平台角色，语义模糊、无目录 | 中 |
| 资源授权 | Owner + ACL(等级) | Owner + 布尔 share | 高 |
| 权限判定 | 单一策略入口，可测、可审计决策 | 判定散落在每个路由函数 | 高 |
| 会话安全 | 短 access + refresh、会话列表 | 24h 静态 token，撤销可用 | 中 |
| 审计 | who/what/对象/前后值 | 路径级 + 状态码 | 高 |
| 共享生命周期 | 有效期、批量、回收 | 无 | 高 |
| 凭据保护 | 密文存储 | 数据源密码明文 | 严重（已立备忘延后） |

---

## 7. 目标架构

### 7.1 授权判定单点

所有受保护请求经过 `PolicyService.decide(subject, action, resource) -> Decision`：

```
Decision = allow | deny(reason)
输入：subject(user_id, 平台角色, 项目成员角色) / action(权限点) / resource(project_id, kind, resource_id, owner_id)
规则优先级：显式拒绝 > 显式授权(ACL) > 平台角色 > 项目角色裁剪 > owner 直通 > 默认拒绝
```

**判定顺序保持平台角色优先**（不放宽）：平台角色是上限，项目角色只能在其之下裁剪。判定结果携带 `reason`，供审计与前端解释，解决当前「403 只返回 permission denied」无法定位的问题。路由层只负责解析资源，不再各自写 if 判断。

### 7.2 角色模型分层（语义不变，表达明确）

- **平台角色**（`platform_role`，4 值不变）：决定「能进入哪些功能域」，是权限上限。
- **项目角色**（`project_role`）：`inherit / viewer / operator`，语义为「在本项目内把平台角色裁剪到什么程度」。默认 `inherit`（完全继承平台角色）；显式配置后按项目角色生效。
- 角色-权限映射从代码常量迁移到 `rebuild_role / rebuild_permission / rebuild_role_permission` 三张表，启动时把现有代码常量作为 seed，保证行为兼容。

> 该分层不改变现有权限结果：`inherit` 时等价于今天的行为；显式降权时收紧。**不产生任何提权路径**，符合「需要写权必须改平台级角色」的裁定。

### 7.3 统一资源 ACL

一张通用表替代四套实现：

```
rebuild_resource_acl
  resource_kind   (datasource | dbx_connection | dbx_object | orchestration_resource | ssh_node | ide_script | workflow | model)
  resource_id
  project_id
  owner_id
  grantee_type    (user | project | role)
  grantee_id
  permission      (view | use | manage)
  expires_at
  granted_by
  created_at
唯一约束: (resource_kind, resource_id, grantee_type, grantee_id)
```

`owner_id` 仍保留在 ACL 表首行（`grantee_type=user, grantee_id=owner_id, permission=manage`），消除「归属表 + 分享表」双表。

### 7.4 资源分享授权

#### 7.4.1 核心模型：分享授「资格」，不授「权限」

分享解决「够得着」（可见性/可访问），角色解决「做得了」（能力上限）。两者取交集，任何一方都不单独构成授权：

**有效权限 = min(分享上限, 被授予者的平台角色 ∩ 项目角色上限)**

| 分享上限 | 被授予者角色上限 | 有效权限 | 说明 |
|---|---|---|---|
| view | view | **view** | 默认情形 |
| view | manage | **view** | 分享是上限，不因角色高而放宽 |
| manage | view | **view** | 角色是上限，分享不能提权 |
| manage | manage | **manage** | 双方都允许 |
| use | manage | **use** | 中间档 |

角色上限的判定沿用 §7.1 已确认规则：**平台角色优先于项目角色**，项目角色只能降权，不提供提权路径。因此分享在语义上是「访问资格的授予」，永远不会成为提权通道。

#### 7.4.2 分享主体

| 主体 | 能否分享 | 能否撤销 |
|---|---|---|
| 资源 owner | 能，可分享给任何人 | 能，可撤销自己发起的分享 |
| admin | 能，可分享任意资源 | 能，可撤销任何分享 |
| 其他成员 | **不能** | 不能 |

owner 分享出去的名义级别可以高于被授予者的角色上限，但生效级别按 7.4.1 收敛；被分享者若后续提升平台角色，则自动获得更高生效权限（无需重新分享）。

#### 7.4.3 被授权方粒度与继承

| grantee_type | 语义 | 继承规则 |
|---|---|---|
| user | 单个用户 | 无继承 |
| project | 整个项目 | 项目成员按**项目角色**继承资格，不产生提权 |
| role | 同平台角色全员 | 角色成员变动自动跟随，无状态需维护 |

`project` 粒度采用**查询时实时计算**而非物化：项目成员变动时无需重算授权，避免状态漂移。

#### 7.4.4 有效期与回收

- 可选 `expires_at`；到期即不可见（实时判定为准），定时任务负责落审计与回收记录。
- 用户停用/删除 → 级联回收其作为 **grantee** 的全部 ACL；保留其作为 **grantor** 的记录（审计需要）。
- owner 转让资源时，该资源的 ACL 首行随 `owner_id` 一并转移，历史分享记录保留。

#### 7.4.5 API

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/rebuild/shares` | 授权（body: resource_kind/resource_id/grantee_type/grantee_id/permission/expires_at） |
| DELETE | `/api/v1/rebuild/shares/{acl_id}` | 撤销（owner 撤自己的 / admin 撤任意） |
| GET | `/api/v1/rebuild/shares/matrix` | 授权矩阵（按资源或按用户），owner 与 admin 可见 |
| GET | `/api/v1/rebuild/shares/mine` | 我被授予的资源清单（所有登录用户） |
| GET | `/api/v1/rebuild/shares/granted` | 我分享出去的清单（owner / admin） |
| POST | `/api/v1/rebuild/connections/{id}/share` | **保留兼容**，内部转调 ACL（旧前端零改动） |
| DELETE | `/api/v1/rebuild/connections/{id}/unshare` | **保留兼容**，同上 |

#### 7.4.6 前端

- 资源详情新增「授权」Tab：授权矩阵表格、分享对话框（选人/选项目/选角色 + 级别 + 有效期）、撤销按钮。
- `SystemAdminView.vue` 增加 admin 全局「共享管理」入口（P3）。
- 非 owner 且非 admin 的界面**不渲染**分享操作入口（同时接口侧 403，双保险）。

#### 7.4.7 分享域验证用例

| 用例 | 预期 |
|---|---|
| owner 分享给任意用户 | 成功，无需 admin 介入 |
| 平台 viewer 被分享 manage 后调用写接口 | 403（角色上限收敛为 view） |
| 平台 developer + 项目 inherit，被分享 view 后调用写接口 | 403（分享上限收敛为 view） |
| 非 owner 且非 admin 调用 grant | 403 |
| `expires_at` 到期后访问 | 403，且 acl_audit 落回收记录 |
| 用户停用后访问被分享资源 | 403，grantee 记录已回收、grantor 记录保留 |
| 旧路径 `POST /connections/{id}/share` | 行为不变 |

### 7.5 审计

在路径级中间件之上补业务级审计：`identity_audit`（用户增删改、角色变更、密码重置、登录成功/失败）与 `acl_audit`（grant/revoke/过期回收/admin 穿透访问），字段含 `actor / target_user / object / action / before / after / result / ip / ua`。append-only，不允许 UPDATE/DELETE。

---

## 8. 分阶段路线

| 阶段 | 目标 | 关键交付 | 风险 |
|---|---|---|---|
| **P0 一致性与止血** | 界面语义对齐后端；清理悬空授权 | ① 成员管理页与「仅 admin 可管理」对齐（移除 owner 可管理的错误提示与无效操作入口）；② `rebuild_project_member` 加 `(project_id,user_id)` 唯一约束；③ 删除/停用用户时级联清理 project_member 与 ACL grantee 记录（保留 grantor 审计）；④ 身份操作写业务审计；⑤ API Key `created_by` 改为 user_id 外键 | 低（纯代码，无数据迁移） |
| **P1 权限模型收敛** | 角色目录化，项目角色语义明确 | 角色三表 + seed（保持 4 平台角色不变）；项目角色枚举 `inherit/viewer/operator` 与项目角色目录接口；成员列表返回用户名/状态/加入时间；判定改由 PolicyService 承载但**保持平台优先顺序不变** | 中 |
| **P2 授权收敛** | 统一 ACL + 配置面 | `rebuild_resource_acl` 建表与回填；四套 ownership/share 迁移；`PolicyService` 接管全部路由判定；分享支持 view/use/manage 三级 + expires_at + 项目/角色粒度（owner 与 admin 可操作）；角色/成员配置页面仅 admin 可见可操作 | 高 |
| **P3 治理体验** | 可运营 | 共享管理视图（owner 本人 + admin 全局：授权矩阵/被授权清单/过期清单）、审计查询页、403 按 `decision.reason` 渲染可解释提示 | 低 |
| **P4 多租户** | 组织隔离 | 见 §14；本期不启动，仅登记 | 高 |

依赖关系：P0 与 P1 可并行；P2 依赖 P1 的角色目录；P3 依赖 P2 的 ACL 表。

---

## 9. Intent Contract

```
intent: 在保持「平台级权限优先于项目级权限」与「角色/成员配置统一由 admin 行使、资源分享由资源 owner 行使」两条前提下，把授权判定收敛为单点、资源授权收敛为统一 ACL，使授权可解释、可审计、可回收。
constraints:
  - 不得放宽平台级权限优先规则；项目角色只能降权/裁剪，不提供提权路径
  - 角色与成员配置仅 admin 可操作，其余角色无此权限
  - 资源分享由资源 owner（及 admin）行使，owner 可分享给任何人；分享只授予访问资格，不构成提权路径
  - 不得破坏现有 API 路径与响应码约定（前端与 E2E 依赖 code 1001/1003/4001/4091 等）
  - admin 全局穿透语义保留，但对 admin 的穿透访问必须落审计
  - dbx 仍是连接配置真身，Datara 侧只维护归属与授权元数据
  - 判定失败一律 fail-closed
  - 本期不加密数据源密码、不引入租户层
success_criteria:
  - 成员管理页的可见性与可操作性同后端 admin-only 语义一致，owner 不再出现 403 错误态
  - 全局 viewer 被授予项目角色后，在项目内仍为只读；任何项目角色配置都不产生写权
  - 任意一次授权/回收/穿透访问都能在审计中还原 actor、对象、前后值
  - 四套 ownership/share 实现收敛为一张 ACL 表 + 一个 PolicyService
  - owner 能独立完成资源分享，无需 admin 介入；被授予者默认只读
  - 非 owner 且非 admin 的主体调用分享接口返回 403，前端不渲染分享操作入口
  - 角色与成员配置仅 admin 可操作，其余角色访问返回 403
risk_level: high
```

## 10. Verification Contract

```
verify_steps:
  - run tests: 后端 rebuild 测试集（pytest datara-backend/tests/rebuild）+ 前端 vitest（systemAdminView / projectMembersView / orchestrationResourceView 契约测试）
  - check: 权限回归用例覆盖 admin / owner / 成员(各档) / 非成员 / 停用用户 五类主体 × 四类资源；重点断言「项目角色配置不产生写权」
  - check: 分享矩阵用例覆盖 分享上限 × 角色上限 全组合；断言「平台 viewer 被分享 manage 后写接口仍 403」「平台 developer 被分享 view 后写接口仍 403」
  - check: 非 admin 主体访问角色/成员配置接口返回 403；非 owner 且非 admin 调用分享接口返回 403；前端对应入口不渲染
  - check: 删除/停用用户后，project_member 与 ACL grantee 记录已清理，grantor 记录保留
  - confirm: 192.168.1.9 隔离环境 E2E 通过 http://192.168.1.9:8090/ 验证成员管理、owner 分享 → 被授予者默认可读 → 越级写入被拒 → 撤销后不可见
```

## 11. Governance Contract

```
approval_gates:
  - P1 项目角色枚举（inherit/viewer/operator）与权限映射迁移方案需产品与安全双确认
  - P2 ACL 表结构与四套 ownership/share 回填映射需评审
  - P2 admin 专属配置面（角色/成员）的入口清单需产品确认（哪些配置项归 admin）
  - P2 分享 API 新增路径与旧路径兼容策略需评审
rollback:
  - 每阶段独立可回滚：P0 无数据迁移；P1 保留代码常量 seed 作为回退源；P2 新旧判定并行（feature flag）一个迭代后切换
ownership: 平台后端负责人（判定与 ACL）+ 安全负责人（审计）+ 前端负责人（成员与共享界面）+ 产品负责人（admin 配置项清单）
```

---

## 12. 决策记录（已裁定）

| # | 决策点 | 裁定（2026-11-01） |
|---|---|---|
| D1 | 项目角色是否独立于平台角色 | 语义上分层：项目角色只做项目内降权（inherit/viewer/operator），**平台角色优先不变，不提供提权路径** |
| D2 | ACL 是否统一单表 | 统一 `rebuild_resource_acl` |
| D3 | 分享是否支持「项目」粒度 | 支持（grantee_type=project） |
| D4 | 是否引入租户层 | **本期不引入**，影响分析见 §14，仅登记备忘 |
| D5 | 授权申请审批流 | **不做**。角色与成员配置统一由 admin 行使，提供功能页面；**资源分享由资源 owner（及 admin）行使**，分享只授予访问资格（见 §7.4） |
| D6 | 数据源密码加密 | **本期不做**，见 `docs/research/2026-11-01-datasource-credential-encryption-memo.md` |

## 13. 风险与开放问题

1. **行为兼容**：本方案刻意**不放宽**任何现有权限，风险集中在 P2 的 ACL 回填正确性。回填映射错误会导致既有授权丢失，需按域逐套校验。
2. **四套 ACL 迁移**：`orchestration` 按 `resource_key` 字符串、`sshnode` 按自增 id、dbx 按 connection_id，回填需逐域写映射规则并做数量对账。
3. **admin 穿透边界**：admin 跨项目访问 dbx 连接配置的穿透保留，必须落审计；否则治理缺口被隐藏。
4. **前端 403 呈现**：当前「403 呈现为错误态」应改为按 `decision.reason` 渲染可解释提示，否则用户仍无法定位原因。
5. **项目角色目录**：新增 `inherit/viewer/operator` 后，存量成员行（developer/operator/viewer）需要映射规则：建议 developer→inherit、operator→inherit、viewer→viewer，保证行为不变。

## 14. 附：租户层引入的影响分析（D4 应答）

> 用户询问「引入会有什么影响和变化」。以下为事实测算，结论支持本期不引入。

**测算基数**：`rebuild` 域现有约 **125 张表**（governance 43、execution 8、model 10、monitor 10、orchestration 10、dbx 5、stream 6、metrics 6、workflow 7，其余 1~3 张/模块），其中约 40+ 张为业务数据表。

**若引入租户层，实际变化面**：

| 影响面 | 具体变化 | 量级 |
|---|---|---|
| 表结构 | 每张业务表加 `tenant_id`，并纳入复合唯一约束与索引（仅 `rebuild_project_datasource` 就涉及 username/type 等唯一键重定义） | 约 40+ 表 |
| 查询层 | 所有仓储方法需带 tenant 过滤；漏一处即构成跨租户越权 | 全部仓储 |
| 上下文注入 | 需类似现有 subject contextvars 的 `tenant_id` 注入机制，并覆盖异步任务、调度、工作流回调等非请求上下文 | 全链路 |
| 数据迁移 | 存量数据需回填 `tenant_id`，且要先定义「默认租户」语义 | 一次性 |
| dbx 同步 | dbx 单用户库天然带 user 维度；ownership/share 表需加 tenant，双向同步链路（push/poll）需重写 | 高 |
| admin 语义 | admin 归属哪个租户？跨租户全局视角如何表达？与现有「admin 全局穿透」如何共存 | 需重新定义 |
| 运维形态 | 共享 schema + tenant_id（索引与查询复杂）vs 每租户独立 schema（迁移与连接管理复杂） | 架构级选择 |
| 全局统计/审计 | 跨租户聚合报表、审计归属划分 | 额外工作 |

**结论**：以当前约 125 张表的体量，租户层是一次架构级改造（表结构 + 查询层 + 上下文注入 + 迁移 + dbx 同步 + admin 语义重定义），远超本期「授权治理收敛」的目标范围，且 Datara 当前为单组织部署、无多组织需求驱动。**本期不引入**；当出现多组织部署、或数据源凭据加密备忘被重新提起时，两项一并排期（见备忘触发条件）。
