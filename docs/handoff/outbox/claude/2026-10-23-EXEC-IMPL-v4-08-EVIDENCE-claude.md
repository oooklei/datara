# IMPL-v4-08 · EVIDENCE（本地段）· EXEC-3

- **席**：Execution EXEC-3（claude）｜**票**：IMPL-v4-08（API 管理 15-P0 契约冻结；v3-0072 自 trae 重派本席，Ops R3 批准，票面四字段/paths/验收/证据要求零变更）
- **时间**：2026-10-23T03:1x+08:00｜**水位**：v3-0074（承接 v3-0072 重派）
- **本机结果口径**：本机仅静态校验，全部输出 **DIAGNOSTIC_ONLY_NOT_PASS_EVIDENCE**；契约测试执行移交 1.9 面（租约请求先于任何 1.9 执行）

## 1. 路径实存清单（3/3，均在票面 `paths` 内）

| 路径 | 状态 |
|---|---|
| `datara-newweb/src/services/rebuild/openapiAdminApi.ts` | 新建（RED 契约骨架，零 I/O，≈230 行） |
| `datara-newweb/src/services/rebuild/__tests__/openapiAdminApi.contract.test.ts` | 新建（9 用例） |
| `docs/increments/evidence/API/2026-10-22-15-P0-契约冻结.md` | 新建（冻结文档 v1.0） |

**无越界路径声明**：本席本票落盘仅上述 3 件 + 本 outbox 证据件；未触 CONTRACT_REGISTRY.md（RED 行文本随本件交付，见 §5）、未触 identity/后端任何件（零新增权限枚举）、未建表未写业务实现。

## 2. 静态检查（三项 EXIT=0）

| 项 | 命令 | 结果 |
|---|---|---|
| 全量类型 | `npx vue-tsc -b` | **EXIT 0** |
| node 侧类型 | `npx tsc --noEmit -p tsconfig.node.json` | **EXIT 0** |
| NO_SECRET | 3 件交付物凭据模式 grep（过滤契约字段名 key_prefix/key_hash/plainKey 与文档术语后） | **0 真实命中** |

## 3. 验收逐项对照（票面 ①~⑦）

| 验收 | 交付 | 状态 |
|---|---|---|
| ① 三表冻结 | 冻结文档 §二（DDL 级字段表：rebuild_api_definition / rebuild_api_key / rebuild_api_call_log，含约束/唯一键/索引/时间戳） | 本地段 ✓ |
| ② 端点清单+状态机 | §三（管理面 12 + 网关 1，URL 前缀 `/api/v1/open` 定稿）+ §四（定义 draft→published→disabled 循环；Key active→revoked 终态+rotate 原子对） | 本地段 ✓ |
| ③ 权限矩阵+错误码 | §六（security:manage / security:read，复用 identity 既有词形零新增）+ §五（11 错误码含 identity 共用 1001/1003） | 本地段 ✓ |
| ④ 安全红线 | §七（原始 key 仅签发/轮换一次回显、hash-only、日志零敏感落盘、管理面 fail-closed）+ FE 类型面冻结（ApiKeyRecord 无 key 字段、plainKey 仅 KeyIssuance、日志记录面无 body/SQL） | 本地段 ✓ |
| ⑤ Acceptance 独立评审（A2） | 候验收席（本件 + 冻结文档为评审输入） | 候 |
| ⑥ 契约测试 1.9 GREEN | 9 用例本地段就绪；RT 租约请求已先行落件 | 候租约 |
| ⑦ 不建表不写实现 | RED 骨架零 I/O：12 方法统一抛 `OPENAPI_ADMIN_NOT_WIRED`（模式同 #8 scheduleApi 先例） | ✓ |

## 4. FE 载体冻结面（契约测试 9 用例覆盖）

方法清单 12（定义 CRUD4+状态机3+Key4+日志1）｜权限矩阵（list*=security:read，其余 security:manage）｜错误码 11 逐项断言｜URL 前缀 `/api/v1/open`｜全方法 RED 拒绝（13 调用点含 query 形参）｜哨兵词形回归守卫｜安全红线类型面（三红线逐字段断言）｜状态机词形与受控方法白名单。

## 5. CONTRACT_REGISTRY RED 行文本（随证据交付，不改 CONTRACT_REGISTRY.md）

> 登记于 §1 映射表（#19，接 #18 rolePermissions 行后）：

```
| 19 | `openapiAdminApi.ts` | `services/rebuild/__tests__/openapiAdminApi.contract.test.ts` | RED | 12 | 9 | 15-P0 API 管理契约冻结（IMPL-v4-08）：三表/13 端点/状态机/错误码 11/权限矩阵（security:manage·read 复用 identity 词形零新增）/URL 前缀 /api/v1/open 全冻结；hash-only+一次性 plainKey+日志零敏感落盘类型面红线落码；RED 骨架零 I/O（12 方法统一抛 OPENAPI_ADMIN_NOT_WIRED），候 15.2-A~D 接线转 GREEN |
```

> 状态快照行（供 Flow 更新）：**GREEN 17 / RED 2（#8 scheduleApi、#19 openapiAdminApi）；冻结方法合计 145（133+12）。**

## 6. 设计输入与授权边界核对

- 三表字段/约束：立项文档 §三表 + 预研 §4.3 逐字段承接；C1（页内页签）/C2（受控 facade only+4091 唯一）/C3（permission+project allowlist scopes_json）/C4（fail-closed/90 天/脱敏清单）四批复全量落冻结面。
- 命名红线：产品「API 管理」≠ FastAPI openapi.json；包名 `api_management`、URL 前缀 `/api/v1/open` 均按立项建议定稿。
- 契约细节均属 C1~C4 批准内 D2；未发现越出项（越出即停票上报，本票零越出）。

## 7. 1.9 段（未执行，候租约）

- 租约请求：`2026-10-23-EXEC-IMPL-v4-08-lease-request.md`（RT-IMPL-V4-08-OPENAPI-CONTRACT，**先于任何 1.9 执行**）。
- 1.9 面：`npx vitest run src/services/rebuild/__tests__/openapiAdminApi.contract.test.ts`（纯契约层，无后端依赖，可并入 RT 串行窗）。

## 8. 资源自报

- 本轮轮次数：1（哨兵→深读 0072 重派→承接 08→三件交付→静态校验→证据面）｜空转比自估：0（产出轮）｜子智能体实际运行数：0
- 本会话累计：2 张同域任务包（16 本地段 + 08 本地段）；下一张包前按轮换纪律评估。

—— Execution EXEC-3（claude），本地段 EVIDENCE_READY 呈递，候 Acceptance A2 独立评审 + Integration 租约回执。
