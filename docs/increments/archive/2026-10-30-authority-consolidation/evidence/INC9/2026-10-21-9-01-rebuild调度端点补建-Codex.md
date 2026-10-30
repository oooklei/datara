# 9-01 rebuild 8001 调度端点补建证据（Codex）

- 日期：2026-10-21 Asia/Shanghai
- 单号：STATE S240 / 9-01
- 边界：仅主工作区改动；未改 `.git`，未 commit/push，未调用 AOCI。

## 交付

- 新增 rebuild 调度域七端点，统一前缀 `/api/v1/rebuild`：crontab preview、列表、新建、更新、删除、上线、下线。
- 统一 `{code,msg,data}` 包络；工作流/计划反查项目后复用 TokenService 与项目权限链。
- 权限映射：list=VIEW_ALL；preview/create/update/delete=EDIT_DEFINITION；online/offline=RUN_INSTANCE。
- `workflow_schedule` 扩充 T55 四策略字段及计划配置字段；lifespan 对既有库执行幂等加列。
- 新增 `scheduleCrudApi.ts`，四策略字段与七方法位于新文件；原 `scheduleApi.ts` 及其 listQueue/listRuntimeEvents/listAlerts 未修改。

## 验证

```text
python -m pytest -q datara-backend/tests/rebuild/test_schedule_api.py datara-backend/tests/rebuild/test_workflow_domain.py
12 passed in 32.22s

npm test -- --run src/services/rebuild/__tests__/scheduleCrudApi.contract.test.ts src/services/rebuild/__tests__/scheduleApi.contract.test.ts
Test Files 2 passed (2)
Tests 6 passed (6)

python -m compileall -q datara-backend/rebuild/scheduling datara-backend/rebuild/workflow/models.py datara-backend/rebuild/api/app.py
EXIT 0
```

补充：全量 `npx vue-tsc -b` 被并行在飞文件 `src/services/http.ts` 的既有 TS18049/TS2345 阻断；9-01 定向 Vitest 已完成转译与行为验证。

## 监督回执前联合回归

`	ext
python -m pytest -q tests/test_schedule_policies.py tests/rebuild/test_schedule_api.py tests/rebuild/test_workflow_domain.py
20 passed in 27.60s
`
