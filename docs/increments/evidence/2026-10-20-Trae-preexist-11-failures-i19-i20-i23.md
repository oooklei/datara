# Trae 线证据：S143 上报 11 个预存失败核查修复（ref: preexist-11-failures-i19-i20-i23）

- 日期：2026-10-20（Asia/Shanghai）
- 执行线：Trae（实施线）
- 派单：mailbox.jsonl s149-930530（from=监督员，ts=2026-10-20T04:02:58）
- 验收目标：全量 `pytest tests/rebuild -q` 由 854P/11F → **865P/0F**

## 一、动手前验证

- 命令：`python -m pytest tests/rebuild/test_governance_legacy_i19_preview_api.py tests/rebuild/test_governance_legacy_i20_preview_api.py tests/rebuild/test_governance_legacy_i23_mapping.py tests/rebuild/test_governance_legacy_i23_preview_api.py -q --tb=line -p no:cacheprovider`（cwd=datara-backend）
- 输出定位：`11 failed, 7 passed`（i19×2、i20×4、i23_mapping×4、i23_preview×1，与 S143 上报一致），确认任务未被他人完成。
- `git status`：4 个目标文件均为工作区改动，无他人同单交付痕迹。

## 二、重大事实修正（git 只读取证）

- HEAD（fce3dff 时点）validation token 发行 `role=Role.DEV`，`current_user` 对 capability token 一律 `raise ValueError("scoped capability is not valid for ordinary API routes")` → i19/i20/i23_preview 在 HEAD 上为绿。
- `git log -S 'role=Role.DEV'` 最后变更为 7270296；`validation-runner, role=Role.VIEWER` 无任何提交命中 → **11 个失败全部是 rb 线工作区未提交改动引入的回归，非 HEAD 预存失败**。
- rb 线工作区改动语义（identity_api 新测试锚定，均为绿）：validation:bootstrap capability token 可走普通路由做 bootstrap（建项目 200），但发行角色降为 VIEWER（越权 403 非 401）。

## 三、根因三分类与修复

### A/B 组：i19×2 + i20×4 —— 用例预期过时（非实现缺陷）

- 根因：rb 线将 validation token 从 `role=Role.DEV` 降为 VIEWER+capability="validation:bootstrap"（bootstrap-only 安全收紧）；mapping-preview 端点需 EDIT_DEFINITION 权限，VIEWER 无 → 403。
- 修复（最小改动，测试意图全部保留）：`_client()` 弃用 validation-token 换 token，改用 i21/i22 已有模式——直插 `UserRecord(role=Role.DEVELOPER)` + `TokenService.issue` + `app.state.active_tokens.add` 直发真实 DEVELOPER token。
- 文件：
  - `datara-backend/tests/rebuild/test_governance_legacy_i19_preview_api.py`（`_client()` L46-50 段替换）
  - `datara-backend/tests/rebuild/test_governance_legacy_i20_preview_api.py`（同模式）
- 测试体（project-scoped、read-only、import disabled、源值不泄露、跨项目隔离断言）零改动；i19 401 用例不受影响。

### C 组：i23_mapping×4 —— 用例预期过时（非实现缺陷）

- 根因：rb 线 Role 枚举改名（dev/analyst → developer/operator）后，mapper 源角色与 target 白名单 = 当前枚举 `{role.value for role in Role}`；测试数据 `"analyst"`/`"dev"` 全报 `unsupported_target_role`，且 `legacy_i23_mapping.py` L61-63 `_validate_context` 有 issue 即 `_empty(*issues)` 提前返回，per-row 分支不执行。
- 修复（仅数据迁移，非法值用例保留）：`datara-backend/tests/rebuild/test_governance_legacy_i23_mapping.py` 6 处数据替换——默认 `"user_role": "analyst"→"operator"`、target `role="analyst"→"operator"`、对应断言 source_role/mapped_role、mismatched target `"dev"→"developer"`（仍触发 target_role_mismatch）、target_users 三处 `"analyst"→"operator"`。
- 保留：源 `user_role="root"`（期望 unsupported_legacy_role）、`state="locked"`（期望 unsupported_legacy_state）、target `role="viewer"`、username "analyst-a"（非法分支仍被覆盖）。

### D 组：i23_preview×1 —— 实现缺陷

- 根因：rb 线把 `current_user` 从 HEAD 的「capability 一律拒绝普通路由」改成「一律放行+打标记」（`app.py` L419-423），过宽——`legacy:i23:preview` capability token 也被放行打 GET /projects，破坏 endpoint-only 契约（i23 测试 L89/L109 断言 401 → 实得 200）。
- 修复（恢复 HEAD 安全契约且兼容 rb 线 bootstrap 机制）：`datara-backend/rebuild/api/app.py` `current_user` 白名单收口——
  ```python
  capability = claims.get("capability")
  if capability is not None and capability != "validation:bootstrap":
      raise ValueError("scoped capability is not valid for ordinary API routes")
  if capability is not None:
      claims["capability_restricted"] = True
  ```
- 依据：GET /projects（L513-518）捕获 ValueError → 401 ✓；`validation:bootstrap` 放行保住 dry_run_api/identity_api 的 bootstrap 场景 ✓；`capability_restricted` 全仓仅此一处赋值、无测试消费。

## 四、回归证据

1. 定向回归（修复后）：`python -m pytest tests/rebuild/test_governance_legacy_i19_preview_api.py tests/rebuild/test_governance_legacy_i20_preview_api.py tests/rebuild/test_governance_legacy_i23_mapping.py tests/rebuild/test_governance_legacy_i23_preview_api.py -q -p no:cacheprovider` → **18 passed in 5.28s**
2. 全量回归：`python -m pytest tests/rebuild -q --tb=short -p no:cacheprovider`（cwd=datara-backend）→ **865 passed, 1 skipped in 238.17s（0 failed）**，验收目标 854P/11F→865P/0F 达成（1 skipped 为既有 skip，非失败）。

## 五、边界遵守

- .git 只读：未提交、未 push，工作区改动待监督线代提交。
- 未调用任何 aoci_* 工具（裁定 #85）。
- 文件域：仅动 `datara-backend/tests/rebuild/` 3 个测试文件 + `datara-backend/rebuild/api/app.py` 最小收口，零业务越界。
