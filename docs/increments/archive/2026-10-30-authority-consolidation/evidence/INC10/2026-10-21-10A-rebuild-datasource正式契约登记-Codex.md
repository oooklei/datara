# 10A：rebuild datasource 正式契约登记（R-47）

- 执行线：Codex
- 日期：2026-10-21 Asia/Shanghai
- 裁定：R-47（新增正式 rebuild datasource 契约登记，不复用旧非项目 API）
- 交付状态：完成，待监督线验收及代提交

## 实施结果

1. 新增 `datara-newweb/src/services/rebuild/datasourceApi.ts`，逐项覆盖后端现有 11 个 rebuild datasource 端点：草稿校验、profile probe、项目内列表/新建/详情/更新/删除/连接测试、schemas/objects/columns 元数据浏览。
2. `createDatasourceContract(projectId)` 在工厂处绑定项目，所有 CRUD/元数据路径均为 `/api/v1/rebuild/projects/{projectId}/datasources/**`；不存在旧 `/api/v1/datasources/**` 调用。
3. 冻结字段和安全边界：`password` 只存在于写请求 `DatasourceDraft`，响应 `DatasourceRecord` 不含凭据；snake_case 响应统一转 camelCase。
4. 冻结权限矩阵：validate=authenticated、profile probe=admin、读/元数据=VIEW_ALL、写/删除/连接测试=EDIT_DEFINITION。
5. 冻结稳定错误码矩阵并开启 `preserveEnvelopeCode`：1001/1003/4001/4002/4041/4042/4091/5021/5022/5031。
6. 更新 `CONTRACT_REGISTRY.md`：新增第 16 个契约，GREEN 14 / RED 2，方法总数 96。

## 验证证据

```text
rtk npx vitest run src/services/rebuild/__tests__/datasourceApi.contract.test.ts
Test Files  1 passed (1)
Tests       4 passed (4)

rtk npx vue-tsc -b
exit code 0

rtk python -m pytest -q tests/rebuild/test_project_datasource_contract.py tests/rebuild/test_project_datasource_api.py tests/rebuild/test_datasource_metadata.py
24 passed in 23.06s

rtk npm run build
vue-tsc -b && vite build
1650 modules transformed; built in 1.37s

rtk git diff --check -- <本票三业务文件>
exit code 0
```

构建仅报告既有的 bundle 大小提示，不影响退出码与本票验证结论。

## 文件与 SHA256

| 文件 | SHA256 |
|---|---|
| `datara-newweb/src/services/rebuild/datasourceApi.ts` | `7fd5a5c0f2bd0ecef1002cdb4ff1bbbd2f128f12f1d4b89f2ac1388bd754467a` |
| `datara-newweb/src/services/rebuild/__tests__/datasourceApi.contract.test.ts` | `8db3902864324ea2d9908c13f9651bd93786b75ec87349701c74fad4169a0713` |
| `datara-newweb/src/services/rebuild/CONTRACT_REGISTRY.md` | `1fbca0c93a0d831c5cc835fd829861d03ee75a7d40d1774727dce9c73d05018b` |

## 边界声明

- 未写 `.git`，未 commit，未 push；提交号无，待监督线代提交。
- 未调用 `aoci_*`。
- 未修改 `docs/handoff/STATE.md` 或 `docs/handoff/mailbox.jsonl`。
