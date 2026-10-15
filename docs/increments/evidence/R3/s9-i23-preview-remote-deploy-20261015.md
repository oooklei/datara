# R3-S9 I23 身份映射只读预览：远端部署与控件验证

- 时间：2026-10-15（Asia/Shanghai），远端操作窗口约 06:17–06:24。
- 范围：仅隔离 `datara-rebuild-api` 及 `/lei/datara/datara-web/dist/rebuild-validation-r3-s9-i23.html`。正式 `datara-api`、正式 Vue/menu、端口 18090、目标业务数据和源库均未修改。
- 权限：用户批准仅读取 `datara_meta.t_user(id,user_name,user_role,state,create_time,update_time)`，固定六列不包含 `user_pwd`；源 reader 使用 root READ ONLY transaction。target 使用 READ ONLY transaction，仅选择 `rebuild_user(id,username,role,status)` 与 `LegacyIdentityMappingRecord` 的映射元数据。
- 部署前：API healthy，I18 dry-run/I22 preview 路由存在，18091 上 I22 页为 200，远端 I23 reader SHA 与本地一致，验证 key 已配置但没有输出其值。I23 首次容器 import preflight 发现远端 source mount 缺少 `legacy_i23_mapping.py`，因此没有重启服务；补入固定 mapper、哈希核对后 import preflight PASS。
- 回滚：既有 `app.py`、`identity/contracts.py`、治理 `api.py` 备份至 `/lei/datara/rebuild-source/backups/r3-s9-i23-20261014T2217Z/`（共 3 文件）。I23 preview/service mapper 和静态页在变更前不存在，故无旧文件可备份；备份目录明确保留该事实。staging 位置 `/lei/datara/rebuild-source/staging/r3-s9-i23-20261014T2217Z/`。
- 远端最终 SHA-256（与本地一致）：

```text
24956df9c9161b3badde6ba75f40f95f32770515be22064a79fc718a0444fbf0  rebuild/api/app.py
28853b67cd38fc9f70ed3684e28d6ced7caa1cb1c6e670f0a79c8d2bdec11679  rebuild/identity/contracts.py
e63510add1b3530898b35609fce880f9ff8d4976a42783574f599f66df6178dd  rebuild/governance/api.py
f9bfdd4c954a87d6b44c0afa9c43a5d7be48607919e126928c2ef9270599f2bc  rebuild/governance/legacy_i23_preview.py
d9348911277b505f7fbe6d80ddc1bf6daa2b5fdee26d85c608d78a4426bd3388  rebuild/governance/legacy_i23_mapping.py
f7e2a97096013c502291ffa24af7193d0f361e1eb72e65e90b4756ee8deee299  datara-web/dist/rebuild-validation-r3-s9-i23.html
```

- 启动结果：只重启 `datara-rebuild-api`；health `ok/healthy`。OpenAPI 同时有 I23 preview、既有 I22 preview 与 I18 dry-run。I18 importer 配置仍为 `false`；`datara-web` running，`datara-mysql-meta` healthy；页面 `http://192.168.1.9:18091/rebuild-validation-r3-s9-i23.html` 返回 200（10,370 bytes）。最近 10 分钟后端 ERROR/Traceback 标记为 0；access log 可见 I23 preview POST 200。
- 受保护能力：runner 从服务端保护的 `.env` 在内存中读取验证 key，仅请求固定的 `legacy:i23:preview` scope；签发结果 TTL 900 秒。最终 Playwright `R3S9I23-20261014222209-50244b` 12/12 PASS。证据 JSON：`r3s9i23-20261014222209-50244b.json`；截图：`r3s9i23-20261014222209-50244b-summary.png`。key/token 未写入报告；页面不使用 local/session storage。
- 控件结果：读取到 4 条 source identities、1 个同名目标账号候选、0 条既有来源身份映射。首轮无显式选择时 4 条均 `unresolved_target_user`；操作员在页面选择唯一候选后重跑预览，显示 1 个 `identity_candidate`、3 个 unresolved/block。六个批准来源字段可见，无 credential field；响应 `parity_verified=false`、`import_enabled=false`；普通 `/api/v1/rebuild/projects` 使用同一 scoped token 返回 401；无导入/账号修改控件、无浏览器错误。此结果是预览控件通过，不是身份 parity 或导入授权。
- 只读约束：源 SELECT 列由六列 allowlist 固定并通过 READ ONLY transaction；目标 SQL 明确投影不包含 `password_hash`，使用只读事务；本地 SQL listener 测试确认 target user SELECT 且 identity mapping 无 INSERT/UPDATE/DELETE。未创建/修改用户、身份映射、项目成员或密码，未执行任何目标业务写入。
- 本地验证：全 Backend `pytest tests -q` 734 passed；`ruff check rebuild tests/rebuild`、`python -m compileall -q rebuild`、`git diff --check` 通过；I23/I22 页面静态合同 5 passed，runner `node --check` 通过。
- 无关前端门禁：完整 `npm run build` 在未修改的正式 `PageInspector.vue`/其测试处因既有 TypeScript 诊断失败（包含 `never` 参数、未使用符号和模板未解析符号）；本增量没有触碰正式 Vue，隔离 HTML 页面由 `public/` 静态路径单独部署并实际验证。该错误不作为 I23 页面通过证据，也保留为后续前端融合前待修项。
- 执行尝试留痕：前两轮 Playwright 报告分别暴露 runner 错 selector、read-only copy matcher，以及预期普通 API 401 被当成 browser console error；对应报告均保留且标记 FAIL。修正 runner 后最终唯一验收报告为上述 12/12 PASS，不覆盖失败记录。
- 状态：`I23_PREVIEW_CONTROL_PASS / IDENTITY_PARITY_PENDING / IMPORT_NOT_AUTHORIZED`。R3-S9 与 R3 仍 `IN_PROGRESS/PARTIAL`；I18-I23 parity、异常/并发/回滚演练及任何目标业务导入仍未完成/未授权。
