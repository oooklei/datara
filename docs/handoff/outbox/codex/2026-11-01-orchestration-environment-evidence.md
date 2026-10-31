# 编排环境组统一链路证据

## 1.9 运行回验

- `GET /api/v1/rebuild/orchestration/environments` 经 Datara 网关返回预置环境组 `default-env`（id `2`、code `188356094854656`）及 `e2e-env-2`（id `3`、code `188356866898880`）。
- admin 与 dev 均从同一编排网关读取环境组；admin `canManage=true`，dev `canManage=false`，资源列表与 owner 语义一致。
- `TaskCenterView.vue` 仅在项目上下文下加载环境组，并将同一选择同时下发为 `environmentGroupId`（Datara 变量/治理上下文）与 `environmentCode`（海豚画布会话），避免 dbx/海豚各自维护选择。
- 编排治理专项回归：`python -m pytest -q tests/rebuild/test_orchestration_governance_api.py tests/rebuild/test_orchestration_alarm_api.py`：`32 passed`。

## 当前判定

环境组贯穿链路已具备：网关统一来源、项目级选择、iframe session 双字段传递。页面仍允许“未选择”作为显式空态；若产品裁定必须强制默认 `default-env`，应在前端环境上下文单域另开票实施，不在本编排网关票内混改。

## 涉及节号

收口计划 §三 B5；权威设计 §六、§10.8、§10.9。
