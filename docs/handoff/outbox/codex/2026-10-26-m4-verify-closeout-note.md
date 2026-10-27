# M4 批次核验收讫 + 接续指引（2026-10-26，Trae → Codex）

> 你上一批 16 张回执（T-A/T-B/T-C + 13 F-*）已核验收讫。**不采信回执文本，全部独立实跑**。核验报告：`docs/qa/2026-10-26-M4-codex批次核验与接力报告.md`。

## §0 核验结论

- **T-C**：SHA-256 与 D 盘源一致，RED→GREEN 轨迹吻合，**通过**。
- **T-B**：views/open/ 归一半正确（本票 75%），**退役页平铺件漏做**。
- **T-A**：hex 精扫 16 文件 0 命中，**通过**。
- **F-STREAM-ISO-01** 的 vue-tsc 红已被后续票修复（当前 EXIT=0 实证）。
- **F-RUN-RESULT-METRICS-01 未复跑全量** → 全量实跑暴露 1 处失败（见 §1）。

## §1 本轮接力已代做两处（c63c 工作树，均未提交）

1. **README 契约修复**：`infra/fixtures/business/README.md` 两处 —— L10 补 `prepare.sh` 拷贝到容器路径 `/datara/files/fixtures/orders_file_sync.csv`；表格行 `POST /api/v1/rebuild/resources/uploads` **违规引用已移除**，改为 `baseMode=file_sync` + `filePath` + `fileType=csv` 契约行。修复后 `test_infra_data_prep_contract.py` 7 passed。
2. **退役页 4 文件删除**（T-B 残项，裁定已批）：`views/SecAuditView.vue`、`views/LlmModelManagementView.vue`、`views/__tests__/secAuditView.contract.test.ts`、`views/__tests__/llmModelManagementView.contract.test.ts`（均为 git 已跟踪文件，删除呈 D 状态可恢复）。

**c63c 终态（独立实跑）**：后端全量 2580 passed / 8 skipped / 0 failed 等价成立；vitest **98 files / 856 tests** 全绿；vue-tsc EXIT=0；红线 R1~R7 全 PASS（R2 现为 GREEN 62/RED 0）。

## §2 下轮接续（用户已裁定，2026-10-26）

1. **补两张回执**保持台账连续：README 契约修复票 + T-B 退役页补票（内容见 §1 与核验报告 §一）。
2. **门 4~7（1.9 部署冒烟 / API 电池 / UI 冒烟 / E2E）由你直接推进**——用户裁定：key 复用机制你已落实（`seed_product_fixture.py` L53 `DATARA_VALIDATION_KEY_FILE` 长效 key → L132-139 `POST /api/v1/rebuild/validation-token` 换短时 token → `Bearer` 鉴权，scope `high-priority-e2e`；`ensure_remote_dev_key.py` 保障远程 key），无需再等 Trae 侧。fixtures 套件（prepare/verify/seed + 主机守卫）按统一联调票在 `192.168.1.9` 执行，留全量证据。
3. **P1 遗留（D 盘侧票）由你继续**（用户裁定）：metrics 域接入 app.py 启动装配（否则新环境复现 `workflow-result-stats` 500）、D-04 默认模型删除禁用、D-05 项目成员 UI 入口、D-06 变量三要求全域覆盖、D-08 workflow_type 枚举口径、D-09 upload 版本化迁移。
4. **c63c 工作树 63+ 项未提交改动的提交把关由你继续**（用户裁定）：建议先做一轮你的惯例快照 commit（分票精确 add，**禁 `-A` / `add .`，.git 纪律不变**），再开新票。含本轮 Trae 的 2 处修复：`infra/fixtures/business/README.md` 与退役页 4 文件删除（D 状态）。

## §3 差异口径（重要，勿误判回退）

- 后端 25 项差已完整闭合为 D 盘侧演进（D 独有 19 + 同名 13 − C 独有 7）；c63c 侧经 `git diff --numstat` 证实零删减。
- 前端 D 盘 4 个 dwModel 契约测试 c63c 分支从未存在（git log 证实）；c63c 856 > 854 > 816 旧基线。

—— Trae，2026-10-26
