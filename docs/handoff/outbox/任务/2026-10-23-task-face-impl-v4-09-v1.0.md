# IMPL-v4-09 票面 **v1.0**（API 15.2-A 三表建模）

- **发起**：Task / epoch 3 / 2026-10-23T02:48+08:00（实测）/ 水位 `v3-0074`
- **依据**：IMPL-v4-08 冻结文档 `docs/increments/evidence/API/2026-10-22-15-P0-契约冻结.md`（本地段 EVIDENCE_READY，候 A2 评审 + RT-08）；立项 §三表 + C1~C4
- **状态**：**BLOCKED**（不占 READY 队首）；08 PASS 后转 READY，票面已预塑以缩短断环时延

## 四字段

| 字段 | 值 |
|---|---|
| base_priority | P2 |
| effective_priority | P2 |
| priority_basis | 15.2-A 建模首票（门 7）；08 冻结是三表唯一授权源 |
| priority_override | null |

## 依赖

- **前置**：`IMPL-v4-08` **PASS**（Acceptance A2 独立评审 + RT-08 GREEN + 集成窗可用；仅 EVIDENCE_READY 不足）。
- **下游**：`10`（15.2-B/C 端点与 Key 服务）→ `11`（15.2-D 网关与日志）→ `12`（15.3 页面）。

## paths（预计，全部新增）

- `datara-backend/rebuild/api_management/__init__.py`
- `datara-backend/rebuild/api_management/models.py`（三表：`rebuild_api_definition` / `rebuild_api_key` / `rebuild_api_call_log`，字段/约束/唯一键/索引严格照冻结文档 §二）
- `datara-backend/rebuild/api_management/migrations.py`
- `datara-backend/rebuild/api_management/revisions/__init__.py`
- `datara-backend/rebuild/api_management/revisions/v0001_api_management.py`
- `datara-backend/tests/rebuild/test_api_management_migrations.py`（新）
- **禁触**：`identity/**`（权限词形复用，零新增）、`governance/**`、`app.py`（挂载窗另议）、任何端点/网关实现（属 10/11）。

## 验收标准

1. 三表 DDL 与冻结文档 §二逐字段/逐约束一致；时间戳 mixin、外键与索引齐备；
2. migrations 按既有 revisions 模式注册，**幂等**（重复执行零 DDL 变更）；
3. 零端点、零 Key 服务、零网关代码（15.2-A 边界）；不建 `app.py` 挂载（create_all 之外不擅改真源，挂载方案随 18/后续票）；
4. 1.9 全量 `pytest` GREEN（新建表后既有套件不回归）；迁移测试覆盖三表建表/约束/回滚口径；
5. 本机仅静态/迁移脚本自检，标 `DIAGNOSTIC_ONLY_NOT_PASS_EVIDENCE`。

## 证据要求

远端证据绑定租约、制品 commit、命令、时间戳、退出码、日志、执行者；新增表名/约束/索引清单入证据面；RED/GREEN 分存。

## 授权路径

Task 票面 → 08 PASS 后 Flow 转 READY 并派单（建议 codex 上线后，否则 claude 空档线；路径全新增、无共享锁）→ EVIDENCE_READY → ENV_VERIFIED → PASS → 集成窗。

---
Task / epoch 3 / 2026-10-23T02:48+08:00 / 水位 v3-0074 / 预塑，不派单
