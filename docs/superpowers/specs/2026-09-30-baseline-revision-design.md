# 基线化组件「修订轮次」+ 三项缺陷修复 设计（spec）

- 日期：2026-09-30
- 状态：已实施（2026-09-30 两批部署 1.9 实测收口，见 DAG 计划 §11 末两条）
- 关联：docs/DAG与组件综合优化实施计划-20260926.md §11、docs/组件基线化/README.md

## 1. 背景与根因

已认可发 v1 的基线化组件（M-B1/M-B2 共 18 个）无修订路径，用户实测暴露 4 个问题：

| # | 现象 | 根因（代码位） | 层 |
|---|---|---|---|
| R1 | 工作台保存底稿报「请求失败（code=undefined）」 | 前端 saveDraft 发驼峰 `draftRev`，后端 BaselineDraftBody 要求下划线 `draft_rev` → pydantic 422（响应体 {detail} 无 code 字段）→ http.ts 兜底文案拼 `code=${json.code}`=undefined | 前端 bug |
| R2 | M1 设计器对内置组件报「无进行中的草稿」 | 18 个 builtin 只有 published 版本行、无 draft 行 → GET /components/{type}/draft 409；设计器组件来源未过滤 builtin | 前端体验 |
| R3 | published 底稿可被静默改写 | save_baseline_draft 只有乐观锁无 status 检查（rev 匹配时 200 且 status 仍 published，改动永远发不出版本） | 后端治理 |
| R4 | 发版后无修订能力 | publish_baseline 硬编码 v1 + status=published 409「基线化一次性」；无「复制上版开新草稿」端点 | 产品缺失 |

证据：1.9 nginx 日志（PUT /baseline/{endpoint_select,sql}/draft → 422；GET /components/{assert,endpoint_select}/draft → 409）+ 代码四层闭环。

## 2. 决策记录

- **D1 版本策略**：修订草稿不自动发布；修订期间 registry 持续供给已发版本（vN），用户手动「认可发 v(N+1)」。历史版本永久留档（t_component_version 多行）。
- **D2 交付方式**：分两批——第一批修 R1/R2/R3（缺陷），第二批实施 R4（修订轮次功能）。
- **D3 状态机**：不新增状态枚举；「修订中」= `status=designing && publishedVersion>0`。
- **D4 治理不变量**：体检照旧全项落库不拦截；认可发版需 publish_component 权限；修订开轮/保存需 design_component 权限。

## 3. 第一批：缺陷修复（不含新功能）

1. **R1**：baselineApi.ts saveDraft 请求体 `draftRev` → `draft_rev`；http.ts code 缺失时兜底文案改「响应格式异常（HTTP xxx）」。
2. **R2**：ComponentDesignView 组件来源过滤 `scope=user`；builtin 不再进入 M1 链；用户组件区空态引导「内置组件请到基线化工作台」。
3. **R3**：save_baseline_draft 增加检查：`row.status == "published"` → 409（msg：已发版底稿不可直接修改，修订能力即将上线）。

验证：vitest/vue-tsc 本地全绿 → 1.9 部署 → 工作台保存 designing 底稿 200、published 保存 409、M1 设计器无 builtin。

## 4. 第二批：修订轮次

### 4.1 新增端点 `POST /components/baseline/{type_name}/redraft`

- 前提：进度行存在且 `status=published`（否则 409：无行 404、designing 409「已有修订草稿进行中」）
- 事务动作：
  1. 取该 type t_component_version 最新 `state=published` 行的 `spec_json` → 写入进度行 `draft_spec`（复制上版）
  2. `draft_rev += 1`
  3. `status = "designing"`（confirmed_by/confirmed_at 保留历史值不清除）
  4. t_component_log 记 `action="redraft"`（version=当前 published_version，operator，remark 可选）
- 返回：`{draftRev, status:"designing", fromVersion, specHash}`

### 4.2 publish 端点改造

- 原 409「已认可发过 v1」仅适用于 `status=published`（未开修订轮直接重复认可）
- 新增路径：`status=designing` 且该 type 已有 t_component 行 → 修订发布：
  - `version = t_component.published_version + 1`
  - 新增 ComponentVersion（version=N+1, state=published, spec_json=当前底稿全文, spec_hash）
  - 更新 t_component.published_version = N+1
  - ComponentLog 记 `action="publish"`（version=N+1）
  - 进度行 status=published、confirmed_by/at 刷新
- 无组件行的首发型走原 v1 路径（行为不变）；`draft_rev` 不重置（连续递增）

### 4.3 放弃修订

- 新增 `POST /components/baseline/{type_name}/discard_draft`（design_component 权限）
- 前提：`status=designing && publishedVersion>0`（修订中）——首发型 designing 无「放弃」语义（无已发版本可回）
- 动作：`draft_spec` 重置为最新 published 版 spec（与上版一致）、`draft_rev += 1`、`status=published`；log 记 `action="discard"`
- 返回：`{status:"published", draftRev}`

### 4.4 状态机

```
pending ──保存──▶ designing ──认可──▶ published(v1) ──redraft──▶ designing(修订中) ──认可──▶ published(v2)
                                        ▲                                            │
                                        └────────────── discard ◀────────────────────┘
```

不变量：published 期间底稿不可写（R3 拦截）；修订中 registry 供给 vN 不变；版本只增不减。

### 4.5 progress 响应扩展

每行增加 `publishedVersion`（从 t_component 左联；无行/未发为 0，与 draftRev 无行=0 先例一致）。前端「修订中」判断：`status==='designing' && publishedVersion>0`。

## 5. 前端交互

- **工作台**：
  - published 态：编辑器只读（现有 disabled 逻辑）+「复制 v1 开修订」按钮（ElMessageBox 确认 → redraft → 重拉底稿 → 可编辑）
  - 修订中：编辑器可编辑；认可按钮文案「认可发 vN」（N=publishedVersion+1），确认框注明「当前 v(N-1) 将留档，registry 供给切换至 vN」
  - 修订中显示「放弃修订」按钮（二次确认 → discard_draft → 重拉）
- **目录页**：按钮分型 published→「查看」/其余→「修改」（现有逻辑，修订中自然落入「修改」）
- **M1 设计器**：builtin 过滤（第一批已做）；空态引导文案第二批更新为「内置组件请到基线化工作台修订（支持复制上版）」

## 6. 测试

- 后端 pytest：redraft 前提与事务与 log、publish v2 递增与版本行、save published 409、discard 状态回退、首发型路径回归
- 前端 vitest：saveDraft 字段名（mock 断言请求体）、工作台三态按钮（published/修订中/designing）、发布文案 vN、目录页分型
- 1.9 实测：sql 组件全链「查看 → 复制 v1 开修订 → 改字段 → 保存 → 体检 → 认可发 v2 → registry 供给 v2 + v1 版本行留档」；其余 17 组件不受影响
- 文档回写：README 台账追加修订记录说明、实施计划 §11

## 7. 风险与非目标

- 非目标：多人协作隔离、修订轮分支/合并、版本 diff 可视化增强（现有 diff 块沿用）
- 风险：publish 改造需兼容首发型（回归用例覆盖）；discard 后 draft_rev 连续递增（乐观锁不受影响）
