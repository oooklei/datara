---
doc_type: project-memo
created_at: 2026-11-01
status: deferred
priority: high
owner: 待定
target_version: 后期版本统一处理
---

# 项目备忘：数据源连接凭据加密（本期不修改）

## 1. 备忘来源

2026-11-01 身份与授权治理方案评审，用户裁定：**本期不做修改，仅登记备忘，后期版本统一处理**。

## 2. 现状事实

`datara-backend/rebuild/datasource/models.py` 的 `ProjectDatasourceRecord` 中，`password` 为 `String(512)` 列，**明文存储，无任何加密或脱敏**。

同仓库已存在正确的加密实现可复用：

- `datara-backend/rebuild/llm/crypto.py` — AES-256-GCM 信封加密，输出格式 `v1.nonce.ciphertext`
- `rebuild/llm/models.py` — `api_key_cipher` 字段 + `set_api_key / get_api_key` 加解密接口
- 密钥来源：`LLM_ENCRYPTION_KEY` 环境变量（32 字节）

两处标准不一致：LLM 供应商 key 已加密，数据源密码未加密。

## 3. 风险

1. 数据库文件/备份/只读副本泄露即等于全部数据源凭据泄露。
2. 具备数据库读权限的运维、DBA、备份流程均可获得明文口令。
3. 数据源口令通常可复用（与业务库口令相同），一处泄露放大为横向风险。
4. 与「凭据最小暴露」的合规基线不符（等保/ISO27001 均要求凭据加密存储）。

## 4. 建议方案（后期实施时参考）

- 新增 `password_cipher` 列，复用 `rebuild/llm/crypto.py` 的 AES-256-GCM 格式；**使用独立密钥环境变量**（如 `DATASOURCE_CREDENTIAL_KEY`），不复用 `LLM_ENCRYPTION_KEY`，避免共用密钥放大泄露面。
- 迁移期**双读兼容**：读取优先 `password_cipher`，为空则回落 `password`；写回时加密写入 `password_cipher` 并清空 `password` 明文列。
- 迁移脚本执行前先统计存量明文量（`SELECT count(*) FROM rebuild_project_datasource WHERE password <> ''`），据此决定是否需要停机窗口。
- 迁移完成后：配置下发链路（datasource_payload / dbx_sync / ide_proxy / 连接池）确认无明文残留；日志与错误输出中不得打印口令。
- 历史备份中的明文口令需按保留策略单独处置（无法通过列清理消除）。

## 5. 触发条件

出现以下任一情况时，本备忘应重新提起排期：

- 多组织/多租户部署需求落地（见 `docs/archive/2026-11-01-authority-refresh/2026-11-01-identity-resource-governance-design.md` §14 租户层影响分析，已归档；现时身份与权限见 `docs/designs/2026-11-01-datara-current-authority.md` §九）
- 安全评审或合规审计提出凭据存储整改要求
- 数据源连接数量或敏感级别显著上升
